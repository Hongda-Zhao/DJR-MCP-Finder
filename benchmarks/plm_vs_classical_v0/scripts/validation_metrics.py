#!/usr/bin/env python3
"""Independent point-metric validation for the cyclic benchmark release.

This module deliberately imports neither ``summarize`` nor ``common``.  It verifies
the exact cyclic score matrix and independently recomputes component-balanced AP,
the conservative 99.5% calibration threshold, evaluation sensitivity, and the
five-cycle macro estimands.  Bootstrap intervals are schema/order checked but the
10,000 bootstrap replicates are not rerun here.
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence


class MetricValidationError(RuntimeError):
    """Raised when a released metric or score violates its frozen contract."""


TASKS = {
    "h1_djr": ("is_djr", False),
    "h2_vma_conditional": ("is_vma", True),
    "vma_end_to_end": ("is_vma", False),
}
METHODS = (
    "esmc6b_cosine",
    "esm2_650m_cosine",
    "blastp",
    "diamond_ultra",
    "mmseqs_s7.5",
    "hmmer_component",
    "psiblast_longest_seed_positiveDB_3iter",
    "hmmer_family",
    "esmc6b_supervised",
)
CONTROLLED = {
    "esmc6b_cosine",
    "esm2_650m_cosine",
    "blastp",
    "diamond_ultra",
    "mmseqs_s7.5",
    "hmmer_component",
}
CLASSICAL_ANCHORS = ("blastp", "diamond_ultra", "mmseqs_s7.5", "hmmer_component")
TRACK = {
    **{method: "controlled_primary" for method in CONTROLLED},
    "psiblast_longest_seed_positiveDB_3iter": "resource_augmented_secondary",
    "hmmer_family": "metadata_augmented_secondary",
    "esmc6b_supervised": "operational_descriptive",
}
FORBIDDEN_FIELD = re.compile(r"(^|_)(p_?value|holm)($|_)", re.IGNORECASE)


def fail(message: str) -> None:
    raise MetricValidationError(f"METRIC VALIDATION FAILED: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    require(path.is_file(), f"missing TSV: {path}")
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            require(reader.fieldnames is not None, f"missing TSV header: {path}")
            fields = list(reader.fieldnames)
            rows = list(reader)
    except (OSError, csv.Error) as error:
        fail(f"cannot read {path}: {error}")
    return fields, rows


def read_json(path: Path) -> dict:
    require(path.is_file(), f"missing JSON: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read {path}: {error}")
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def close(observed: float, expected: float, label: str) -> None:
    require(
        math.isfinite(observed)
        and math.isfinite(expected)
        and math.isclose(observed, expected, rel_tol=2e-12, abs_tol=2e-12),
        f"{label}: observed={observed:.17g}, expected={expected:.17g}",
    )


def parse_score(text: str, status: str, label: str) -> float:
    try:
        value = float(text)
    except ValueError:
        fail(f"malformed score for {label}: {text!r}")
    require(status in {"ok", "no_hit"}, f"engine/parser failure in {label}: {status}")
    if status == "no_hit":
        require(value == -math.inf, f"no_hit is not -inf in {label}")
    else:
        require(math.isfinite(value), f"ok score is not finite in {label}")
    return value


def calibration_fold(evaluation_fold: int, fold_count: int, offset: int) -> int:
    value = ((evaluation_fold - 1 + offset) % fold_count) + 1
    require(value != evaluation_fold, "calibration fold equals evaluation fold")
    return value


def eligible(rows: Iterable[dict[str, str]], task: str) -> list[dict[str, str]]:
    _, conditional = TASKS[task]
    return [row for row in rows if not conditional or row["is_djr"] == "1"]


def component_weights(rows: Sequence[dict[str, str]]) -> list[float]:
    require(bool(rows), "component weighting received no rows")
    counts = Counter(row["global_component_id"] for row in rows)
    return [1.0 / counts[row["global_component_id"]] for row in rows]


def source_component_weights(rows: Sequence[dict[str, str]]) -> list[float]:
    require(bool(rows), "source-component weighting received no rows")
    sources = {row["source_dataset"] for row in rows}
    by_source_component: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        by_source_component[row["source_dataset"]][row["global_component_id"]] += 1
    return [
        1.0
        / len(sources)
        / len(by_source_component[row["source_dataset"]])
        / by_source_component[row["source_dataset"]][row["global_component_id"]]
        for row in rows
    ]


def weighted_ap(labels: Sequence[int], scores: Sequence[float], weights: Sequence[float]) -> float:
    require(len(labels) == len(scores) == len(weights) and bool(labels), "AP vector shape")
    require(all(label in {0, 1} for label in labels), "AP label is not binary")
    require(all(not math.isnan(score) and score != math.inf for score in scores), "invalid AP score")
    positive_total = sum(weight for label, weight in zip(labels, weights) if label)
    negative_total = sum(weight for label, weight in zip(labels, weights) if not label)
    require(positive_total > 0 and negative_total > 0, "AP class loss")
    groups: dict[float, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for label, score, weight in zip(labels, scores, weights):
        groups[score][0 if label else 1] += weight
    true_positive = 0.0
    false_positive = 0.0
    previous_recall = 0.0
    result = 0.0
    for score in sorted(groups, reverse=True):
        positive_mass, negative_mass = groups[score]
        true_positive += positive_mass
        false_positive += negative_mass
        recall = true_positive / positive_total
        precision = true_positive / (true_positive + false_positive)
        result += (recall - previous_recall) * precision
        previous_recall = recall
    return result


def conservative_threshold(
    scores: Sequence[float], weights: Sequence[float], specificity: float
) -> tuple[float, float]:
    require(len(scores) == len(weights) and bool(scores), "threshold vector shape")
    require(all(not math.isnan(score) and score != math.inf for score in scores), "invalid threshold score")
    require(all(math.isfinite(weight) and weight >= 0 for weight in weights), "invalid threshold weight")
    total = sum(weights)
    require(total > 0, "zero threshold weight")
    mass: dict[float, float] = defaultdict(float)
    for score, weight in zip(scores, weights):
        if weight > 0:
            mass[score] += weight / total
    achieved = 0.0
    for score in sorted(mass, reverse=True):
        if achieved + mass[score] <= 1.0 - specificity + 1e-15:
            achieved += mass[score]
        else:
            return math.nextafter(score, math.inf), achieved
    fail("threshold calibration consumed all negative mass")


def weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    require(len(values) == len(weights) and sum(weights) > 0, "weighted mean vector shape")
    return sum(value * weight for value, weight in zip(values, weights)) / sum(weights)


def load_exact_scores(
    benchmark_root: Path,
    cohort: Sequence[dict[str, str]],
    fold_count: int,
    offset: int,
) -> tuple[dict[tuple[str, str, int, str, str], tuple[float, str]], int]:
    by_id = {row["protein_id"]: row for row in cohort}
    require(len(by_id) == len(cohort), "duplicate cohort protein ID")
    raw_rows: list[dict[str, str]] = []
    for relative in ("work/scores/plm_scores.tsv", "work/scores/classical_scores.tsv"):
        _, rows = read_tsv(benchmark_root / relative)
        raw_rows.extend(rows)
    lookup: dict[tuple[str, str, int, str, str], tuple[float, str]] = {}
    for row in raw_rows:
        method = row.get("method", "")
        task = row.get("task", "")
        role = row.get("role", "")
        protein = row.get("protein_id", "")
        require(method in METHODS and task in TASKS and role in {"calibration", "evaluation"}, f"unknown raw score scope: {row}")
        require(protein in by_id, f"raw score outside cohort: {protein}")
        try:
            fold = int(row["evaluation_fold"])
            source_fold = int(row["source_fold"])
        except (KeyError, ValueError):
            fail(f"malformed raw fold fields: {row}")
        require(fold in range(1, fold_count + 1), f"raw evaluation fold outside range: {row}")
        expected_source = fold if role == "evaluation" else calibration_fold(fold, fold_count, offset)
        require(source_fold == expected_source == int(by_id[protein]["fold"]), f"raw cyclic role/source mismatch: {row}")
        _, conditional = TASKS[task]
        require(not conditional or by_id[protein]["is_djr"] == "1", f"ineligible H2 raw row: {row}")
        key = (method, task, fold, role, protein)
        require(key not in lookup, f"duplicate raw score key: {key}")
        lookup[key] = (parse_score(row["score"], row["status"], str(key)), row["status"])

    expected: set[tuple[str, str, int, str, str]] = set()
    for fold in range(1, fold_count + 1):
        cal = calibration_fold(fold, fold_count, offset)
        for task in TASKS:
            for role, source_fold in (("calibration", cal), ("evaluation", fold)):
                rows = eligible((row for row in cohort if int(row["fold"]) == source_fold), task)
                expected.update(
                    (method, task, fold, role, row["protein_id"])
                    for method in METHODS
                    for row in rows
                )
    require(set(lookup) == expected, f"raw score matrix mismatch; missing={len(expected-set(lookup))}, extra={len(set(lookup)-expected)}")

    fields, result_rows = read_tsv(benchmark_root / "results/query_scores.tsv")
    required_fields = {
        "protein_id", "global_component_id", "evaluation_fold", "source_fold", "role",
        "source_dataset", "task", "label", "method", "score", "status",
    }
    require(required_fields <= set(fields), "query score schema incomplete")
    result_keys: set[tuple[str, str, int, str, str]] = set()
    for row in result_rows:
        try:
            key = (
                row["method"], row["task"], int(row["evaluation_fold"]), row["role"],
                row["protein_id"],
            )
        except (KeyError, ValueError):
            fail(f"malformed result score row: {row}")
        require(key in lookup and key not in result_keys, f"unexpected/duplicate result score: {key}")
        result_keys.add(key)
        source = by_id[key[4]]
        require(
            row["source_fold"] == source["fold"]
            and row["global_component_id"] == source["global_component_id"]
            and row["source_dataset"] == source["source_dataset"]
            and row["label"] == source[TASKS[key[1]][0]],
            f"query-score cohort provenance mismatch: {key}",
        )
        value = parse_score(row["score"], row["status"], str(key))
        raw_value, raw_status = lookup[key]
        require(row["status"] == raw_status and value == raw_value, f"query/raw score mismatch: {key}")
    require(result_keys == expected, "result query score matrix is not exact")
    return lookup, len(result_rows)


def keyed_rows(path: Path, key_fields: Sequence[str]) -> tuple[list[str], dict[tuple[str, ...], dict[str, str]]]:
    fields, rows = read_tsv(path)
    result: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        key = tuple(row.get(field, "") for field in key_fields)
        require(all(key) and key not in result, f"duplicate/empty key in {path.name}: {key}")
        result[key] = row
    return fields, result


def validate_point_metrics(
    benchmark_root: Path,
    config: Mapping[str, object],
    cohort: Sequence[dict[str, str]],
    scores: Mapping[tuple[str, str, int, str, str], tuple[float, str]],
) -> tuple[dict[tuple[str, str], dict[str, object]], int, int]:
    fold_count = int(config["parameters"]["folds"])
    offset = int(config["parameters"]["calibration_fold_offset"])
    specificity = float(config["parameters"]["primary_specificity"])
    _, cycles = keyed_rows(
        benchmark_root / "results/metrics_cycle.tsv", ("task", "method", "evaluation_fold")
    )
    _, primary = keyed_rows(benchmark_root / "results/metrics_primary.tsv", ("task", "method"))
    threshold_fields, thresholds = keyed_rows(
        benchmark_root / "results/thresholds.tsv",
        ("task", "method", "evaluation_fold", "specificity_target"),
    )
    ladder_fields, ladder = keyed_rows(
        benchmark_root / "results/metrics_specificity_ladder.tsv",
        ("task", "method", "evaluation_fold", "specificity_target"),
    )
    require(len(cycles) == len(TASKS) * len(METHODS) * fold_count, "cycle metric row count")
    require(len(primary) == len(TASKS) * len(METHODS), "primary metric row count")
    expected_specificities = {f"{float(value):.4f}" for value in config["parameters"]["specificity_ladder"]}
    expected_cycle_keys = {
        (task, method, str(fold))
        for task in TASKS for method in METHODS for fold in range(1, fold_count + 1)
    }
    expected_primary_keys = {(task, method) for task in TASKS for method in METHODS}
    expected_ladder_keys = {
        (task, method, str(fold), target)
        for task in TASKS for method in METHODS for fold in range(1, fold_count + 1)
        for target in expected_specificities
    }
    require(set(cycles) == expected_cycle_keys, "cycle metric key set")
    require(set(primary) == expected_primary_keys, "primary metric key set")
    require(set(thresholds) == expected_ladder_keys, "threshold key set")
    require(set(ladder) == expected_ladder_keys, "specificity ladder key set")
    require(
        len(thresholds) == len(ladder) == len(TASKS) * len(METHODS) * fold_count * len(expected_specificities),
        "specificity ladder/threshold row count",
    )
    require(
        "endpoint_status" in ladder_fields and "endpoint_status" in threshold_fields,
        "specificity endpoint status absent",
    )
    for key, row in ladder.items():
        target = float(key[3])
        expected_status = (
            "PRIMARY" if math.isclose(target, specificity) else
            "RESOLUTION_LIMITED_SECONDARY" if math.isclose(target, 0.999) else
            "SECONDARY"
        )
        require(row["endpoint_status"] == expected_status, f"endpoint status mismatch: {key}")
        require(thresholds[key]["endpoint_status"] == expected_status, f"threshold endpoint status mismatch: {key}")

    summary = read_json(benchmark_root / "results/summary.json")
    resolution = summary.get("resolution_audit")
    require(isinstance(resolution, dict) and set(resolution) == set(TASKS), "metric resolution audit coverage")

    recomputed: dict[tuple[str, str], dict[str, object]] = {}
    for task in TASKS:
        label_field, _ = TASKS[task]
        for method in METHODS:
            fold_ap: list[float] = []
            fold_sensitivity: list[float] = []
            fold_record_sensitivity: list[float] = []
            fold_specificity: list[float] = []
            no_hit = 0
            all_eval_rows: list[dict[str, str]] = []
            for fold in range(1, fold_count + 1):
                cal_fold = calibration_fold(fold, fold_count, offset)
                evaluation_rows = eligible(
                    (row for row in cohort if int(row["fold"]) == fold), task
                )
                calibration_rows = eligible(
                    (row for row in cohort if int(row["fold"]) == cal_fold), task
                )
                evaluation_scores = [
                    scores[(method, task, fold, "evaluation", row["protein_id"])][0]
                    for row in evaluation_rows
                ]
                labels = [int(row[label_field]) for row in evaluation_rows]
                ap = weighted_ap(labels, evaluation_scores, component_weights(evaluation_rows))
                negative_calibration = [
                    row for row in calibration_rows if row[label_field] == "0"
                ]
                negative_scores = [
                    scores[(method, task, fold, "calibration", row["protein_id"])][0]
                    for row in negative_calibration
                ]
                threshold, achieved_fpr = conservative_threshold(
                    negative_scores, source_component_weights(negative_calibration), specificity
                )
                positive_rows = [row for row in evaluation_rows if row[label_field] == "1"]
                positive_predictions = [
                    float(scores[(method, task, fold, "evaluation", row["protein_id"])][0] >= threshold)
                    for row in positive_rows
                ]
                sensitivity = weighted_mean(positive_predictions, component_weights(positive_rows))
                record_sensitivity = sum(positive_predictions) / len(positive_predictions)
                negative_evaluation = [row for row in evaluation_rows if row[label_field] == "0"]
                negative_predictions = [
                    float(scores[(method, task, fold, "evaluation", row["protein_id"])][0] >= threshold)
                    for row in negative_evaluation
                ]
                observed_specificity = 1.0 - weighted_mean(
                    negative_predictions, source_component_weights(negative_evaluation)
                )
                row = cycles[(task, method, str(fold))]
                require(row["track"] == TRACK[method] and int(row["calibration_fold"]) == cal_fold, f"cycle role/track: {task} {method} {fold}")
                require(
                    row["primary_sensitivity_inference_status"]
                    == resolution[task]["primary_sensitivity_inference_status"],
                    f"cycle sensitivity inference status {task} {method} {fold}",
                )
                close(float(row["component_balanced_ap"]), ap, f"cycle AP {task} {method} {fold}")
                require(float(row["threshold_99.5"]) == threshold, f"cycle threshold {task} {method} {fold}")
                close(float(row["calibration_achieved_fpr"]), achieved_fpr, f"cycle calibration FPR {task} {method} {fold}")
                close(float(row["component_sensitivity_99.5"]), sensitivity, f"cycle sensitivity {task} {method} {fold}")
                require(
                    int(row["evaluation_positive_records"]) == len(positive_rows)
                    and int(row["evaluation_positive_components"]) == len({r["global_component_id"] for r in positive_rows})
                    and int(row["evaluation_negative_records"]) == len(negative_evaluation)
                    and int(row["calibration_negative_records"]) == len(negative_calibration),
                    f"cycle class counts {task} {method} {fold}",
                )
                primary_threshold_key = (task, method, str(fold), f"{specificity:.4f}")
                threshold_row = thresholds[primary_threshold_key]
                ladder_row = ladder[primary_threshold_key]
                require(float(threshold_row["threshold"]) == threshold, f"threshold table point {task} {method} {fold}")
                close(float(ladder_row["component_balanced_sensitivity"]), sensitivity, f"ladder sensitivity {task} {method} {fold}")
                close(float(ladder_row["observed_source_balanced_specificity"]), observed_specificity, f"ladder specificity {task} {method} {fold}")
                fold_ap.append(ap)
                fold_sensitivity.append(sensitivity)
                fold_record_sensitivity.append(record_sensitivity)
                fold_specificity.append(observed_specificity)
                all_eval_rows.extend(evaluation_rows)
                no_hit += sum(score == -math.inf for score in evaluation_scores)

            macro_ap = sum(fold_ap) / fold_count
            macro_sensitivity = sum(fold_sensitivity) / fold_count
            primary_row = primary[(task, method)]
            require(
                primary_row["track"] == TRACK[method]
                and primary_row["primary_eligible"] == ("1" if method in CONTROLLED else "0"),
                f"primary track/eligibility {task} {method}",
            )
            require(
                primary_row["primary_sensitivity_inference_status"]
                == resolution[task]["primary_sensitivity_inference_status"],
                f"primary sensitivity inference status {task} {method}",
            )
            close(float(primary_row["fold_macro_component_ap"]), macro_ap, f"primary AP {task} {method}")
            close(float(primary_row["fold_component_ap_min"]), min(fold_ap), f"primary AP min {task} {method}")
            close(float(primary_row["fold_component_ap_max"]), max(fold_ap), f"primary AP max {task} {method}")
            try:
                released_fold_ap = json.loads(primary_row["fold_component_ap_values"])
            except json.JSONDecodeError:
                fail(f"malformed fold AP vector: {task} {method}")
            require(isinstance(released_fold_ap, list) and len(released_fold_ap) == fold_count, f"fold AP vector shape {task} {method}")
            for index, (observed, expected) in enumerate(zip(released_fold_ap, fold_ap), 1):
                close(float(observed), expected, f"fold AP vector {task} {method} {index}")
            close(
                float(primary_row["fold_macro_component_sensitivity_at_primary_specificity"]),
                macro_sensitivity,
                f"primary sensitivity {task} {method}",
            )
            close(float(primary_row["fold_component_sensitivity_min"]), min(fold_sensitivity), f"primary sensitivity min {task} {method}")
            close(float(primary_row["fold_component_sensitivity_max"]), max(fold_sensitivity), f"primary sensitivity max {task} {method}")
            close(float(primary_row["fold_macro_record_sensitivity_at_primary_specificity"]), sum(fold_record_sensitivity) / fold_count, f"primary record sensitivity {task} {method}")
            close(float(primary_row["fold_macro_observed_source_balanced_specificity"]), sum(fold_specificity) / fold_count, f"primary observed specificity {task} {method}")
            require(
                int(primary_row["records"]) == len(all_eval_rows)
                and int(primary_row["positive_records"]) == sum(row[label_field] == "1" for row in all_eval_rows)
                and int(primary_row["positive_components"]) == len({row["global_component_id"] for row in all_eval_rows if row[label_field] == "1"})
                and int(primary_row["no_hit_evaluation_records"]) == no_hit
                and math.isclose(float(primary_row["primary_specificity_target"]), specificity),
                f"primary counts/specificity {task} {method}",
            )
            recomputed[(task, method)] = {
                "fold_ap": fold_ap,
                "macro_ap": macro_ap,
                "macro_sensitivity": macro_sensitivity,
            }
    return recomputed, len(cycles), len(primary)


def validate_paired(
    benchmark_root: Path,
    config: Mapping[str, object],
    points: Mapping[tuple[str, str], Mapping[str, object]],
) -> int:
    fields, rows = read_tsv(benchmark_root / "results/paired_deltas.tsv")
    required = {
        "task", "anchor_method", "comparator_method", "baseline_method",
        "comparison_registry_status", "point_delta_component_sensitivity",
        "bootstrap_delta_ci95_low", "bootstrap_delta_ci95_high", "bootstrap_replicates",
        "point_delta_fold_macro_component_ap", "bootstrap_ap_delta_ci95_low",
        "bootstrap_ap_delta_ci95_high", "fold_ap_delta_min", "fold_ap_delta_max",
        "sensitivity_metric", "ap_metric", "ap_inference_status",
        "sensitivity_inference_status", "sensitivity_resolution_note",
        "inference_status",
    }
    require(required <= set(fields), "paired delta schema incomplete")
    require(not any(FORBIDDEN_FIELD.search(field) for field in fields), "paired table contains p/Holm field")
    expected = {(task, method) for task in TASKS for method in CLASSICAL_ANCHORS}
    seen: set[tuple[str, str]] = set()
    summary = read_json(benchmark_root / "results/summary.json")
    resolution = summary.get("resolution_audit")
    require(isinstance(resolution, dict), "summary resolution audit absent")
    for row in rows:
        key = (row["task"], row["comparator_method"])
        require(key in expected and key not in seen, f"unexpected/duplicate paired comparison: {key}")
        seen.add(key)
        task, comparator = key
        require(
            row["anchor_method"] == "esmc6b_cosine"
            and row["baseline_method"] == comparator
            and row["comparison_registry_status"] == "PRE_REGISTERED_CONTROLLED_ANCHOR_COMPARISON",
            f"paired comparison identity: {key}",
        )
        require(
            row["sensitivity_metric"]
            == "fold_macro_component_sensitivity_at_0.995_specificity"
            and row["ap_metric"]
            == "fold_macro_component_balanced_average_precision",
            f"paired metric identity: {key}",
        )
        anchor = points[(task, "esmc6b_cosine")]
        baseline = points[(task, comparator)]
        sensitivity_delta = float(anchor["macro_sensitivity"]) - float(baseline["macro_sensitivity"])
        ap_delta = float(anchor["macro_ap"]) - float(baseline["macro_ap"])
        close(float(row["point_delta_component_sensitivity"]), sensitivity_delta, f"paired sensitivity point {key}")
        close(float(row["point_delta_fold_macro_component_ap"]), ap_delta, f"paired AP point {key}")
        fold_deltas = [
            float(a) - float(b)
            for a, b in zip(anchor["fold_ap"], baseline["fold_ap"])
        ]
        close(float(row["fold_ap_delta_min"]), min(fold_deltas), f"paired AP min {key}")
        close(float(row["fold_ap_delta_max"]), max(fold_deltas), f"paired AP max {key}")
        sensitivity_low = float(row["bootstrap_delta_ci95_low"])
        sensitivity_high = float(row["bootstrap_delta_ci95_high"])
        ap_low = float(row["bootstrap_ap_delta_ci95_low"])
        ap_high = float(row["bootstrap_ap_delta_ci95_high"])
        require(
            all(math.isfinite(value) and -1.0 <= value <= 1.0 for value in (sensitivity_low, sensitivity_high, ap_low, ap_high))
            and sensitivity_low <= sensitivity_high
            and ap_low <= ap_high,
            f"paired CI order/range: {key}",
        )
        require(int(row["bootstrap_replicates"]) == int(config["parameters"]["bootstrap_replicates"]), f"paired replicate count: {key}")
        require(row["ap_inference_status"] == "PAIRED_COMPONENT_BOOTSTRAP_CI_NO_NULL_P_VALUE", f"paired AP status: {key}")
        require(row["sensitivity_inference_status"] == resolution[task]["primary_sensitivity_inference_status"], f"paired sensitivity resolution: {key}")
        require(
            row["sensitivity_resolution_note"] == resolution[task]["bootstrap_caveat"],
            f"paired sensitivity resolution note: {key}",
        )
        require(row["inference_status"] == "METRIC_SPECIFIC_STATUS_REQUIRED", f"paired inference status: {key}")
    require(seen == expected and len(rows) == 12, "paired comparison coverage")
    registered = summary.get("registered_comparisons")
    require(isinstance(registered, list) and len(registered) == 12, "summary paired comparison registry")
    return len(rows)


def validate_no_inferential_fields(results: Path) -> None:
    for path in sorted(results.glob("*.tsv")):
        fields, _ = read_tsv(path)
        require(not any(FORBIDDEN_FIELD.search(field) for field in fields), f"p/Holm field in {path.name}")
    def keys(value: object) -> Iterable[str]:
        if isinstance(value, dict):
            for key, child in value.items():
                yield str(key)
                yield from keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from keys(child)
    summary = read_json(results / "summary.json")
    require(not any(FORBIDDEN_FIELD.search(key) for key in keys(summary)), "p/Holm JSON key")


def validate_final_metrics(
    benchmark_root: Path, config: Mapping[str, object]
) -> dict[str, object]:
    """Validate all released point metrics and return a JSON-safe audit summary."""

    benchmark_root = benchmark_root.resolve()
    _, cohort = read_tsv(benchmark_root / "inputs/cohort.tsv")
    require(len(cohort) == 6634, "cohort record count")
    fold_count = int(config["parameters"]["folds"])
    offset = int(config["parameters"]["calibration_fold_offset"])
    require(fold_count == 5 and math.isclose(float(config["parameters"]["primary_specificity"]), 0.995), "frozen metric design drift")
    scores, query_rows = load_exact_scores(benchmark_root, cohort, fold_count, offset)
    points, cycle_rows, primary_rows = validate_point_metrics(
        benchmark_root, config, cohort, scores
    )
    paired_rows = validate_paired(benchmark_root, config, points)
    validate_no_inferential_fields(benchmark_root / "results")
    return {
        "status": "PASS",
        "independent_implementation": True,
        "bootstrap_recomputed": False,
        "bootstrap_validation": "CI schema, finite range, ordering, replicate count, comparison registry, and point deltas validated",
        "raw_score_rows": len(scores),
        "query_score_rows": query_rows,
        "metrics_cycle_rows": cycle_rows,
        "metrics_primary_rows": primary_rows,
        "paired_delta_rows": paired_rows,
        "methods": len(METHODS),
        "tasks": len(TASKS),
        "primary_specificity": 0.995,
    }
