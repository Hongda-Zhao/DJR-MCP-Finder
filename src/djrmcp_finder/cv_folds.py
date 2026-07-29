"""Freeze and verify the shared project-V0 development CV fold map.

The biological resampling unit is ``global_component_id``.  A single map is
created from Train rows only and is then consumed unchanged by every classifier
head and every embedding candidate.  This makes fold-level composite scores
meaningfully paired across heads and models.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from sklearn.model_selection import StratifiedGroupKFold


FOLD_MAP_FIELDS = ("global_component_id", "fold")
KNOWN_H3_CLASSES = ("Nucleocytoviricota", "Preplasmiviricota")
UNKNOWN_H3_LABEL = "unknown/other"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise RuntimeError(f"TSV has no header: {path}")
        return list(reader)


def _atomic_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def _hierarchy_stratum(row: dict[str, str]) -> str:
    """Return the Train-only hierarchy stratum used to balance shared folds."""

    head1 = row.get("head1_label")
    if head1 == "non_djr":
        return "head1::non_djr"
    if head1 != "djr":
        raise RuntimeError(f"Unexpected Train Head-1 label: {head1!r}")
    head2 = row.get("head2_label")
    if head2 == "none":
        return "head2::none"
    if head2 != "viral_morphogenesis_associated":
        raise RuntimeError(f"Unexpected Train Head-2 label: {head2!r}")
    head3 = row.get("head3_operational_label")
    if head3 not in {*KNOWN_H3_CLASSES, UNKNOWN_H3_LABEL}:
        raise RuntimeError(f"Unexpected Train Head-3 operational label: {head3!r}")
    return f"head3::{head3}"


def _train_rows(manifest: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    component_splits: dict[str, set[str]] = defaultdict(set)
    for row in manifest:
        component = row.get("global_component_id", "")
        split = row.get("split", "")
        if not component or not split:
            raise RuntimeError("Manifest row lacks global_component_id or split")
        component_splits[component].add(split)
    crossed = sorted(
        component for component, splits in component_splits.items() if len(splits) != 1
    )
    if crossed:
        raise RuntimeError(
            "Cannot freeze CV folds because global components cross dataset splits: "
            f"{crossed[:5]}"
        )
    rows = [dict(row) for row in manifest if row["split"] == "train"]
    if not rows:
        raise RuntimeError("Manifest has no Train rows")
    return sorted(rows, key=lambda row: (row["global_component_id"], row["protein_id"]))


def build_fold_assignment(
    manifest: Sequence[dict[str, str]], *, folds: int, seed: int
) -> tuple[dict[str, int], dict[str, Any]]:
    """Build one deterministic hierarchy-stratified component assignment."""

    if folds < 2:
        raise ValueError("At least two CV folds are required")
    rows = _train_rows(manifest)
    groups = np.asarray([row["global_component_id"] for row in rows], dtype=str)
    strata = np.asarray([_hierarchy_stratum(row) for row in rows], dtype=str)
    unique_components = sorted(set(groups.tolist()))
    if len(unique_components) < folds:
        raise RuntimeError("Fewer Train global components than requested CV folds")
    splitter = StratifiedGroupKFold(
        n_splits=folds,
        shuffle=True,
        random_state=seed,
    )
    assignment: dict[str, int] = {}
    for fold, (_, heldout_indices) in enumerate(
        splitter.split(np.zeros((len(rows), 1), dtype=np.uint8), strata, groups),
        start=1,
    ):
        for component in sorted(set(groups[heldout_indices].tolist())):
            if component in assignment:
                raise RuntimeError(f"Global component assigned twice: {component}")
            assignment[component] = fold
    validate_fold_assignment(manifest, assignment, folds=folds)

    stratum_by_fold: dict[str, dict[str, int]] = {}
    component_count_by_fold: dict[str, int] = {}
    row_count_by_fold: dict[str, int] = {}
    for fold in range(1, folds + 1):
        selected = [
            row for row in rows if assignment[row["global_component_id"]] == fold
        ]
        stratum_by_fold[str(fold)] = dict(
            sorted(Counter(_hierarchy_stratum(row) for row in selected).items())
        )
        component_count_by_fold[str(fold)] = len(
            {row["global_component_id"] for row in selected}
        )
        row_count_by_fold[str(fold)] = len(selected)
    diagnostics = {
        "train_record_count": len(rows),
        "train_global_component_count": len(unique_components),
        "component_count_by_fold": component_count_by_fold,
        "record_count_by_fold": row_count_by_fold,
        "hierarchy_stratum_count": dict(sorted(Counter(strata.tolist()).items())),
        "hierarchy_stratum_count_by_fold": stratum_by_fold,
    }
    return assignment, diagnostics


def validate_fold_assignment(
    manifest: Sequence[dict[str, str]], assignment: dict[str, int], *, folds: int
) -> None:
    rows = _train_rows(manifest)
    expected_components = {row["global_component_id"] for row in rows}
    if set(assignment) != expected_components:
        missing = sorted(expected_components - set(assignment))
        extra = sorted(set(assignment) - expected_components)
        raise RuntimeError(
            "Frozen CV map does not exactly cover Train global components: "
            f"missing={missing[:5]}, extra={extra[:5]}"
        )
    expected_folds = set(range(1, folds + 1))
    observed_folds = set(assignment.values())
    if observed_folds != expected_folds:
        raise RuntimeError(
            f"Frozen CV fold IDs differ: observed={sorted(observed_folds)}, "
            f"expected={sorted(expected_folds)}"
        )


def _fold_paths(config: dict[str, Any]) -> tuple[Path, Path]:
    paths = config.get("paths", {})
    map_value = paths.get("benchmark_cv_fold_map")
    metadata_value = paths.get("benchmark_cv_fold_metadata")
    if not isinstance(map_value, str) or not map_value:
        raise RuntimeError("Config must define paths.benchmark_cv_fold_map")
    if not isinstance(metadata_value, str) or not metadata_value:
        raise RuntimeError("Config must define paths.benchmark_cv_fold_metadata")
    return Path(map_value), Path(metadata_value)


def _fold_map_payload(assignment: dict[str, int]) -> str:
    lines = ["\t".join(FOLD_MAP_FIELDS)]
    lines.extend(f"{component}\t{assignment[component]}" for component in sorted(assignment))
    return "\n".join(lines) + "\n"


def load_frozen_cv_fold_map(
    config: dict[str, Any], manifest_path: Path | None = None
) -> tuple[dict[str, Any], dict[str, int]]:
    """Load and fully attest the shared map against the current config/manifest."""

    map_path, metadata_path = _fold_paths(config)
    if manifest_path is None:
        manifest_path = Path(config["paths"]["v0_manifest"])
    if not map_path.is_file() or not metadata_path.is_file():
        raise RuntimeError(
            "Frozen benchmark CV fold map is missing; run "
            "scripts/freeze_benchmark_cv_folds.py before calibration"
        )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise RuntimeError("Frozen CV metadata must be a JSON object")
    folds = int(config["classifier"]["cross_validation_folds"])
    seed = int(config["project"]["seed"])
    expected = {
        "schema_version": 1,
        "split": "train",
        "group_field": "global_component_id",
        "folds": folds,
        "seed": seed,
        "manifest_sha256": sha256_file(manifest_path),
        "fold_map_sha256": sha256_file(map_path),
    }
    for field, value in expected.items():
        if metadata.get(field) != value:
            raise RuntimeError(
                f"Frozen CV metadata mismatch for {field}: "
                f"observed={metadata.get(field)!r}, expected={value!r}"
            )
    if metadata.get("method") != "StratifiedGroupKFold_on_train_hierarchy_stratum":
        raise RuntimeError("Frozen CV map method differs from the project-V0 contract")
    rows = _read_tsv(map_path)
    if rows and tuple(rows[0]) != FOLD_MAP_FIELDS:
        raise RuntimeError(f"Frozen CV map fields must be exactly {FOLD_MAP_FIELDS}")
    assignment: dict[str, int] = {}
    for row in rows:
        component = row["global_component_id"]
        try:
            fold = int(row["fold"])
        except ValueError as error:
            raise RuntimeError(f"Invalid fold for global component {component!r}") from error
        if not component or component in assignment:
            raise RuntimeError(f"Empty or duplicate CV component ID: {component!r}")
        assignment[component] = fold
    manifest = _read_tsv(manifest_path)
    validate_fold_assignment(manifest, assignment, folds=folds)
    if metadata.get("train_global_component_count") != len(assignment):
        raise RuntimeError("Frozen CV metadata component count is inconsistent")
    attestation = {
        "schema_version": 1,
        "method": metadata["method"],
        "split": "train",
        "group_field": "global_component_id",
        "folds": folds,
        "seed": seed,
        "manifest_sha256": expected["manifest_sha256"],
        "fold_map_path": str(map_path),
        "fold_map_sha256": expected["fold_map_sha256"],
        "fold_metadata_path": str(metadata_path),
        "fold_metadata_sha256": sha256_file(metadata_path),
        "train_global_component_count": len(assignment),
    }
    return attestation, assignment


def freeze_cv_fold_map(
    config: dict[str, Any], *, reuse_if_valid: bool = False
) -> dict[str, Any]:
    """Create the shared map once, or validate an already frozen map."""

    map_path, metadata_path = _fold_paths(config)
    manifest_path = Path(config["paths"]["v0_manifest"])
    map_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    # Calibration jobs may enter concurrently.  The advisory lock serializes
    # creation/validation while the immutable map and metadata are published.
    import fcntl

    lock_path = metadata_path.with_suffix(metadata_path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        present = (map_path.exists(), metadata_path.exists())
        if any(present):
            if not all(present):
                raise RuntimeError("Partial frozen CV fold artifact exists; refusing overwrite")
            if not reuse_if_valid:
                raise RuntimeError("Frozen CV fold map already exists; refusing overwrite")
            attestation, _ = load_frozen_cv_fold_map(config, manifest_path)
            return {**attestation, "status": "already_frozen_and_valid"}

        manifest = _read_tsv(manifest_path)
        folds = int(config["classifier"]["cross_validation_folds"])
        seed = int(config["project"]["seed"])
        assignment, diagnostics = build_fold_assignment(
            manifest, folds=folds, seed=seed
        )
        _atomic_text(map_path, _fold_map_payload(assignment))
        metadata = {
            "schema_version": 1,
            "status": "frozen",
            "method": "StratifiedGroupKFold_on_train_hierarchy_stratum",
            "split": "train",
            "group_field": "global_component_id",
            "stratification_field": "derived_hierarchical_operational_label",
            "folds": folds,
            "seed": seed,
            "manifest_path": str(manifest_path),
            "manifest_sha256": sha256_file(manifest_path),
            "fold_map_path": str(map_path),
            "fold_map_sha256": sha256_file(map_path),
            "software": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "scikit_learn": __import__("sklearn").__version__,
            },
            **diagnostics,
        }
        _atomic_text(
            metadata_path,
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        )
        attestation, _ = load_frozen_cv_fold_map(config, manifest_path)
        return {**attestation, "status": "frozen_now"}
