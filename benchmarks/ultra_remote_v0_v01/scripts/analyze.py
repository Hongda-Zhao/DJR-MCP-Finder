#!/usr/bin/env python3
"""Analyze v0/v0.1 and classical scores with frozen ultra-remote audit rules."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_curve


SOURCE = Path(__file__).resolve()
LOCAL_PROJECT_ROOT = SOURCE.parents[3]
PARENT_SCRIPTS = LOCAL_PROJECT_ROOT / "benchmarks/plm_vs_classical_v0/scripts"
if str(PARENT_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PARENT_SCRIPTS))

from common import atomic_json, parse_score, read_tsv, score_text, sha256_file, write_tsv  # noqa: E402
from summarize import conservative_threshold, finite_ranking_score, source_component_weights  # noqa: E402


METHOD_ORDER = [
    "esmc6b_cosine",
    "esm2_3b_cosine",
    "esm2_650m_cosine",
    "blastp",
    "diamond_ultra",
    "mmseqs_s7.5",
    "hmmer_component",
    "psiblast_longest_seed_positiveDB_3iter",
    "hmmer_family",
    "esmc6b_supervised",
    "esm2_3b_supervised",
]
TASK_ORDER = ["h1_djr", "h2_vma_conditional", "vma_end_to_end"]
METHOD_META = {
    "esmc6b_cosine": ("v0", "encoder_readout", "controlled_primary"),
    "esm2_3b_cosine": ("v0.1", "encoder_readout", "controlled_primary"),
    "esm2_650m_cosine": ("context", "encoder_readout", "controlled_context"),
    "blastp": ("classical", "pairwise", "controlled_primary"),
    "diamond_ultra": ("classical", "pairwise", "controlled_primary"),
    "mmseqs_s7.5": ("classical", "pairwise", "controlled_primary"),
    "hmmer_component": ("classical", "profile", "controlled_primary"),
    "psiblast_longest_seed_positiveDB_3iter": (
        "classical",
        "iterative_profile",
        "resource_augmented_secondary",
    ),
    "hmmer_family": ("classical", "profile", "metadata_augmented_secondary"),
    "esmc6b_supervised": ("v0", "task_adapted_detector", "operational_descriptive"),
    "esm2_3b_supervised": (
        "v0.1",
        "task_adapted_detector",
        "operational_descriptive",
    ),
}
PAIR_SPECS = [
    ("encoder", "esm2_3b_cosine", "esmc6b_cosine"),
    ("task_adapted_detector", "esm2_3b_supervised", "esmc6b_supervised"),
]
STRATA = [
    "component_holdout_all",
    "blast_defined_qcov_lt80",
    "blast_defined_qcov_ge80_pident_20_to_lt30",
    "blast_defined_pident_lt20_any_qcov",
    "blast_defined_qcov_ge80_pident_lt20",
]


def component_mean(rows: list[dict], value_key: str) -> dict[str, float]:
    values: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        values[row["global_component_id"]].append(float(row[value_key]))
    return {component: float(np.mean(items)) for component, items in values.items()}


def normalized_partial_auc(
    rows: list[dict], scores: np.ndarray, max_fpr: float
) -> float:
    labels = np.asarray([int(row["label"]) for row in rows], dtype=np.int64)
    positives = [row for row in rows if row["label"] == "1"]
    negatives = [row for row in rows if row["label"] == "0"]
    if not positives or not negatives:
        return math.nan
    positive_weight_array = source_component_weights(positives)
    negative_weight_array = source_component_weights(negatives)
    positive_iter = iter(positive_weight_array.tolist())
    negative_iter = iter(negative_weight_array.tolist())
    weights = []
    for row in rows:
        if row["label"] == "1":
            weights.append(0.5 * next(positive_iter))
        else:
            weights.append(0.5 * next(negative_iter))
    ranking_scores = finite_ranking_score(scores)
    fpr, tpr, _ = roc_curve(
        labels,
        ranking_scores,
        sample_weight=np.asarray(weights, dtype=np.float64),
        drop_intermediate=False,
    )
    if fpr[-1] < max_fpr:
        raise RuntimeError("ROC does not reach requested partial-AUC boundary")
    keep = fpr < max_fpr
    x = np.r_[fpr[keep], max_fpr]
    y = np.r_[tpr[keep], np.interp(max_fpr, fpr, tpr)]
    return float(np.trapezoid(y, x) / max_fpr)


def bootstrap_ci(values: dict[str, float], replicates: int, seed_text: str) -> tuple[float, float]:
    vector = np.asarray(list(values.values()), dtype=np.float64)
    if not len(vector):
        return math.nan, math.nan
    seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:16], 16)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(vector), size=(replicates, len(vector)))
    sampled = vector[draws].mean(axis=1)
    return tuple(float(value) for value in np.quantile(sampled, [0.025, 0.975]))


def read_score_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            for row in reader:
                if row["method"] in METHOD_ORDER:
                    rows.append(row)
    return rows


def blast_best_hits(
    parent_root: Path,
    task: str,
    evaluation_ids_by_fold: dict[int, set[str]],
    fold_count: int,
) -> dict[str, dict[str, float]]:
    reference = "djr" if task == "h1_djr" else "vma"
    best: dict[str, dict[str, float]] = {}
    for fold in range(1, fold_count + 1):
        path = parent_root / f"work/classical/fold_{fold}/{reference}/pairwise/blastp.hits.tsv"
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip() or line.startswith("#"):
                    continue
                fields = line.rstrip("\n").split("\t")
                if len(fields) != 6:
                    raise ValueError(f"Malformed BLAST row {path}:{line_number}")
                query = fields[0]
                if query not in evaluation_ids_by_fold[fold]:
                    continue
                hit = {
                    "bitscore": float(fields[2]),
                    "evalue": float(fields[3]),
                    "pident": float(fields[4]),
                    "qcov": float(fields[5]),
                }
                if query not in best or hit["bitscore"] > best[query]["bitscore"]:
                    best[query] = hit
    return best


def assigned_strata(protein_id: str, best: dict[str, dict[str, float]]) -> set[str]:
    result = {"component_holdout_all"}
    hit = best.get(protein_id)
    if hit is None:
        return result
    if hit["qcov"] < 80.0:
        result.add("blast_defined_qcov_lt80")
    elif hit["pident"] < 20.0:
        result.add("blast_defined_qcov_ge80_pident_lt20")
    elif hit["pident"] < 30.0:
        result.add("blast_defined_qcov_ge80_pident_20_to_lt30")
    if hit["pident"] < 20.0:
        result.add("blast_defined_pident_lt20_any_qcov")
    return result


def inference_status(
    stratum: str,
    component_count: int,
    fold_counts: list[int],
    config: dict,
) -> str:
    if "pident_lt20" in stratum:
        return "CASE_SERIES_NO_CI"
    if stratum == "component_holdout_all":
        return "DEVELOPMENT_COMPONENT_HOLDOUT_FIXED_THRESHOLD_COMPONENT_BOOTSTRAP_NOT_ULTRA_REMOTE"
    minimum = int(config["parameters"]["minimum_descriptive_components"])
    per_fold = int(config["parameters"]["minimum_descriptive_components_per_fold"])
    if component_count >= minimum and min(fold_counts) >= per_fold:
        return "DESCRIPTIVE_FIXED_THRESHOLD_COMPONENT_BOOTSTRAP"
    return "DESCRIPTIVE_LOW_N_NO_CI"


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    project_root = Path(config["project_root"]).resolve()
    benchmark_root = (project_root / config["benchmark_root"]).resolve()
    parent_root = (project_root / config["parent_benchmark_root"]).resolve()
    results_root = benchmark_root / "results"
    cohort = read_tsv(parent_root / "inputs/cohort.tsv")
    cohort_by_id = {row["protein_id"]: row for row in cohort}
    if len(cohort_by_id) != len(cohort):
        raise RuntimeError("Duplicate protein ID in frozen parent cohort")
    old_score_path = parent_root / "results/query_scores.tsv"
    new_score_path = benchmark_root / "work/v01_query_scores.tsv"
    rows = read_score_rows([old_score_path, new_score_path])
    methods_present = {row["method"] for row in rows}
    missing = [method for method in METHOD_ORDER if method not in methods_present]
    if missing:
        raise RuntimeError(f"Missing required score methods: {missing}")
    allowed_status = {"ok", "no_hit"}
    if any(row["status"] not in allowed_status for row in rows):
        raise RuntimeError("Unexpected score status entered analysis")
    if any(row["status"] == "no_hit" and row["score"] != "-inf" for row in rows):
        raise RuntimeError("A no-hit score is not encoded as -inf")
    expected_label_key = {
        "h1_djr": "is_djr",
        "h2_vma_conditional": "is_vma",
        "vma_end_to_end": "is_vma",
    }
    unique_score_keys: set[tuple[str, str, str, str, str]] = set()
    offset = int(config["parameters"]["calibration_fold_offset"])
    fold_count = int(config["parameters"]["folds"])
    for row in rows:
        protein_id = row["protein_id"]
        frozen = cohort_by_id.get(protein_id)
        if frozen is None:
            raise RuntimeError(f"Score ID absent from frozen Train cohort: {protein_id}")
        if row["task"] not in expected_label_key or row["method"] not in METHOD_ORDER:
            raise RuntimeError("Unknown task/method entered score table")
        expected = {
            "global_component_id": frozen["global_component_id"],
            "source_fold": frozen["fold"],
            "source_dataset": frozen["source_dataset"],
            "label": frozen[expected_label_key[row["task"]]],
        }
        if any(row[key] != value for key, value in expected.items()):
            raise RuntimeError(f"Score/cohort metadata mismatch: {protein_id}, {row['task']}")
        if row["task"] == "h2_vma_conditional" and frozen["is_djr"] != "1":
            raise RuntimeError("Non-DJR row entered conditional H2 endpoint")
        evaluation_fold = int(row["evaluation_fold"])
        if not 1 <= evaluation_fold <= fold_count:
            raise RuntimeError("Evaluation fold is outside the frozen five-fold design")
        if row["role"] not in {"calibration", "evaluation"}:
            raise RuntimeError("Unexpected cyclic role")
        expected_calibration_fold = (
            (evaluation_fold - 1 + offset) % fold_count
        ) + 1
        expected_source_fold = (
            evaluation_fold if row["role"] == "evaluation" else expected_calibration_fold
        )
        if int(row["source_fold"]) != expected_source_fold:
            raise RuntimeError("Score row violates cyclic fold-role contract")
        key = (
            protein_id,
            row["task"],
            row["method"],
            row["evaluation_fold"],
            row["role"],
        )
        if key in unique_score_keys:
            raise RuntimeError(f"Duplicate score key: {key}")
        unique_score_keys.add(key)

    specificity = float(config["parameters"]["primary_specificity"])
    max_fpr = float(config["parameters"]["low_fpr_max"])
    fold_count = int(config["parameters"]["folds"])
    replicates = int(config["parameters"]["bootstrap_replicates"])
    grouped: dict[tuple[str, str, int, str], list[dict]] = defaultdict(list)
    for row in rows:
        row["score_value"] = parse_score(row["score"])
        grouped[
            (row["task"], row["method"], int(row["evaluation_fold"]), row["role"])
        ].append(row)
    for task in TASK_ORDER:
        for fold in range(1, fold_count + 1):
            for role in ("calibration", "evaluation"):
                anchor_ids = {
                    row["protein_id"]
                    for row in grouped[(task, "blastp", fold, role)]
                }
                for method in METHOD_ORDER:
                    observed_ids = {
                        row["protein_id"]
                        for row in grouped[(task, method, fold, role)]
                    }
                    if observed_ids != anchor_ids:
                        raise RuntimeError(
                            f"Method query-set mismatch: {task}, {method}, fold={fold}, {role}"
                        )

    fold_metric_rows: list[dict[str, str]] = []
    threshold_by_key: dict[tuple[str, str, int], float] = {}
    for task in TASK_ORDER:
        for method in METHOD_ORDER:
            version, layer, track = METHOD_META[method]
            for fold in range(1, fold_count + 1):
                calibration = grouped[(task, method, fold, "calibration")]
                evaluation = grouped[(task, method, fold, "evaluation")]
                if not calibration or not evaluation:
                    raise RuntimeError(f"Missing cycle rows: {task}, {method}, {fold}")
                calibration_negative = [row for row in calibration if row["label"] == "0"]
                evaluation_positive = [row for row in evaluation if row["label"] == "1"]
                evaluation_negative = [row for row in evaluation if row["label"] == "0"]
                cal_weights = source_component_weights(calibration_negative)
                threshold, achieved_cal_fpr = conservative_threshold(
                    np.asarray([row["score_value"] for row in calibration_negative]),
                    cal_weights,
                    specificity,
                )
                threshold_by_key[(task, method, fold)] = threshold
                positive_detection = component_mean(
                    [
                        {**row, "detected": float(row["score_value"] >= threshold)}
                        for row in evaluation_positive
                    ],
                    "detected",
                )
                sensitivity = float(np.mean(list(positive_detection.values())))
                neg_weights = source_component_weights(evaluation_negative)
                evaluation_fpr = float(
                    np.sum(
                        neg_weights
                        * np.asarray(
                            [row["score_value"] >= threshold for row in evaluation_negative],
                            dtype=np.float64,
                        )
                    )
                )
                negative_sources = sorted({row["source_dataset"] for row in evaluation_negative})
                negative_component_counts = {
                    source: len(
                        {
                            row["global_component_id"]
                            for row in evaluation_negative
                            if row["source_dataset"] == source
                        }
                    )
                    for source in negative_sources
                }
                limiting_negative_mass = max(
                    1.0 / len(negative_sources) / count
                    for count in negative_component_counts.values()
                )
                if limiting_negative_mass <= max_fpr + 1e-15:
                    pauc = normalized_partial_auc(
                        evaluation,
                        np.asarray([row["score_value"] for row in evaluation]),
                        max_fpr,
                    )
                    pauc_status = "RESOLVABLE"
                else:
                    pauc = math.nan
                    pauc_status = "RESOLUTION_LIMITED_NO_ESTIMATE"
                fold_metric_rows.append(
                    {
                        "task": task,
                        "method": method,
                        "system_version": version,
                        "layer": layer,
                        "track": track,
                        "evaluation_fold": str(fold),
                        "threshold_99.5": score_text(threshold),
                        "calibration_achieved_specificity": score_text(1.0 - achieved_cal_fpr),
                        "evaluation_specificity": score_text(1.0 - evaluation_fpr),
                        "component_sensitivity_99.5": score_text(sensitivity),
                        "normalized_pauc_fpr_0.005": score_text(pauc),
                        "limiting_source_balanced_negative_component_mass": score_text(
                            limiting_negative_mass
                        ),
                        "low_fpr_pauc_status": pauc_status,
                        "evaluation_positive_records": str(len(evaluation_positive)),
                        "evaluation_positive_components": str(len(positive_detection)),
                        "evaluation_negative_records": str(len(evaluation_negative)),
                        "evaluation_negative_components": str(
                            len({row["global_component_id"] for row in evaluation_negative})
                        ),
                    }
                )

    write_tsv(results_root / "fold_metrics.tsv", fold_metric_rows, list(fold_metric_rows[0]))
    metric_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in fold_metric_rows:
        metric_groups[(row["task"], row["method"])].append(row)
    summary_rows: list[dict[str, str]] = []
    for task in TASK_ORDER:
        for method in METHOD_ORDER:
            values = metric_groups[(task, method)]
            specificities = np.asarray(
                [float(row["evaluation_specificity"]) for row in values]
            )
            version, layer, track = METHOD_META[method]
            pauc_values = np.asarray(
                [
                    float(row["normalized_pauc_fpr_0.005"])
                    for row in values
                    if row["normalized_pauc_fpr_0.005"] != "NA"
                ],
                dtype=np.float64,
            )
            complete_pauc = len(pauc_values) == fold_count
            summary_rows.append(
                {
                    "task": task,
                    "method": method,
                    "system_version": version,
                    "layer": layer,
                    "track": track,
                    "mean_component_sensitivity_99.5": score_text(
                        float(
                            np.mean(
                                [float(row["component_sensitivity_99.5"]) for row in values]
                            )
                        )
                    ),
                    "mean_normalized_pauc_fpr_0.005": score_text(
                        float(np.mean(pauc_values)) if complete_pauc else math.nan
                    ),
                    "low_fpr_pauc_fold_count": str(len(pauc_values)),
                    "low_fpr_pauc_status": (
                        "COMPLETE_FIVE_FOLD"
                        if complete_pauc
                        else "NOT_HEADLINE_RESOLUTION_LIMITED_FOLD"
                    ),
                    "mean_evaluation_specificity": score_text(float(np.mean(specificities))),
                    "minimum_fold_evaluation_specificity": score_text(
                        float(np.min(specificities))
                    ),
                    "specificity_gate_99.5": (
                        "PASS_ALL_FOLDS"
                        if np.all(specificities >= specificity - 1e-15)
                        else "FAIL_AT_LEAST_ONE_FOLD"
                    ),
                    "inference_scope": "TRAIN_ONLY_COMPONENT_CROSSFIT_DEVELOPMENT",
                }
            )
    write_tsv(results_root / "method_summary.tsv", summary_rows, list(summary_rows[0]))

    # Freeze BLAST-defined difficulty assignments once per task, then apply every
    # method's independently calibrated threshold without reselecting or recalibrating.
    positive_eval_rows_by_task: dict[str, list[dict]] = {}
    best_by_task: dict[str, dict[str, dict[str, float]]] = {}
    strata_by_task: dict[str, dict[str, set[str]]] = {}
    for task in TASK_ORDER:
        anchor = []
        for fold in range(1, fold_count + 1):
            anchor.extend(
                row
                for row in grouped[(task, "blastp", fold, "evaluation")]
                if row["label"] == "1"
            )
        positive_eval_rows_by_task[task] = anchor
        ids_by_fold = {
            fold: {
                row["protein_id"]
                for row in anchor
                if int(row["evaluation_fold"]) == fold
            }
            for fold in range(1, fold_count + 1)
        }
        best = blast_best_hits(parent_root, task, ids_by_fold, fold_count)
        best_by_task[task] = best
        strata_by_task[task] = {
            row["protein_id"]: assigned_strata(row["protein_id"], best) for row in anchor
        }

    stratum_rows: list[dict[str, str]] = []
    component_detection: dict[tuple[str, str, str], dict[str, float]] = {}
    for task in TASK_ORDER:
        for method in METHOD_ORDER:
            method_eval: list[dict] = []
            for fold in range(1, fold_count + 1):
                threshold = threshold_by_key[(task, method, fold)]
                for row in grouped[(task, method, fold, "evaluation")]:
                    if row["label"] == "1":
                        method_eval.append(
                            {**row, "detected": float(row["score_value"] >= threshold)}
                        )
            for stratum in STRATA:
                selected = [
                    row
                    for row in method_eval
                    if stratum in strata_by_task[task][row["protein_id"]]
                ]
                per_component = component_mean(selected, "detected")
                component_detection[(task, method, stratum)] = per_component
                component_folds = {
                    component: int(next(row["evaluation_fold"] for row in selected if row["global_component_id"] == component))
                    for component in per_component
                }
                fold_counts = [
                    sum(value == fold for value in component_folds.values())
                    for fold in range(1, fold_count + 1)
                ]
                status = inference_status(
                    stratum, len(per_component), fold_counts, config
                )
                sensitivity = (
                    float(np.mean(list(per_component.values())))
                    if per_component
                    else math.nan
                )
                if "BOOTSTRAP" in status:
                    ci_low, ci_high = bootstrap_ci(
                        per_component,
                        replicates,
                        f"{config['seed']}|{task}|{method}|{stratum}",
                    )
                else:
                    ci_low, ci_high = math.nan, math.nan
                version, layer, track = METHOD_META[method]
                stratum_rows.append(
                    {
                        "task": task,
                        "method": method,
                        "system_version": version,
                        "layer": layer,
                        "track": track,
                        "stratum": stratum,
                        "positive_records": str(len(selected)),
                        "positive_components": str(len(per_component)),
                        "components_by_fold": ",".join(map(str, fold_counts)),
                        "component_sensitivity_99.5": score_text(sensitivity),
                        "ci95_low_fixed_threshold": score_text(ci_low),
                        "ci95_high_fixed_threshold": score_text(ci_high),
                        "inference_status": status,
                        "stratifier": (
                            "pre_frozen_global_component"
                            if stratum == "component_holdout_all"
                            else "evaluation_cycle_best_blast_hit_descriptive_only"
                        ),
                    }
                )
    write_tsv(
        results_root / "stratum_sensitivity.tsv", stratum_rows, list(stratum_rows[0])
    )

    paired_rows: list[dict[str, str]] = []
    summary_lookup = {(row["task"], row["method"]): row for row in summary_rows}
    for task in TASK_ORDER:
        for pair_name, v01_method, v0_method in PAIR_SPECS:
            for stratum in STRATA:
                v01 = component_detection[(task, v01_method, stratum)]
                v0 = component_detection[(task, v0_method, stratum)]
                if set(v01) != set(v0):
                    raise RuntimeError(f"Paired component mismatch: {task}, {stratum}")
                difference = {
                    component: v01[component] - v0[component] for component in v01
                }
                anchor_row = next(
                    row
                    for row in stratum_rows
                    if row["task"] == task
                    and row["method"] == v01_method
                    and row["stratum"] == stratum
                )
                status = anchor_row["inference_status"]
                delta = (
                    float(np.mean(list(difference.values()))) if difference else math.nan
                )
                if "BOOTSTRAP" in status:
                    low, high = bootstrap_ci(
                        difference,
                        replicates,
                        f"{config['seed']}|delta|{task}|{pair_name}|{stratum}",
                    )
                else:
                    low, high = math.nan, math.nan
                paired_rows.append(
                    {
                        "task": task,
                        "comparison_layer": pair_name,
                        "v01_method": v01_method,
                        "v0_method": v0_method,
                        "stratum": stratum,
                        "positive_components": anchor_row["positive_components"],
                        "components_by_fold": anchor_row["components_by_fold"],
                        "delta_sensitivity_v01_minus_v0": score_text(delta),
                        "ci95_low_fixed_threshold": score_text(low),
                        "ci95_high_fixed_threshold": score_text(high),
                        "v01_specificity_gate_99.5": summary_lookup[(task, v01_method)][
                            "specificity_gate_99.5"
                        ],
                        "v0_specificity_gate_99.5": summary_lookup[(task, v0_method)][
                            "specificity_gate_99.5"
                        ],
                        "v01_minimum_fold_evaluation_specificity": summary_lookup[
                            (task, v01_method)
                        ]["minimum_fold_evaluation_specificity"],
                        "v0_minimum_fold_evaluation_specificity": summary_lookup[
                            (task, v0_method)
                        ]["minimum_fold_evaluation_specificity"],
                        "matched_specificity_status": (
                            "PASS_BOTH_ALL_FOLDS"
                            if summary_lookup[(task, v01_method)]["specificity_gate_99.5"]
                            == "PASS_ALL_FOLDS"
                            and summary_lookup[(task, v0_method)]["specificity_gate_99.5"]
                            == "PASS_ALL_FOLDS"
                            else "NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY"
                        ),
                        "inference_status": status,
                    }
                )
    write_tsv(
        results_root / "paired_v0_v01.tsv", paired_rows, list(paired_rows[0])
    )

    complementarity_rows: list[dict[str, str]] = []
    complementarity_comparators = [
        "blastp",
        "diamond_ultra",
        "mmseqs_s7.5",
        "hmmer_component",
        "psiblast_longest_seed_positiveDB_3iter",
        "hmmer_family",
    ]
    for task in TASK_ORDER:
        for stratum in STRATA:
            v01 = component_detection[(task, "esm2_3b_cosine", stratum)]
            for comparator in complementarity_comparators:
                other = component_detection[(task, comparator, stratum)]
                if set(v01) != set(other):
                    raise RuntimeError(
                        f"Complementarity component mismatch: {task}, {comparator}, {stratum}"
                    )
                v01_only = sum(v01[key] > 0 and other[key] == 0 for key in v01)
                comparator_only = sum(
                    other[key] > 0 and v01[key] == 0 for key in v01
                )
                both = sum(v01[key] > 0 and other[key] > 0 for key in v01)
                neither = sum(v01[key] == 0 and other[key] == 0 for key in v01)
                v01_better = sum(v01[key] > other[key] for key in v01)
                comparator_better = sum(v01[key] < other[key] for key in v01)
                equal = sum(v01[key] == other[key] for key in v01)
                anchor = next(
                    row
                    for row in stratum_rows
                    if row["task"] == task
                    and row["method"] == "esm2_3b_cosine"
                    and row["stratum"] == stratum
                )
                complementarity_rows.append(
                    {
                        "task": task,
                        "stratum": stratum,
                        "plm_method": "esm2_3b_cosine",
                        "comparator": comparator,
                        "positive_components": str(len(v01)),
                        "both_have_any_detected_record": str(both),
                        "plm_only_has_any_detected_record": str(v01_only),
                        "comparator_only_has_any_detected_record": str(comparator_only),
                        "neither_has_any_detected_record": str(neither),
                        "plm_higher_component_average_detection": str(v01_better),
                        "comparator_higher_component_average_detection": str(
                            comparator_better
                        ),
                        "equal_component_average_detection": str(equal),
                        "plm_component_sensitivity": score_text(
                            float(np.mean(list(v01.values()))) if v01 else math.nan
                        ),
                        "comparator_component_sensitivity": score_text(
                            float(np.mean(list(other.values()))) if other else math.nan
                        ),
                        "delta_plm_minus_comparator": score_text(
                            float(
                                np.mean(
                                    [v01[key] - other[key] for key in v01]
                                )
                            )
                            if v01
                            else math.nan
                        ),
                        "plm_specificity_gate_99.5": summary_lookup[
                            (task, "esm2_3b_cosine")
                        ]["specificity_gate_99.5"],
                        "comparator_specificity_gate_99.5": summary_lookup[
                            (task, comparator)
                        ]["specificity_gate_99.5"],
                        "inference_status": anchor["inference_status"],
                        "detection_definition": (
                            "any means at least one record in an independent component "
                            "meets its calibration-fold-locked threshold"
                        ),
                    }
                )
    write_tsv(
        results_root / "plm_classical_complementarity.tsv",
        complementarity_rows,
        list(complementarity_rows[0]),
    )

    strict_case_rows: list[dict[str, str]] = []
    for task in TASK_ORDER:
        strict_ids = {
            protein_id
            for protein_id, strata in strata_by_task[task].items()
            if "blast_defined_qcov_ge80_pident_lt20" in strata
        }
        for method in METHOD_ORDER:
            for fold in range(1, fold_count + 1):
                threshold = threshold_by_key[(task, method, fold)]
                for row in grouped[(task, method, fold, "evaluation")]:
                    if row["label"] != "1" or row["protein_id"] not in strict_ids:
                        continue
                    hit = best_by_task[task][row["protein_id"]]
                    strict_case_rows.append(
                        {
                            "task": task,
                            "protein_id": row["protein_id"],
                            "global_component_id": row["global_component_id"],
                            "evaluation_fold": row["evaluation_fold"],
                            "best_blast_pident": score_text(hit["pident"]),
                            "best_blast_qcov": score_text(hit["qcov"]),
                            "best_blast_bitscore": score_text(hit["bitscore"]),
                            "method": method,
                            "score": row["score"],
                            "threshold_99.5": score_text(threshold),
                            "detected": str(int(row["score_value"] >= threshold)),
                            "case_status": "EXPLORATORY_NO_INFERENCE",
                        }
                    )
    write_tsv(
        results_root / "strict_qcov_ge80_lt20_cases.tsv",
        strict_case_rows,
        list(strict_case_rows[0]),
    )

    # A machine-readable sufficiency gate makes it impossible to silently promote a
    # one-component case series to the benchmark headline.
    strict_counts = {
        task: len(
            {
                row["global_component_id"]
                for row in positive_eval_rows_by_task[task]
                if "blast_defined_qcov_ge80_pident_lt20"
                in strata_by_task[task][row["protein_id"]]
            }
        )
        for task in TASK_ORDER
    }
    validation = {
        "status": "PASS_WITH_FORMAL_ULTRA_REMOTE_BLOCKED_BY_SAMPLE_SIZE",
        "benchmark_id": config["benchmark_id"],
        "design_id": config["design_id"],
        "parent_query_scores_sha256": sha256_file(old_score_path),
        "v01_query_scores_sha256": sha256_file(new_score_path),
        "score_rows_analyzed": len(rows),
        "validation_prediction_rows": 0,
        "test_prediction_rows": 0,
        "strict_ultra_remote_positive_components": strict_counts,
        "formal_ultra_remote_minimum_components": int(
            config["parameters"]["minimum_formal_ultra_remote_components"]
        ),
        "formal_ultra_remote_claim_allowed": False,
        "reason": (
            "Strict qcov>=80 and pident<20 strata are BLAST-defined and contain "
            "far fewer than 100 independent positive components."
        ),
    }
    atomic_json(results_root / "validation.json", validation)

    paired_lookup = {
        (row["task"], row["comparison_layer"], row["stratum"]): row
        for row in paired_rows
    }
    report_rows = []
    for task in TASK_ORDER:
        enc = paired_lookup[(task, "encoder", "component_holdout_all")]
        det = paired_lookup[(task, "task_adapted_detector", "component_holdout_all")]
        report_rows.append(
            [
                task,
                f"{float(enc['delta_sensitivity_v01_minus_v0']):+.3f}",
                f"{float(det['delta_sensitivity_v01_minus_v0']):+.3f}",
                enc["matched_specificity_status"],
                det["matched_specificity_status"],
            ]
        )
    lowcov_rows = []
    for task in TASK_ORDER:
        for layer in ("encoder", "task_adapted_detector"):
            row = paired_lookup[(task, layer, "blast_defined_qcov_lt80")]
            lowcov_rows.append(
                [
                    task,
                    layer,
                    row["positive_components"],
                    f"{float(row['delta_sensitivity_v01_minus_v0']):+.3f}",
                    (
                        f"[{float(row['ci95_low_fixed_threshold']):+.3f}, "
                        f"{float(row['ci95_high_fixed_threshold']):+.3f}]"
                        if row["ci95_low_fixed_threshold"] != "NA"
                        else "NA"
                    ),
                ]
            )
    twilight_rows = []
    for task in TASK_ORDER:
        for layer in ("encoder", "task_adapted_detector"):
            row = paired_lookup[
                (task, layer, "blast_defined_qcov_ge80_pident_20_to_lt30")
            ]
            twilight_rows.append(
                [
                    task,
                    layer,
                    row["positive_components"],
                    f"{float(row['delta_sensitivity_v01_minus_v0']):+.3f}",
                    (
                        f"[{float(row['ci95_low_fixed_threshold']):+.3f}, "
                        f"{float(row['ci95_high_fixed_threshold']):+.3f}]"
                        if row["ci95_low_fixed_threshold"] != "NA"
                        else "NA"
                    ),
                ]
            )
    report = f"""# v0 / v0.1 超远缘开发评测报告

