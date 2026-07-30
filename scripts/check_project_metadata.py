#!/usr/bin/env python3
"""Validate repository, package, model, and bundle version metadata."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release-manifest.json"
PEP440_RELEASE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:a[0-9]+|b[0-9]+|rc[0-9]+|\.post[0-9]+)?$")
REQUIRED_URLS = {"Homepage", "Documentation", "Repository", "Bug Tracker", "Changelog"}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"metadata check failed: {message}")


def _resolve(relative: str) -> Path:
    candidate = (ROOT / relative).resolve()
    _require(candidate == ROOT or ROOT in candidate.parents, f"path escapes repository: {relative}")
    return candidate


def _read_cff_scalar(key: str) -> str:
    text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    match = re.search(rf"(?m)^{re.escape(key)}:\s*['\"]?([^'\"\n]+)", text)
    _require(match is not None, f"CITATION.cff is missing {key}")
    return match.group(1).strip()


def validate(tag: str | None = None) -> dict[str, Any]:
    manifest = _read_json(MANIFEST)
    _require(manifest.get("schema_version") == 1, "unsupported release-manifest schema")

    repository_release = manifest["repository_release"]
    repository_version = str(repository_release["version"])
    repository_tag = str(repository_release["tag"])
    _require(PEP440_RELEASE.fullmatch(repository_version) is not None, "invalid repository version")
    _require(repository_tag == f"v{repository_version}", "repository tag/version mismatch")
    _require(_read_cff_scalar("version") == repository_version, "CITATION.cff version mismatch")
    _require(_read_cff_scalar("license") == "MIT", "CITATION.cff license mismatch")
    if tag is not None:
        _require(tag == repository_tag, f"tag {tag!r} does not match {repository_tag!r}")

    package_versions: dict[str, str] = {}
    package_models: set[str] = set()
    for package in manifest["packages"]:
        distribution = str(package["distribution"])
        expected_version = str(package["version"])
        package_root = _resolve(str(package["path"]))
        pyproject = _read_toml(package_root / "pyproject.toml")["project"]
        _require(pyproject["name"] == distribution, f"distribution mismatch for {distribution}")
        _require(pyproject["version"] == expected_version, f"version mismatch for {distribution}")
        _require(PEP440_RELEASE.fullmatch(expected_version) is not None, f"invalid version for {distribution}")
        _require(pyproject.get("license") == "MIT", f"{distribution} must use SPDX MIT metadata")
        _require(pyproject.get("license-files") == ["LICENSE"], f"{distribution} license-files mismatch")
        _require(REQUIRED_URLS <= set(pyproject.get("urls", {})), f"{distribution} project URLs incomplete")
        _require("Typing :: Typed" in pyproject.get("classifiers", []), f"{distribution} typed classifier missing")
        module_root = _resolve(str(package["module"]))
        _require((module_root / "py.typed").is_file(), f"{distribution} py.typed missing")
        init_text = (module_root / "__init__.py").read_text(encoding="utf-8")
        _require("importlib.metadata" in init_text, f"{distribution} runtime version is not metadata-backed")
        _require(f'__version__ = "{expected_version}"' not in init_text, f"{distribution} hardcodes __version__")
        package_versions[distribution] = expected_version
        if package["model_id"] is not None:
            package_models.add(str(package["model_id"]))

    model_ids: set[str] = set()
    model_statuses: dict[str, str] = {}
    for model in manifest["models"]:
        model_id = str(model["model_id"])
        _require(model_id not in model_ids, f"duplicate model ID: {model_id}")
        model_ids.add(model_id)
        bundle = _read_json(_resolve(str(model["bundle_metadata"])))
        expected_release_id = str(model["bundle_release_id"])
        _require(bundle.get("release_id") == expected_release_id, f"bundle release ID mismatch for {model_id}")
        if model_id == "model-v0":
            _require(model["status"] == "released", "formal model-v0 status changed")
        if model_id == "model-v0.1-candidate":
            _require(bundle.get("released_v0_unchanged") is True, "candidate must preserve formal V0")
            _require(bundle.get("release_status") == model["status"], "candidate status mismatch")
        model_statuses[model_id] = str(model["status"])

    _require(package_models == model_ids, "package/model mapping is incomplete")
    return {
        "repository_release": repository_tag,
        "packages": package_versions,
        "models": model_statuses,
        "status": "valid",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Require this Git tag to match the repository release")
    args = parser.parse_args()
    print(json.dumps(validate(args.tag), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
