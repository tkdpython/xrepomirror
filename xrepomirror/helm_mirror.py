"""Helm chart mirroring logic for xrepomirror."""

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import requests

from .config import get_proxy_env


def _run(cmd: list[str], extra_env: dict[str, str] | None = None,
         cwd: str | None = None) -> None:
    """Run a subprocess command, streaming output to stdout/stderr."""
    import os
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(cmd, env=env, cwd=cwd)
    if result.returncode != 0:
        print(f"ERROR: command failed (exit {result.returncode}): {' '.join(cmd)}",
              file=sys.stderr)
        raise SystemExit(result.returncode)


def _push_nexus3(chart_path: Path, dest_repo: str,
                 proxy_env: dict[str, str]) -> None:
    """Upload a chart archive to a Nexus 3 helm hosted repository via REST API."""
    # dest_repo expected format: <host>/<repository-name>  e.g. repo.bcr.io/helm
    parts = dest_repo.split("/", 1)
    if len(parts) != 2:
        raise ValueError(
            f"nexus3 dest repo must be '<host>/<repo-name>', got: '{dest_repo}'"
        )
    host, repo_name = parts
    url = f"https://{host}/service/rest/v1/components?repository={repo_name}"

    proxies: dict[str, str] = {}
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
        )
    if response.status_code not in (200, 201, 204):
        print(
            f"ERROR: Nexus3 upload failed ({response.status_code}): {response.text}",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _push_oci(chart_path: Path, dest_repo: str,
              proxy_env: dict[str, str]) -> None:
    """Push a chart archive to an OCI-compatible registry using helm push."""
    oci_ref = f"oci://{dest_repo}"
    _run(["helm", "push", str(chart_path), oci_ref], extra_env=proxy_env)


def mirror_charts(helm_charts: list[dict[str, Any]], dest_repo: str,
                  dest_type: str = "oci") -> None:
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
            _run(["helm", "repo", "add", "--force-update", repo_alias, repo],
                 extra_env=proxy_env)

            print(f"  updating repo cache")
            _run(["helm", "repo", "update", repo_alias], extra_env=proxy_env)

            print(f"  pulling {chart} v{version}")
            _run(
                ["helm", "pull", f"{repo_alias}/{chart}",
                 "--version", str(version),
                 "--destination", tmpdir],
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

            print(f"  done ✓")
