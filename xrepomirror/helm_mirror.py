"""Helm chart mirroring logic for xrepomirror."""

import getpass
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from .config import get_proxy_env


def _run(cmd: List[str], extra_env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None) -> None:
    """Run a subprocess command, streaming output to stdout/stderr."""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(cmd, env=env, cwd=cwd)
    if result.returncode != 0:
        print(f"ERROR: command failed (exit {result.returncode}): {' '.join(cmd)}", file=sys.stderr)
        raise SystemExit(result.returncode)


_AUTH_HINTS = ("401", "403", "unauthorized", "authentication required", "credentials required")


def _run_capturing(
    cmd: List[str], extra_env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None
) -> Tuple[int, str]:
    """Run a command and capture stderr; return (returncode, stderr_text). Does not raise."""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(cmd, env=env, cwd=cwd, stderr=subprocess.PIPE, universal_newlines=True)
    return result.returncode, result.stderr or ""


def _is_auth_error(text: str) -> bool:
    """Return True if *text* looks like an authentication / authorisation failure."""
    lower = text.lower()
    return any(hint in lower for hint in _AUTH_HINTS)


def _prompt_credentials(host: str) -> Tuple[str, str]:
    """Interactively prompt for a username and password for *host*."""
    print(f"\n  Authentication required for {host}")
    username = input("  Username: ")
    password = getpass.getpass("  Password: ")
    return username, password


def _helm_registry_login(host: str, username: str, password: str, proxy_env: Dict[str, str]) -> bool:
    """Run ``helm registry login`` for *host*, passing the password via stdin."""
    env = os.environ.copy()
    env.update(proxy_env)
    result = subprocess.run(
        ["helm", "registry", "login", host, "--username", username, "--password-stdin"],
        input=password,
        env=env,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    if result.returncode != 0:
        print(f"ERROR: helm registry login failed: {result.stderr}", file=sys.stderr)
        return False
    return True


def _push_nexus3(chart_path: Path, dest_repo: str, proxy_env: Dict[str, str]) -> None:
    """Upload a chart archive to a Nexus 3 helm hosted repository via REST API."""
    # dest_repo expected format: <host>/<repository-name>  e.g. repo.bcr.io/helm
    parts = dest_repo.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"nexus3 dest repo must be '<host>/<repo-name>', got: '{dest_repo}'")
    host, repo_name = parts
    url = f"https://{host}/service/rest/v1/components?repository={repo_name}"

    proxies: Dict[str, str] = {}
    if "https_proxy" in proxy_env:
        proxies["https"] = proxy_env["https_proxy"]
    elif "HTTPS_PROXY" in proxy_env:
        proxies["https"] = proxy_env["HTTPS_PROXY"]
    if "http_proxy" in proxy_env:
        proxies["http"] = proxy_env["http_proxy"]
    elif "HTTP_PROXY" in proxy_env:
        proxies["http"] = proxy_env["HTTP_PROXY"]

    print(f"  uploading to Nexus3 at {url}")
    with chart_path.open("rb") as fh:
        response = requests.post(
            url,
            files={"helm.asset": (chart_path.name, fh, "application/gzip")},
            proxies=proxies or None,
            timeout=120,
        )

    if response.status_code in (401, 403):
        host = dest_repo.split("/")[0]
        username, password = _prompt_credentials(host)
        with chart_path.open("rb") as fh:
            response = requests.post(
                url,
                files={"helm.asset": (chart_path.name, fh, "application/gzip")},
                proxies=proxies or None,
                timeout=120,
                auth=(username, password),
            )

    if response.status_code not in (200, 201, 204):
        print(
            f"ERROR: Nexus3 upload failed ({response.status_code}): {response.text}",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _push_oci(chart_path: Path, dest_repo: str, proxy_env: Dict[str, str]) -> None:
    """Push a chart archive to an OCI-compatible registry using helm push."""
    oci_ref = f"oci://{dest_repo}"
    cmd = ["helm", "push", str(chart_path), oci_ref]

    # First attempt – capture stderr so we can inspect it for auth errors.
    returncode, stderr = _run_capturing(cmd, extra_env=proxy_env)
    if returncode == 0:
        return

    if _is_auth_error(stderr):
        # Extract the registry host (everything before the first '/') and log in.
        host = dest_repo.split("/")[0]
        username, password = _prompt_credentials(host)
        if not _helm_registry_login(host, username, password, proxy_env):
            raise SystemExit(1)
        # Retry – let output stream normally so the user sees the result.
        _run(cmd, extra_env=proxy_env)
    else:
        # Non-auth failure: surface the captured stderr and exit.
        if stderr:
            print(stderr, file=sys.stderr)
        print(f"ERROR: command failed (exit {returncode}): {' '.join(cmd)}", file=sys.stderr)
        raise SystemExit(returncode)


def mirror_charts(helm_charts: List[Dict[str, Any]], dest_repo: str, dest_type: str = "oci") -> None:
    """Pull each helm chart and push it to *dest_repo*.

    *dest_type* controls how charts are uploaded:
    - ``"nexus3"`` – uploads via the Nexus 3 REST API.
    - anything else (including ``"oci"``) – uses ``helm push`` with an OCI ref.
    """
    proxy_env = get_proxy_env()

    with tempfile.TemporaryDirectory(prefix="xrepomirror_helm_") as tmpdir:
        for entry in helm_charts:
            chart = entry.get("chart")
            repo = entry.get("repo")
            version = entry.get("version")

            if not (chart and repo and version):
                print(
                    f"WARNING: skipping incomplete helm entry: {entry}",
                    file=sys.stderr,
                )
                continue

            print(f"\n[helm] {chart} {version} from {repo}  →  {dest_repo}")

            # Add the upstream repository using a stable alias
            repo_alias = f"xrepomirror_{chart}"
            print(f"  adding repo {repo_alias} → {repo}")
            _run(["helm", "repo", "add", "--force-update", repo_alias, repo], extra_env=proxy_env)

            print("  updating repo cache")
            _run(["helm", "repo", "update", repo_alias], extra_env=proxy_env)

            print(f"  pulling {chart} v{version}")
            _run(
                ["helm", "pull", f"{repo_alias}/{chart}", "--version", str(version), "--destination", tmpdir],
                extra_env=proxy_env,
            )

            # Locate the downloaded archive
            archives = list(Path(tmpdir).glob(f"{chart}-{version}.tgz"))
            if not archives:
                # helm may append extra characters; fall back to any matching name
                archives = list(Path(tmpdir).glob(f"{chart}-*.tgz"))
            if not archives:
                print(
                    f"ERROR: could not find downloaded chart archive for {chart}",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            chart_path = archives[0]

            print(f"  pushing {chart_path.name}")
            if dest_type == "nexus3":
                _push_nexus3(chart_path, dest_repo, proxy_env)
            else:
                _push_oci(chart_path, dest_repo, proxy_env)

            # Remove the archive so the tmpdir stays clean between iterations
            chart_path.unlink()

            print("  done \u2713")
