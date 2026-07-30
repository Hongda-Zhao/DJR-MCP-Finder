"""DJR-MCP Finder research pipeline."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("djrmcp-finder")
except PackageNotFoundError:  # pragma: no cover - source checkout without installation
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