## 一句话结论

本次计算可以回答 v0.1 在**冻结 component 分折**和**BLAST 定义的低覆盖压力层**上是否优于 v0，
但不能回答严格超远缘优越性：`qcov >=80% 且 identity <20%` 的独立正 component 计数为
`{strict_counts}`，远低于预注册的 100 个下限。

## v0.1 相对 v0：全部 component-holdout

{markdown_table(['任务', 'encoder 灵敏度差', '监督检测器灵敏度差', 'encoder specificity', 'detector specificity'], report_rows)}

差值为 v0.1 减 v0。只有双方五个评价 folds 都守住实际 99.5% specificity 才标为 matched；
否则差值只是固定 calibration 阈值下的描述，不能叫 matched-specificity 提升。这里证明的也只是
Train-only component-level 泛化，不等于严格超远缘。

## BLAST-defined 低覆盖压力层（qcov <80%）

{markdown_table(['任务', '比较层', '独立 components', '灵敏度差', '95% paired CI'], lowcov_rows)}

此层只做描述：低覆盖可能来自短同源片段、domain fusion、截短或真正远缘；并且分层来自
被比较的 BLAST，因此不能用于正式宣称 PLM 胜过 BLAST。

## BLAST-defined twilight 层（qcov >=80%，20% <= identity <30%）

