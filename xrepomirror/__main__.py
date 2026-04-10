"""Entry point for the xrepomirror CLI tool."""

import argparse
import sys

from . import __version__
from .config import apply_env_vars, load_sources
from .docker_mirror import mirror_images
from .helm_mirror import mirror_charts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xrepomirror",
        description=("Mirror docker images and helm charts from public registries to local/private repositories."),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--sources",
        default="sources.yaml",
        metavar="FILE",
        help="Path to the sources YAML file (default: sources.yaml in the current directory).",
    )
    parser.add_argument(
        "--skip-docker",
        action="store_true",
        help="Skip mirroring docker images.",
    )
    parser.add_argument(
        "--skip-helm",
        action="store_true",
        help="Skip mirroring helm charts.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Load configuration
    try:
        config = load_sources(args.sources)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: failed to parse {args.sources}: {exc}", file=sys.stderr)
        sys.exit(1)

    sources = config.get("sources") or {}
    settings = config.get("settings") or {}

    # Apply env_vars from settings before anything else so proxy settings are
    # available when pulling/pushing images and charts.
    apply_env_vars(settings)

    dest_repos = settings.get("destination_repositories") or {}
    docker_dest = (dest_repos.get("docker") or {}).get("repo", "")
    helm_dest = (dest_repos.get("helm") or {}).get("repo", "")
    helm_type = (dest_repos.get("helm") or {}).get("type", "oci")
    helm_ssl_verify = (dest_repos.get("helm") or {}).get("ssl_verify", True)

    docker_images = sources.get("docker_images") or []
    helm_charts = sources.get("helm_charts") or []

    if not args.skip_docker:
        if docker_images:
            if not docker_dest:
                print(
                    "WARNING: no docker destination repo configured "
                    "(settings.destination_repositories.docker.repo). "
                    "Skipping docker images.",
                    file=sys.stderr,
                )
            else:
                print(f"=== Mirroring {len(docker_images)} docker image(s) to {docker_dest} ===")
                mirror_images(docker_images, docker_dest)
        else:
            print("No docker images defined in sources.yaml.")

    if not args.skip_helm:
        if helm_charts:
            if not helm_dest:
                print(
                    "WARNING: no helm destination repo configured "
                    "(settings.destination_repositories.helm.repo). "
                    "Skipping helm charts.",
                    file=sys.stderr,
                )
            else:
                print(f"\n=== Mirroring {len(helm_charts)} helm chart(s) to {helm_dest} (type: {helm_type}) ===")
                mirror_charts(helm_charts, helm_dest, dest_type=helm_type, ssl_verify=helm_ssl_verify)
        else:
            print("No helm charts defined in sources.yaml.")

    print("\nAll done.")


if __name__ == "__main__":
    main()
