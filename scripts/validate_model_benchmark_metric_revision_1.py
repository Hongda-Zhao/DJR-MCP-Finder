#!/usr/bin/env python3
"""Independently validate the metric-revision-1 development benchmark.

This validator is intentionally development-only.  It opens only the revision
configuration, calibration/CV/Validation JSON files, and the four comparison
bundle files.  Test-like paths are rejected before any file content is read;
the result tree is inspected only by filename to attest that no Test artifact
exists.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import os
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


MODEL_IDS = (
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
HEADS = ("head1", "head2", "head3_phylum")
WEIGHTS = {"head1": 0.60, "head2": 0.30, "head3_phylum": 0.10}
BASELINE_MODEL_ID = "esm2_650m"
REVISION_ID = "raw-score-stable-calibration-v1"
RANKING_SOURCE = "raw_decision_function"
R1_TEST_POLICY = (
    "No candidate Test results were read or generated. Metric Revision 1 keeps "
    "the newly selected model Test closed; the previously opened project-V0 "
    "cohort is used only for explicitly post-hoc, same-model historical numeric "
    "reanalysis and never for selection."
)
VALIDATION_TOLERANCE = 0.01
PERMISSIVE_LICENSES = {"MIT", "Apache-2.0", "BSD-3-Clause"}
COMPARISON_FILES = {
    "model_comparison.json",
    "model_comparison.tsv",
    "fold_scores.tsv",
}
COMPARISON_CHECKSUM = "COMPARISON_CHECKSUMS.sha256"
FORBIDDEN_TEST_ARTIFACTS = {
    "FINAL_TEST_EVALUATED.json",
    "TEST_EVALUATION_RESERVED.json",
    "TEST_SELECTION_AUTHORIZATION.json",
    "TEST_EVALUATION_RECEIPT.json",
    "frozen_test_metrics.json",
    "frozen_test_predictions.tsv",
}
_TEST_TOKEN = re.compile(r"(^|[^a-z0-9])test([^a-z0-9]|$)", flags=re.IGNORECASE)
_ABS_TOL = 1e-12


def _guard_development_input(path: Path) -> None:
    """Reject a Test-like input name before its content can be accessed."""

    if path.name in FORBIDDEN_TEST_ARTIFACTS or _TEST_TOKEN.search(path.name):
        raise RuntimeError(f"Refusing to read Test-like input: {path}")


def _read_text(path: Path) -> str:
    _guard_development_input(path)
    if path.is_symlink():
        raise RuntimeError(f"Input artifacts must not be symlinks: {path}")
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(_read_text(path))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    _guard_development_input(path)
    if path.is_symlink():
        raise RuntimeError(f"Input artifacts must not be symlinks: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_config(path: Path, stack: tuple[Path, ...] = ()) -> dict[str, Any]:
    """Load the pinned overlay without relying on production config code."""

    try:
        import yaml
    except ModuleNotFoundError as error:  # pragma: no cover - packaging failure
        raise RuntimeError("PyYAML is required") from error
    resolved = path.resolve()
    if resolved in stack:
        raise RuntimeError(f"Configuration extension cycle: {resolved}")
    value = yaml.safe_load(_read_text(resolved))
    if not isinstance(value, dict):
        raise RuntimeError(f"Configuration is not a mapping: {resolved}")
    extends = value.pop("extends", None)
    expected_sha256 = value.pop("extends_sha256", None)
    if extends is None:
        return value
    base_path = (resolved.parent / str(extends)).resolve()
    if expected_sha256 is None or _sha256(base_path) != str(expected_sha256):
        raise RuntimeError("Pinned base-configuration SHA-256 mismatch")
    merged = _deep_merge(_load_config(base_path, stack + (resolved,)), value)
    merged["config_lineage"] = {
        "overlay_path": str(resolved),
        "base_path": str(base_path),
        "base_sha256": _sha256(base_path),
    }
    return merged


def _mean(values: Iterable[float]) -> float:
    collected = [float(value) for value in values]
    if not collected:
        raise RuntimeError("Cannot compute an empty mean")
    return float(sum(collected) / len(collected))


def _se(values: Iterable[float]) -> float:
    collected = [float(value) for value in values]
    if len(collected) < 2:
        return 0.0
    return float(statistics.stdev(collected) / math.sqrt(len(collected)))


def _finite_float(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"{label} is not numeric: {value!r}") from error
    if not math.isfinite(result):
        raise RuntimeError(f"{label} is not finite")
    return result


def _close(observed: Any, expected: Any, label: str, tolerance: float = _ABS_TOL) -> None:
    observed_value = _finite_float(observed, label)
    expected_value = _finite_float(expected, label)
    if not math.isclose(observed_value, expected_value, rel_tol=0.0, abs_tol=tolerance):
        raise RuntimeError(
            f"{label} mismatch: observed={observed_value}, expected={expected_value}"
        )


def _resolve(project_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return (path if path.is_absolute() else project_root / path).resolve()


def _scan_forbidden_test_artifacts(result_root: Path) -> None:
    """Inspect names only; never open a forbidden artifact."""

    found: list[str] = []
    for candidate in result_root.rglob("*"):
        relative = candidate.relative_to(result_root)
        if candidate.is_symlink():
            raise RuntimeError(f"Revision result tree must not contain symlinks: {relative}")
        if any(
            part in FORBIDDEN_TEST_ARTIFACTS or _TEST_TOKEN.search(part)
            for part in relative.parts
        ):
            found.append(str(relative))
    if found:
        raise RuntimeError(
            "Metric-revision result tree contains forbidden Test-like artifacts: "
            + ", ".join(sorted(found))
        )


def _verify_comparison_checksums(comparison_dir: Path) -> dict[str, str]:
    checksum_path = comparison_dir / COMPARISON_CHECKSUM
    observed: dict[str, str] = {}
    for line_number, raw in enumerate(_read_text(checksum_path).splitlines(), start=1):
        if not raw.strip():
            continue
        parts = raw.split(maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError(f"Malformed checksum line {line_number}: {checksum_path}")
        digest, relative = parts[0], parts[1].strip().lstrip("*")
        if (
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or Path(relative).is_absolute()
            or len(Path(relative).parts) != 1
            or relative in observed
        ):
            raise RuntimeError(f"Unsafe checksum entry at {checksum_path}:{line_number}")
        target = comparison_dir / relative
        if not target.is_file() or _sha256(target) != digest:
            raise RuntimeError(f"Comparison checksum mismatch: {target}")
        observed[relative] = digest
    if set(observed) != COMPARISON_FILES:
        raise RuntimeError(
            f"Comparison checksum coverage mismatch: {sorted(observed)}"
        )
    return observed


def _read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    lines = _read_text(path).splitlines()
    if not lines:
        raise RuntimeError(f"Empty TSV: {path}")
    reader = csv.DictReader(lines, delimiter="\t")
    if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise RuntimeError(f"Malformed or duplicate TSV header: {path}")
    return list(reader.fieldnames), list(reader)


def _require_keys(value: dict[str, Any], keys: Iterable[str], label: str) -> None:
    missing = sorted(set(keys) - set(value))
    if missing:
        raise RuntimeError(f"{label} lacks required keys: {missing}")


def _validate_config(config: dict[str, Any]) -> None:
    _require_keys(config, ("project", "paths", "classifier", "benchmark"), "config")
    project = config["project"]
    classifier = config["classifier"]
    if project.get("metric_revision_id") != REVISION_ID:
        raise RuntimeError("Not the frozen metric-revision-1 overlay")
    if project.get("test_evaluation_permitted") is not False:
        raise RuntimeError("Metric revision must explicitly prohibit Test evaluation")
    if classifier.get("binary_ranking_score") != RANKING_SOURCE:
        raise RuntimeError("Binary ranking source is not raw_decision_function")
    expected_temperature = {
        "temperature_objective": "stable_label_smoothed_logit_nll",
        "temperature_label_smoothing": 0.001,
        "temperature_boundary_policy": "fail",
        "temperature_log10_min": -6.0,
        "temperature_log10_max": 6.0,
        "temperature_coarse_points": 481,
        "temperature_fine_points": 401,
    }
    for key, expected in expected_temperature.items():
        if classifier.get(key) != expected:
            raise RuntimeError(f"Unfrozen classifier setting {key}: {classifier.get(key)!r}")
    models = config["benchmark"].get("models")
    if not isinstance(models, dict) or tuple(models) != MODEL_IDS:
        raise RuntimeError("Revision validator requires the exact ordered 14-model registry")


def _expected_temperature_contract(config: dict[str, Any]) -> dict[str, Any]:
    settings = config["classifier"]
    return {
        "log10_min": float(settings["temperature_log10_min"]),
        "log10_max": float(settings["temperature_log10_max"]),
        "coarse_points": int(settings["temperature_coarse_points"]),
        "fine_points": int(settings["temperature_fine_points"]),
        "boundary_policy": settings["temperature_boundary_policy"],
        "objective": settings["temperature_objective"],
        "label_smoothing": float(settings["temperature_label_smoothing"]),
    }


def _validate_temperature_contract(
    observed: Any, expected: dict[str, Any], label: str
) -> None:
    if not isinstance(observed, dict):
        raise RuntimeError(f"{label} lacks temperature-search diagnostics")
    for key, expected_value in expected.items():
        if isinstance(expected_value, float):
            _close(observed.get(key), expected_value, f"{label}/{key}")
        elif observed.get(key) != expected_value:
            raise RuntimeError(f"{label}/{key} differs from the frozen contract")
    if observed.get("coarse_boundary_hit") is not False:
        raise RuntimeError(f"{label} hit the global temperature-search boundary")
    if not isinstance(observed.get("coarse_best_index"), int) or not isinstance(
        observed.get("fine_best_index"), int
    ):
        raise RuntimeError(f"{label} lacks temperature-search indices")


def _validate_model_artifacts(
    *,
    model_id: str,
    model_spec: dict[str, Any],
    row: dict[str, Any],
    result_dir: Path,
    summary: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    artifacts = {
        "calibration": result_dir / "calibration.json",
        "cross_validation": result_dir / "metrics" / "cross_validation.json",
        "validation": result_dir / "metrics" / "validation_metrics.json",
    }
    for name, path in artifacts.items():
        if not path.is_file():
            raise FileNotFoundError(f"Missing {model_id} {name}: {path}")
    recorded_hashes = row.get("input_sha256")
    if not isinstance(recorded_hashes, dict):
        raise RuntimeError(f"{model_id} comparison row lacks input_sha256")
    artifact_sha256: dict[str, str] = {}
    for name, path in artifacts.items():
        artifact_sha256[name] = _sha256(path)
        if recorded_hashes.get(name) != artifact_sha256[name]:
            raise RuntimeError(f"{model_id}/{name} input SHA-256 mismatch")
    candidate_hashes = summary.get("candidate_artifact_hashes", {}).get(model_id)
    if not isinstance(candidate_hashes, dict) or candidate_hashes.get(
        "input_sha256"
    ) != recorded_hashes:
        raise RuntimeError(f"{model_id} candidate hash ledger differs from its row")
    if candidate_hashes.get("embedding_artifact_sha256") != row.get(
        "embedding_artifact_sha256"
    ) or candidate_hashes.get("model_sha256") != row.get("model_sha256"):
        raise RuntimeError(f"{model_id} candidate checksum ledgers are inconsistent")

    calibration = _read_json(artifacts["calibration"])
    cv = _read_json(artifacts["cross_validation"])
    validation = _read_json(artifacts["validation"])
    if calibration.get("schema_version") != 4:
        raise RuntimeError(f"{model_id} calibration schema is not 4")
    if cv.get("schema_version") != 3:
        raise RuntimeError(f"{model_id} CV schema is not 3")
    if calibration.get("binary_ranking_score_source") != RANKING_SOURCE or cv.get(
        "binary_ranking_score_source"
    ) != RANKING_SOURCE:
        raise RuntimeError(f"{model_id} lacks corrected raw-score lineage")
    if calibration.get("test_evaluated") is not False:
        raise RuntimeError(f"{model_id} calibration is not development-only")
    if calibration.get("manifest_sha256") != summary.get("manifest_sha256"):
        raise RuntimeError(f"{model_id} manifest lineage mismatch")
    if calibration.get("cv_fold_contract") != summary.get("cv_fold_contract") or cv.get(
        "cv_fold_contract"
    ) != summary.get("cv_fold_contract"):
        raise RuntimeError(f"{model_id} frozen-fold lineage mismatch")
    if set(calibration.get("heads", {})) != set(HEADS) or set(cv.get("heads", {})) != set(
        HEADS
    ) or set(validation.get("heads", {})) != set(HEADS):
        raise RuntimeError(f"{model_id} does not contain exactly the three frozen heads")

    expected_temperature = _expected_temperature_contract(config)
    fold_count = int(config["classifier"]["cross_validation_folds"])
    expected_fold_ids = list(range(1, fold_count + 1))
    head_scores: dict[str, list[float]] = {}
    head_means: dict[str, float] = {}
    head_ses: dict[str, float] = {}
    selected_parameters: dict[str, float] = {}
    for head in HEADS:
        calibration_head = calibration["heads"][head]
        report = cv["heads"][head]
        metric = "macro_f1" if head == "head3_phylum" else "average_precision"
        metric_input = (
            "uncalibrated_probabilities"
            if head == "head3_phylum"
            else RANKING_SOURCE
        )
        if report.get("primary_metric") != metric or report.get(
            "primary_metric_input"
        ) != metric_input:
            raise RuntimeError(f"{model_id}/{head} CV metric lineage mismatch")
        if report.get("splitter") != "FrozenGlobalComponentFoldMap":
            raise RuntimeError(f"{model_id}/{head} did not use the frozen fold map")
        if report.get("folds") != fold_count or report.get("fold_ids") != expected_fold_ids:
            raise RuntimeError(f"{model_id}/{head} fold identities mismatch")
        candidates = report.get("candidates_ranked")
        if not isinstance(candidates, list) or not candidates:
            raise RuntimeError(f"{model_id}/{head} has no CV candidates")
        independently_ranked: list[tuple[float, float, dict[str, Any]]] = []
        for candidate in candidates:
            scores = [
                _finite_float(score, f"{model_id}/{head} fold score")
                for score in candidate.get("fold_scores", [])
            ]
            if len(scores) != fold_count or any(score < 0.0 or score > 1.0 for score in scores):
                raise RuntimeError(f"{model_id}/{head} has invalid CV fold scores")
            mean_score = _mean(scores)
            _close(candidate.get("mean_score"), mean_score, f"{model_id}/{head} candidate mean")
            population_sd = float(statistics.pstdev(scores))
            _close(
                candidate.get("standard_deviation"),
                population_sd,
                f"{model_id}/{head} candidate population SD",
            )
            parameter = _finite_float(candidate.get("parameter"), f"{model_id}/{head} parameter")
            independently_ranked.append((-mean_score, parameter, candidate))
        expected_order = [
            item[2]
            for item in sorted(
                independently_ranked, key=lambda item: (item[0], item[1])
            )
        ]
        if candidates != expected_order:
            raise RuntimeError(f"{model_id}/{head} candidates are not deterministically ranked")
        best = candidates[0]
        selected_parameter = _finite_float(best["parameter"], f"{model_id}/{head} best parameter")
        _close(
            calibration_head.get("best_parameter"),
            selected_parameter,
            f"{model_id}/{head} calibration parameter",
        )
        _validate_temperature_contract(
            calibration_head.get("temperature_search"),
            expected_temperature,
            f"{model_id}/{head}",
        )
        temperature = _finite_float(
            calibration_head.get("temperature"), f"{model_id}/{head} temperature"
        )
        if not (
            10.0 ** expected_temperature["log10_min"]
            < temperature
            < 10.0 ** expected_temperature["log10_max"]
        ):
            raise RuntimeError(f"{model_id}/{head} temperature lies on/outside global bounds")
        scores = [float(value) for value in best["fold_scores"]]
        head_scores[head] = scores
        head_means[head] = _mean(scores)
        head_ses[head] = _se(scores)
        selected_parameters[head] = selected_parameter

    for head in ("head1", "head2"):
        if validation["heads"][head].get("ranking_score_source") != RANKING_SOURCE:
            raise RuntimeError(f"{model_id}/{head} Validation lacks raw-score lineage")
    composite_folds = [
        sum(WEIGHTS[head] * head_scores[head][fold] for head in HEADS)
        for fold in range(fold_count)
    ]
    validation_h1 = validation["heads"]["head1"]
    validation_h2 = validation["heads"]["head2"]
    validation_h3 = validation["heads"]["head3_phylum"]
    validation_values = {
        "head1": _finite_float(
            validation_h1.get("average_precision"), f"{model_id}/Validation H1 AP"
        ),
        "head2": _mean(
            _finite_float(value, f"{model_id}/Validation H2 F1")
            for value in validation_h2.get("f1_by_class", [])
        ),
        "head3": _finite_float(
            validation_h3.get("macro_f1_unknown_as_error"),
            f"{model_id}/Validation H3 macro-F1",
        ),
    }
    if len(validation_h2.get("f1_by_class", [])) != 2:
        raise RuntimeError(f"{model_id}/Validation H2 must contain two class F1 values")
    open_set = calibration["heads"]["head3_phylum"].get("open_set")
    if not isinstance(open_set, dict):
        raise RuntimeError(f"{model_id}/H3 lacks the Validation unknown diagnostic")

    expected_row_values = {
        "cv_head1_average_precision": head_means["head1"],
        "cv_head1_se": head_ses["head1"],
        "cv_head2_average_precision": head_means["head2"],
        "cv_head2_se": head_ses["head2"],
        "cv_head3_macro_f1": head_means["head3_phylum"],
        "cv_head3_se": head_ses["head3_phylum"],
        "composite_score": _mean(composite_folds),
        "composite_se": _se(composite_folds),
        "val_head1_average_precision": validation_values["head1"],
        "val_head2_macro_f1": validation_values["head2"],
        "val_head3_macro_f1": validation_values["head3"],
    }
    for field, expected in expected_row_values.items():
        _close(row.get(field), expected, f"{model_id}/{field}")
    recorded_folds = row.get("composite_fold_scores")
    if not isinstance(recorded_folds, list) or len(recorded_folds) != fold_count:
        raise RuntimeError(f"{model_id} comparison has invalid composite folds")
    for fold, expected in enumerate(composite_folds, start=1):
        _close(recorded_folds[fold - 1], expected, f"{model_id}/composite fold {fold}")
    if row.get("composite_se_method") != "sd_of_five_shared_fold_composites_div_sqrt5":
        raise RuntimeError(f"{model_id} composite SE method mismatch")
    if row.get("cv_fold_map_sha256") != summary["cv_fold_contract"].get(
        "fold_map_sha256"
    ) or row.get("cv_fold_metadata_sha256") != summary["cv_fold_contract"].get(
        "fold_metadata_sha256"
    ):
        raise RuntimeError(f"{model_id} comparison-row fold lineage mismatch")
    if row.get("temperature_search_contract") != calibration["heads"]["head1"].get(
        "temperature_search"
    ):
        raise RuntimeError(f"{model_id} comparison-row temperature contract mismatch")
    if row.get("label") != model_spec.get("label"):
        raise RuntimeError(f"{model_id} label differs from config")
    if row.get("license") != model_spec.get("license"):
        raise RuntimeError(f"{model_id} license differs from config")
    if row.get("permissive_license") is not (
        model_spec.get("license") in PERMISSIVE_LICENSES
    ):
        raise RuntimeError(f"{model_id} permissive-license flag mismatch")
    raw_validation_fpr = validation_h1.get("fpr_at_95pct_recall")
    validation_fpr = (
        None
        if raw_validation_fpr is None
        else _finite_float(raw_validation_fpr, f"{model_id}/Validation H1 FPR@95% recall")
    )
    recorded_fpr = row.get("val_head1_fpr_at_95pct_recall")
    if validation_fpr is None:
        if recorded_fpr is not None:
            raise RuntimeError(f"{model_id}/Validation H1 FPR null-state mismatch")
    else:
        _close(recorded_fpr, validation_fpr, f"{model_id}/Validation H1 FPR@95% recall")
    return {
        "model_id": model_id,
        "label": row["label"],
        "head_fold_scores": head_scores,
        "head_means": head_means,
        "head_ses": head_ses,
        "selected_parameters": selected_parameters,
        "composite_fold_scores": composite_folds,
        "composite_score": expected_row_values["composite_score"],
        "composite_se": expected_row_values["composite_se"],
        "validation": validation_values,
        "validation_h1_fpr_at_95pct_recall": validation_fpr,
        "artifact_sha256": artifact_sha256,
    }


def _compute_selection(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Recompute gating, paired one-SE membership, and staged tie-breaking."""

    by_id = {row["model_id"]: row for row in rows}
    if len(by_id) != len(rows) or BASELINE_MODEL_ID not in by_id:
        raise RuntimeError("Selection rows are duplicated or lack the baseline")
    baseline = by_id[BASELINE_MODEL_ID]
    computed: dict[str, dict[str, Any]] = {}
    for row in rows:
        deltas = {
            head: float(row["validation"][head]) - float(baseline["validation"][head])
            for head in ("head1", "head2", "head3")
        }
        failures = [
            head
            for head in ("head1", "head2", "head3")
            if deltas[head] < -VALIDATION_TOLERANCE
        ]
        computed[row["model_id"]] = {
            "validation_delta_vs_esm2_650m": deltas,
            "validation_gate_failures": failures,
            "selectable": not failures,
        }
    raw_ranked = sorted(rows, key=lambda row: (-float(row["composite_score"]), row["model_id"]))
    selectable = [row for row in raw_ranked if computed[row["model_id"]]["selectable"]]
    if not selectable:
        raise RuntimeError("No model passes the Validation regression gate")
    reference = selectable[0]
    reference_folds = [float(value) for value in reference["composite_fold_scores"]]
    one_se: list[dict[str, Any]] = []
    for raw_rank, row in enumerate(raw_ranked, start=1):
        model_id = row["model_id"]
        candidate_folds = [float(value) for value in row["composite_fold_scores"]]
        if len(candidate_folds) != len(reference_folds):
            raise RuntimeError(f"{model_id} paired fold count mismatch")
        paired_deltas = [
            best - candidate
            for best, candidate in zip(reference_folds, candidate_folds)
        ]
        difference = float(reference["composite_score"]) - float(row["composite_score"])
        _close(_mean(paired_deltas), difference, f"{model_id}/paired delta mean")
        paired_se = _se(paired_deltas)
        within = bool(
            computed[model_id]["selectable"] and difference <= paired_se + 1e-15
        )
        computed[model_id].update(
            {
                "raw_cv_rank": raw_rank,
                "one_se_reference_model_id": reference["model_id"],
                "difference_from_best_selectable_cv": difference,
                "paired_fold_deltas_vs_best_selectable_cv": paired_deltas,
                "paired_delta_se_vs_best_selectable_cv": paired_se,
                "within_one_paired_se": within,
            }
        )
        if within:
            one_se.append(row)

    fpr_groups: dict[float, list[dict[str, Any]]] = {}
    for row in one_se:
        raw_fpr = row.get("validation_h1_fpr_at_95pct_recall")
        fpr = math.inf if raw_fpr is None else _finite_float(raw_fpr, f"{row['model_id']}/FPR")
        fpr_groups.setdefault(fpr, []).append(row)
    tie_order: list[dict[str, Any]] = []
    for fpr in sorted(fpr_groups):
        group = fpr_groups[fpr]
        comparable = bool(
            len(group) > 1
            and all(row.get("speed_tie_break_eligible") is True for row in group)
            and all(
                row.get("gpu_seconds_per_sequence") is not None
                and _finite_float(
                    row["gpu_seconds_per_sequence"], f"{row['model_id']}/speed"
                )
                > 0.0
                for row in group
            )
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
        if comparable:
            group.sort(
                key=lambda row: (
                    float(row["gpu_seconds_per_sequence"]),
                    0 if row["permissive_license"] else 1,
                    -float(row["composite_score"]),
                    row["model_id"],
                )
            )
            status = "used_comparable_same_fpr_group"
        else:
            group.sort(
                key=lambda row: (
                    0 if row["permissive_license"] else 1,
                    -float(row["composite_score"]),
                    row["model_id"],
                )
            )
            status = (
                "not_invoked_single_model_after_fpr"
                if len(group) == 1
                else "skipped_incomparable_same_fpr_group"
            )
        for row in group:
            computed[row["model_id"]]["speed_tie_break_status"] = status
        tie_order.extend(group)
    for rank, row in enumerate(tie_order, start=1):
        computed[row["model_id"]]["tie_break_rank"] = rank
    return {
        "raw_cv_best_model_id": raw_ranked[0]["model_id"],
        "highest_selectable_cv_model_id": reference["model_id"],
        "selected_model_id": tie_order[0]["model_id"],
        "one_se_model_ids": [row["model_id"] for row in tie_order],
        "models": computed,
    }


def _validate_recorded_selection(
    summary_rows: list[dict[str, Any]], selection: dict[str, Any], summary: dict[str, Any]
) -> None:
    by_id = {row["model_id"]: row for row in summary_rows}
    for field in (
        "selected_model_id",
        "raw_cv_best_model_id",
        "highest_selectable_cv_model_id",
    ):
        if summary.get(field) != selection[field]:
            raise RuntimeError(f"Comparison {field} differs from independent recomputation")
    selected_flags = [row["model_id"] for row in summary_rows if row.get("selected") is True]
    if selected_flags != [selection["selected_model_id"]]:
        raise RuntimeError("Comparison does not contain one matching selected flag")
    for model_id, expected in selection["models"].items():
        row = by_id[model_id]
        for field in (
            "selectable",
            "raw_cv_rank",
            "one_se_reference_model_id",
            "within_one_paired_se",
        ):
            if row.get(field) != expected[field]:
                raise RuntimeError(f"{model_id}/{field} differs from recomputation")
        for field in (
            "difference_from_best_selectable_cv",
            "paired_delta_se_vs_best_selectable_cv",
        ):
            _close(row.get(field), expected[field], f"{model_id}/{field}")
        observed_deltas = row.get("validation_delta_vs_esm2_650m")
        if not isinstance(observed_deltas, dict):
            raise RuntimeError(f"{model_id} lacks Validation deltas")
        for head, expected_delta in expected["validation_delta_vs_esm2_650m"].items():
            _close(observed_deltas.get(head), expected_delta, f"{model_id}/Validation delta {head}")
        if row.get("validation_gate_failures") != expected["validation_gate_failures"]:
            raise RuntimeError(f"{model_id} Validation gate failures differ")
        observed_paired = row.get("paired_fold_deltas_vs_best_selectable_cv")
        expected_paired = expected["paired_fold_deltas_vs_best_selectable_cv"]
        if not isinstance(observed_paired, list) or len(observed_paired) != len(expected_paired):
            raise RuntimeError(f"{model_id} paired fold deltas are malformed")
        for fold, expected_delta in enumerate(expected_paired, start=1):
            _close(observed_paired[fold - 1], expected_delta, f"{model_id}/paired fold {fold}")
        if expected["within_one_paired_se"]:
            if row.get("tie_break_rank") != expected.get("tie_break_rank") or row.get(
                "speed_tie_break_status"
            ) != expected.get("speed_tie_break_status"):
                raise RuntimeError(f"{model_id} tie-break evidence differs")
        elif row.get("tie_break_rank") is not None or row.get(
            "speed_tie_break_status"
        ) is not None:
            raise RuntimeError(f"{model_id} has tie-break evidence outside the one-SE set")


def _validate_model_comparison_tsv(
    path: Path, summary_rows: list[dict[str, Any]]
) -> None:
    fields, rows = _read_tsv(path)
    required = {
        "model_id",
        "label",
        "status",
        "selectable",
        "selected",
        "raw_cv_rank",
        "within_one_paired_se",
        "tie_break_rank",
        "composite_score",
        "composite_se",
        "difference_from_best_selectable_cv",
        "paired_delta_se_vs_best_selectable_cv",
        "paired_fold_deltas_vs_best_selectable_cv",
        "one_se_reference_model_id",
        "cv_head1_average_precision",
        "cv_head1_se",
        "cv_head2_average_precision",
        "cv_head2_se",
        "cv_head3_macro_f1",
        "cv_head3_se",
        "val_head1_average_precision",
        "val_head1_fpr_at_95pct_recall",
        "val_head2_macro_f1",
        "val_head3_macro_f1",
        "test_status",
        "validation_gate_failures",
    }
    if not required.issubset(fields):
        raise RuntimeError("model_comparison.tsv lacks required fields")
    if tuple(row["model_id"] for row in rows) != MODEL_IDS:
        raise RuntimeError("model_comparison.tsv model order/set mismatch")
    by_id = {row["model_id"]: row for row in summary_rows}
    numeric = required & {
        "raw_cv_rank",
        "composite_score",
        "composite_se",
        "cv_head1_average_precision",
        "cv_head1_se",
        "cv_head2_average_precision",
        "cv_head2_se",
        "cv_head3_macro_f1",
        "cv_head3_se",
        "val_head1_average_precision",
        "val_head2_macro_f1",
        "val_head3_macro_f1",
        "difference_from_best_selectable_cv",
        "paired_delta_se_vs_best_selectable_cv",
    }
    for tsv_row in rows:
        summary_row = by_id[tsv_row["model_id"]]
        for field in numeric:
            _close(tsv_row[field], summary_row[field], f"TSV {tsv_row['model_id']}/{field}")
        for field in ("label", "status", "test_status", "one_se_reference_model_id"):
            if tsv_row[field] != str(summary_row[field]):
                raise RuntimeError(f"TSV {tsv_row['model_id']}/{field} mismatch")
        for field in ("selectable", "selected", "within_one_paired_se"):
            if tsv_row[field] != str(summary_row[field]):
                raise RuntimeError(f"TSV {tsv_row['model_id']}/{field} mismatch")
        for field in ("tie_break_rank", "val_head1_fpr_at_95pct_recall"):
            observed = tsv_row[field]
            expected = summary_row.get(field)
            if expected is None:
                if observed != "":
                    raise RuntimeError(f"TSV {tsv_row['model_id']}/{field} null mismatch")
            else:
                _close(observed, expected, f"TSV {tsv_row['model_id']}/{field}")
        for field in (
            "paired_fold_deltas_vs_best_selectable_cv",
            "validation_gate_failures",
        ):
            try:
                observed = ast.literal_eval(tsv_row[field])
            except (SyntaxError, ValueError) as error:
                raise RuntimeError(
                    f"TSV {tsv_row['model_id']}/{field} is malformed"
                ) from error
            expected = summary_row[field]
            if field == "validation_gate_failures":
                if observed != expected:
                    raise RuntimeError(f"TSV {tsv_row['model_id']}/{field} mismatch")
            else:
                if not isinstance(observed, list) or len(observed) != len(expected):
                    raise RuntimeError(f"TSV {tsv_row['model_id']}/{field} mismatch")
                for fold, expected_delta in enumerate(expected, start=1):
                    _close(
                        observed[fold - 1],
                        expected_delta,
                        f"TSV {tsv_row['model_id']}/{field}/fold {fold}",
                    )


def _validate_fold_scores_tsv(
    path: Path,
    verified_models: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    fields, rows = _read_tsv(path)
    required = {
        "model_id",
        "label",
        "head",
        "metric",
        "fold",
        "score",
        "selected_parameter",
        "composite_fold_score",
        "fold_map_sha256",
    }
    if not required.issubset(fields):
        raise RuntimeError("fold_scores.tsv lacks required fields")
    folds = int(summary["cv_fold_contract"]["folds"])
    if len(rows) != len(MODEL_IDS) * len(HEADS) * folds:
        raise RuntimeError("fold_scores.tsv row count mismatch")
    by_id = {row["model_id"]: row for row in verified_models}
    seen: set[tuple[str, str, int]] = set()
    for row in rows:
        model_id = row["model_id"]
        head = row["head"]
        fold = int(row["fold"])
        key = (model_id, head, fold)
        if (
            model_id not in by_id
            or head not in HEADS
            or fold not in range(1, folds + 1)
            or key in seen
        ):
            raise RuntimeError(f"Invalid or duplicate fold_scores.tsv key: {key}")
        seen.add(key)
        verified = by_id[model_id]
        if row["label"] != verified["label"]:
            raise RuntimeError(f"fold_scores.tsv label mismatch: {key}")
        expected_metric = "macro_f1" if head == "head3_phylum" else "average_precision"
        if row["metric"] != expected_metric:
            raise RuntimeError(f"fold_scores.tsv metric mismatch: {key}")
        _close(row["score"], verified["head_fold_scores"][head][fold - 1], f"fold TSV score {key}")
        _close(
            row["selected_parameter"],
            verified["selected_parameters"][head],
            f"fold TSV parameter {key}",
        )
        _close(
            row["composite_fold_score"],
            verified["composite_fold_scores"][fold - 1],
            f"fold TSV composite {key}",
        )
        if row["fold_map_sha256"] != summary["cv_fold_contract"]["fold_map_sha256"]:
            raise RuntimeError(f"fold_scores.tsv fold-map lineage mismatch: {key}")


def _exclusive_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def validate(
    *, config_path: Path, comparison_dir: Path | None, project_root: Path | None
) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = _load_config(config_path)
    _validate_config(config)
    root = (project_root or config_path.parent.parent).resolve()
    configured_result_root = _resolve(root, config["paths"]["benchmark_result_root"])
    comparison_root = (comparison_dir or configured_result_root).resolve()
    if comparison_root != configured_result_root:
        raise RuntimeError("Comparison directory must be the configured revision result root")
    if comparison_root.is_symlink():
        raise RuntimeError("Revision result root must not be a symlink")
    _scan_forbidden_test_artifacts(comparison_root)
    comparison_hashes = _verify_comparison_checksums(comparison_root)
    summary_path = comparison_root / "model_comparison.json"
    summary = _read_json(summary_path)
    if summary.get("schema_version") != 4:
        raise RuntimeError("Metric-revision comparison schema is not 4")
    if summary.get("metric_revision_id") != REVISION_ID or summary.get(
        "binary_ranking_score_source"
    ) != RANKING_SOURCE:
        raise RuntimeError("Comparison lacks metric-revision-1 raw-score lineage")
    if summary.get("benchmark_config_sha256") != _sha256(config_path) or summary.get(
        "config_sha256"
    ) != _sha256(config_path):
        raise RuntimeError("Comparison/config SHA-256 mismatch")
    if summary.get("candidate_model_ids") != list(MODEL_IDS):
        raise RuntimeError("Comparison candidate order/set mismatch")
    if summary.get("complete_model_count") != len(MODEL_IDS) or summary.get(
        "pending_models"
    ) != []:
        raise RuntimeError("Comparison is incomplete")
    if summary.get("weights") != WEIGHTS:
        raise RuntimeError("Comparison score weights differ from 0.60/0.30/0.10")
    if summary.get("validation_regression_tolerance") != VALIDATION_TOLERANCE:
        raise RuntimeError("Comparison Validation gate tolerance differs from 0.01")
    if summary.get("test_policy") != R1_TEST_POLICY:
        raise RuntimeError("Comparison does not attest the frozen Metric-R1 Test policy")
    summary_rows = summary.get("models")
    if not isinstance(summary_rows, list) or len(summary_rows) != len(MODEL_IDS):
        raise RuntimeError("Comparison does not contain exactly 14 model rows")
    by_id = {row.get("model_id"): row for row in summary_rows if isinstance(row, dict)}
    if len(by_id) != len(MODEL_IDS) or set(by_id) != set(MODEL_IDS):
        raise RuntimeError("Comparison model rows are duplicated or incomplete")

    verified_models: list[dict[str, Any]] = []
    for model_id in MODEL_IDS:
        row = by_id[model_id]
        if row.get("status") != "complete" or row.get("test_status") != "not_evaluated":
            raise RuntimeError(f"{model_id} is incomplete or has a non-clean Test state")
        if row.get("metric_revision_id") != REVISION_ID or row.get(
            "binary_ranking_score_source"
        ) != RANKING_SOURCE:
            raise RuntimeError(f"{model_id} comparison row lacks revision lineage")
        unresolved_result_dir = comparison_root / model_id
        if unresolved_result_dir.is_symlink():
            raise RuntimeError(f"{model_id} result directory must not be a symlink")
        result_dir = unresolved_result_dir.resolve()
        if result_dir.parent != comparison_root or _resolve(
            root, row.get("result_dir", "")
        ) != result_dir:
            raise RuntimeError(f"{model_id} result path differs from the frozen revision root")
        verified = _validate_model_artifacts(
            model_id=model_id,
            model_spec=config["benchmark"]["models"][model_id],
            row=row,
            result_dir=result_dir,
            summary=summary,
            config=config,
        )
        verified.update(
            {
                "permissive_license": row["permissive_license"],
                "gpu_seconds_per_sequence": row.get("gpu_seconds_per_sequence"),
                "speed_tie_break_eligible": row.get("speed_tie_break_eligible"),
                "timing_comparability_key": row.get("timing_comparability_key"),
            }
        )
        verified_models.append(verified)

    selection = _compute_selection(verified_models)
    _validate_recorded_selection(summary_rows, selection, summary)
    _validate_model_comparison_tsv(
        comparison_root / "model_comparison.tsv", summary_rows
    )
    _validate_fold_scores_tsv(
        comparison_root / "fold_scores.tsv", verified_models, summary
    )
    return {
        "schema_version": 1,
        "status": "pass",
        "validator": "independent_development_only_metric_revision_1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "metric_revision_id": REVISION_ID,
        "binary_ranking_score_source": RANKING_SOURCE,
        "scope": {
            "opened_inputs": (
                "revision overlay/base config; 14 calibration, CV and Validation JSONs; "
                "comparison JSON, model TSV, fold TSV and checksum manifest"
            ),
            "test_files_opened": 0,
            "test_artifact_check": "filename/path metadata only; any Test-like artifact fails",
            "test_status": "not_evaluated",
        },
        "config_sha256": _sha256(config_path),
        "comparison_bundle_sha256": comparison_hashes,
        "comparison_checksum_manifest_sha256": _sha256(
            comparison_root / COMPARISON_CHECKSUM
        ),
        "verified_model_count": len(verified_models),
        "verified_model_ids": list(MODEL_IDS),
        "weights": WEIGHTS,
        "validation_regression_tolerance": VALIDATION_TOLERANCE,
        "raw_cv_best_model_id": selection["raw_cv_best_model_id"],
        "highest_selectable_cv_model_id": selection[
            "highest_selectable_cv_model_id"
        ],
        "one_se_model_ids_in_tie_break_order": selection["one_se_model_ids"],
        "selected_model_id": selection["selected_model_id"],
        "models": [
            {
                "model_id": row["model_id"],
                "head_means": row["head_means"],
                "head_ses": row["head_ses"],
                "composite_score": row["composite_score"],
                "composite_se": row["composite_se"],
                **selection["models"][row["model_id"]],
            }
            for row in verified_models
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--comparison-dir", type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output_path = args.output.resolve()
    _guard_development_input(output_path)
    report = validate(
        config_path=args.config,
        comparison_dir=args.comparison_dir,
        project_root=args.project_root,
    )
    _exclusive_json(output_path, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "verified_model_count": report["verified_model_count"],
                "selected_model_id": report["selected_model_id"],
                "output": str(output_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
