#!/usr/bin/env python3
"""Render the fail-closed Project V0 development-only model-selection figure."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec, GridSpecFromSubplotSpec
from matplotlib.patches import Rectangle
from PIL import Image

from djrmcp_finder.config import load_config
from djrmcp_finder.cv_folds import KNOWN_H3_CLASSES, UNKNOWN_H3_LABEL


# Nature-family double-column contract.  Python/Matplotlib is the exclusive backend.
width_mm = 183
height_mm = 238
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "Helvetica", "Liberation Sans", "DejaVu Sans"]
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["pdf.fonttype"] = 42
mpl.rcParams.update(
    {
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.size": 6.0,
        "axes.titlesize": 7.0,
        "axes.labelsize": 6.5,
        "xtick.labelsize": 5.5,
        "ytick.labelsize": 5.5,
        "legend.fontsize": 5.2,
        "axes.linewidth": 0.6,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "legend.frameon": False,
        "xtick.major.width": 0.5,
        "ytick.major.width": 0.5,
    }
)

FIGURE_BASENAME = "figure_1_model_selection_project_v0"
# Canonical delivery suffixes are stated explicitly for static journal preflight.
DELIVERY_SUFFIXES = (".svg", ".pdf", ".tiff", ".png")
EXPECTED_COMPARISON_FILES = {
    "model_comparison.tsv",
    "model_comparison.json",
    "fold_scores.tsv",
}
HEAD_ORDER = ("head1", "head2", "head3_phylum")
HEAD_LABELS = {"head1": "H1 AP", "head2": "H2 AP", "head3_phylum": "H3 known macro-F1"}
HEAD_COLORS = {"head1": "#2F6F9F", "head2": "#4B9B80", "head3_phylum": "#B97843"}
SELECTED_COLOR = "#C18400"
SELECTABLE_COLOR = "#4C78A8"
EXCLUDED_COLOR = "#A7A7A7"
FAIL_COLOR = "#B44D48"
TEXT_GREY = "#4D4D4D"
GRID_GREY = "#E2E2E2"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows:
        raise RuntimeError(f"Refusing an empty TSV: {path.name}")
    return rows


def _write_tsv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _float(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    if value == "":
        raise RuntimeError(f"Missing {key} for {row.get('model_id', '<unknown>')}")
    result = float(value)
    if not math.isfinite(result):
        raise RuntimeError(f"Non-finite {key} for {row.get('model_id', '<unknown>')}")
    return result


def _bool_text(value: str) -> bool:
    if value not in {"True", "False"}:
        raise RuntimeError(f"Expected canonical boolean text, observed {value!r}")
    return value == "True"


def _literal(value: str) -> Any:
    try:
        return ast.literal_eval(value)
    except (SyntaxError, ValueError) as error:
        raise RuntimeError(f"Invalid literal in comparison TSV: {value!r}") from error


def _verify_comparison_checksums(
    manifest_path: Path,
    *,
    comparison: Path,
    summary: Path,
    fold_scores: Path,
) -> dict[str, str]:
    """Require the exact frozen three-file checksum manifest and verify every byte."""
    paths = {
        "model_comparison.tsv": comparison,
        "model_comparison.json": summary,
        "fold_scores.tsv": fold_scores,
    }
    for expected_name, path in paths.items():
        if path.name != expected_name or not path.is_file():
            raise RuntimeError(f"Expected frozen input named {expected_name}, observed {path}")
    if not manifest_path.is_file():
        raise RuntimeError(f"Missing COMPARISON_CHECKSUMS manifest: {manifest_path}")
    recorded: dict[str, str] = {}
    for line_number, raw in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), 1):
        parts = raw.split("  ")
        if len(parts) != 2 or len(parts[0]) != 64 or any(ch not in "0123456789abcdef" for ch in parts[0]):
            raise RuntimeError(f"Malformed checksum line {line_number}")
        name = parts[1]
        if Path(name).name != name or name in recorded:
            raise RuntimeError(f"Unsafe or duplicate checksum target: {name!r}")
        recorded[name] = parts[0]
    if set(recorded) != EXPECTED_COMPARISON_FILES:
        raise RuntimeError(
            f"Checksum target set drift: observed={sorted(recorded)}, expected={sorted(EXPECTED_COMPARISON_FILES)}"
        )
    for name, path in paths.items():
        actual = _sha256(path)
        if actual != recorded[name]:
            raise RuntimeError(f"Checksum mismatch for {name}: expected {recorded[name]}, observed {actual}")
    return recorded


def _registry_candidate_ids(config: dict[str, Any]) -> list[str]:
    models = config.get("benchmark", {}).get("models")
    if not isinstance(models, dict) or not models:
        raise RuntimeError("Benchmark config has no non-empty model registry")
    candidate_ids = list(models)
    if len(candidate_ids) != 14 or len(set(candidate_ids)) != 14:
        raise RuntimeError(f"Project V0 figure requires the exact 14-model registry; observed {len(candidate_ids)}")
    return candidate_ids


def _exact_row_ids(
    rows: list[dict[str, Any]], expected_ids: list[str], context: str
) -> dict[str, dict[str, Any]]:
    observed = [row.get("model_id") for row in rows]
    if any(not isinstance(value, str) or not value for value in observed):
        raise RuntimeError(f"{context} contains an invalid model_id")
    if len(observed) != len(set(observed)):
        raise RuntimeError(f"{context} contains duplicate model IDs")
    if observed != expected_ids:
        raise RuntimeError(f"{context} model order/set differs from the frozen registry")
    return {str(row["model_id"]): row for row in rows}


def _baseline_model_id(summary: dict[str, Any], expected_ids: list[str]) -> str:
    models = summary.get("models")
    if not isinstance(models, list):
        raise RuntimeError("Comparison JSON models must be a list")
    candidates: set[str] = set()
    for row in models:
        for key, value in row.items():
            if key.startswith("validation_delta_vs_") and isinstance(value, dict):
                candidate = key.removeprefix("validation_delta_vs_")
                if candidate in expected_ids:
                    candidates.add(candidate)
    if len(candidates) != 1:
        raise RuntimeError(f"Comparison must attest exactly one Validation baseline; observed={sorted(candidates)}")
    baseline_id = next(iter(candidates))
    baseline_row = next(row for row in models if row["model_id"] == baseline_id)
    deltas = baseline_row[f"validation_delta_vs_{baseline_id}"]
    if set(deltas) != {"head1", "head2", "head3"} or any(abs(float(v)) > 1e-12 for v in deltas.values()):
        raise RuntimeError("Validation baseline lacks exact zero self-deltas")
    return baseline_id


def _assert_json_tsv_equal(model_id: str, json_row: dict[str, Any], tsv_row: dict[str, str]) -> None:
    string_fields = (
        "label", "status", "composite_se_method", "one_se_reference_model_id",
        "cv_fold_map_sha256", "cv_fold_metadata_sha256", "parameter_count_source",
        "embedding_timing_source", "license", "pretraining_overlap_risk", "source_kind",
        "resolved_model_revision", "test_status",
    )
    bool_fields = ("selectable", "selected", "within_one_paired_se", "speed_tie_break_eligible")
    int_fields = (
        "raw_cv_rank", "val_head3_unknown_diagnostic_n", "embedding_dimension",
        "parameter_count", "peak_gpu_memory_bytes",
    )
    float_fields = (
        "composite_score", "composite_se", "difference_from_best_selectable_cv",
        "paired_delta_se_vs_best_selectable_cv", "cv_head1_average_precision", "cv_head1_se",
        "cv_head2_average_precision", "cv_head2_se", "cv_head3_macro_f1", "cv_head3_se",
        "val_head1_average_precision", "val_head1_fpr_at_95pct_recall", "val_head1_mcc",
        "val_head2_macro_f1", "val_head2_balanced_accuracy", "val_head3_macro_f1",
        "val_head3_balanced_accuracy", "val_head3_ece", "val_head3_brier",
        "val_head3_unknown_recall", "val_head3_ood_auroc", "embedding_seconds",
        "gpu_seconds_per_sequence",
    )
    for field in string_fields:
        if tsv_row.get(field) != str(json_row.get(field)):
            raise RuntimeError(f"JSON/TSV mismatch for {model_id}.{field}")
    for field in bool_fields:
        if _bool_text(tsv_row.get(field, "")) is not bool(json_row.get(field)):
            raise RuntimeError(f"JSON/TSV mismatch for {model_id}.{field}")
    for field in int_fields:
        if int(tsv_row.get(field, "")) != int(json_row.get(field)):
            raise RuntimeError(f"JSON/TSV mismatch for {model_id}.{field}")
    for field in float_fields:
        if not math.isclose(_float(tsv_row, field), float(json_row.get(field)), rel_tol=0.0, abs_tol=1e-12):
            raise RuntimeError(f"JSON/TSV mismatch for {model_id}.{field}")
    for field in ("paired_fold_deltas_vs_best_selectable_cv", "validation_gate_failures"):
        if _literal(tsv_row.get(field, "")) != json_row.get(field):
            raise RuntimeError(f"JSON/TSV mismatch for {model_id}.{field}")
    if _literal(tsv_row.get("timing_comparability_key", "")) != json_row.get("timing_comparability_key"):
        raise RuntimeError(f"JSON/TSV mismatch for {model_id}.timing_comparability_key")


def _sample_se(values: list[float]) -> float:
    return float(np.std(np.asarray(values, dtype=float), ddof=1) / math.sqrt(len(values)))


def _validate_benchmark_inputs(
    config: dict[str, Any],
    config_path: Path,
    summary: dict[str, Any],
    rows: list[dict[str, str]],
    fold_rows: list[dict[str, str]],
) -> tuple[list[str], str]:
    """Cross-check registry, JSON, TSV, folds, gates and the frozen selection arithmetic."""
    expected_ids = _registry_candidate_ids(config)
    metric_revision = summary.get("metric_revision_id")
    expected_schema = 4 if metric_revision else 3
    if summary.get("schema_version") != expected_schema:
        raise RuntimeError(
            f"Comparison must use schema {expected_schema} for metric revision={metric_revision!r}"
        )
    if metric_revision and summary.get("binary_ranking_score_source") != "raw_decision_function":
        raise RuntimeError("Corrected figure requires raw decision-function ranking lineage")
    if summary.get("candidate_model_ids") != expected_ids or summary.get("complete_model_count") != 14:
        raise RuntimeError("Comparison candidate registry/count drift")
    if summary.get("pending_models") != []:
        raise RuntimeError("Refusing an incomplete benchmark")
    if summary.get("weights") != {"head1": 0.6, "head2": 0.3, "head3_phylum": 0.1}:
        raise RuntimeError("Frozen score weights differ from 0.60/0.30/0.10")
    if summary.get("benchmark_config_sha256", summary.get("config_sha256")) != _sha256(config_path):
        raise RuntimeError("Comparison benchmark config checksum mismatch")

    tsv_by_id = _exact_row_ids(rows, expected_ids, "Comparison TSV")
    json_models = summary.get("models")
    if not isinstance(json_models, list):
        raise RuntimeError("Comparison JSON models must be a list")
    json_by_id = _exact_row_ids(json_models, expected_ids, "Comparison JSON")
    baseline_id = _baseline_model_id(summary, expected_ids)
    model_cfg = config["benchmark"]["models"]
    selected_id = summary.get("selected_model_id")
    if selected_id not in expected_ids:
        raise RuntimeError("Selected model is outside the registry")
    for model_id in expected_ids:
        tsv_row, json_row = tsv_by_id[model_id], json_by_id[model_id]
        _assert_json_tsv_equal(model_id, json_row, tsv_row)
        cfg = model_cfg[model_id]
        if (
            tsv_row["label"] != cfg["label"]
            or tsv_row["license"] != cfg["license"]
            or tsv_row["source_kind"] != cfg["source_kind"]
            or tsv_row["pretraining_overlap_risk"] != cfg.get("pretraining_overlap_risk", "not_flagged")
        ):
            raise RuntimeError(f"Config/summary metadata mismatch for {model_id}")
        if tsv_row["status"] != "complete" or tsv_row["test_status"] != "not_evaluated":
            raise RuntimeError(f"Development figure refuses incomplete or Test-evaluated row: {model_id}")
    if [row["model_id"] for row in rows if _bool_text(row["selected"])] != [selected_id]:
        raise RuntimeError("Selected row does not match the frozen summary")

    fold_contract = summary.get("cv_fold_contract")
    folds = int(config["classifier"]["cross_validation_folds"])
    if not isinstance(fold_contract, dict) or (
        fold_contract.get("folds"), fold_contract.get("split"), fold_contract.get("group_field")
    ) != (folds, "train", "global_component_id"):
        raise RuntimeError("Missing shared frozen Train global-component fold contract")
    expected_keys = {(model, head, fold) for model in expected_ids for head in HEAD_ORDER for fold in range(1, folds + 1)}
    observed_keys: list[tuple[str, str, int]] = []
    fold_lookup: dict[tuple[str, str, int], dict[str, str]] = {}
    metric_names = {"head1": "average_precision", "head2": "average_precision", "head3_phylum": "macro_f1"}
    for row in fold_rows:
        key = (row.get("model_id", ""), row.get("head", ""), int(row.get("fold", "0")))
        observed_keys.append(key)
        fold_lookup[key] = row
        if row.get("metric") != metric_names.get(key[1]) or row.get("fold_map_sha256") != fold_contract["fold_map_sha256"]:
            raise RuntimeError(f"Fold metric/map attestation mismatch for {key}")
    if len(observed_keys) != len(set(observed_keys)) or set(observed_keys) != expected_keys:
        raise RuntimeError("Fold-score coverage differs from 14 models × 3 heads × 5 folds")

    composite_by_model: dict[str, list[float]] = {}
    mean_fields = {"head1": "cv_head1_average_precision", "head2": "cv_head2_average_precision", "head3_phylum": "cv_head3_macro_f1"}
    se_fields = {"head1": "cv_head1_se", "head2": "cv_head2_se", "head3_phylum": "cv_head3_se"}
    weights = summary["weights"]
    for model_id in expected_ids:
        per_head = {
            head: [float(fold_lookup[(model_id, head, fold)]["score"]) for fold in range(1, folds + 1)]
            for head in HEAD_ORDER
        }
        for head, values in per_head.items():
            if not math.isclose(float(np.mean(values)), _float(tsv_by_id[model_id], mean_fields[head]), abs_tol=1e-12):
                raise RuntimeError(f"Fold/summary mean mismatch for {model_id}.{head}")
            if not math.isclose(_sample_se(values), _float(tsv_by_id[model_id], se_fields[head]), abs_tol=1e-12):
                raise RuntimeError(f"Fold/summary SE mismatch for {model_id}.{head}")
        composites: list[float] = []
        for fold_index in range(folds):
            value = sum(float(weights[head]) * per_head[head][fold_index] for head in HEAD_ORDER)
            recorded = {float(fold_lookup[(model_id, head, fold_index + 1)]["composite_fold_score"]) for head in HEAD_ORDER}
            if len(recorded) != 1 or not math.isclose(value, next(iter(recorded)), abs_tol=1e-12):
                raise RuntimeError(f"Composite fold mismatch for {model_id}, fold {fold_index + 1}")
            composites.append(value)
        composite_by_model[model_id] = composites
        if not math.isclose(float(np.mean(composites)), _float(tsv_by_id[model_id], "composite_score"), abs_tol=1e-12):
            raise RuntimeError(f"Composite mean mismatch for {model_id}")
        if not math.isclose(_sample_se(composites), _float(tsv_by_id[model_id], "composite_se"), abs_tol=1e-12):
            raise RuntimeError(f"Composite SE mismatch for {model_id}")

    raw_order = sorted(expected_ids, key=lambda model: (-_float(tsv_by_id[model], "composite_score"), model))
    if summary.get("raw_cv_best_model_id") != raw_order[0] or any(int(tsv_by_id[m]["raw_cv_rank"]) != i + 1 for i, m in enumerate(raw_order)):
        raise RuntimeError("Raw CV ranking mismatch")
    selectable_ids = [m for m in expected_ids if _bool_text(tsv_by_id[m]["selectable"])]
    reference_id = max(selectable_ids, key=lambda model: _float(tsv_by_id[model], "composite_score"))
    if reference_id != summary.get("highest_selectable_cv_model_id"):
        raise RuntimeError("Highest-selectable CV reference mismatch")
    reference_folds = composite_by_model[reference_id]
    tolerance = float(summary.get("validation_regression_tolerance"))
    baseline_json = json_by_id[baseline_id]
    val_fields = {"head1": "val_head1_average_precision", "head2": "val_head2_macro_f1", "head3": "val_head3_macro_f1"}
    for model_id in expected_ids:
        row, jrow = tsv_by_id[model_id], json_by_id[model_id]
        deltas = [reference_folds[i] - composite_by_model[model_id][i] for i in range(folds)]
        if len(deltas) != len(jrow["paired_fold_deltas_vs_best_selectable_cv"]) or any(
            not math.isclose(a, b, abs_tol=1e-12)
            for a, b in zip(deltas, jrow["paired_fold_deltas_vs_best_selectable_cv"])
        ):
            raise RuntimeError(f"Paired fold delta mismatch for {model_id}")
        delta_mean, delta_se = float(np.mean(deltas)), _sample_se(deltas)
        if not math.isclose(delta_mean, float(jrow["difference_from_best_selectable_cv"]), abs_tol=1e-12) or not math.isclose(delta_se, float(jrow["paired_delta_se_vs_best_selectable_cv"]), abs_tol=1e-12):
            raise RuntimeError(f"Paired one-SE arithmetic mismatch for {model_id}")
        expected_one_se = bool(jrow["selectable"]) and delta_mean <= delta_se + 1e-12
        if bool(jrow["within_one_paired_se"]) is not expected_one_se or jrow["one_se_reference_model_id"] != reference_id:
            raise RuntimeError(f"Paired one-SE membership mismatch for {model_id}")
        delta_key = f"validation_delta_vs_{baseline_id}"
        expected_failures: list[str] = []
        for head, field in val_fields.items():
            delta = float(jrow[field]) - float(baseline_json[field])
            if not math.isclose(delta, float(jrow[delta_key][head]), abs_tol=1e-12):
                raise RuntimeError(f"Validation delta mismatch for {model_id}.{head}")
            if delta < -tolerance - 1e-12:
                expected_failures.append(head)
        if jrow["validation_gate_failures"] != expected_failures or bool(jrow["selectable"]) is not (not expected_failures):
            raise RuntimeError(f"Validation gate/selectable mismatch for {model_id}")
    one_se_ranks = sorted(int(row["tie_break_rank"]) for row in rows if row["tie_break_rank"])
    one_se_count = sum(_bool_text(row["within_one_paired_se"]) for row in rows)
    if one_se_ranks != list(range(1, one_se_count + 1)) or int(tsv_by_id[selected_id]["tie_break_rank"]) != 1:
        raise RuntimeError("Tie-break ranks do not resolve the paired one-SE set")
    return expected_ids, baseline_id


def _panel_label(ax: Any, label: str) -> None:
    ax.text(-0.055, 1.035, label, transform=ax.transAxes, fontsize=8.0, fontweight="bold", ha="right")


def _gate_text(row: dict[str, str]) -> str:
    failures = _literal(row["validation_gate_failures"])
    return "PASS" if not failures else "FAIL " + ",".join(item.upper().replace("HEAD", "H") for item in failures)


def _timing_groups(rows: list[dict[str, str]]) -> dict[str, str]:
    hashes = sorted({_canonical_sha256(_literal(row["timing_comparability_key"])) for row in rows})
    labels = {value: f"env {chr(65 + index)}" for index, value in enumerate(hashes)}
    return {_canonical_sha256(_literal(row["timing_comparability_key"])): labels[_canonical_sha256(_literal(row["timing_comparability_key"]))] for row in rows}


def _peak_memory_contract(summary: dict[str, Any]) -> tuple[bool, str]:
    rows = summary["models"]
    if all(isinstance(row.get("peak_gpu_memory_bytes"), (int, float)) and row.get("peak_gpu_memory_bytes", 0) > 0 and isinstance(row.get("peak_gpu_memory_source"), str) and row["peak_gpu_memory_source"] for row in rows):
        return True, "source-attested in every frozen model row"
    return False, "NA: frozen comparison has no per-model peak_gpu_memory_source attestation"


def _decision_reason(row: dict[str, str], selected: dict[str, str]) -> str:
    if _bool_text(row["selected"]):
        return "selected; tie-break rank 1"
    if not _bool_text(row["selectable"]):
        return "excluded by " + _gate_text(row).replace("FAIL ", "Validation ")
    if not _bool_text(row["within_one_paired_se"]):
        return "outside paired one-SE set"
    if _float(row, "val_head1_fpr_at_95pct_recall") > _float(selected, "val_head1_fpr_at_95pct_recall") + 1e-12:
        return "higher Validation H1 FPR"
    if _float(row, "gpu_seconds_per_sequence") > _float(selected, "gpu_seconds_per_sequence") + 1e-12:
        return "same H1 FPR; slower comparable run"
    return "lower preregistered tie-break rank"


def _build_source_data(
    output_dir: Path,
    rows: list[dict[str, str]],
    summary: dict[str, Any],
    fold_rows: list[dict[str, str]],
    baseline_id: str,
) -> dict[str, Path]:
    by_fold = {(row["model_id"], row["head"], int(row["fold"])): row for row in fold_rows}
    folds = int(summary["cv_fold_contract"]["folds"])
    a_rows: list[dict[str, Any]] = []
    for row in rows:
        metrics = [
            ("weighted_S", "Weighted S", "composite_score", "composite_se"),
            ("head1", HEAD_LABELS["head1"], "cv_head1_average_precision", "cv_head1_se"),
            ("head2", HEAD_LABELS["head2"], "cv_head2_average_precision", "cv_head2_se"),
            ("head3_phylum", HEAD_LABELS["head3_phylum"], "cv_head3_macro_f1", "cv_head3_se"),
        ]
        for key, label, mean_field, se_field in metrics:
            for fold in range(1, folds + 1):
                fold_score = (
                    by_fold[(row["model_id"], HEAD_ORDER[0], fold)]["composite_fold_score"]
                    if key == "weighted_S"
                    else by_fold[(row["model_id"], key, fold)]["score"]
                )
                a_rows.append(
                    {
                        "model_id": row["model_id"], "label": row["label"], "raw_cv_rank": row["raw_cv_rank"],
                        "selected": row["selected"], "selectable": row["selectable"], "metric": key,
                        "metric_label": label, "fold": fold, "fold_score": fold_score,
                        "mean": row[mean_field], "se": row[se_field],
                        "uncertainty_definition": "sample SD of five shared-fold scores divided by sqrt(5)",
                    }
                )
    baseline = next(row for row in rows if row["model_id"] == baseline_id)
    b_rows = []
    for row in rows:
        b_rows.append(
            {
                "model_id": row["model_id"], "label": row["label"], "baseline_model_id": baseline_id,
                "val_h1_delta": _float(row, "val_head1_average_precision") - _float(baseline, "val_head1_average_precision"),
                "val_h2_delta": _float(row, "val_head2_macro_f1") - _float(baseline, "val_head2_macro_f1"),
                "val_h3_delta": _float(row, "val_head3_macro_f1") - _float(baseline, "val_head3_macro_f1"),
                "regression_tolerance": summary["validation_regression_tolerance"],
                "gate_failures": row["validation_gate_failures"], "selectable": row["selectable"],
                "one_se_reference_model_id": row["one_se_reference_model_id"],
                "mean_delta_s_reference_minus_candidate": row["difference_from_best_selectable_cv"],
                "paired_delta_se": row["paired_delta_se_vs_best_selectable_cv"],
                "paired_fold_deltas": row["paired_fold_deltas_vs_best_selectable_cv"],
                "within_one_paired_se": row["within_one_paired_se"], "selected": row["selected"],
            }
        )
    memory_usable, memory_reason = _peak_memory_contract(summary)
    timing_groups = _timing_groups(rows)
    c_rows = []
    for row in rows:
        timing_hash = _canonical_sha256(_literal(row["timing_comparability_key"]))
        c_rows.append(
            {
                "model_id": row["model_id"], "label": row["label"], "selected": row["selected"],
                "selectable": row["selectable"], "composite_score": row["composite_score"],
                "composite_se": row["composite_se"], "gpu_seconds_per_sequence": row["gpu_seconds_per_sequence"],
                "timing_source": row["embedding_timing_source"], "timing_group": timing_groups[timing_hash],
                "timing_comparability_key_sha256": timing_hash,
                "raw_peak_gpu_memory_bytes": row["peak_gpu_memory_bytes"],
                "peak_memory_used": str(memory_usable), "peak_memory_for_plot_gib": (float(row["peak_gpu_memory_bytes"]) / 2**30 if memory_usable else ""),
                "peak_memory_status": memory_reason, "pareto_status": "not_inferred_without_source-attested_memory",
            }
        )
    d_rows = [
        {
            "model_id": row["model_id"], "label": row["label"], "selected": row["selected"],
            "known_output_1": KNOWN_H3_CLASSES[0], "known_output_2": KNOWN_H3_CLASSES[1],
            "rejection_output": UNKNOWN_H3_LABEL, "validation_known_two_class_macro_f1": row["val_head3_macro_f1"],
            "validation_unknown_diagnostic_recall": row["val_head3_unknown_recall"],
            "validation_unknown_diagnostic_n": row["val_head3_unknown_diagnostic_n"],
            "validation_ood_auroc_descriptive": row["val_head3_ood_auroc"],
            "unknown_scope_note": "diagnostic rejection only; not arbitrary unseen-virus detection",
        }
        for row in rows
    ]
    selected = next(row for row in rows if _bool_text(row["selected"]))
    e_rows = [
        {
            "model_id": row["model_id"], "label": row["label"], "selected": row["selected"],
            "selectable": row["selectable"], "within_one_paired_se": row["within_one_paired_se"],
            "mean_delta_s_reference_minus_candidate": row["difference_from_best_selectable_cv"],
            "paired_delta_se": row["paired_delta_se_vs_best_selectable_cv"], "validation_gate": _gate_text(row),
            "license": row["license"], "pretraining_overlap_risk": row["pretraining_overlap_risk"],
            "source_kind": row["source_kind"], "decision_reason": _decision_reason(row, selected),
        }
        for row in rows
    ]
    payloads = {
        "panel_a_cv_metrics.tsv": a_rows,
        "panel_b_validation_one_se.tsv": b_rows,
        "panel_c_compute.tsv": c_rows,
        "panel_d_h3_contract.tsv": d_rows,
        "panel_e_decision.tsv": e_rows,
    }
    paths: dict[str, Path] = {}
    for name, payload in payloads.items():
        path = output_dir / name
        _write_tsv(path, list(payload[0]), payload)
        paths[name] = path
    return paths


def _render(
    output_dir: Path,
    rows: list[dict[str, str]],
    summary: dict[str, Any],
    baseline_id: str,
    figure_basename: str,
) -> list[Path]:
    selected_id = summary["selected_model_id"]
    baseline = next(row for row in rows if row["model_id"] == baseline_id)
    selected = next(row for row in rows if row["model_id"] == selected_id)
    labels = [row["label"] for row in rows]
    y = np.arange(len(rows))
    fig = plt.figure(figsize=(width_mm / 25.4, height_mm / 25.4), facecolor="white")
    outer = GridSpec(4, 1, figure=fig, height_ratios=[1.25, 1.15, 1.0, 0.82], left=0.115, right=0.985, bottom=0.035, top=0.925, hspace=0.50)
    fig.text(0.115, 0.978, "Development-only selection of protein representations", fontsize=10.0, fontweight="bold", ha="left", va="top")
    revision_text = summary.get("metric_revision_id") or "legacy metric protocol"
    fig.text(0.115, 0.954, f"data-curation V3 (560 VMA-DJR) → project V0 · {revision_text} · Train CV + Validation only · no Test metrics", fontsize=6.3, color=TEXT_GREY, ha="left", va="top")

    # a — 14 models × S + three heads, with uncertainty from the five shared folds.
    ax_a = fig.add_subplot(outer[0])
    metric_fields = [
        ("S", "composite_score", "composite_se"), ("H1 AP", "cv_head1_average_precision", "cv_head1_se"),
        ("H2 AP", "cv_head2_average_precision", "cv_head2_se"), ("H3 known\nmacro-F1", "cv_head3_macro_f1", "cv_head3_se"),
    ]
    matrix = np.asarray([[_float(row, field) for _, field, _ in metric_fields] for row in rows])
    cmap = mpl.colors.LinearSegmentedColormap.from_list("restrained_blue", ["#F2F4F6", "#B8D3E6", "#376C92"])
    heatmap_norm = mpl.colors.Normalize(vmin=0.62, vmax=1.0)
    ax_a.imshow(matrix, aspect="auto", cmap=cmap, norm=heatmap_norm)
    ax_a.set_xticks(range(4), [item[0] for item in metric_fields])
    ax_a.xaxis.tick_top()
    ax_a.set_yticks(y, labels)
    ax_a.tick_params(length=0)
    for i, row in enumerate(rows):
        for j, (_, mean_field, se_field) in enumerate(metric_fields):
            value, se = _float(row, mean_field), _float(row, se_field)
            red, green, blue, _ = cmap(heatmap_norm(value))
            relative_luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
            text_color = "white" if relative_luminance < 0.50 else "#222222"
            ax_a.text(
                j,
                i,
                f"{value:.3f}\n±{se:.3f}",
                ha="center",
                va="center",
                fontsize=5.0,
                color=text_color,
            )
        if row["model_id"] == selected_id:
            ax_a.add_patch(Rectangle((-0.49, i - 0.47), 3.98, 0.94, fill=False, edgecolor=SELECTED_COLOR, linewidth=1.4))
    for tick, row in zip(ax_a.get_yticklabels(), rows):
        if row["model_id"] == selected_id:
            tick.set_color(SELECTED_COLOR); tick.set_fontweight("bold")
        elif not _bool_text(row["selectable"]):
            tick.set_color("#777777")
    ax_a.set_xlim(-0.5, 3.5)
    ax_a.set_title("Frozen Train-only 5-fold global-component CV (mean ± fold SE)", loc="left", pad=22)
    _panel_label(ax_a, "a")

    # b — Validation regression gates and paired one-SE evidence.
    nested_b = GridSpecFromSubplotSpec(1, 2, subplot_spec=outer[1], width_ratios=[1.22, 0.78], wspace=0.18)
    ax_bg = fig.add_subplot(nested_b[0]); ax_bs = fig.add_subplot(nested_b[1], sharey=ax_bg)
    validation = {"head1": "val_head1_average_precision", "head2": "val_head2_macro_f1", "head3_phylum": "val_head3_macro_f1"}
    offsets = {"head1": -0.19, "head2": 0.0, "head3_phylum": 0.19}
    markers = {"head1": "o", "head2": "s", "head3_phylum": "^"}
    for head, field in validation.items():
        delta = np.asarray([_float(row, field) - _float(baseline, field) for row in rows])
        ax_bg.scatter(delta, y + offsets[head], s=15, marker=markers[head], color=HEAD_COLORS[head], edgecolor="white", linewidth=0.3, label=HEAD_LABELS[head], zorder=3)
    tolerance = float(summary["validation_regression_tolerance"])
    ax_bg.axvspan(-1, -tolerance, color="#F4D9D7", alpha=0.75, zorder=0)
    ax_bg.axvline(0, color="#333333", linewidth=0.6); ax_bg.axvline(-tolerance, color=FAIL_COLOR, linewidth=0.8, linestyle="--")
    ax_bg.set_xlim(min(-0.08, min(_float(r, f) - _float(baseline, f) for r in rows for f in validation.values()) - 0.01), 0.035)
    ax_bg.set_yticks(y, labels); ax_bg.invert_yaxis(); ax_bg.grid(axis="x", color=GRID_GREY, linewidth=0.4)
    ax_bg.set_xlabel(f"Validation Δ vs {baseline['label']} (red: < −{tolerance:.2f})")
    ax_bg.set_title("Validation gates", loc="left", pad=15)
    ax_bg.legend(ncol=3, loc="lower left", bbox_to_anchor=(0, 1.0), handletextpad=0.3, columnspacing=0.8)
    for tick, row in zip(ax_bg.get_yticklabels(), rows):
        if row["model_id"] == selected_id: tick.set_color(SELECTED_COLOR); tick.set_fontweight("bold")
    differences = np.asarray([_float(row, "difference_from_best_selectable_cv") for row in rows])
    delta_se = np.asarray([_float(row, "paired_delta_se_vs_best_selectable_cv") for row in rows])
    colors = [SELECTED_COLOR if row["model_id"] == selected_id else (SELECTABLE_COLOR if _bool_text(row["within_one_paired_se"]) else EXCLUDED_COLOR) for row in rows]
    for i, row in enumerate(rows):
        ax_bs.errorbar(differences[i], i, xerr=delta_se[i], fmt="o", ms=3.2, color=colors[i], ecolor=colors[i], elinewidth=0.7, capsize=1.3)
    ax_bs.axvline(0, color="#333333", linewidth=0.6); ax_bs.grid(axis="x", color=GRID_GREY, linewidth=0.4)
    ax_bs.tick_params(axis="y", labelleft=False, left=False)
    ax_bs.set_xlabel("paired ΔS = Sref − S (± SEΔ)")
    ax_bs.set_title("Paired one-SE", loc="left", pad=15)
    ax_bs.text(0.02, 1.01, f"reference: {summary['highest_selectable_cv_model_id']}", transform=ax_bs.transAxes, fontsize=5.0, color=TEXT_GREY)
    _panel_label(ax_bg, "b")

    # c/d — compute evidence and H3 scope.
    nested_cd = GridSpecFromSubplotSpec(1, 2, subplot_spec=outer[2], width_ratios=[1.05, 0.95], wspace=0.36)
    ax_c = fig.add_subplot(nested_cd[0]); ax_d = fig.add_subplot(nested_cd[1])
    timing_groups = _timing_groups(rows)
    group_markers = {group: marker for group, marker in zip(sorted(set(timing_groups.values())), ("o", "^", "s"))}
    for row in rows:
        key_hash = _canonical_sha256(_literal(row["timing_comparability_key"]))
        group = timing_groups[key_hash]
        color = SELECTED_COLOR if row["model_id"] == selected_id else (SELECTABLE_COLOR if _bool_text(row["selectable"]) else EXCLUDED_COLOR)
        ax_c.errorbar(_float(row, "gpu_seconds_per_sequence") * 1000, _float(row, "composite_score"), yerr=_float(row, "composite_se"), fmt=group_markers[group], ms=4.2 if row["model_id"] == selected_id else 3.3, color=color, ecolor=color, elinewidth=0.6, capsize=1.2)
        ax_c.annotate(row["raw_cv_rank"], (_float(row, "gpu_seconds_per_sequence") * 1000, _float(row, "composite_score")), xytext=(2, 2), textcoords="offset points", fontsize=5.0, color=TEXT_GREY)
    if any(_float(row, "gpu_seconds_per_sequence") <= 0 for row in rows):
        raise RuntimeError("Embedding time must be strictly positive for the log axis")
    ax_c.set_xscale("log"); ax_c.grid(color=GRID_GREY, linewidth=0.4)
    ax_c.set_xlabel("Recorded embedding time (ms per protein; log)"); ax_c.set_ylabel("Train-CV S (± fold SE)")
    ax_c.set_title("S–compute evidence (descriptive)", loc="left", pad=6)
    memory_usable, memory_reason = _peak_memory_contract(summary)
    if memory_usable:
        raise RuntimeError("Peak-memory plotting is not implemented without a separately audited source contract")
    ax_c.text(
        0.02,
        0.03,
        f"Rank numbers label points.\nPeak GPU memory: NA (measurement source not attested).\n"
        f"{len(set(timing_groups.values()))} timing groups; no global Pareto inferred.",
        transform=ax_c.transAxes,
        fontsize=5.0,
        color=TEXT_GREY,
        va="bottom",
    )
    handles = [mpl.lines.Line2D([], [], marker=marker, linestyle="none", color="#666666", label=group) for group, marker in group_markers.items()]
    ax_c.legend(handles=handles, loc="upper right")
    _panel_label(ax_c, "c")

    known = np.asarray([_float(row, "val_head3_macro_f1") for row in rows])
    unknown = np.asarray([_float(row, "val_head3_unknown_recall") for row in rows])
    ax_d.scatter(known, y - 0.11, s=14, marker="o", color=HEAD_COLORS["head3_phylum"], label="known two-class macro-F1")
    ax_d.scatter(unknown, y + 0.11, s=16, marker="D", color="#7A5A9E", label="unknown/other recall")
    ax_d.set_xlim(-0.04, 1.04); ax_d.set_yticks(y, labels); ax_d.invert_yaxis(); ax_d.grid(axis="x", color=GRID_GREY, linewidth=0.4)
    ax_d.set_xlabel("Validation diagnostic metric"); ax_d.set_title("H3 output and rejection scope", loc="left", pad=18)
    ax_d.legend(ncol=2, loc="lower left", bbox_to_anchor=(0, 1.0), handletextpad=0.3, columnspacing=0.7)
    unknown_n = sorted({int(row["val_head3_unknown_diagnostic_n"]) for row in rows})
    if len(unknown_n) != 1:
        raise RuntimeError("Unknown-diagnostic n differs across candidates")
    ax_d.text(0.01, 0.02, f"known: {KNOWN_H3_CLASSES[0]} / {KNOWN_H3_CLASSES[1]}\nrejection: {UNKNOWN_H3_LABEL}; Validation n={unknown_n[0]} (diagnostic only)", transform=ax_d.transAxes, fontsize=5.0, color=TEXT_GREY, va="bottom")
    for tick, row in zip(ax_d.get_yticklabels(), rows):
        if row["model_id"] == selected_id: tick.set_color(SELECTED_COLOR); tick.set_fontweight("bold")
    _panel_label(ax_d, "d")

    # e — complete audit table; no candidate is hidden.
    ax_e = fig.add_subplot(outer[3]); ax_e.axis("off")
    table_rows = []
    for row in rows:
        risk = row["pretraining_overlap_risk"].replace("low_for_viruses_training_set_excluded_viruses", "low (viruses excluded)").replace("not_flagged", "not flagged")
        delta = _float(row, "difference_from_best_selectable_cv"); delta_se_value = _float(row, "paired_delta_se_vs_best_selectable_cv")
        table_rows.append([row["label"], "yes" if _bool_text(row["within_one_paired_se"]) else "no", f"{delta:+.3f} ± {delta_se_value:.3f}", _gate_text(row), row["license"], risk, _decision_reason(row, selected)])
    table = ax_e.table(cellText=table_rows, colLabels=["Model", "1-SE", "mean ΔS ± SEΔ", "Val gate", "License", "Pretraining-overlap risk", "Decision"], colLoc="center", cellLoc="left", loc="upper left", bbox=[0, 0, 1, 0.92], colWidths=[0.14, 0.055, 0.12, 0.085, 0.095, 0.15, 0.355])
    table.auto_set_font_size(False); table.set_fontsize(5.0)
    for (i, j), cell in table.get_celld().items():
        cell.set_linewidth(0.3); cell.set_edgecolor("#D3D3D3")
        if i == 0: cell.set_facecolor("#E8EEF3"); cell.set_text_props(fontweight="bold")
        elif rows[i - 1]["model_id"] == selected_id: cell.set_facecolor("#FFF0C4"); cell.set_text_props(fontweight="bold")
        elif not _bool_text(rows[i - 1]["selectable"]): cell.set_facecolor("#F6F6F6")
        if j in {1, 2, 3}: cell.set_text_props(ha="center")
    relation = "selected = baseline" if selected_id == baseline_id else f"baseline = {baseline['label']}"
    ax_e.set_title(f"Frozen decision audit — selected {summary['selected_model_label']} ({relation})", loc="left", pad=6, fontweight="bold")
    _panel_label(ax_e, "e")

    exports = [output_dir / f"{figure_basename}{suffix}" for suffix in DELIVERY_SUFFIXES]
    fig.savefig(exports[0]); fig.savefig(exports[1]); fig.savefig(exports[2], dpi=600, pil_kwargs={"compression": "tiff_lzw"}); fig.savefig(exports[3], dpi=300)
    plt.close(fig)
    return exports


def _export_qa(exports: list[Path]) -> dict[str, Any]:
    by_suffix = {path.suffix: path for path in exports}
    svg = by_suffix[".svg"].read_text(encoding="utf-8")
    if "<text" not in svg or "figure_1" not in by_suffix[".svg"].stem:
        raise RuntimeError("SVG lacks editable text or canonical naming")
    expected = {
        ".png": (round(width_mm / 25.4 * 300), round(height_mm / 25.4 * 300)),
        ".tiff": (round(width_mm / 25.4 * 600), round(height_mm / 25.4 * 600)),
    }
    raster: dict[str, Any] = {}
    for suffix, dimensions in expected.items():
        with Image.open(by_suffix[suffix]) as image:
            if any(abs(observed - wanted) > 2 for observed, wanted in zip(image.size, dimensions)):
                raise RuntimeError(f"Unexpected {suffix} dimensions: {image.size} vs {dimensions}")
            raster[suffix] = {
                "pixels": [int(value) for value in image.size],
                "dpi": [float(value) for value in list(image.info.get("dpi", ()))[:2]],
            }
    return {"status": "PASS", "svg_editable_text": True, "physical_size_mm": [width_mm, height_mm], "raster": raster}


def _environment() -> dict[str, str]:
    return {
        "python": sys.version.split()[0], "platform": platform.platform(), "matplotlib": mpl.__version__,
        "numpy": np.__version__, "pillow": importlib.metadata.version("Pillow"), "backend": mpl.get_backend(),
    }


def _write_documents(
    output_dir: Path,
    *,
    rows: list[dict[str, str]],
    summary: dict[str, Any],
    baseline_id: str,
    memory_reason: str,
    visual_qa_status: str,
    visual_qa_notes: list[str],
) -> tuple[Path, Path]:
    unknown_n = int(rows[0]["val_head3_unknown_diagnostic_n"])
    baseline_label = next(row["label"] for row in rows if row["model_id"] == baseline_id)
    selected_label = summary["selected_model_label"]
    selection_relation = (
        "The selected model is also the Validation baseline."
        if summary["selected_model_id"] == baseline_id
        else f"The frozen Validation baseline is {baseline_label}."
    )
    caption = f"""# Figure 1 | Frozen development-only selection of protein representations

