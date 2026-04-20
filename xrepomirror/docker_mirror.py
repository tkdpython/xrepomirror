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


def _source_tag(source: str) -> str:
    """Extract the tag from a source image reference, or 'latest' if absent."""
    # Tag follows the last ':' that is not part of a port number (i.e. after a '/')
    name_part = source.split("/")[-1]
    if ":" in name_part:
        return name_part.split(":", 1)[1]
    return "latest"


def _destination_ref(source: str, dest_repo: str, destination: str = "") -> str:
    """Compute the destination image reference.

    Three modes depending on *destination*:

    1. ``destination`` includes a tag (e.g. ``grafana:superversion``):
       ``<dest_repo>/grafana:superversion``

    2. ``destination`` has no tag (e.g. ``grafana``):
       ``<dest_repo>/grafana:<source_tag>``

    3. No ``destination`` provided:
       ``<dest_repo>/<full_source_ref>`` — the complete source reference
       (including the original registry) is appended to the destination repo,
       e.g. ``docker.io/grafana/grafana:12.3.0`` →
       ``<dest_repo>/docker.io/grafana/grafana:12.3.0``.
    """
    base = dest_repo.rstrip("/")
    if destination:
        # Check whether a tag was supplied in the destination
        dest_name_part = destination.split("/")[-1]
        if ":" in dest_name_part:
            return f"{base}/{destination}"
        else:
            tag = _source_tag(source)
            return f"{base}/{destination}:{tag}"
    # No destination override — append the full source reference
    return f"{base}/{source}"


def mirror_images(docker_images: List[Dict[str, Any]], dest_repo: str) -> None:
    """Pull each image from its source and push it to *dest_repo*."""
    proxy_env = get_proxy_env()

    for entry in docker_images:
        source = entry.get("source")
        if not source:
            print("WARNING: skipping entry with no 'source' key.", file=sys.stderr)
            continue

        destination = _destination_ref(source, dest_repo, destination=entry.get("destination", ""))
        print(f"\n[docker] {source}  →  {destination}")

        print(f"  pulling  {source}")
        _run(["docker", "pull", source], extra_env=proxy_env)

        print(f"  tagging  {source}  as  {destination}")
        _run(["docker", "tag", source, destination])

        print(f"  pushing  {destination}")
        _run(["docker", "push", destination], extra_env=proxy_env)

        print("  done \u2713")
