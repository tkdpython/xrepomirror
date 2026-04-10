"""Docker image mirroring logic for xrepomirror."""

import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

from .config import get_proxy_env


def _run(cmd: List[str], extra_env: Optional[Dict[str, str]] = None) -> None:
    """Run a subprocess command, streaming output to stdout/stderr."""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        print(f"ERROR: command failed (exit {result.returncode}): {' '.join(cmd)}", file=sys.stderr)
        raise SystemExit(result.returncode)


def _destination_ref(source: str, dest_repo: str) -> str:
    """Compute the destination image reference.

    The last path component and tag of the source image are preserved so that
    ``docker.io/grafana/grafana:12.3.0`` becomes
    ``<dest_repo>/grafana:12.3.0``.
    """
    # Strip the registry prefix (everything up to the first '/')
    parts = source.split("/")
    # Determine if the first segment is a registry host
    # (contains a dot or a colon, or is "localhost")
    if len(parts) > 1 and ("." in parts[0] or ":" in parts[0] or parts[0] == "localhost"):
        remainder = "/".join(parts[1:])
    else:
        remainder = source

    # Use only the last path segment (image name + tag)
    image_with_tag = remainder.split("/")[-1]
    return f"{dest_repo.rstrip('/')}/{image_with_tag}"


def mirror_images(docker_images: List[Dict[str, Any]], dest_repo: str) -> None:
    """Pull each image from its source and push it to *dest_repo*."""
    proxy_env = get_proxy_env()

    for entry in docker_images:
        source = entry.get("source")
        if not source:
            print("WARNING: skipping entry with no 'source' key.", file=sys.stderr)
            continue

        destination = _destination_ref(source, dest_repo)
        print(f"\n[docker] {source}  →  {destination}")

        print(f"  pulling  {source}")
        _run(["docker", "pull", source], extra_env=proxy_env)

        print(f"  tagging  {source}  as  {destination}")
        _run(["docker", "tag", source, destination])

        print(f"  pushing  {destination}")
        _run(["docker", "push", destination], extra_env=proxy_env)

        print("  done \u2713")
