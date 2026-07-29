"""Configuration loading and stage path resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge a small versioned config overlay into its frozen base."""

    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | Path) -> dict[str, Any]:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise RuntimeError("PyYAML is required to read configs") from exc
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"Configuration must contain a YAML mapping: {config_path}")
    extends = config.pop("extends", None)
    expected_base_sha256 = config.pop("extends_sha256", None)
    if extends is not None:
        import hashlib

        base_path = (config_path.parent / str(extends)).resolve()
        if base_path == config_path.resolve():
            raise ValueError(f"Configuration cannot extend itself: {config_path}")
        if not base_path.is_file():
            raise FileNotFoundError(f"Extended configuration is missing: {base_path}")
        if expected_base_sha256 is None:
            raise ValueError("Versioned configuration overlays must pin extends_sha256")
        observed_base_sha256 = hashlib.sha256(base_path.read_bytes()).hexdigest()
        if observed_base_sha256 != str(expected_base_sha256):
            raise RuntimeError(
                "Extended configuration SHA-256 mismatch: "
                f"expected={expected_base_sha256}, observed={observed_base_sha256}"
            )
        config = _deep_merge(load_config(base_path), config)
        config["config_lineage"] = {
            "overlay_path": str(config_path),
            "base_path": str(base_path),
            "base_sha256": observed_base_sha256,
        }
    for section in ("project", "paths", "known_mcps", "dataset", "embedding", "classifier"):
        if section not in config:
            raise ValueError(f"Missing required configuration section: {section}")
    return config
