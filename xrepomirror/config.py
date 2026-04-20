"""Configuration loader for xrepomirror."""

import os
from pathlib import Path
from typing import Any, Dict, Generator, List

import yaml


def load_sources(path: str = "sources.yaml") -> Dict[str, Any]:
    """Load and return the sources configuration from a YAML file."""
    sources_path = Path(path)
    if not sources_path.exists():
        raise FileNotFoundError(
            f"sources.yaml not found at '{sources_path.resolve()}'. "
            "Please create a sources.yaml file in the current directory."
        )
    with sources_path.open() as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError("sources.yaml must contain a YAML mapping at the top level.")
    return data


def validate_sources_data(data: Any, path: str) -> List[str]:
    """Validate a loaded sources config dict and return a list of error strings.

    A valid file must:
    - Be a dict with a top-level 'sources' key.
    - Contain at least one of 'sources.docker_images' or 'sources.helm_charts',
      and each must be a list if present.
    """
    errors: List[str] = []
    if not isinstance(data, dict):
        errors.append(f"{path}: top-level value must be a YAML mapping")
        return errors
    sources = data.get("sources")
    if not isinstance(sources, dict):
        errors.append(f"{path}: missing or invalid 'sources' key")
        return errors
    has_docker = "docker_images" in sources
    has_helm = "helm_charts" in sources
    if not has_docker and not has_helm:
        errors.append(f"{path}: 'sources' must contain at least one of 'docker_images' or 'helm_charts'")
    if has_docker and not isinstance(sources["docker_images"], list):
        errors.append(f"{path}: 'sources.docker_images' must be a list")
    if has_helm and not isinstance(sources["helm_charts"], list):
        errors.append(f"{path}: 'sources.helm_charts' must be a list")
    return errors


def find_sources_files(tree_path: str) -> Generator[Path, None, None]:
    """Recursively walk tree_path, yielding valid sources.yaml / sources.yml files.

    Each file is loaded and validated via validate_sources_data().  Files that
    fail validation are reported to stderr and skipped.
    """
    import sys

    root = Path(tree_path)
    if not root.is_dir():
        raise NotADirectoryError(f"--sources-tree path is not a directory: '{root.resolve()}'")

    for dirpath, _dirnames, filenames in os.walk(str(root)):
        for candidate in ("sources.yaml", "sources.yml"):
            if candidate in filenames:
                full_path = Path(dirpath) / candidate
                try:
                    with full_path.open() as fh:
                        data = yaml.safe_load(fh)
                except Exception as exc:
                    print(f"WARNING: skipping '{full_path}': failed to parse YAML: {exc}", file=sys.stderr)
                    break  # don't also try sources.yml in the same dir
                errors = validate_sources_data(data, str(full_path))
                if errors:
                    for err in errors:
                        print(f"WARNING: skipping '{full_path}': {err}", file=sys.stderr)
                    break
                yield full_path
                break  # only process one sources file per directory


def apply_env_vars(settings: Dict[str, Any]) -> None:
    """Apply env_vars from the settings block to the process environment.

    Values already set in the environment take precedence so that the operator
    can override anything at runtime without editing sources.yaml.
    """
    env_vars: Dict[str, str] = settings.get("env_vars") or {}
    for key, value in env_vars.items():
        if key not in os.environ:
            os.environ[key] = str(value)


def get_proxy_env() -> Dict[str, str]:
    """Return a dict of current proxy-related environment variables, if set."""
    proxy_keys = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy")
    return {k: os.environ[k] for k in proxy_keys if k in os.environ}