**a,** Four frozen Train-only scores for all 14 candidates. H1/H2 AP is computed from raw decision-function scores; H3 uses uncalibrated class probabilities. Values are means ± SE, where SE is the sample standard deviation of five scores on one shared global-component fold map divided by √5. S = 0.60·H1 AP + 0.30·H2 AP + 0.10·H3 two-known-class macro-F1. **b,** Validation metric differences relative to the fresh {baseline_label} baseline (red region: regression greater than {summary['validation_regression_tolerance']:.2f}) and paired one-SE evidence relative to {summary['highest_selectable_cv_model_id']}; ΔS = S_reference − S_candidate and SEΔ is calculated from the five same-fold differences. **c,** Descriptive S–embedding-time comparison. Times are accumulated inference duration excluding model load; markers distinguish {len(set(_timing_groups(rows).values()))} non-identical timing-comparability groups. Peak GPU memory is {memory_reason}; therefore no Pareto frontier is inferred. **d,** H3 Validation evidence separates the supervised two-class metric ({KNOWN_H3_CLASSES[0]} versus {KNOWN_H3_CLASSES[1]}) from operational `{UNKNOWN_H3_LABEL}` rejection recall (diagnostic n = {unknown_n}); the latter does not establish detection of arbitrary unseen viruses. **e,** Complete decision audit; the corrected protocol selects {selected_label}. {selection_relation} No candidate is omitted and no Test prediction or metric is read.

