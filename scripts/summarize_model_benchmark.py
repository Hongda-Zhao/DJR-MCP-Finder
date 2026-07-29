#!/usr/bin/env python3
"""Aggregate the data-curation-V3/project-V0 development-only embedding benchmark.

Every candidate, including the freshly rerun ESM-2 650M baseline, must be free of
a Test marker.  Selection reads Train-CV and Validation artifacts only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any

from djrmcp_finder.config import load_config
from djrmcp_finder.cv_folds import load_frozen_cv_fold_map
from djrmcp_finder.benchmark_config import benchmark_artifact_paths


WEIGHTS = {"head1": 0.60, "head2": 0.30, "head3_phylum": 0.10}
GATE_TOLERANCE = 0.01
PERMISSIVE_LICENSES = {"MIT", "Apache-2.0", "BSD-3-Clause"}
PAIRED_TIE_RULE = (
    "within one paired standard error of the highest-selectable CV model; "
    "SE is computed from the five same-fold deltas S_best_fold - S_candidate_fold"
)
TIE_BREAK_ORDER = [
    "lower Validation Head1 FPR@95% recall",
    "lower seconds per sequence only within a same-FPR group with an identical "
    "GPU/host/software/timing-definition comparability key",
    "permissive license",
    "higher composite S, then stable model ID",
]
SPEED_TIE_BREAK_POLICY = (
    "Speed is evaluated only after an exact tie on the preceding Validation H1 FPR "
    "criterion. Every model in that FPR group must have a positive accumulated "
    "inference duration excluding model load and the same host, GPU, device, Python, "
    "platform, PyTorch, Transformers and CUDA-runtime values. Otherwise speed is "
    "skipped for the whole group and license is the next preregistered criterion. "
    "Timestamp-derived wall time is descriptive only and is never selection evidence."
)
SELECTED_INPUT_NAMES = {
    "embedding_metadata",
    "embedding_checksums",
    "calibration",
    "cross_validation",
    "validation",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_sha256_manifest(path: Path, base: Path) -> dict[str, str]:
    observed: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        parts = raw_line.split(maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError(f"Malformed checksum line {line_number}: {path}")
        digest, name = parts[0], parts[1].strip().lstrip("*")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise RuntimeError(f"Invalid SHA-256 on line {line_number}: {path}")
        candidate = Path(name)
        if candidate.is_absolute() or len(candidate.parts) != 1 or name in observed:
            raise RuntimeError(f"Unsafe or duplicate checksum entry {name!r}: {path}")
        artifact = base / candidate
        if not artifact.is_file() or _sha256(artifact) != digest:
            raise RuntimeError(f"Embedding checksum mismatch for {artifact}")
        observed[name] = digest
    expected = {"embeddings.float16.npy", "index.tsv", "completed.npy", "metadata.json"}
    if set(observed) != expected:
        raise RuntimeError(
            f"Embedding checksum coverage differs for {base}: "
            f"observed={sorted(observed)}, expected={sorted(expected)}"
        )
    return observed


def _mean(values: list[float]) -> float:
    return float(sum(values) / len(values))


def _se(values: list[float]) -> float:
    return float(statistics.stdev(values) / math.sqrt(len(values))) if len(values) > 1 else 0.0


def _paths(
    model_id: str, spec: dict[str, Any], config: dict[str, Any] | None = None
) -> tuple[Path, Path]:
    default_embedding, default_result = benchmark_artifact_paths(config or {}, model_id)
    embedding = Path(
        spec.get("reuse_embedding", default_embedding)
    )
    result = Path(spec.get("reuse_result", default_result))
    return embedding, result


def _development_row(
    model_id: str,
    spec: dict[str, Any],
    current_manifest_sha256: str,
    cv_fold_contract: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    embedding_dir, result_dir = _paths(model_id, spec, config)
    required = {
        "embedding_metadata": embedding_dir / "metadata.json",
        "embedding_checksums": embedding_dir / "CHECKSUMS.sha256",
        "calibration": result_dir / "calibration.json",
        "cross_validation": result_dir / "metrics" / "cross_validation.json",
        "validation": result_dir / "metrics" / "validation_metrics.json",
        "cv_fold_map": Path(cv_fold_contract["fold_map_path"]),
        "cv_fold_metadata": Path(cv_fold_contract["fold_metadata_path"]),
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    base = {
        "model_id": model_id,
        "label": spec["label"],
        "model_name": spec["model_name"],
        "license": spec["license"],
        "permissive_license": spec["license"] in PERMISSIVE_LICENSES,
        "source_kind": spec["source_kind"],
        "pretraining_overlap_risk": spec.get("pretraining_overlap_risk", "not_flagged"),
        "embedding_dir": str(embedding_dir),
        "result_dir": str(result_dir),
    }
    if missing:
        return {**base, "status": "pending", "missing": missing}, []

    metadata = _read_json(required["embedding_metadata"])
    calibration = _read_json(required["calibration"])
    cv = _read_json(required["cross_validation"])
    validation = _read_json(required["validation"])
    if metadata.get("status") != "complete":
        return {**base, "status": "pending", "missing": ["complete embedding"]}, []
    if metadata.get("manifest_sha256") != current_manifest_sha256:
        raise RuntimeError(f"Embedding manifest mismatch for {model_id}")
    if calibration.get("manifest_sha256") != current_manifest_sha256:
        raise RuntimeError(f"Calibration manifest mismatch for {model_id}")
    if calibration.get("embedding_metadata_sha256") != _sha256(
        required["embedding_metadata"]
    ):
        raise RuntimeError(f"Calibration embedding lineage mismatch for {model_id}")
    if calibration.get("cv_fold_contract") != cv_fold_contract:
        raise RuntimeError(f"Calibration CV-fold lineage mismatch for {model_id}")
    metric_revision = (config or {}).get("project", {}).get("metric_revision_id")
    expected_cv_schema = 3 if metric_revision else 2
    expected_calibration_schema = 4 if metric_revision else 3
    if calibration.get("schema_version") != expected_calibration_schema:
        raise RuntimeError(f"Calibration schema mismatch for {model_id}")
    if cv.get("schema_version") != expected_cv_schema or cv.get("cv_fold_contract") != cv_fold_contract:
        raise RuntimeError(f"Cross-validation fold lineage mismatch for {model_id}")
    if metric_revision:
        if calibration.get("binary_ranking_score_source") != "raw_decision_function":
            raise RuntimeError(f"Corrected calibration lacks raw ranking-score lineage for {model_id}")
        if cv.get("binary_ranking_score_source") != "raw_decision_function":
            raise RuntimeError(f"Corrected CV lacks raw ranking-score lineage for {model_id}")
    forbidden_test_artifacts = (
        result_dir / "FINAL_TEST_EVALUATED.json",
        result_dir / "TEST_EVALUATION_RESERVED.json",
        result_dir / "TEST_SELECTION_AUTHORIZATION.json",
        result_dir / "TEST_EVALUATION_RECEIPT.json",
        result_dir / "metrics" / "frozen_test_metrics.json",
        result_dir / "predictions" / "frozen_test_predictions.tsv",
    )
    present_forbidden = [str(path) for path in forbidden_test_artifacts if path.exists()]
    if present_forbidden:
        raise RuntimeError(
            f"Forbidden benchmark Test artifact found for {model_id}: {present_forbidden}"
        )
    if calibration.get("test_evaluated") is not False:
        raise RuntimeError(f"Unexpected test_evaluated state for {model_id}")
    embedding_artifact_sha256 = _verify_sha256_manifest(
        required["embedding_checksums"], embedding_dir
    )
    expected_heads = {"head1", "head2", "head3_phylum"}
    if set(calibration.get("heads", {})) != expected_heads:
        raise RuntimeError(f"Incomplete calibration heads for {model_id}")
    model_sha256: dict[str, str] = {}
    for head_name in sorted(expected_heads):
        head = calibration["heads"][head_name]
        model_path = Path(head["model_path"])
        if not model_path.is_file() or _sha256(model_path) != head.get("model_sha256"):
            raise RuntimeError(f"Model checksum mismatch for {model_id}/{head_name}")
        model_sha256[head_name] = head["model_sha256"]

    head_means: dict[str, float] = {}
    head_ses: dict[str, float] = {}
    head_fold_scores: dict[str, list[float]] = {}
    fold_rows: list[dict[str, Any]] = []
    if set(cv.get("heads", {})) != set(WEIGHTS):
        raise RuntimeError(f"Cross-validation heads differ from the frozen contract for {model_id}")
    folds = int(cv_fold_contract["folds"])
    expected_fold_ids = list(range(1, folds + 1))
    for head in WEIGHTS:
        report = cv["heads"][head]
        expected_metric = "macro_f1" if head == "head3_phylum" else "average_precision"
        if report.get("primary_metric") != expected_metric:
            raise RuntimeError(f"{model_id}/{head} primary metric differs from the contract")
        expected_metric_input = (
            "raw_decision_function" if head in {"head1", "head2"} else "uncalibrated_probabilities"
        )
        if metric_revision and report.get("primary_metric_input") != expected_metric_input:
            raise RuntimeError(f"{model_id}/{head} metric input differs from the revision contract")
        if report.get("splitter") != "FrozenGlobalComponentFoldMap":
            raise RuntimeError(f"{model_id}/{head} did not use the frozen CV map")
        if report.get("fold_ids") != expected_fold_ids or report.get("folds") != folds:
            raise RuntimeError(f"{model_id}/{head} fold identities differ from the frozen map")
        best = report["candidates_ranked"][0]
        if float(calibration["heads"][head]["best_parameter"]) != float(best["parameter"]):
            raise RuntimeError(f"{model_id}/{head} selected parameter lineage is inconsistent")
        scores = [float(value) for value in best["fold_scores"]]
        if len(scores) != folds:
            raise RuntimeError(f"{model_id}/{head} does not contain exactly {folds} fold scores")
        head_means[head] = _mean(scores)
        if not math.isclose(
            head_means[head], float(best["mean_score"]), rel_tol=0.0, abs_tol=1e-12
        ):
            raise RuntimeError(f"{model_id}/{head} recorded CV mean is inconsistent")
        head_ses[head] = _se(scores)
        head_fold_scores[head] = scores
        for fold, score in enumerate(scores, start=1):
            fold_rows.append(
                {
                    "model_id": model_id,
                    "label": spec["label"],
                    "head": head,
                    "metric": report["primary_metric"],
                    "fold": fold,
                    "score": score,
                    "selected_parameter": best["parameter"],
                    "fold_map_sha256": cv_fold_contract["fold_map_sha256"],
                }
            )

    composite_fold_scores = [
        sum(WEIGHTS[head] * head_fold_scores[head][fold] for head in WEIGHTS)
        for fold in range(folds)
    ]
    composite = _mean(composite_fold_scores)
    composite_se = _se(composite_fold_scores)
    for fold_row in fold_rows:
        fold_row["composite_fold_score"] = composite_fold_scores[
            int(fold_row["fold"]) - 1
        ]
    val_h1 = validation["heads"]["head1"]
    val_h2 = validation["heads"]["head2"]
    val_h3 = validation["heads"]["head3_phylum"]
    raw_embedding_seconds = metadata.get("accumulated_embedding_seconds")
    embedding_seconds = (
        float(raw_embedding_seconds)
        if isinstance(raw_embedding_seconds, (int, float))
        and math.isfinite(float(raw_embedding_seconds))
        and float(raw_embedding_seconds) > 0.0
        else None
    )
    timing_source = (
        "accumulated_inference_seconds_excluding_model_load"
        if embedding_seconds is not None
        else "unavailable_no_comparable_accumulated_inference_time"
    )
    timing_comparability_key = {
        "definition": timing_source,
        "host": metadata.get("host"),
        "gpu": metadata.get("gpu"),
        "device": metadata.get("device"),
        "python": metadata.get("python"),
        "platform": metadata.get("platform"),
        "torch": metadata.get("torch"),
        "transformers": metadata.get("transformers"),
        "cuda_runtime": metadata.get("cuda_runtime"),
    }
    required_timing_values = (
        "host",
        "gpu",
        "device",
        "python",
        "platform",
        "torch",
        "transformers",
        "cuda_runtime",
    )
    speed_tie_break_eligible = bool(
        embedding_seconds is not None
        and all(timing_comparability_key[key] not in (None, "") for key in required_timing_values)
    )
    record_count = int(metadata["record_count"])
    row = {
        **base,
        "status": "complete",
        "test_status": (
            "not_evaluated"
        ),
        "metric_revision_id": metric_revision,
        "binary_ranking_score_source": calibration.get("binary_ranking_score_source"),
        "temperature_search_contract": calibration["heads"]["head1"].get(
            "temperature_search"
        ),
        "resolved_model_revision": metadata.get("resolved_model_revision"),
        "embedding_dimension": metadata.get("embedding_dimension"),
        "parameter_count": metadata.get(
            "parameter_count", spec.get("reported_parameter_count")
        ),
        "parameter_count_source": (
            "embedding_metadata"
            if metadata.get("parameter_count") is not None
            else "registry_reported"
        ),
        "record_count": record_count,
        "embedding_seconds": embedding_seconds,
        "embedding_timing_source": timing_source,
        "timing_comparability_key": timing_comparability_key,
        "speed_tie_break_eligible": speed_tie_break_eligible,
        "gpu_seconds_per_sequence": (
            float(embedding_seconds) / record_count if embedding_seconds is not None else None
        ),
        "peak_gpu_memory_bytes": metadata.get("peak_gpu_memory_bytes"),
        "cv_head1_average_precision": head_means["head1"],
        "cv_head1_se": head_ses["head1"],
        "cv_head2_average_precision": head_means["head2"],
        "cv_head2_se": head_ses["head2"],
        "cv_head3_macro_f1": head_means["head3_phylum"],
        "cv_head3_se": head_ses["head3_phylum"],
        "composite_score": composite,
        "composite_se": composite_se,
        "composite_se_method": "sd_of_five_shared_fold_composites_div_sqrt5",
        "composite_fold_scores": composite_fold_scores,
        "cv_fold_map_sha256": cv_fold_contract["fold_map_sha256"],
        "cv_fold_metadata_sha256": cv_fold_contract["fold_metadata_sha256"],
        "val_head1_average_precision": float(val_h1["average_precision"]),
        "val_head1_fpr_at_95pct_recall": val_h1["fpr_at_95pct_recall"],
        "val_head1_mcc": float(val_h1["mcc"]),
        "val_head2_macro_f1": _mean([float(value) for value in val_h2["f1_by_class"]]),
        "val_head2_balanced_accuracy": float(val_h2["balanced_accuracy"]),
        "val_head3_macro_f1": float(val_h3["macro_f1_unknown_as_error"]),
        "val_head3_balanced_accuracy": float(
            val_h3["balanced_accuracy_unknown_as_error"]
        ),
        "val_head3_ece": float(val_h3["ece"]),
        "val_head3_brier": float(val_h3["multiclass_brier"]),
        "val_head3_unknown_diagnostic_n": int(
            calibration["heads"]["head3_phylum"]["open_set"][
                "validation_unknown_diagnostic_n"
            ]
        ),
        "val_head3_unknown_recall": calibration["heads"]["head3_phylum"][
            "open_set"
        ]["validation_unknown_recall"],
        "val_head3_ood_auroc": calibration["heads"]["head3_phylum"]["open_set"][
            "validation_ood_auroc"
        ],
        # Keep the selected-candidate evidence schema consumed by the one-shot
        # Test lock stable.  Fold artifacts have dedicated, independently
        # validated fields above and are also bound by the comparison JSON hash.
        "input_sha256": {
            name: _sha256(path)
            for name, path in required.items()
            if name in SELECTED_INPUT_NAMES
        },
        "embedding_artifact_sha256": embedding_artifact_sha256,
        "model_sha256": model_sha256,
    }
    return row, fold_rows


def _apply_development_selection(
    rows: list[dict[str, Any]], *, baseline_model_id: str = "esm2_650m"
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Apply gates and paired one-SE selection to complete development rows."""

    baselines = [row for row in rows if row["model_id"] == baseline_model_id]
    if len(baselines) != 1:
        raise RuntimeError(f"Benchmark requires exactly one {baseline_model_id} baseline")
    baseline = baselines[0]
    for row in rows:
        deltas = {
            "head1": row["val_head1_average_precision"]
            - baseline["val_head1_average_precision"],
            "head2": row["val_head2_macro_f1"] - baseline["val_head2_macro_f1"],
            "head3": row["val_head3_macro_f1"] - baseline["val_head3_macro_f1"],
        }
        failures = [head for head, delta in deltas.items() if delta < -GATE_TOLERANCE]
        row["validation_delta_vs_esm2_650m"] = deltas
        row["validation_gate_failures"] = failures
        row["selectable"] = not failures

    raw_ranked = sorted(rows, key=lambda row: (-row["composite_score"], row["model_id"]))
    for rank, row in enumerate(raw_ranked, start=1):
        row["raw_cv_rank"] = rank
    eligible = [row for row in rows if row["selectable"]]
    if not eligible:
        raise RuntimeError("No selectable benchmark candidate")
    highest_selectable = sorted(
        eligible, key=lambda row: (-row["composite_score"], row["model_id"])
    )[0]
    best_folds = [float(value) for value in highest_selectable["composite_fold_scores"]]
    if len(best_folds) < 2:
        raise RuntimeError("Paired one-SE selection requires at least two shared folds")

    tied: list[dict[str, Any]] = []
    for row in rows:
        candidate_folds = [float(value) for value in row["composite_fold_scores"]]
        if len(candidate_folds) != len(best_folds):
            raise RuntimeError(f"Composite fold-count mismatch for {row['model_id']}")
        paired_deltas = [
            best_score - candidate_score
            for best_score, candidate_score in zip(best_folds, candidate_folds)
        ]
        paired_delta_mean = _mean(paired_deltas)
        score_difference = highest_selectable["composite_score"] - row["composite_score"]
        if not math.isclose(
            paired_delta_mean, score_difference, rel_tol=0.0, abs_tol=1e-12
        ):
            raise RuntimeError(f"Paired fold delta mean is inconsistent for {row['model_id']}")
        paired_delta_se = _se(paired_deltas)
        row["one_se_reference_model_id"] = highest_selectable["model_id"]
        row["difference_from_best_selectable_cv"] = score_difference
        row["paired_fold_deltas_vs_best_selectable_cv"] = paired_deltas
        row["paired_delta_se_vs_best_selectable_cv"] = paired_delta_se
        row["within_one_paired_se"] = bool(
            row["selectable"] and score_difference <= paired_delta_se + 1e-15
        )
        if row["within_one_paired_se"]:
            tied.append(row)

    # Apply the preregistered criteria in stages.  Speed is not assigned an
    # unconditional numeric key: it is used only within a same-FPR group whose
    # complete timing-comparability evidence is identical.
    fpr_groups: dict[float, list[dict[str, Any]]] = {}
    for row in tied:
        fpr = row["val_head1_fpr_at_95pct_recall"]
        fpr_key = math.inf if fpr is None else float(fpr)
        fpr_groups.setdefault(fpr_key, []).append(row)
    ordered_tied: list[dict[str, Any]] = []
    for fpr_key in sorted(fpr_groups):
        group = fpr_groups[fpr_key]
        comparable_speed = bool(
            len(group) > 1
            and all(row.get("speed_tie_break_eligible") is True for row in group)
            and len(
                {
                    json.dumps(
                        row.get("timing_comparability_key"),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    for row in group
                }
            )
            == 1
        )
        if comparable_speed:
            group.sort(
                key=lambda row: (
                    float(row["gpu_seconds_per_sequence"]),
                    0 if row["permissive_license"] else 1,
                    -row["composite_score"],
                    row["model_id"],
                )
            )
            for row in group:
                row["speed_tie_break_status"] = "used_comparable_same_fpr_group"
        else:
            group.sort(
                key=lambda row: (
                    0 if row["permissive_license"] else 1,
                    -row["composite_score"],
                    row["model_id"],
                )
            )
            status = (
                "not_invoked_single_model_after_fpr"
                if len(group) == 1
                else "skipped_incomparable_same_fpr_group"
            )
            for row in group:
                row["speed_tie_break_status"] = status
        ordered_tied.extend(group)
    tied[:] = ordered_tied
    for rank, row in enumerate(tied, start=1):
        row["tie_break_rank"] = rank
    selected = tied[0]
    for row in rows:
        row["selected"] = row is selected
    return raw_ranked, highest_selectable, selected


def _write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument(
        "--output-dir", default=Path("results/model_benchmark_v0"), type=Path
    )
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    manifest_path = Path(config["paths"]["v0_manifest"])
    current_manifest_sha256 = _sha256(manifest_path)
    cv_fold_contract, _ = load_frozen_cv_fold_map(config, manifest_path)
    rows: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    for model_id, spec in config["benchmark"]["models"].items():
        row, folds = _development_row(
            model_id, spec, current_manifest_sha256, cv_fold_contract, config
        )
        rows.append(row)
        fold_rows.extend(folds)

    pending = [row["model_id"] for row in rows if row["status"] != "complete"]
    if pending and not args.allow_incomplete:
        raise RuntimeError(f"Incomplete benchmark candidates: {pending}")
    complete = [row for row in rows if row["status"] == "complete"]
    raw_ranked, highest_selectable, selected = _apply_development_selection(complete)

    fields = [
        "model_id", "label", "status", "selectable", "selected", "raw_cv_rank",
        "within_one_paired_se", "tie_break_rank", "composite_score", "composite_se",
        "composite_se_method", "paired_fold_deltas_vs_best_selectable_cv",
        "difference_from_best_selectable_cv", "paired_delta_se_vs_best_selectable_cv",
        "one_se_reference_model_id", "cv_fold_map_sha256", "cv_fold_metadata_sha256",
        "cv_head1_average_precision", "cv_head1_se", "cv_head2_average_precision",
        "cv_head2_se", "cv_head3_macro_f1", "cv_head3_se",
        "val_head1_average_precision", "val_head1_fpr_at_95pct_recall", "val_head1_mcc",
        "val_head2_macro_f1", "val_head2_balanced_accuracy", "val_head3_macro_f1",
        "val_head3_balanced_accuracy", "val_head3_ece", "val_head3_brier",
        "val_head3_unknown_diagnostic_n", "val_head3_unknown_recall",
        "val_head3_ood_auroc",
        "embedding_dimension", "parameter_count", "embedding_seconds",
        "parameter_count_source", "embedding_timing_source", "gpu_seconds_per_sequence",
        "speed_tie_break_eligible", "speed_tie_break_status", "timing_comparability_key",
        "peak_gpu_memory_bytes", "license",
        "pretraining_overlap_risk", "source_kind", "resolved_model_revision",
        "test_status", "validation_gate_failures",
    ]
    _write_tsv(args.output_dir / "model_comparison.tsv", rows, fields)
    _write_tsv(
        args.output_dir / "fold_scores.tsv",
        fold_rows,
        [
            "model_id", "label", "head", "metric", "fold", "score",
            "selected_parameter", "composite_fold_score", "fold_map_sha256",
        ],
    )
    summary = {
        # Schema 4 attests the corrected raw-score ranking lineage.  Legacy
        # comparisons remain schema 3 and are never overwritten by this run.
        "schema_version": 4 if config.get("project", {}).get("metric_revision_id") else 3,
        "metric_revision_id": config.get("project", {}).get("metric_revision_id"),
        "binary_ranking_score_source": (
            "raw_decision_function"
            if config.get("project", {}).get("metric_revision_id")
            else "legacy_calibrated_probability"
        ),
        "benchmark_version": config["project"]["version"],
        "selection_boundary": "Train component-aware CV plus Validation only",
        "test_policy": (
            "No candidate Test results were read or generated. Metric Revision 1 keeps "
            "the newly selected model Test closed; the previously opened project-V0 "
            "cohort is used only for explicitly post-hoc, same-model historical numeric "
            "reanalysis and never for selection."
            if config.get("project", {}).get("test_evaluation_permitted") is False
            else (
                "No candidate Test results were read or generated. The selected model may "
                "be evaluated once only after this comparison is frozen."
            )
        ),
        "weights": WEIGHTS,
        "cv_fold_contract": cv_fold_contract,
        "score_definition": (
            "S = 0.60 * CV Head1 AP + 0.30 * CV Head2 AP + "
            "0.10 * CV Head3 two-known-class macro-F1"
        ),
        "manifest_sha256": current_manifest_sha256,
        "config_path": str(args.config),
        "config_sha256": _sha256(args.config),
        "benchmark_config_path": str(args.config),
        "benchmark_config_sha256": _sha256(args.config),
        "candidate_model_ids": list(config["benchmark"]["models"]),
        "complete_model_count": len(complete),
        "validation_regression_tolerance": GATE_TOLERANCE,
        "tie_rule": PAIRED_TIE_RULE,
        "tie_break_order": TIE_BREAK_ORDER,
        "speed_tie_break_policy": SPEED_TIE_BREAK_POLICY,
        "uncertainty": (
            "Per-head SE is the sample SD of five selected-hyperparameter fold scores divided "
            "by sqrt(5). Each fold composite is first computed as 0.60*H1 + 0.30*H2 + "
            "0.10*H3 on the one shared global-component fold map; displayed composite SE is "
            "the SE of those five composite scores. The one-SE candidate set uses the SE of "
            "paired same-fold deltas versus the highest-selectable CV model, without "
            "independence propagation across heads or models."
        ),
        "timing_note": (
            "Per-sequence timing is accumulated embedding inference time excluding model load "
            "divided by record count. Timestamp wall time is never substituted. Comparability "
            "and whether speed was invoked are recorded per candidate."
        ),
        "pending_models": pending,
        "selected_model_id": selected["model_id"],
        "selected_model_label": selected["label"],
        "raw_cv_best_model_id": raw_ranked[0]["model_id"],
        "highest_selectable_cv_model_id": highest_selectable["model_id"],
        "models": rows,
        "candidate_artifact_hashes": {
            row["model_id"]: {
                "input_sha256": row["input_sha256"],
                "embedding_artifact_sha256": row["embedding_artifact_sha256"],
                "model_sha256": row["model_sha256"],
            }
            for row in complete
        },
    }
    json_path = args.output_dir / "model_comparison.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksums = args.output_dir / "COMPARISON_CHECKSUMS.sha256"
    outputs = [
        args.output_dir / "model_comparison.tsv",
        args.output_dir / "fold_scores.tsv",
        json_path,
    ]
    checksums.write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in outputs), encoding="utf-8"
    )
    print(json.dumps({
        "selected_model_id": selected["model_id"],
        "raw_cv_best_model_id": raw_ranked[0]["model_id"],
        "highest_selectable_cv_model_id": highest_selectable["model_id"],
        "complete": len(complete),
        "pending": pending,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
