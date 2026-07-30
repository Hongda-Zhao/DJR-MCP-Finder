#!/usr/bin/env python3
"""Inspect built wheels and sdists for required metadata and files."""

from __future__ import annotations

import argparse
import json
import re
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release-manifest.json"


def _normalise_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name).lower()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"artifact check failed: {message}")


def _wheel_metadata(archive: zipfile.ZipFile) -> dict[str, str]:
    metadata_names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
    _require(len(metadata_names) == 1, "wheel must contain exactly one METADATA file")
    message = Parser().parsestr(archive.read(metadata_names[0]).decode("utf-8"))
    return {key: str(message[key]) for key in ("Name", "Version", "Requires-Python", "License-Expression")}


def validate(artifact_root: Path) -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    checked: dict[str, list[str]] = {}
    for package in manifest["packages"]:
        distribution = str(package["distribution"])
        version = str(package["version"])
        directory = artifact_root / str(package["artifact_directory"])
        normalised = _normalise_distribution(distribution)
        wheels = sorted(directory.glob(f"{normalised}-{version}-*.whl"))
        sdists = sorted(directory.glob(f"{normalised}-{version}.tar.gz"))
        _require(len(wheels) == 1, f"expected one wheel for {distribution}, found {len(wheels)}")
        _require(len(sdists) == 1, f"expected one sdist for {distribution}, found {len(sdists)}")

        with zipfile.ZipFile(wheels[0]) as archive:
            names = archive.namelist()
            metadata = _wheel_metadata(archive)
            _require(metadata["Name"] == distribution, f"wheel name metadata mismatch for {distribution}")
            _require(metadata["Version"] == version, f"wheel version mismatch for {distribution}")
            _require(metadata["License-Expression"] == "MIT", f"wheel SPDX license mismatch for {distribution}")
            _require(any(name.endswith(".dist-info/licenses/LICENSE") for name in names), f"wheel license missing for {distribution}")
            module_name = Path(str(package["module"])).name
            _require(f"{module_name}/py.typed" in names, f"wheel py.typed missing for {distribution}")
            if package["model_id"] is not None:
                _require(any(name.endswith("/THIRD_PARTY_NOTICES.md") for name in names), f"wheel third-party notice missing for {distribution}")

        with tarfile.open(sdists[0], "r:gz") as archive:
            names = archive.getnames()
            _require(any(name.endswith("/LICENSE") for name in names), f"sdist license missing for {distribution}")
            _require(any(name.endswith("/pyproject.toml") for name in names), f"sdist pyproject missing for {distribution}")

        checked[distribution] = [wheels[0].name, sdists[0].name]

    return {"artifacts": checked, "status": "valid"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=ROOT / "build" / "release")
    args = parser.parse_args()
    print(json.dumps(validate(args.artifact_root.resolve()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