{markdown_table(['任务', '比较层', '独立 components', '灵敏度差', '95% paired CI'], twilight_rows)}

这是当前最接近远缘、同时仍有一定样本量的 identity 分层，但它仍由 BLAST 定义，所以只作
描述性结果；真正 `<20%` 的严格层仍只有个案。

## 如何解读 v0 与 v0.1

- `esm2_3b_cosine` 对 `esmc6b_cosine`：只比较 encoder 的检索几何，信息预算相同。
- `esm2_3b_supervised` 对 `esmc6b_supervised`：相同训练标签、分类器 family、超参数、fold 与
  阈值协议，最接近 H1/H2 实际检测器的公平比较。
- H3 没有参与：v0 和 v0.1 都使用同一个 ESM-C 6B H3，而且 H3 是 phylum 分类而非远缘检出。
- 任何在 99.5% specificity gate 失败的方法，其灵敏度不能称为“matched-specificity 提升”。

## 当前能与不能下的结论

能：内部开发集上的 component-holdout 泛化、低 FPR pAUROC、低覆盖压力层的描述性差值。

不能：外部 Test 提升、结构确认的超远缘提升、用 BLAST-failure 选样后再宣称优于 BLAST。
正式结论需要方法独立的结构/人工证据 lockbox，至少 100 个正 components、每 fold 至少 20 个。
"""
    (results_root / "REPORT.md").write_text(report, encoding="utf-8")
    print(
        "PASS analyzed v0/v0.1; formal strict ultra-remote claim blocked: "
        + json.dumps(strict_counts, sort_keys=True)
    )


if __name__ == "__main__":
    main()
