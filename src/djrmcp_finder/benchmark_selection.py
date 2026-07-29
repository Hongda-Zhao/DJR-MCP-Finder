"""Verify and resolve the frozen development-benchmark selection bundle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from djrmcp_finder.benchmark_config import expand_benchmark_model
from djrmcp_finder.config import load_config


BASELINE_MODEL_ID = "esm2_650m"
COMPARISON_CHECKSUM_NAME = "COMPARISON_CHECKSUMS.sha256"
FROZEN_V0_BENCHMARK_MODEL_IDS = (
    "esm2_150m",
    "esm2_650m",
    "esm2_3b",
    "esmc_300m",
    "esmc_600m",
    "esmc_6b",
    "prott5_xl",
    "ankh3_large",
    "amplify_350m",
    "protsent_150m",
    "protrek_650m",
    "prostt5",
    "mimic_1b",
    "esm3_open_1_4b",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksum_manifest(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing checksum manifest: {path}")
    root = path.parent.resolve()
    verified: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            expected, relative = raw.split(maxsplit=1)
        except ValueError as error:
            raise RuntimeError(f"Malformed checksum line at {path}:{line_number}") from error
        relative = relative.strip()
        target = (path.parent / relative).resolve()
        if target.parent != root:
            raise RuntimeError(f"Checksum path escapes its directory: {relative}")
        if not target.is_file():
            raise FileNotFoundError(f"Missing checksummed artifact: {target}")
        observed = sha256_file(target)
        if observed != expected:
            raise RuntimeError(f"Artifact checksum mismatch for {target}")
        if relative in verified:
            raise RuntimeError(f"Duplicate checksum entry: {relative}")
        verified[relative] = observed
    return verified


def _verify_selected_model_artifacts(
    base_config: dict[str, Any],
    model_id: str,
    row: dict[str, Any],
    manifest_sha256: str,
) -> dict[str, Any]:
    expanded = expand_benchmark_model(base_config, model_id)
    embedding_dir = Path(expanded["paths"]["embedding_output"])
    result_dir = Path(expanded["paths"]["result_output"])
    expected_paths = {
        "embedding_metadata": embedding_dir / "metadata.json",
        "calibration": result_dir / "calibration.json",
        "cross_validation": result_dir / "metrics" / "cross_validation.json",
        "validation": result_dir / "metrics" / "validation_metrics.json",
    }
    recorded_hashes = row.get("input_sha256")
    if not isinstance(recorded_hashes, dict):
        raise RuntimeError(f"Frozen comparison lacks input hashes for {model_id}")
    for name, artifact_path in expected_paths.items():
        if not artifact_path.is_file():
            raise FileNotFoundError(f"Missing frozen {model_id} artifact: {artifact_path}")
        observed = sha256_file(artifact_path)
        if recorded_hashes.get(name) != observed:
            raise RuntimeError(f"Frozen comparison artifact mismatch for {model_id}/{name}")

    metadata = json.loads(expected_paths["embedding_metadata"].read_text(encoding="utf-8"))
    if metadata.get("status") != "complete":
        raise RuntimeError(f"Selected embedding is incomplete for {model_id}")
    if metadata.get("benchmark_model_id") != model_id:
        raise RuntimeError(f"Embedding model ID mismatch for {model_id}")
    if metadata.get("manifest_sha256") != manifest_sha256:
        raise RuntimeError(f"Embedding manifest mismatch for {model_id}")
    if metadata.get("resolved_model_revision") != row.get("resolved_model_revision"):
        raise RuntimeError(f"Frozen comparison revision mismatch for {model_id}")
    embedding_checksums = embedding_dir / "CHECKSUMS.sha256"
    if not embedding_checksums.is_file():
        raise FileNotFoundError(f"Missing embedding checksum manifest: {embedding_checksums}")
    verified_embedding = verify_checksum_manifest(embedding_checksums)
    if set(verified_embedding) != {
        "completed.npy",
        "embeddings.float16.npy",
        "index.tsv",
        "metadata.json",
    }:
        raise RuntimeError(f"Incomplete embedding checksum manifest for {model_id}")

    calibration = json.loads(expected_paths["calibration"].read_text(encoding="utf-8"))
    if calibration.get("manifest_sha256") != manifest_sha256:
        raise RuntimeError(f"Calibration manifest mismatch for {model_id}")
    if calibration.get("embedding_metadata_sha256") != sha256_file(
        expected_paths["embedding_metadata"]
    ):
        raise RuntimeError(f"Calibration/embedding mismatch for {model_id}")
    model_hashes: dict[str, str] = {}
    for head_name, head in calibration.get("heads", {}).items():
        model_path = Path(head["model_path"])
        if not model_path.is_file() or sha256_file(model_path) != head.get("model_sha256"):
            raise RuntimeError(f"Frozen classifier checksum mismatch: {model_id}/{head_name}")
        model_hashes[head_name] = head["model_sha256"]
    if set(model_hashes) != {"head1", "head2", "head3_phylum"}:
        raise RuntimeError(f"Incomplete frozen classifier heads for {model_id}")

    return {
        "label": row["label"],
        "model_name": row["model_name"],
        "resolved_model_revision": metadata.get("resolved_model_revision"),
        "embedding_dir": str(embedding_dir),
        "embedding_metadata_sha256": sha256_file(expected_paths["embedding_metadata"]),
        "embedding_checksums_sha256": sha256_file(embedding_checksums),
        "result_dir": str(result_dir),
        "calibration_sha256": sha256_file(expected_paths["calibration"]),
        "model_sha256": model_hashes,
    }


def load_frozen_benchmark_selection(
    config_path: Path,
    summary_path: Path,
    *,
    verify_artifacts: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the loaded benchmark config and an attested robustness selection."""
    config_path = Path(config_path)
    summary_path = Path(summary_path)
    base_config = load_config(config_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    checksum_path = summary_path.parent / COMPARISON_CHECKSUM_NAME
    verified_comparison = verify_checksum_manifest(checksum_path)
    required_comparison_files = {
        summary_path.name,
        "model_comparison.tsv",
        "fold_scores.tsv",
    }
    if set(verified_comparison) != required_comparison_files:
        raise RuntimeError(
            "Comparison checksum manifest must cover exactly the JSON, comparison TSV, "
            "and fold-score TSV"
        )
    if verified_comparison.get(summary_path.name) != sha256_file(summary_path):
        raise RuntimeError("Comparison JSON is not covered by its checksum manifest")

    config_sha256 = sha256_file(config_path)
    if summary.get("benchmark_config_sha256") != config_sha256:
        raise RuntimeError("Frozen comparison and current benchmark config differ")
    manifest_path = Path(base_config["paths"]["v0_manifest"])
    manifest_sha256 = sha256_file(manifest_path)
    if summary.get("manifest_sha256") != manifest_sha256:
        raise RuntimeError("Frozen comparison and current V0 manifest differ")
    if summary.get("pending_models") != []:
        raise RuntimeError("Frozen comparison still contains pending models")

    expected_ids = list(base_config["benchmark"]["models"])
    if expected_ids != list(FROZEN_V0_BENCHMARK_MODEL_IDS):
        raise RuntimeError(
            "Frozen project-V0 comparison requires the exact ordered 14-candidate registry"
        )
    if summary.get("candidate_model_ids") != expected_ids:
        raise RuntimeError("Frozen comparison candidate order/set differs from config")
    rows = summary.get("models")
    if not isinstance(rows, list):
        raise RuntimeError("Frozen comparison has no model rows")
    row_by_id = {row.get("model_id"): row for row in rows}
    if len(row_by_id) != len(rows) or set(row_by_id) != set(expected_ids):
        raise RuntimeError("Frozen comparison model rows are incomplete or duplicated")
    if any(row.get("status") != "complete" for row in rows):
        raise RuntimeError("Frozen comparison contains an incomplete model row")
    if summary.get("complete_model_count") != len(expected_ids):
        raise RuntimeError("Frozen comparison complete-model count is inconsistent")

    selected_model_id = summary.get("selected_model_id")
    if selected_model_id not in row_by_id:
        raise RuntimeError(f"Invalid frozen selected_model_id: {selected_model_id!r}")
    selected_flags = [row["model_id"] for row in rows if row.get("selected") is True]
    if selected_flags != [selected_model_id]:
        raise RuntimeError("Frozen comparison does not have one matching selected row")
    if BASELINE_MODEL_ID not in row_by_id:
        raise RuntimeError(f"Frozen comparison lacks baseline {BASELINE_MODEL_ID}")
    for model_id, row in row_by_id.items():
        spec = base_config["benchmark"]["models"][model_id]
        expanded = expand_benchmark_model(base_config, model_id)
        if row.get("label") != spec.get("label") or row.get("model_name") != spec.get(
            "model_name"
        ):
            raise RuntimeError(f"Frozen comparison/config model identity mismatch: {model_id}")
        if row.get("embedding_dir") != expanded["paths"]["embedding_output"] or row.get(
            "result_dir"
        ) != expanded["paths"]["result_output"]:
            raise RuntimeError(f"Frozen comparison/config artifact path mismatch: {model_id}")
        if row.get("test_status") != "not_evaluated":
            raise RuntimeError(f"Candidate Test state was not clean at freeze time: {model_id}")
        if not isinstance(row.get("resolved_model_revision"), str) or not row[
            "resolved_model_revision"
        ]:
            raise RuntimeError(f"Frozen comparison lacks resolved revision for {model_id}")
    if row_by_id[selected_model_id].get("selectable") is not True:
        raise RuntimeError("Frozen selected model is not marked selectable")

    comparison_mode = (
        "selected_is_baseline_identical_control"
        if selected_model_id == BASELINE_MODEL_ID
        else "selected_vs_baseline"
    )
    robustness_model_ids = (
        [BASELINE_MODEL_ID]
        if selected_model_id == BASELINE_MODEL_ID
        else [BASELINE_MODEL_ID, selected_model_id]
    )
    model_lineage: dict[str, Any] = {}
    for model_id in robustness_model_ids:
        row = row_by_id[model_id]
        if verify_artifacts:
            model_lineage[model_id] = _verify_selected_model_artifacts(
                base_config, model_id, row, manifest_sha256
            )
        else:
            expanded = expand_benchmark_model(base_config, model_id)
            model_lineage[model_id] = {
                "label": row["label"],
                "model_name": row["model_name"],
                "resolved_model_revision": row.get("resolved_model_revision"),
                "embedding_dir": expanded["paths"]["embedding_output"],
                "result_dir": expanded["paths"]["result_output"],
            }

    selection = {
        "schema_version": 1,
        "baseline_model_id": BASELINE_MODEL_ID,
        "selected_model_id": selected_model_id,
        "comparison_mode": comparison_mode,
        "robustness_model_ids": robustness_model_ids,
        "benchmark_config_path": str(config_path),
        "benchmark_config_sha256": config_sha256,
        "comparison_summary_path": str(summary_path),
        "comparison_summary_sha256": sha256_file(summary_path),
        "comparison_checksums_path": str(checksum_path),
        "comparison_checksums_sha256": sha256_file(checksum_path),
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "candidate_model_count": len(expected_ids),
        "models": model_lineage,
    }
    return base_config, selection
