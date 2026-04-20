"""xrepomirror - Mirror helm charts and docker images to local repositories."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("xrepomirror")
except PackageNotFoundError:
    __version__ = "unknown"
