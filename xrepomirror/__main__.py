"""Entry point for the xrepomirror CLI tool."""

import argparse
import sys

from . import __version__
from .config import apply_env_vars, find_sources_files, load_sources
from .docker_mirror import mirror_images
from .helm_mirror import mirror_charts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xrepomirror",
        description=("Mirror docker images and helm charts from public registries to local/private repositories."),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sources_group = parser.add_mutually_exclusive_group()
    sources_group.add_argument(
        "--sources",
        default="sources.yaml",
        metavar="FILE",
        help="Path to a single sources YAML file (default: sources.yaml in the current directory).",
    )
    sources_group.add_argument(
        "--sources-tree",
        metavar="DIR",
        help=(
            "Recursively search DIR for sources.yaml / sources.yml files and process each one. "
            "Each file must contain at least 'sources.docker_images' or 'sources.helm_charts'. "
            "Mutually exclusive with --sources."
        ),
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


def _process_sources_file(config, sources_file_label, args):
    """Process a single loaded sources config dict."""
    sources = config.get("sources") or {}
    settings = config.get("settings") or {}

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
            print(f"No docker images defined in {sources_file_label}.")

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
            print(f"No helm charts defined in {sources_file_label}.")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.sources_tree:
        try:
            sources_files = list(find_sources_files(args.sources_tree))
        except NotADirectoryError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)

        if not sources_files:
            print(f"No valid sources files found under '{args.sources_tree}'.")
            sys.exit(0)

        print(f"Found {len(sources_files)} sources file(s) under '{args.sources_tree}'.")
        for sources_path in sources_files:
            print(f"\n{'=' * 60}")
            print(f"Processing: {sources_path}")
            print(f"{'=' * 60}")
            try:
                config = load_sources(str(sources_path))
            except Exception as exc:
                print(f"ERROR: failed to load '{sources_path}': {exc} — skipping.", file=sys.stderr)
                continue
            _process_sources_file(config, str(sources_path), args)

    else:
        try:
            config = load_sources(args.sources)
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            print(f"ERROR: failed to parse {args.sources}: {exc}", file=sys.stderr)
            sys.exit(1)
        _process_sources_file(config, args.sources, args)

    print("\nAll done.")


if __name__ == "__main__":
    main()