Source data: `panel_a_cv_metrics.tsv` through `panel_e_decision.tsv`. Train/Validation/Test boundary: selection uses Train component-aware CV and Validation only; Test status in the frozen comparison is `not_evaluated`. No hypothesis test or multiple-comparison correction is used; intervals in a and b are fold-derived uncertainty, not confidence intervals.
"""
    qa_lines = "\n".join(f"- {note}" for note in visual_qa_notes) if visual_qa_notes else "- No free-text visual-QA note supplied."
    qa = f"""# Figure 1 QA notes

- Core conclusion: corrected raw-score AP, paired one-SE, Validation gates and preregistered tie breaks select {selected_label} from the exact 14-model registry.
- Metric lineage: binary ranking metrics use raw decision-function scores; calibrated probabilities are reserved for calibration/threshold metrics.
- Archetype/backend: quantitative grid; Python/Matplotlib only.
- Final size: {width_mm} × {height_mm} mm; SVG/PDF editable vectors, TIFF 600 dpi, PNG 300 dpi.
- Input integrity: exact candidate count before/after = 14/14; exclusions = 0; sampling = none; hidden failed candidates = 0.
- Boundary: development-only; every frozen candidate row must say `test_status=not_evaluated`.
- Statistics: one shared Train-only five-fold global-component map; per-head/composite SE = SD/√5; paired SEΔ uses same-fold differences.
- H3 limitation: `{UNKNOWN_H3_LABEL}` is an operational rejection diagnostic (Validation n={unknown_n}), not an arbitrary unseen-virus detector.
- Compute limitation: {memory_reason}. Timing has {len(set(_timing_groups(rows).values()))} comparability groups, so panel c is descriptive and no Pareto frontier is claimed.
- Image integrity: all panels are programmatic quantitative vector graphics; no microscopy, photographs, crops, local contrast adjustment or pseudo-colour processing.
- Automated export QA: PASS (dimensions and editable SVG text checked before publication).
- Visual QA status: {visual_qa_status}.
{qa_lines}
"""
    caption_path, qa_path = output_dir / "CAPTION.md", output_dir / "QA_NOTES.md"
    caption_path.write_text(caption, encoding="utf-8"); qa_path.write_text(qa, encoding="utf-8")
    return caption_path, qa_path


def _build_bundle(args: argparse.Namespace, output_dir: Path) -> dict[str, Any]:
    checksum_manifest = args.checksums or args.summary.with_name("COMPARISON_CHECKSUMS.sha256")
    checksum_records = _verify_comparison_checksums(checksum_manifest, comparison=args.comparison, summary=args.summary, fold_scores=args.fold_scores)
    config = load_config(args.config)
    rows = _read_tsv(args.comparison)
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    fold_rows = _read_tsv(args.fold_scores)
    candidate_ids, baseline_id = _validate_benchmark_inputs(config, args.config, summary, rows, fold_rows)
    rows.sort(key=lambda row: int(row["raw_cv_rank"]))
    sources = _build_source_data(output_dir, rows, summary, fold_rows, baseline_id)
    exports = _render(output_dir, rows, summary, baseline_id, args.figure_basename)
    export_qa = _export_qa(exports)
    export_qa_path = output_dir / "EXPORT_QA.json"
    export_qa_path.write_text(json.dumps(export_qa, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _, memory_reason = _peak_memory_contract(summary)
    caption_path, qa_path = _write_documents(output_dir, rows=rows, summary=summary, baseline_id=baseline_id, memory_reason=memory_reason, visual_qa_status=args.visual_qa_status, visual_qa_notes=args.visual_qa_note)
    environment = _environment()
    environment_path = output_dir / "render_environment.json"
    environment_path.write_text(json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    provenance = {
        "schema_version": 1,
        "figure_contract": "Figure 1 — development-only 14-model selection",
        "project_mapping": "data-curation V3 (560 VMA-DJR) -> project V0",
        "script_sha256": _sha256(Path(__file__).resolve()),
        "input_sha256": {
            "benchmark_config": _sha256(args.config), "comparison_checksums": _sha256(checksum_manifest),
            **checksum_records,
        },
        "comparison_checksum_manifest_verified": True,
        "candidate_model_ids": candidate_ids, "candidate_count_before": 14, "candidate_count_after": 14,
        "excluded_candidate_count": 0, "selected_model_id": summary["selected_model_id"], "baseline_model_id": baseline_id,
        "metric_revision_id": summary.get("metric_revision_id"),
        "binary_ranking_score_source": summary.get("binary_ranking_score_source"),
        "test_metrics_read": False, "final_size_mm": [width_mm, height_mm],
        "peak_memory_status": memory_reason, "pareto_status": "not_inferred",
        "timing_group_count": len(set(_timing_groups(rows).values())),
        "source_data_sha256": {name: _sha256(path) for name, path in sorted(sources.items())},
        "export_sha256": {path.name: _sha256(path) for path in exports},
        "render_environment": environment, "render_environment_sha256": _canonical_sha256(environment),
        "export_qa_sha256": _sha256(export_qa_path), "caption_sha256": _sha256(caption_path), "qa_notes_sha256": _sha256(qa_path),
    }
    provenance_path = output_dir / "PROVENANCE.json"
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksum_path = output_dir / "FIGURE_CHECKSUMS.sha256"
    all_paths = sorted(path for path in output_dir.iterdir() if path.is_file() and path != checksum_path)
    checksum_path.write_text("".join(f"{_sha256(path)}  {path.name}\n" for path in all_paths), encoding="utf-8")
    provenance["bundle_file_count_excluding_checksum_manifest"] = len(all_paths)
    return provenance


def _atomic_publish(args: argparse.Namespace) -> dict[str, Any]:
    destination = args.output_dir.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / f".{destination.name}.publish.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise RuntimeError(f"Publication lock already exists: {lock}") from error
    staging: Path | None = None
    try:
        os.close(descriptor)
        if destination.exists():
            raise FileExistsError(f"Refusing to overwrite existing output directory: {destination}")
        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent))
        provenance = _build_bundle(args, staging)
        if destination.exists():
            raise FileExistsError(f"Output directory appeared during rendering: {destination}")
        os.rename(staging, destination)
        staging = None
        return provenance
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)
        lock.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/model_benchmark_v0.yaml"))
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--fold-scores", type=Path, required=True)
    parser.add_argument("--checksums", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--figure-basename", default=FIGURE_BASENAME)
    parser.add_argument("--visual-qa-status", choices=("pending", "passed"), default="pending")
    parser.add_argument("--visual-qa-note", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    provenance = _atomic_publish(args)
    print(json.dumps(provenance, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
