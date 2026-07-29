#!/usr/bin/env python3
"""Independently validate schema-4 four-source robustness results."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import yaml


ANALYSIS_ID = "project_v0_validation_family_robustness_schema4"
MODELS = ("esm2_650m", "esmc_6b")
SOURCES = (
    "viral_vma_djr",
    "cellular_djr_none",
    "background_non_djr",
    "hard_non_djr",
)
APPLICABLE_HEADS = {
    "viral_vma_djr": ("head1", "head2", "head3_phylum"),
    "cellular_djr_none": ("head1", "head2"),
    "background_non_djr": ("head1",),
    "hard_non_djr": ("head1",),
}
HEAD_SEED_OFFSET = {
    ("viral_vma_djr", "head1"): 1_000,
    ("viral_vma_djr", "head2"): 1_010,
    ("viral_vma_djr", "head3_phylum"): 1_020,
    ("cellular_djr_none", "head1"): 2_000,
    ("cellular_djr_none", "head2"): 2_010,
    ("background_non_djr", "head1"): 3_000,
    ("hard_non_djr", "head1"): 4_000,
}
PATH_SEED_OFFSET = {
    "viral_vma_djr": 5_000,
    "cellular_djr_none": 5_010,
    "background_non_djr": 5_020,
    "hard_non_djr": 5_030,
}
PATH_ID = "full_expected_path"
TOLERANCE = 1e-12


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise RuntimeError(f"Missing TSV header: {path}")
        return list(reader)


def _as_int(value: Any) -> int:
    text = str(value).strip().lower()
    if text in {"1", "true", "yes"}:
        return 1
    if text in {"0", "false", "no", ""}:
        return 0
    raise RuntimeError(f"Expected Boolean/integer flag, observed {value!r}")


def _close(left: Any, right: Any, tolerance: float = TOLERANCE) -> bool:
    if str(left) == "" and str(right) == "":
        return True
    return abs(float(left) - float(right)) <= tolerance


def _verify_result(directory: Path) -> dict[str, str]:
    manifest = directory / "CHECKSUMS.sha256"
    verified: dict[str, str] = {}
    for line_number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split(maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError(f"Malformed result checksum at line {line_number}")
        expected, name = parts[0].lower(), parts[1].strip().lstrip("*")
        target = directory / name
        if Path(name).name != name or name in verified or not target.is_file():
            raise RuntimeError(f"Unsafe or missing result checksum target: {name}")
        if _sha256(target) != expected:
            raise RuntimeError(f"Result checksum mismatch: {target}")
        verified[name] = expected
    required = {
        "predictions.tsv",
        "expected_path_predictions.tsv",
        "source_head_summary.tsv",
        "source_path_summary.tsv",
        "cluster_all_members_summary.tsv",
        "h3_class_summary.tsv",
        "hardnegative_summary.tsv",
        "coverage_summary.tsv",
        "error_destination_summary.tsv",
        "bootstrap_replicates.tsv",
        "summary.json",
    }
    if set(verified) != required:
        difference = sorted(set(verified) ^ required)
        raise RuntimeError(f"Schema-4 result bundle differs from exact contract: {difference}")
    return verified


def _bootstrap(
    representative: np.ndarray, member: np.ndarray, replicates: int, seed: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    rep_draws = np.empty(replicates, dtype=np.float64)
    member_draws = np.empty(replicates, dtype=np.float64)
    batch = 256
    for start in range(0, replicates, batch):
        stop = min(start + batch, replicates)
        selected = rng.integers(0, len(member), size=(stop - start, len(member)))
        rep_draws[start:stop] = representative[selected].mean(axis=1)
        member_draws[start:stop] = member[selected].mean(axis=1)
    return rep_draws, member_draws, member_draws - rep_draws


def _recompute_nested(
    rows: list[dict[str, str]], replicates: int, seed: int
) -> tuple[dict[str, float | int], tuple[np.ndarray, np.ndarray, np.ndarray]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["dependence_block_id"], row["source_cluster_key"])].append(row)
    if not grouped:
        raise RuntimeError("Cannot recompute empty endpoint")
    rep_by_block: dict[str, list[float]] = defaultdict(list)
    member_by_block: dict[str, list[float]] = defaultdict(list)
    cluster_all: list[int] = []
    for (block, _cluster), members in sorted(grouped.items()):
        rep = {_as_int(row["representative_correct"]) for row in members}
        if len(rep) != 1:
            raise RuntimeError("Nonconstant representative call inside source cluster")
        rep_by_block[block].append(float(next(iter(rep))))
        member_values = [_as_int(row["member_correct"]) for row in members]
        member_by_block[block].append(float(np.mean(member_values)))
        cluster_all.append(int(all(member_values)))
    blocks = sorted(member_by_block)
    rep_values = np.asarray([np.mean(rep_by_block[b]) for b in blocks], dtype=float)
    member_values = np.asarray([np.mean(member_by_block[b]) for b in blocks], dtype=float)
    boot = _bootstrap(rep_values, member_values, replicates, seed)
    values: dict[str, float | int] = {
        "representative_value": float(rep_values.mean()),
        "representative_ci_low": float(np.quantile(boot[0], 0.025)),
        "representative_ci_high": float(np.quantile(boot[0], 0.975)),
        "member_value": float(member_values.mean()),
        "member_ci_low": float(np.quantile(boot[1], 0.025)),
        "member_ci_high": float(np.quantile(boot[1], 0.975)),
        "delta_members_minus_representative": float(member_values.mean() - rep_values.mean()),
        "delta_ci_low": float(np.quantile(boot[2], 0.025)),
        "delta_ci_high": float(np.quantile(boot[2], 0.975)),
        "n_member_records": len(rows),
        "n_source_clusters": len(grouped),
        "n_dependence_blocks": len(blocks),
        "clusters_all_members_correct": sum(cluster_all),
        "proportion_clusters_all_members_correct": float(np.mean(cluster_all)),
    }
    return values, boot


def _compare_metric_row(observed: dict[str, str], recomputed: dict[str, Any]) -> None:
    integer_fields = (
        "n_member_records",
        "n_source_clusters",
        "n_dependence_blocks",
        "clusters_all_members_correct",
    )
    for field in integer_fields:
        if int(observed[field]) != int(recomputed[field]):
            raise RuntimeError(f"Metric support mismatch for {field}")
    for field in (
        "representative_value",
        "representative_ci_low",
        "representative_ci_high",
        "member_value",
        "member_ci_low",
        "member_ci_high",
        "delta_members_minus_representative",
        "delta_ci_low",
        "delta_ci_high",
        "proportion_clusters_all_members_correct",
    ):
        if not _close(observed[field], recomputed[field]):
            raise RuntimeError(f"Metric value mismatch for {field}")


def _validate_schema3_continuity(
    config: dict[str, Any], predictions: list[dict[str, str]]
) -> int:
    old_path = Path(config["schema3"]["full_result_dir"]) / "family_member_predictions.tsv"
    old_rows = _read_tsv(old_path)
    old_index = {
        (row["model_id"], row["protein_id"], row["head"]): row for row in old_rows
    }
    new_rows = [row for row in predictions if row["source_dataset"] != "hard_non_djr"]
    new_index = {
        (row["model_id"], row["protein_id"], row["head"]): row for row in new_rows
    }
    if set(old_index) != set(new_index):
        raise RuntimeError("Schema-3/schema-4 per-record prediction key discontinuity")
    text_fields = (
        "source_dataset",
        "paired_representative_id",
        "source_cluster_id",
        "source_cluster_key",
        "dependence_block_id",
        "member_prediction",
        "representative_prediction",
        "test_record",
    )
    numeric_fields = (
        "member_probability",
        "member_raw_decision_score",
        "representative_probability",
        "representative_raw_decision_score",
        "threshold",
    )
    for key in sorted(old_index):
        old, new = old_index[key], new_index[key]
        for field in text_fields:
            if old[field] != new[field]:
                raise RuntimeError(f"Schema-3 continuity mismatch {key}/{field}")
        for field in numeric_fields:
            if not _close(old[field], new[field], tolerance=0.0):
                raise RuntimeError(f"Schema-3 numeric continuity mismatch {key}/{field}")
    return len(new_rows)


def _validate_expected_paths(
    predictions: list[dict[str, str]], paths: list[dict[str, str]]
) -> None:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in predictions:
        grouped[(row["model_id"], row["protein_id"])].append(row)
    path_index = {(row["model_id"], row["protein_id"]): row for row in paths}
    if len(path_index) != len(paths) or set(path_index) != set(grouped):
        raise RuntimeError("Expected-path rows do not map one-to-one to prediction records")
    for key, records in grouped.items():
        source = records[0]["source_dataset"]
        eligible = [row for row in records if _as_int(row["metric_eligible"]) == 1]
        eligible.sort(key=lambda row: APPLICABLE_HEADS[source].index(row["head"]))
        path = path_index[key]
        expected = ">".join(row["truth_label"] for row in eligible)
        member = ">".join(row["member_predicted_label"] for row in eligible)
        representative = ">".join(
            row["representative_predicted_label"] for row in eligible
        )
        if (
            path["path_id"] != PATH_ID
            or path["source_dataset"] != source
            or path["expected_path"] != expected
            or path["member_observed_path"] != member
            or path["representative_observed_path"] != representative
            or _as_int(path["member_correct"])
            != int(all(_as_int(row["member_correct"]) for row in eligible))
            or _as_int(path["representative_correct"])
            != int(all(_as_int(row["representative_correct"]) for row in eligible))
            or int(path["n_applicable_heads"]) != len(eligible)
        ):
            raise RuntimeError(f"Expected-path derivation mismatch: {key}")


def validate(config_path: Path, output_path: Path | None = None) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if (
        config.get("schema_version") != 4
        or config.get("analysis_id") != ANALYSIS_ID
        or config.get("selection_feedback_permitted") is not False
        or config.get("release_gate") is not False
        or config.get("model_state") != "frozen"
        or int(config.get("bootstrap_replicates", 0)) != 10_000
        or int(config.get("bootstrap_seed", 0)) != 20260724
    ):
        raise RuntimeError("Schema-4 validation boundary mismatch")
    result_dir = Path(config["result_dir"])
    verified = _verify_result(result_dir)
    summary = json.loads((result_dir / "summary.json").read_text(encoding="utf-8"))
    if (
        summary.get("schema_version") != 4
        or summary.get("analysis_id") != ANALYSIS_ID
        or summary.get("status") != "complete_four_source"
        or summary.get("selection_feedback_permitted") is not False
        or summary.get("release_gate") is not False
        or summary.get("model_state") != "frozen"
        or summary.get("test_vectors_selected_for_inference") != 0
        or summary.get("test_predictions_or_metrics_computed") != 0
        or summary.get("input_sha256", {}).get("config") != _sha256(config_path)
    ):
        raise RuntimeError("Summary boundary/lineage mismatch")

    predictions = _read_tsv(result_dir / "predictions.tsv")
    paths = _read_tsv(result_dir / "expected_path_predictions.tsv")
    head_summary = _read_tsv(result_dir / "source_head_summary.tsv")
    path_summary = _read_tsv(result_dir / "source_path_summary.tsv")
    coverage = _read_tsv(result_dir / "coverage_summary.tsv")
    h3_summary = _read_tsv(result_dir / "h3_class_summary.tsv")
    bootstrap_rows = _read_tsv(result_dir / "bootstrap_replicates.tsv")
    if any(_as_int(row["test_record"]) for row in predictions + paths):
        raise RuntimeError("Test records occur in schema-4 outputs")
    observed_sources = {row["source_dataset"] for row in predictions}
    coverage_sources = {row["source_dataset"] for row in coverage}
    if observed_sources != set(SOURCES) or coverage_sources != set(SOURCES):
        raise RuntimeError("Four-source coverage mismatch")
    for row in predictions:
        if row["head"] not in APPLICABLE_HEADS[row["source_dataset"]]:
            raise RuntimeError("Prediction emitted for a source/head N/A cell")
    hard_h2_h3 = sum(
        row["source_dataset"] == "hard_non_djr" and row["head"] != "head1"
        for row in predictions
    )
    if hard_h2_h3 != 0:
        raise RuntimeError("HardNeg H2/H3 predictions must be absent, not zero")
    _validate_expected_paths(predictions, paths)

    expected_head_keys = {
        (model, source, head)
        for model in MODELS
        for source in SOURCES
        for head in APPLICABLE_HEADS[source]
    }
    observed_head_keys = {
        (row["model_id"], row["source_dataset"], row["head"]) for row in head_summary
    }
    if observed_head_keys != expected_head_keys or len(head_summary) != len(expected_head_keys):
        raise RuntimeError("Source/head summary is incomplete or duplicated")
    forbidden_metric = ("average_precision", "roc_auc", "macro_f1", "micro_f1")
    if any(
        any(value in row["metric"].lower() for value in forbidden_metric)
        for row in head_summary
    ):
        raise RuntimeError("Forbidden AP/AUC/F1 metric in source/head table")

    replicates = int(config["bootstrap_replicates"])
    base_seed = int(config["bootstrap_seed"])
    recomputed_endpoints = 0
    for observed in head_summary:
        selected = [
            row
            for row in predictions
            if row["model_id"] == observed["model_id"]
            and row["source_dataset"] == observed["source_dataset"]
            and row["head"] == observed["head"]
            and _as_int(row["metric_eligible"]) == 1
        ]
        seed = base_seed + HEAD_SEED_OFFSET[(observed["source_dataset"], observed["head"])]
        values, boot = _recompute_nested(selected, replicates, seed)
        _compare_metric_row(observed, values)
        stored = [
            row
            for row in bootstrap_rows
            if row["analysis_part"] == "source_head"
            and row["model_id"] == observed["model_id"]
            and row["source_dataset"] == observed["source_dataset"]
            and row["endpoint_id"] == observed["head"]
        ]
        if len(stored) != replicates:
            raise RuntimeError("Missing exact source/head bootstrap draws")
        for index, row in enumerate(stored):
            if not (
                _close(row["representative_value"], boot[0][index])
                and _close(row["member_value"], boot[1][index])
                and _close(row["delta_member_minus_representative"], boot[2][index])
            ):
                raise RuntimeError("Stored source/head bootstrap draw mismatch")
        recomputed_endpoints += 1

    expected_path_keys = {(model, source) for model in MODELS for source in SOURCES}
    if {
        (row["model_id"], row["source_dataset"]) for row in path_summary
    } != expected_path_keys or len(path_summary) != len(expected_path_keys):
        raise RuntimeError("Source/path summary is incomplete or duplicated")
    for observed in path_summary:
        if observed["path_id"] != PATH_ID:
            raise RuntimeError("Unexpected path ID")
        selected = [
            row
            for row in paths
            if row["model_id"] == observed["model_id"]
            and row["source_dataset"] == observed["source_dataset"]
        ]
        seed = base_seed + PATH_SEED_OFFSET[observed["source_dataset"]]
        values, _boot = _recompute_nested(selected, replicates, seed)
        _compare_metric_row(observed, values)
        recomputed_endpoints += 1

    expected_h3 = {
        "Nucleocytoviricota_recall",
        "Nucleocytoviricota_f1",
        "Preplasmiviricota_recall",
        "Preplasmiviricota_f1",
        "Produgelaviricota_reject_recall",
        "literature_unclassified_reject_recall",
    }
    observed_h3 = {row["endpoint_id"] for row in h3_summary}
    if observed_h3 != expected_h3 or len(h3_summary) != 2 * len(expected_h3):
        raise RuntimeError("Separated H3 class/rejection endpoints are incomplete")
    if any(int(row["n_truth_records"]) <= 0 for row in h3_summary):
        raise RuntimeError("H3 small-sample support must be explicit and positive")
    if not all(
        "not_general_unknown_detection" in row["interpretation"]
        for row in h3_summary
        if row["metric"] == "reject_recall"
    ):
        raise RuntimeError("H3 reject-recall interpretation guard missing")

    continuity_records = _validate_schema3_continuity(config, predictions)
    hard_manifest = Path(
        config["hardnegative_matched"].get(
            "legal_manifest",
            Path(config["hardnegative_matched"]["legal_dir"]) / "member_manifest.tsv",
        )
    )
    hard_ids = {row["protein_id"] for row in _read_tsv(hard_manifest)}
    hard_prediction_ids = {
        row["protein_id"] for row in predictions if row["source_dataset"] == "hard_non_djr"
    }
    if hard_prediction_ids != hard_ids:
        raise RuntimeError("HardNeg legal/predicted member set mismatch")

    payload: dict[str, Any] = {
        "schema_version": 4,
        "analysis_id": ANALYSIS_ID,
        "status": "PASS",
        "validated_result_status": "complete_four_source",
        "gates": {
            "checksum_exact_bundle": "PASS",
            "four_source_coverage": "PASS",
            "applicable_heads_only": "PASS",
            "expected_paths_rederived_from_per_head_predictions": "PASS",
            "hardnegative_h2_h3_prediction_count_zero": "PASS",
            "test_record_count_zero": "PASS",
            "negative_only_no_ap_auc_f1": "PASS",
            "fixed_seed_nested_bootstrap_recomputed": "PASS",
            "schema3_three_source_per_record_continuity": "PASS",
            "h3_endpoints_separated_and_small_n_explicit": "PASS",
        },
        "counts": {
            "verified_artifacts": len(verified),
            "prediction_rows": len(predictions),
            "path_rows": len(paths),
            "recomputed_primary_endpoints": recomputed_endpoints,
            "schema3_continuity_prediction_rows": continuity_records,
            "hardnegative_legal_members": len(hard_ids),
            "hardnegative_h2_h3_predictions": hard_h2_h3,
            "test_records": 0,
        },
        "input_sha256": {
            "config": _sha256(config_path),
            "result_checksums": _sha256(result_dir / "CHECKSUMS.sha256"),
            "schema3_predictions": _sha256(
                Path(config["schema3"]["full_result_dir"]) / "family_member_predictions.tsv"
            ),
            "hardnegative_legal_manifest": _sha256(hard_manifest),
        },
    }
    destination = output_path or result_dir.with_name("validation.json")
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite validation: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/validation_family_robustness_v0_schema4.yaml"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.config, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
