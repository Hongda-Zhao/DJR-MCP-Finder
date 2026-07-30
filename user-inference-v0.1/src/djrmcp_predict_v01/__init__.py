"""User-facing inference for the DJR-MCP Finder V0.1 mixed-encoder candidate."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("djrmcp-user-inference-v01")
except PackageNotFoundError:  # pragma: no cover - source checkout without installation
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
