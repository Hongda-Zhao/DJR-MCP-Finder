"""User-facing inference for the frozen DJR-MCP Finder project V0."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("djrmcp-user-inference")
except PackageNotFoundError:  # pragma: no cover - source checkout without installation
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
