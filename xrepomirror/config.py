"""Configuration loader for xrepomirror."""

import os
from pathlib import Path
from typing import Any, Dict

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
