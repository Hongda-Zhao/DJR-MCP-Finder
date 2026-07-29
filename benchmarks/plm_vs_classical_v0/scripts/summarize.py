#!/usr/bin/env python3
"""Summarize the cyclic 3-fit/1-calibration/1-evaluation benchmark.

The controlled headline is deliberately restricted to pre-registered comparisons of
ESM-C 6B cosine retrieval against each classical anchor.  Calibration and evaluation
rows are keyed by evaluation cycle and are never pooled across roles.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.metrics import average_precision_score

from common import (
    TASKS,
    atomic_json,
    cyclic_fold_roles,
    load_config,
    parse_score,
    read_tsv,
    score_text,
    sha256_file,
    write_tsv,
)


CONTROLLED_PRIMARY = [
    "esmc6b_cosine",
    "esm2_650m_cosine",
    "blastp",
    "diamond_ultra",
    "mmseqs_s7.5",
    "hmmer_component",
]
CLASSICAL_ANCHORS = ["blastp", "diamond_ultra", "mmseqs_s7.5", "hmmer_component"]
PSI_METHOD = "psiblast_longest_seed_positiveDB_3iter"
RESOURCE_AUGMENTED_SECONDARY = [PSI_METHOD]
METADATA_SECONDARY = ["hmmer_family"]
OPERATIONAL_DESCRIPTIVE = ["esmc6b_supervised"]
ALL_METHODS = [
    *CONTROLLED_PRIMARY,
    *RESOURCE_AUGMENTED_SECONDARY,
    *METADATA_SECONDARY,
    *OPERATIONAL_DESCRIPTIVE,
]
METHOD_ALIASES = {
    "psiblast_component_3iter": "psiblast_longest_seed_positiveDB_3iter",
}

METHOD_SPECS = {
    "esmc6b_cosine": {
        "track": "controlled_primary",
        "native_score": "maximum cosine similarity",
        "information_budget": "fit-fold positive reference IDs only",
        "primary_eligible": "1",
        "inference_role": "primary_anchor",
        "external_pretraining_exposure": "model_dependent",
    },
    "esm2_650m_cosine": {
        "track": "controlled_primary",
        "native_score": "maximum cosine similarity",
        "information_budget": "fit-fold positive reference IDs only",
        "primary_eligible": "1",
        "inference_role": "controlled_plm_comparator",
        "external_pretraining_exposure": "model_dependent",
    },
    "blastp": {
        "track": "controlled_primary",
        "native_score": "maximum bit score",
        "information_budget": "fit-fold positive reference IDs only",
        "primary_eligible": "1",
        "inference_role": "pre_registered_classical_anchor",
        "external_pretraining_exposure": "none_for_task_specific_database",
    },
    "diamond_ultra": {
        "track": "controlled_primary",
        "native_score": "maximum bit score",
        "information_budget": "fit-fold positive reference IDs only",
        "primary_eligible": "1",
        "inference_role": "pre_registered_classical_anchor",
        "external_pretraining_exposure": "none_for_task_specific_database",
    },
    "mmseqs_s7.5": {
        "track": "controlled_primary",
        "native_score": "maximum bit score",
        "information_budget": "fit-fold positive reference IDs only",
        "primary_eligible": "1",
        "inference_role": "pre_registered_classical_anchor",
        "external_pretraining_exposure": "none_for_task_specific_database",
    },
    "hmmer_component": {
        "track": "controlled_primary",
        "native_score": "maximum full-sequence HMM bit score",
        "information_budget": "fit-fold positives grouped only by global component",
        "primary_eligible": "1",
        "inference_role": "pre_registered_classical_anchor",
        "external_pretraining_exposure": "none_for_task_specific_database",
    },
    "psiblast_longest_seed_positiveDB_3iter": {
        "track": "resource_augmented_secondary",
        "native_score": "maximum frozen-PSSM bit score",
        "information_budget": "longest positive seed plus positive-only database; three iterations",
        "primary_eligible": "0",
        "inference_role": "secondary_descriptive",
        "external_pretraining_exposure": "none_for_task_specific_database",
    },
    "hmmer_family": {
        "track": "metadata_augmented_secondary",
        "native_score": "maximum full-sequence HMM bit score",
        "information_budget": "fit-fold positives plus frozen family/taxonomy grouping metadata",
        "primary_eligible": "0",
        "inference_role": "secondary_descriptive",
        "external_pretraining_exposure": "none_for_task_specific_database",
    },
    "esmc6b_supervised": {
        "track": "operational_descriptive",
        "native_score": "fit-once head logit or nested tail-evidence cascade",
        "information_budget": "three fit folds with labelled positives and negatives",
        "primary_eligible": "0",
        "inference_role": "operational_descriptive_only",
        "external_pretraining_exposure": "model_dependent",
    },
}


def normalize_method(value: str) -> str:
    return METHOD_ALIASES.get(value, value)


def finite_ranking_score(values: np.ndarray) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64).copy()
    if np.isnan(result).any() or np.isposinf(result).any():
        raise ValueError("Ranking score contains NA/+inf")
    finite = result[np.isfinite(result)]
    floor = (
        float(np.min(finite) - max(1.0, abs(float(np.min(finite))) * 1e-6))
        if len(finite)
        else -1.0
    )
    result[np.isneginf(result)] = floor
    return result


def component_weights(rows: list[dict[str, str]]) -> np.ndarray:
    if not rows:
        raise ValueError("Cannot weight an empty row set")
    counts = Counter(row["global_component_id"] for row in rows)
    return np.asarray(
        [1.0 / counts[row["global_component_id"]] for row in rows], dtype=np.float64
    )


def source_component_weights(rows: list[dict[str, str]]) -> np.ndarray:
    sources = sorted({row["source_dataset"] for row in rows})
    if not sources:
        raise ValueError("Cannot weight an empty calibration set")
    source_components: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        source_components[row["source_dataset"]][row["global_component_id"]] += 1
    component_counts = {source: len(values) for source, values in source_components.items()}
    return np.asarray(
        [
            1.0
            / len(sources)
            / component_counts[row["source_dataset"]]
            / source_components[row["source_dataset"]][row["global_component_id"]]
            for row in rows
        ],
        dtype=np.float64,
    )


def conservative_threshold(
    scores: np.ndarray, weights: np.ndarray, specificity: float
) -> tuple[float, float]:
    """Return an inclusive threshold while excluding the first unaffordable tie.

    With prediction ``score >= threshold``, setting the threshold to infinity when
    the highest negative tie is too large would incorrectly reject positive scores
    above the largest negative.  ``nextafter(rejected_score, +inf)`` expresses the
    exact conservative boundary at every rejected tie, including the highest one.
    Zero-mass rows (which occur in bootstrap resamples) do not define support.
    """

    score = np.asarray(scores, dtype=np.float64)
    weight = np.asarray(weights, dtype=np.float64)
    if (
        len(score) == 0
        or len(score) != len(weight)
        or np.isnan(score).any()
        or np.isposinf(score).any()
    ):
        raise ValueError("Invalid threshold inputs")
    if np.any(weight < 0) or not np.isfinite(weight).all() or weight.sum() <= 0:
        raise ValueError("Invalid threshold weights")
    keep = weight > 0
    score = score[keep]
    weight = weight[keep] / weight[keep].sum()
    allowed_fpr = 1.0 - specificity
    achieved_fpr = 0.0
    for value in sorted(set(score.tolist()), reverse=True):
        tie_weight = float(weight[score == value].sum())
        if achieved_fpr + tie_weight <= allowed_fpr + 1e-15:
            achieved_fpr += tie_weight
            continue
        return float(np.nextafter(value, math.inf)), achieved_fpr
    raise RuntimeError("Threshold calibration consumed all negative mass")


def batched_conservative_thresholds(
    scores: np.ndarray, weights: np.ndarray, specificity: float
) -> tuple[np.ndarray, np.ndarray]:
    """Vectorized form of :func:`conservative_threshold` for bootstrap batches."""

    score = np.asarray(scores, dtype=np.float64)
    weight = np.asarray(weights, dtype=np.float64)
    if weight.ndim != 2 or weight.shape[1] != len(score):
        raise ValueError("Bootstrap threshold shape mismatch")
    if np.isnan(score).any() or np.isposinf(score).any():
        raise ValueError("Invalid bootstrap calibration score")
    if np.any(weight < 0) or not np.isfinite(weight).all():
        raise ValueError("Invalid bootstrap calibration weights")
    order = np.argsort(-score, kind="stable")
    ordered_scores = score[order]
    ordered_weights = weight[:, order]
    starts = np.flatnonzero(
        np.r_[True, ordered_scores[1:] != ordered_scores[:-1]]
    )
    group_scores = ordered_scores[starts]
    group_weights = np.add.reduceat(ordered_weights, starts, axis=1)
    cumulative = np.cumsum(group_weights, axis=1)
    rejected = (group_weights > 0) & (cumulative > (1.0 - specificity) + 1e-15)
    if not np.all(np.any(rejected, axis=1)):
        raise RuntimeError("Bootstrap threshold calibration consumed all negative mass")
    first_rejected = np.argmax(rejected, axis=1)
    thresholds = np.nextafter(group_scores[first_rejected], math.inf)
    achieved = np.zeros(len(weight), dtype=np.float64)
    has_previous = first_rejected > 0
    achieved[has_previous] = cumulative[
        np.flatnonzero(has_previous), first_rejected[has_previous] - 1
    ]
    return thresholds.astype(np.float64), achieved


def task_rows(rows: list[dict[str, str]], task: str) -> list[dict[str, str]]:
    if TASKS[task]["eligible"] == "djr":
        return [row for row in rows if row["is_djr"] == "1"]
    return list(rows)


def endpoint_status(specificity: float, primary: float) -> str:
    if math.isclose(specificity, 0.999):
        return "RESOLUTION_LIMITED_SECONDARY"
    if math.isclose(specificity, primary):
        return "PRIMARY"
    return "SECONDARY"


def calibration_resolution_status(
    rows: list[dict[str, str]], weights: np.ndarray, specificity: float
) -> tuple[str, float]:
    """Describe empirical FPR granularity without changing the frozen endpoint.

    Thresholds operate on records, whereas uncertainty resamples whole global
    components.  A single-component negative source is therefore a distinct
    limitation even when that component contains many records.  The minimum
    non-zero row weight records whether *any* empirical false positive can fit
    inside the requested global FPR budget before score ties are considered.
    """

    if not rows or len(rows) != len(weights):
        raise ValueError("Invalid calibration-resolution inputs")
    weight = np.asarray(weights, dtype=np.float64)
    if np.any(weight <= 0) or not np.isfinite(weight).all():
        raise ValueError("Calibration-resolution weights must be finite and positive")
    minimum_row_mass = float(np.min(weight))
    component_count = len({row["global_component_id"] for row in rows})
    zero_fp_granularity = minimum_row_mass > (1.0 - specificity) + 1e-15
    if component_count == 1 and zero_fp_granularity:
        status = "CALIBRATION_RESOLUTION_LIMITED_SINGLE_COMPONENT_ZERO_FP"
    elif component_count == 1:
        status = "CALIBRATION_RESOLUTION_LIMITED_SINGLE_COMPONENT"
    elif zero_fp_granularity:
        status = "CALIBRATION_ZERO_FP_ROW_RESOLUTION_LIMITED"
    else:
        status = "CALIBRATION_NONZERO_FP_ROW_RESOLVABLE"
    return status, minimum_row_mass


def evaluation_resolution_status(rows: list[dict[str, str]]) -> str:
    component_count = len({row["global_component_id"] for row in rows})
    if component_count == 1:
        return "EVALUATION_RESOLUTION_LIMITED_SINGLE_COMPONENT"
    if component_count < 20:
        return "EVALUATION_LOW_COMPONENT_N"
    return "EVALUATION_DESCRIPTIVE"


def checked_ap(y: np.ndarray, score: np.ndarray, weights: np.ndarray | None = None) -> float:
    if set(np.unique(y).tolist()) != {0, 1}:
        raise RuntimeError("Average precision requires both classes in every evaluation fold")
    return float(average_precision_score(y, finite_ranking_score(score), sample_weight=weights))


@dataclass(frozen=True)
class ComponentAPPlan:
    """Sparse component-by-score-tie masses for a fold-specific AP estimand."""

    global_component_indices: np.ndarray
    positive_mass_by_tie: csr_matrix
    negative_mass_by_tie: csr_matrix
    descending_tie_scores: np.ndarray


def prepare_component_ap_plan(
    rows: list[dict[str, str]],
    y: np.ndarray,
    scores: np.ndarray,
    global_component_index: dict[str, int],
) -> ComponentAPPlan:
    labels = np.asarray(y, dtype=np.int8)
    ranking_score = finite_ranking_score(np.asarray(scores, dtype=np.float64))
    if len(rows) != len(labels) or len(labels) != len(ranking_score):
        raise ValueError("AP plan length mismatch")
    if set(np.unique(labels).tolist()) != {0, 1}:
        raise ValueError("AP plan requires both classes")

    components = sorted({row["global_component_id"] for row in rows})
    local_index = {component: index for index, component in enumerate(components)}
    row_component = np.asarray(
        [local_index[row["global_component_id"]] for row in rows], dtype=np.int64
    )
    component_record_count = np.bincount(
        row_component, minlength=len(components)
    ).astype(np.float64)
    record_fraction = 1.0 / component_record_count[row_component]

    order = np.argsort(ranking_score, kind="mergesort")[::-1]
    sorted_score = ranking_score[order]
    new_group = np.r_[True, sorted_score[1:] != sorted_score[:-1]]
    sorted_group = np.cumsum(new_group) - 1
    row_group = np.empty(len(rows), dtype=np.int64)
    row_group[order] = sorted_group
    group_count = int(sorted_group[-1]) + 1

    def mass_matrix(label: int) -> csr_matrix:
        selected = np.flatnonzero(labels == label)
        matrix = csr_matrix(
            (
                record_fraction[selected],
                (row_component[selected], row_group[selected]),
            ),
            shape=(len(components), group_count),
            dtype=np.float64,
        )
        matrix.sum_duplicates()
        matrix.sort_indices()
        return matrix

    positive = mass_matrix(1)
    negative = mass_matrix(0)
    component_mass = np.asarray((positive + negative).sum(axis=1)).ravel()
    # Sparse accumulation order depends on the score-tie pattern.  A component
    # with hundreds of records can therefore differ from its exact unit mass by
    # a few dozen float64 ulps (observed maximum: 1.14e-14 for 470 records).
    # Keep this fail-closed for material errors while accepting bounded
    # representation roundoff.
    mass_error = np.abs(component_mass - 1.0)
    max_mass_error = float(np.max(mass_error, initial=0.0))
    if (
        not np.all(np.isfinite(component_mass))
        or max_mass_error > 1e-12
    ):
        raise RuntimeError(
            "Component AP mass does not sum to one; "
            f"max_abs_error={max_mass_error:.17g}"
        )
    return ComponentAPPlan(
        global_component_indices=np.asarray(
            [global_component_index[value] for value in components], dtype=np.int64
        ),
        positive_mass_by_tie=positive,
        negative_mass_by_tie=negative,
        descending_tie_scores=sorted_score[new_group],
    )


def batched_component_average_precision(
    global_multiplicities: np.ndarray, plan: ComponentAPPlan
) -> np.ndarray:
    local = np.asarray(
        global_multiplicities[:, plan.global_component_indices], dtype=np.float64
    )
    positive_by_tie = np.asarray(local @ plan.positive_mass_by_tie)
    negative_by_tie = np.asarray(local @ plan.negative_mass_by_tie)
    cumulative_positive = np.cumsum(positive_by_tie, axis=1, dtype=np.float64)
    cumulative_negative = np.cumsum(negative_by_tie, axis=1, dtype=np.float64)
    total_positive = cumulative_positive[:, -1]
    total_negative = cumulative_negative[:, -1]
    if np.any(total_positive <= 0) or np.any(total_negative <= 0):
        raise RuntimeError("Bootstrap AP replicate lost a class")
    positive_increment = np.diff(
        np.concatenate(
            [np.zeros((len(local), 1), dtype=np.float64), cumulative_positive], axis=1
        ),
        axis=1,
    )
    denominator = cumulative_positive + cumulative_negative
    precision = np.divide(
        cumulative_positive,
        denominator,
        out=np.zeros_like(cumulative_positive),
        where=denominator > 0,
    )
    return np.sum(positive_increment * precision, axis=1) / total_positive


def normalize_registry_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized = []
    for row in rows:
        value = dict(row)
        if "method" in value:
            value["method"] = normalize_method(value["method"])
        normalized.append(value)
    return normalized


def stable_json_sha(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def is_sha256(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", value))


def write_union_tsv(path: Path, sources: list[tuple[str, list[dict[str, str]]]]) -> None:
    fields = ["source_registry"]
    seen = set(fields)
    output: list[dict[str, str]] = []
    for source_name, rows in sources:
        for row in normalize_registry_rows(rows):
            value = {"source_registry": source_name, **row}
            output.append(value)
            for field in value:
                if field not in seen:
                    fields.append(field)
                    seen.add(field)
    write_tsv(path, output, fields)


def component_bootstrap_strata(
    cohort: list[dict[str, str]], component_index: dict[str, int]
) -> list[np.ndarray]:
    """Build fixed strata while retaining each global component as one block."""

    by_component: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in cohort:
        by_component[row["global_component_id"]].append(row)
    grouped: dict[tuple, list[int]] = defaultdict(list)
    for component, rows in by_component.items():
        folds = {int(row["fold"]) for row in rows}
        if len(folds) != 1:
            raise RuntimeError(f"Component spans folds: {component}")
        signature = (
            next(iter(folds)),
            tuple(
                sorted(
                    {
                        (row["source_dataset"], row["is_djr"], row["is_vma"])
                        for row in rows
                    }
                )
            ),
        )
        grouped[signature].append(component_index[component])
    return [np.asarray(sorted(indices), dtype=np.int64) for _, indices in sorted(grouped.items())]


def draw_global_component_multiplicities(
    rng: np.random.Generator,
    strata: list[np.ndarray],
    batch_size: int,
    component_count: int,
) -> np.ndarray:
    """Draw each replicate once globally, stratified by immutable component signature."""

    result = np.zeros((batch_size, component_count), dtype=np.float64)
    for indices in strata:
        count = len(indices)
        if count == 1:
            result[:, indices[0]] = 1.0
        else:
            result[:, indices] = rng.multinomial(
                count, np.full(count, 1.0 / count), size=batch_size
            )
    return result


def bootstrap_calibration_weights(
    multiplicities: np.ndarray, cycle: dict
) -> np.ndarray:
    raw = multiplicities[:, cycle["cal_component_index"]] / cycle[
        "cal_record_denominator"
    ][None, :]
    weights = np.zeros_like(raw)
    active_source_count = np.zeros(len(raw), dtype=np.float64)
    for mask in cycle["cal_source_masks"]:
        source_total = raw[:, mask].sum(axis=1)
        active = source_total > 0
        active_source_count += active
        if np.any(active):
            local = weights[:, mask]
            local[active, :] = raw[:, mask][active, :] / source_total[active, None]
            weights[:, mask] = local
    if np.any(active_source_count == 0):
        raise RuntimeError("A global bootstrap draw removed every calibration source")
    weights /= active_source_count[:, None]
    if not np.allclose(weights.sum(axis=1), 1.0, atol=1e-12):
        raise RuntimeError("Bootstrap source-component weights do not sum to one")
    return weights


def bootstrap_evaluation_sensitivity(
    multiplicities: np.ndarray,
    cycle: dict,
    scores: np.ndarray,
    thresholds: np.ndarray,
) -> np.ndarray:
    row_weights = multiplicities[:, cycle["eval_positive_component_index"]] / cycle[
        "eval_positive_record_denominator"
    ][None, :]
    denominator = multiplicities[:, cycle["eval_positive_unique_component_index"]].sum(
        axis=1
    )
    if np.any(denominator <= 0):
        raise RuntimeError("A bootstrap stratum lost all positive evaluation components")
    detected = scores[None, :] >= thresholds[:, None]
    return np.sum(row_weights * detected, axis=1) / denominator


def bootstrap_primary_metrics_global(
    cohort: list[dict[str, str]],
    cycles: dict[str, dict[int, dict]],
    methods: list[str],
    specificity: float,
    replicates: int,
    seed: int,
    batch_size: int = 64,
) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, dict[str, np.ndarray]]]:
    """Paired sensitivity and AP bootstrap with one global draw per replicate.

    A replicate's component multiplicity is reused wherever that component appears:
    in calibration for one cycle, in evaluation for another cycle, and across every
    task and method.  Each method-specific threshold is recalculated in that draw.
    """

    components = sorted({row["global_component_id"] for row in cohort})
    component_index = {component: index for index, component in enumerate(components)}
    strata = component_bootstrap_strata(cohort, component_index)
    ap_plans: dict[str, dict[int, dict[str, ComponentAPPlan]]] = defaultdict(
        lambda: defaultdict(dict)
    )

    for task, task_cycles in cycles.items():
        for evaluation_fold, cycle in task_cycles.items():
            cal_rows = cycle["calibration_negative_rows"]
            cal_counts = Counter(
                (row["source_dataset"], row["global_component_id"]) for row in cal_rows
            )
            cycle["cal_component_index"] = np.asarray(
                [component_index[row["global_component_id"]] for row in cal_rows],
                dtype=np.int64,
            )
            cycle["cal_record_denominator"] = np.asarray(
                [
                    cal_counts[(row["source_dataset"], row["global_component_id"])]
                    for row in cal_rows
                ],
                dtype=np.float64,
            )
            cycle["cal_source_masks"] = [
                np.asarray(
                    [row["source_dataset"] == source for row in cal_rows], dtype=bool
                )
                for source in sorted({row["source_dataset"] for row in cal_rows})
            ]

            positive_rows = cycle["evaluation_positive_rows"]
            positive_counts = Counter(row["global_component_id"] for row in positive_rows)
            cycle["eval_positive_component_index"] = np.asarray(
                [component_index[row["global_component_id"]] for row in positive_rows],
                dtype=np.int64,
            )
            cycle["eval_positive_record_denominator"] = np.asarray(
                [positive_counts[row["global_component_id"]] for row in positive_rows],
                dtype=np.float64,
            )
            cycle["eval_positive_unique_component_index"] = np.asarray(
                [component_index[value] for value in sorted(positive_counts)], dtype=np.int64
            )

            for method in methods:
                plan = prepare_component_ap_plan(
                    cycle["evaluation_rows"],
                    cycle["evaluation_y"],
                    cycle["evaluation_scores"][method],
                    component_index,
                )
                observed = batched_component_average_precision(
                    np.ones((1, len(components)), dtype=np.float64), plan
                )[0]
                expected = checked_ap(
                    cycle["evaluation_y"],
                    cycle["evaluation_scores"][method],
                    component_weights(cycle["evaluation_rows"]),
                )
                if not np.isclose(observed, expected, rtol=1e-13, atol=1e-15):
                    raise RuntimeError(
                        f"AP bootstrap plan disagrees with point estimator: "
                        f"{task} cycle {evaluation_fold} {method}"
                    )
                ap_plans[task][evaluation_fold][method] = plan

    sensitivity_output = {
        task: {method: np.empty(replicates, dtype=np.float64) for method in methods}
        for task in cycles
    }
    ap_output = {
        task: {method: np.empty(replicates, dtype=np.float64) for method in methods}
        for task in cycles
    }
    rng = np.random.default_rng(seed)
    fold_count = len(next(iter(cycles.values())))
    for start in range(0, replicates, batch_size):
        stop = min(start + batch_size, replicates)
        size = stop - start
        multiplicities = draw_global_component_multiplicities(
            rng, strata, size, len(components)
        )
        for task, task_cycles in cycles.items():
            sampled_sensitivity = {
                method: np.zeros(size, dtype=np.float64) for method in methods
            }
            sampled_ap = {method: np.zeros(size, dtype=np.float64) for method in methods}
            for evaluation_fold, cycle in task_cycles.items():
                calibration_weights = bootstrap_calibration_weights(
                    multiplicities, cycle
                )
                for method in methods:
                    threshold, _ = batched_conservative_thresholds(
                        cycle["calibration_negative_scores"][method],
                        calibration_weights,
                        specificity,
                    )
                    sampled_sensitivity[method] += bootstrap_evaluation_sensitivity(
                        multiplicities,
                        cycle,
                        cycle["evaluation_positive_scores"][method],
                        threshold,
                    ) / fold_count
                    sampled_ap[method] += batched_component_average_precision(
                        multiplicities, ap_plans[task][evaluation_fold][method]
                    ) / fold_count
            for method in methods:
                sensitivity_output[task][method][start:stop] = sampled_sensitivity[method]
                ap_output[task][method][start:stop] = sampled_ap[method]
    return sensitivity_output, ap_output


def blast_local_distance_strata(
    benchmark_root: Path,
    task: str,
    evaluation_rows: list[dict[str, str]],
    fold_count: int,
) -> dict[str, str]:
    """Assign descriptive strata using each query's evaluation-cycle BLAST result."""

    reference = TASKS[task]["reference"]
    expected_fold = {row["protein_id"]: int(row["fold"]) for row in evaluation_rows}
    best: dict[str, tuple[float, float, float]] = {}
    for evaluation_fold in range(1, fold_count + 1):
        path = (
            benchmark_root
            / f"work/classical/fold_{evaluation_fold}/{reference}/pairwise/blastp.hits.tsv"
        )
        if not path.is_file():
            raise FileNotFoundError(f"Missing BLAST distance receipt: {path}")
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip() or line.startswith("#"):
                    continue
                fields = line.rstrip("\n").split("\t")
                if len(fields) != 6:
                    raise ValueError(f"Malformed BLAST distance row at {path}:{line_number}")
                query = fields[0]
                if expected_fold.get(query) != evaluation_fold:
                    continue
                bitscore, pident, qcov = float(fields[2]), float(fields[4]), float(fields[5])
                if query not in best or bitscore > best[query][0]:
                    best[query] = (bitscore, pident, qcov)
    strata = {}
    for row in evaluation_rows:
        protein_id = row["protein_id"]
        if protein_id not in best:
            strata[protein_id] = "no_blast_hit_at_evalue_1000"
            continue
        _, pident, qcov = best[protein_id]
        if qcov < 80.0:
            strata[protein_id] = "best_local_qcov_lt80"
        elif pident < 20.0:
            strata[protein_id] = "best_local_qcov_ge80_pident_lt20"
        elif pident < 30.0:
            strata[protein_id] = "best_local_qcov_ge80_pident_20_to_lt30"
        else:
            strata[protein_id] = "best_local_qcov_ge80_pident_ge30"
    return strata


def method_registry(profile_members: list[dict[str, str]]) -> list[dict[str, str]]:
    singleton = Counter(
        normalize_method(row.get("method", ""))
        for row in profile_members
        if row.get("singleton_profile") == "1"
    )
    profile_counts = Counter()
    profiles_by_method: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    for row in profile_members:
        method = normalize_method(row.get("method", ""))
        profiles_by_method[method].add(
            (
                row.get("evaluation_fold", row.get("fold", "")),
                row.get("reference_kind", ""),
                row.get("profile_id", ""),
            )
        )
    for method, values in profiles_by_method.items():
        profile_counts[method] = len(values)
    result = []
    for method in ALL_METHODS:
        spec = METHOD_SPECS[method]
        result.append(
            {
                "method": method,
                "track": spec["track"],
                "native_score": spec["native_score"],
                "task_specific_information": spec["information_budget"],
                "primary_eligible": spec["primary_eligible"],
                "inference_role": spec["inference_role"],
                "profile_count_all_cycles_tasks": str(profile_counts[method]),
                "singleton_member_rows_all_cycles_tasks": str(singleton[method]),
                "external_pretraining_exposure": spec["external_pretraining_exposure"],
            }
        )
    return result


def profile_summary_rows(
    profile_members: list[dict[str, str]],
    seed_registry: list[dict[str, str]],
    artifact_registry: list[dict[str, str]],
) -> list[dict[str, str]]:
    grouped_members: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in normalize_registry_rows(profile_members):
        grouped_members[(row.get("method", ""), row.get("reference_kind", ""))].append(row)
    grouped_seeds: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in normalize_registry_rows(seed_registry):
        grouped_seeds[(row.get("method", ""), row.get("reference_kind", ""))].append(row)
    grouped_artifacts: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in normalize_registry_rows(artifact_registry):
        grouped_artifacts[(row.get("method", ""), row.get("reference_kind", ""))].append(row)
    result = []
    for key in sorted(set(grouped_members) | set(grouped_seeds) | set(grouped_artifacts)):
        members = grouped_members[key]
        seeds = grouped_seeds[key]
        artifacts = grouped_artifacts[key]
        fold = lambda row: row.get("evaluation_fold", row.get("fold", ""))
        profiles = {
            (fold(row), row.get("profile_id", "")) for row in members if row.get("profile_id", "")
        }
        seed_profiles = {
            (fold(row), row.get("profile_id", row.get("seed_profile_id", "")))
            for row in seeds
        }
        artifact_profiles = {
            (fold(row), row.get("profile_id", ""))
            for row in artifacts
            if row.get("profile_id", "")
        }
        result.append(
            {
                "method": key[0],
                "reference_kind": key[1],
                "evaluation_cycles": str(
                    len({fold(row) for row in [*members, *seeds, *artifacts] if fold(row)})
                ),
                "profile_count": str(len(profiles)),
                "member_rows": str(len(members)),
                "unique_member_ids": str(
                    len({row.get("member_id", "") for row in members if row.get("member_id", "")})
                ),
                "unique_member_components": str(
                    len(
                        {
                            row.get("member_component", "")
                            for row in members
                            if row.get("member_component", "")
                        }
                    )
                ),
                "singleton_profiles": str(
                    len(
                        {
                            (fold(row), row.get("profile_id", ""))
                            for row in members
                            if row.get("singleton_profile") == "1"
                        }
                    )
                ),
                "seed_registry_rows": str(len(seeds)),
                "seed_profile_count": str(len(seed_profiles)),
                "artifact_registry_rows": str(len(artifacts)),
                "artifact_profile_count": str(len(artifact_profiles)),
                "artifact_kinds": ",".join(
                    sorted({row.get("artifact_kind", "") for row in artifacts if row.get("artifact_kind", "")})
                ),
                "artifact_receipts_pass": str(
                    sum(row.get("receipt_status", "").upper() == "PASS" for row in artifacts)
                ),
            }
        )
    return result


def runtime_cost_rows(
    runtime_rows: list[dict[str, str]], pbs_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in normalize_registry_rows(runtime_rows):
        grouped[(row.get("method", ""), row.get("reference_kind", ""))].append(row)
    result: list[dict[str, str]] = []
    for (method, reference), rows in sorted(grouped.items()):
        seconds = [float(row.get("wall_seconds", "0") or 0) for row in rows]
        result.append(
            {
                "record_kind": "summed_stage_runtime",
                "method": method,
                "reference_kind": reference,
                "stage_count": str(len(rows)),
                "summed_stage_wall_seconds": f"{sum(seconds):.17g}",
                "maximum_stage_wall_seconds": f"{max(seconds, default=0.0):.17g}",
                "ok_stage_count": str(sum(row.get("status") == "ok" for row in rows)),
                "reused_stage_count": str(sum(row.get("status") == "reused" for row in rows)),
                "failed_stage_count": str(
                    sum(row.get("status") not in {"ok", "reused"} for row in rows)
                ),
                "cost_caveat": "stage wall times are summed receipts, not elapsed parallel job wall time",
            }
        )
    for row in pbs_rows:
        result.append(
            {
                "record_kind": "pbs_job_resource_receipt",
                "job_id": row.get("job_id", ""),
                "job_name": row.get("job_name", ""),
                "pbs_wall": row.get(
                    "resources_used_walltime", row.get("wall", row.get("walltime", ""))
                ),
                "pbs_cput": row.get("resources_used_cput", row.get("cput", "")),
                "pbs_mem": row.get(
                    "resources_used_mem", row.get("mem", row.get("maxvmem", ""))
                ),
                "cost_caveat": "scheduler-reported job resource receipt",
            }
        )
    return result


def validate_reference_contracts(rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError("Reference contract registry is empty")
    by_cycle: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    observed_contracts = Counter()
    required_fields = {
        "method",
        "evaluation_fold",
        "calibration_fold",
        "reference_kind",
        "expected_record_count",
        "observed_record_count",
        "expected_id_set_sha256",
        "observed_id_set_sha256",
        "reference_fasta_sha256",
        "reference_manifest_sha256",
        "exact_equal",
        "receipt_kind",
        "receipt_status",
    }
    sha_fields = {
        "expected_id_set_sha256",
        "observed_id_set_sha256",
        "reference_fasta_sha256",
        "reference_manifest_sha256",
    }
    for row in rows:
        missing = sorted(field for field in required_fields if not row.get(field, ""))
        if missing:
            raise RuntimeError(f"Reference contract has empty required fields {missing}: {row}")
        method = normalize_method(row.get("method", ""))
        evaluation_fold = row.get("evaluation_fold", row.get("fold", ""))
        reference = row.get("reference_kind", "")
        if not method or not evaluation_fold or not reference:
            raise RuntimeError("Reference contract lacks method/evaluation_fold/reference_kind")
        try:
            expected_count = int(row["expected_record_count"])
            observed_count = int(row["observed_record_count"])
        except ValueError as error:
            raise RuntimeError(f"Reference contract has a malformed record count: {row}") from error
        if expected_count <= 0 or expected_count != observed_count:
            raise RuntimeError(f"Reference record-count contract mismatch: {row}")
        if any(not re.fullmatch(r"[0-9a-f]{64}", row[field]) for field in sha_fields):
            raise RuntimeError(f"Reference contract has a malformed SHA256: {row}")
        if row["expected_id_set_sha256"] != row["observed_id_set_sha256"]:
            raise RuntimeError(f"Reference ID-set contract mismatch: {row}")
        observed_contracts[(method, int(evaluation_fold), reference)] += 1
        if row["exact_equal"] != "1":
            raise RuntimeError(f"Reference exact-equality contract failed: {row}")
        if row["receipt_status"] != "PASS":
            raise RuntimeError(f"Reference receipt is not PASS: {row}")
        by_cycle[(evaluation_fold, reference)]["id"].add(
            row["observed_id_set_sha256"]
        )
        by_cycle[(evaluation_fold, reference)]["fasta"].add(
            row["reference_fasta_sha256"]
        )
        by_cycle[(evaluation_fold, reference)]["manifest"].add(
            row["reference_manifest_sha256"]
        )
    for key, fields in by_cycle.items():
        if any(len(fields[name]) != 1 for name in ("id", "fasta", "manifest")):
            raise RuntimeError(f"Controlled reference contract differs at {key}: {fields}")
    reference_methods = [method for method in ALL_METHODS if method not in OPERATIONAL_DESCRIPTIVE]
    expected_contracts = {
        (method, fold, reference)
        for method in reference_methods
        for fold in range(1, 6)
        for reference in ("djr", "vma")
    }
    if set(observed_contracts) != expected_contracts or any(
        count != 1 for count in observed_contracts.values()
    ):
        missing = sorted(expected_contracts - set(observed_contracts))
        extra = sorted(set(observed_contracts) - expected_contracts)
        raise RuntimeError(
            f"Reference contract coverage failure; missing={missing[:5]} extra={extra[:5]}"
        )


def required_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Required benchmark receipt is missing: {path}")
    return read_tsv(path)


def validate_raw_receipt_ledger(
    rows: list[dict[str, str]], benchmark_root: Path
) -> None:
    required = {
        "evaluation_fold",
        "reference_kind",
        "method",
        "stage",
        "artifact_path",
        "artifact_sha256",
        "receipt_path",
        "receipt_sha256",
        "receipt_status",
        "status",
        "argv_json",
        "input_sha256",
        "tool_sha256",
        "argv_sha256",
        "output_path",
        "output_sha256",
    }
    sha_fields = {
        "artifact_sha256",
        "receipt_sha256",
        "input_sha256",
        "tool_sha256",
        "argv_sha256",
        "output_sha256",
    }
    root = benchmark_root.resolve()
    seen: set[tuple[str, str, str, str, str]] = set()
    coverage: set[tuple[int, str, str]] = set()
    classical_methods = set(ALL_METHODS) - {
        "esmc6b_cosine",
        "esm2_650m_cosine",
        "esmc6b_supervised",
    }
    for row in rows:
        missing = sorted(field for field in required if not row.get(field, ""))
        if missing:
            raise RuntimeError(f"Raw receipt ledger has empty required fields {missing}: {row}")
        if any(not is_sha256(row[field]) for field in sha_fields):
            raise RuntimeError(f"Raw receipt ledger has a malformed SHA256: {row}")
        try:
            evaluation_fold = int(row["evaluation_fold"])
        except ValueError as error:
            raise RuntimeError(f"Raw receipt ledger has an invalid fold: {row}") from error
        if evaluation_fold not in range(1, 6):
            raise RuntimeError(f"Raw receipt fold is outside 1..5: {row}")
        method = normalize_method(row["method"])
        reference = row["reference_kind"]
        if method not in classical_methods or reference not in {"djr", "vma"}:
            raise RuntimeError(f"Unexpected method/reference in raw receipt ledger: {row}")
        if row["receipt_status"] != "PASS" or row["status"] != "PASS":
            raise RuntimeError(f"Raw receipt is not PASS: {row}")
        if (
            row["artifact_path"] != row["output_path"]
            or row["artifact_sha256"] != row["output_sha256"]
        ):
            raise RuntimeError(f"Raw receipt artifact/output aliases disagree: {row}")
        key = (
            row["evaluation_fold"],
            method,
            reference,
            row["stage"],
            row["artifact_path"],
        )
        if key in seen:
            raise RuntimeError(f"Duplicate raw receipt ledger row: {key}")
        seen.add(key)
        coverage.add((evaluation_fold, method, reference))

        artifact = (benchmark_root / row["artifact_path"]).resolve()
        receipt_path = (benchmark_root / row["receipt_path"]).resolve()
        for path in (artifact, receipt_path):
            if not path.is_relative_to(root) or not path.is_file():
                raise RuntimeError(f"Raw receipt path is missing or escapes benchmark root: {path}")
        if sha256_file(artifact) != row["artifact_sha256"]:
            raise RuntimeError(f"Raw artifact SHA mismatch: {artifact}")
        if sha256_file(receipt_path) != row["receipt_sha256"]:
            raise RuntimeError(f"Raw receipt SHA mismatch: {receipt_path}")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        semantic = {
            "evaluation_fold": evaluation_fold,
            "reference_kind": reference,
            "method": method,
            "stage": row["stage"],
            "status": "PASS",
            "artifact_path": row["artifact_path"],
            "artifact_sha256": row["artifact_sha256"],
            "output_sha256": row["output_sha256"],
            "input_sha256": row["input_sha256"],
            "tool_sha256": row["tool_sha256"],
            "argv_sha256": row["argv_sha256"],
        }
        if any(receipt.get(field) != value for field, value in semantic.items()):
            raise RuntimeError(f"Raw receipt JSON disagrees with ledger: {receipt_path}")
        try:
            ledger_argv = json.loads(row["argv_json"])
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Raw receipt argv_json is malformed: {row}") from error
        if receipt.get("argv") != ledger_argv or stable_json_sha(ledger_argv) != row["argv_sha256"]:
            raise RuntimeError(f"Raw receipt argv binding failed: {receipt_path}")
        for map_field, digest_field in (("inputs", "input_sha256"), ("tools", "tool_sha256")):
            value = receipt.get(map_field)
            if not isinstance(value, dict) or stable_json_sha(value) != row[digest_field]:
                raise RuntimeError(f"Raw receipt {map_field} binding failed: {receipt_path}")
        outputs = receipt.get("outputs")
        if not isinstance(outputs, dict) or row["artifact_path"] not in outputs:
            raise RuntimeError(f"Raw receipt output map is malformed: {receipt_path}")
        for relative, expected in outputs.items():
            output = (benchmark_root / relative).resolve()
            if (
                not output.is_relative_to(root)
                or not output.is_file()
                or not is_sha256(expected)
                or sha256_file(output) != expected
            ):
                raise RuntimeError(f"Raw receipt output binding failed: {relative}")
    expected_coverage = {
        (fold, method, reference)
        for fold in range(1, 6)
        for method in classical_methods
        for reference in ("djr", "vma")
    }
    if coverage != expected_coverage:
        raise RuntimeError(
            f"Raw receipt coverage mismatch; missing={sorted(expected_coverage - coverage)[:5]} "
            f"extra={sorted(coverage - expected_coverage)[:5]}"
        )


def validate_profile_registries(
    benchmark_root: Path,
    cohort_by_id: dict[str, dict[str, str]],
    profile_members: list[dict[str, str]],
    psiblast_seeds: list[dict[str, str]],
    profile_inclusion: list[dict[str, str]],
    profile_artifacts: list[dict[str, str]],
    inclusion_evalue: float,
) -> None:
    expected_references: dict[tuple[int, str], list[dict[str, str]]] = {}
    for fold in range(1, 6):
        for reference in ("djr", "vma"):
            rows = read_tsv(
                benchmark_root / f"inputs/fold_{fold}/reference_{reference}.tsv"
            )
            if not rows:
                raise RuntimeError(f"Empty frozen reference: cycle {fold} {reference}")
            expected_references[(fold, reference)] = rows

    grouped_members: dict[tuple[int, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in profile_members:
        method = normalize_method(row.get("method", ""))
        if method not in {"hmmer_component", "hmmer_family"}:
            raise RuntimeError(f"Non-HMM row entered profile_members: {row}")
        grouped_members[(int(row["evaluation_fold"]), row["reference_kind"], method)].append(row)
    for (fold, reference), expected_rows in expected_references.items():
        expected_ids = {row["protein_id"] for row in expected_rows}
        expected_by_id = {row["protein_id"]: row for row in expected_rows}
        for method in ("hmmer_component", "hmmer_family"):
            rows = grouped_members[(fold, reference, method)]
            member_ids = [row["member_id"] for row in rows]
            if len(member_ids) != len(expected_ids) or set(member_ids) != expected_ids:
                raise RuntimeError(
                    f"HMM member union is not the exact reference: {fold} {reference} {method}"
                )
            profiles: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in rows:
                profiles[row["profile_id"]].append(row)
            expected_groups = {
                row["global_component_id"] if method == "hmmer_component" else row["profile_group"]
                for row in expected_rows
            }
            observed_groups = {row["group_key"] for row in rows}
            if not expected_groups or observed_groups != expected_groups or len(profiles) != len(expected_groups):
                raise RuntimeError(f"HMM profile-group coverage mismatch: {fold} {reference} {method}")
            for profile_rows in profiles.values():
                group_keys = {row["group_key"] for row in profile_rows}
                if len(group_keys) != 1:
                    raise RuntimeError(f"HMM profile mixes group keys: {profile_rows[:2]}")
                group = next(iter(group_keys))
                for row in profile_rows:
                    expected = expected_by_id[row["member_id"]]
                    expected_group = (
                        expected["global_component_id"]
                        if method == "hmmer_component"
                        else expected["profile_group"]
                    )
                    if group != expected_group:
                        raise RuntimeError(f"HMM member assigned to wrong profile group: {row}")
                    if row["singleton_profile"] != ("1" if len(profile_rows) == 1 else "0"):
                        raise RuntimeError(f"HMM singleton flag is incorrect: {row}")

    grouped_seeds: dict[tuple[int, str], list[dict[str, str]]] = defaultdict(list)
    for row in psiblast_seeds:
        if normalize_method(row.get("method", "")) != PSI_METHOD:
            raise RuntimeError(f"Non-PSI row entered seed ledger: {row}")
        grouped_seeds[(int(row["evaluation_fold"]), row["reference_kind"])].append(row)
    seed_profiles: set[tuple[int, str, str]] = set()
    for key, expected_rows in expected_references.items():
        fold, reference = key
        expected_ids = {row["protein_id"] for row in expected_rows}
        expected_components: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in expected_rows:
            expected_components[row["global_component_id"]].append(row)
        rows = grouped_seeds[key]
        if len(rows) != len(expected_components):
            raise RuntimeError(f"PSI seed count differs from reference component count: {key}")
        observed_components = [row["seed_component"] for row in rows]
        if len(observed_components) != len(set(observed_components)) or set(observed_components) != set(expected_components):
            raise RuntimeError(f"PSI seed component coverage mismatch: {key}")
        reference_sha = hashlib.sha256(
            "".join(f"{value}\n" for value in sorted(expected_ids)).encode("utf-8")
        ).hexdigest()
        for row in rows:
            component = row["seed_component"]
            expected_seed = sorted(
                expected_components[component],
                key=lambda value: (-int(value["length_aa"]), value["protein_id"]),
            )[0]
            if (
                row["seed_id"] != expected_seed["protein_id"]
                or row["group_key"] != component
                or row["seed_fold"] != expected_seed["fold"]
                or row["seed_length_aa"] != expected_seed["length_aa"]
                or row["reference_record_count"] != str(len(expected_ids))
                or row["reference_id_set_sha256"] != reference_sha
            ):
                raise RuntimeError(f"PSI deterministic seed/reference contract failed: {row}")
            seed_profiles.add((fold, reference, row["profile_id"]))

    artifact_profiles: Counter[tuple[int, str, str, str]] = Counter()
    for row in profile_artifacts:
        if row.get("receipt_status") != "PASS":
            raise RuntimeError(f"Profile artifact receipt is not PASS: {row}")
        method = normalize_method(row.get("method", ""))
        artifact_profiles[
            (int(row["evaluation_fold"]), row["reference_kind"], method, row["profile_id"])
        ] += 1
    expected_hmm_profiles = {
        (int(row["evaluation_fold"]), row["reference_kind"], normalize_method(row["method"]), row["profile_id"])
        for row in profile_members
    }
    for key in expected_hmm_profiles:
        if artifact_profiles[(key[0], key[1], key[2], key[3])] != 1:
            raise RuntimeError(f"HMM profile artifact is missing/duplicated: {key}")
    for fold, reference, profile in seed_profiles:
        if artifact_profiles[(fold, reference, PSI_METHOD, profile)] != 1:
            raise RuntimeError(f"PSI PSSM artifact is missing/duplicated: {(fold, reference, profile)}")

    inclusion_profiles: set[tuple[int, str, str]] = set()
    seen_inclusion: set[tuple[int, str, str, int, str]] = set()
    for row in profile_inclusion:
        if normalize_method(row.get("method", "")) != PSI_METHOD:
            raise RuntimeError(f"Non-PSI row entered inclusion ledger: {row}")
        fold = int(row["evaluation_fold"])
        reference = row["reference_kind"]
        profile = row["profile_id"]
        iteration = int(row["iteration"])
        subject = row["subject_id"]
        key = (fold, reference, profile, iteration, subject)
        if key in seen_inclusion:
            raise RuntimeError(f"Duplicate PSI inclusion row: {key}")
        seen_inclusion.add(key)
        if (fold, reference, profile) not in seed_profiles or iteration not in {1, 2, 3}:
            raise RuntimeError(f"PSI inclusion row has unknown profile/iteration: {row}")
        expected_ids = {
            value["protein_id"] for value in expected_references[(fold, reference)]
        }
        if subject not in expected_ids:
            raise RuntimeError(f"PSI inclusion subject is outside the reference: {row}")
        evalue = float(row["best_evalue"])
        if not math.isfinite(evalue) or evalue < 0:
            raise RuntimeError(f"PSI inclusion E-value is invalid: {row}")
        expected_flag = "1" if evalue <= inclusion_evalue else "0"
        if row["passes_threshold_in_iteration"] != expected_flag:
            raise RuntimeError(f"PSI inclusion-threshold flag is incorrect: {row}")
        inclusion_profiles.add((fold, reference, profile))
    if inclusion_profiles != seed_profiles:
        raise RuntimeError("PSI inclusion ledger does not cover every frozen PSSM profile")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    config, project_root, benchmark_root = load_config(args.config)
    results = benchmark_root / "results"
    results.mkdir(parents=True, exist_ok=True)

    fold_count = int(config["parameters"]["folds"])
    offset = int(config["parameters"]["calibration_fold_offset"])
    specificities = [float(value) for value in config["parameters"]["specificity_ladder"]]
    primary_specificity = float(config["parameters"]["primary_specificity"])
    if fold_count != 5 or not math.isclose(primary_specificity, 0.995):
        raise RuntimeError("This frozen summarizer requires five folds and 99.5% primary specificity")

    cohort = read_tsv(benchmark_root / "inputs/cohort.tsv")
    if len({row["protein_id"] for row in cohort}) != len(cohort):
        raise RuntimeError("Duplicate cohort protein_id")
    if {int(row["fold"]) for row in cohort} != set(range(1, fold_count + 1)):
        raise RuntimeError("Cohort does not contain every configured fold")
    component_folds: dict[str, set[str]] = defaultdict(set)
    for row in cohort:
        component_folds[row["global_component_id"]].add(row["fold"])
    leaking = [component for component, folds in component_folds.items() if len(folds) != 1]
    if leaking:
        raise RuntimeError(f"global_component_id spans folds: {leaking[:5]}")

    attestation_paths = {
        "inputs": benchmark_root / "inputs/input_attestation.json",
        "plm": benchmark_root / "work/plm_reproduction.json",
        "classical": benchmark_root / "work/classical_attestation.json",
    }
    attestations: dict[str, dict] = {}
    for name, path in attestation_paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"Required benchmark attestation is missing: {path}")
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("status") != "PASS":
            raise RuntimeError(f"Benchmark attestation is not PASS: {path}")
        if document.get("design_id") != config["design_id"]:
            raise RuntimeError(f"Benchmark attestation design mismatch: {path}")
        attestations[name] = document
    if attestations["inputs"].get("allowed_split") != "train":
        raise RuntimeError("Input attestation is not restricted to Train")
    current_config_sha = sha256_file(args.config.resolve())
    input_source_bindings = {
        "config_sha256": current_config_sha,
        "prepare_inputs_script_sha256": sha256_file(
            Path(__file__).with_name("prepare_inputs.py")
        ),
        "common_script_sha256": sha256_file(Path(__file__).with_name("common.py")),
    }
    if any(
        attestations["inputs"].get(field) != expected
        for field, expected in input_source_bindings.items()
    ):
        raise RuntimeError("Input attestation is not bound to current config/source")
    derived_outputs = attestations["inputs"].get("derived_output_sha256")
    if not isinstance(derived_outputs, dict) or not derived_outputs:
        raise RuntimeError("Input attestation lacks the derived-output checksum map")
    input_root = (benchmark_root / "inputs").resolve()
    for relative, expected in derived_outputs.items():
        path = (input_root / relative).resolve()
        if (
            not path.is_relative_to(input_root)
            or not path.is_file()
            or not is_sha256(expected)
            or sha256_file(path) != expected
        ):
            raise RuntimeError(f"Prepared input artifact checksum mismatch: {relative}")
    input_attestation_sha = sha256_file(attestation_paths["inputs"])
    for name in ("plm", "classical"):
        document = attestations[name]
        if document.get("config_sha256") != current_config_sha:
            raise RuntimeError(f"{name} attestation is bound to a different config")
        if document.get("input_attestation_sha256") != input_attestation_sha:
            raise RuntimeError(f"{name} attestation is bound to different prepared inputs")
    source_bindings = {
        "plm": {
            "run_plm_script_sha256": Path(__file__).with_name("run_plm.py"),
            "common_script_sha256": Path(__file__).with_name("common.py"),
            "classifier_module_sha256": project_root
            / "src/djrmcp_finder/stages/classifier.py",
        },
        "classical": {
            "run_classical_script_sha256": Path(__file__).with_name("run_classical.py"),
            "common_script_sha256": Path(__file__).with_name("common.py"),
        },
    }
    for name, bindings in source_bindings.items():
        for field, path in bindings.items():
            if not path.is_file() or attestations[name].get(field) != sha256_file(path):
                raise RuntimeError(f"{name} attestation is not bound to current {path.name}")
    score_bindings = {
        "plm": ("score_sha256", benchmark_root / "work/scores/plm_scores.tsv"),
        "classical": (
            "classical_scores_sha256",
            benchmark_root / "work/scores/classical_scores.tsv",
        ),
    }
    for name, (field, path) in score_bindings.items():
        if not path.is_file() or attestations[name].get(field) != sha256_file(path):
            raise RuntimeError(f"{name} score table is not bound by its attestation")
    protected_validation_rows = max(
        [int(config["protected_split_policy"].get("validation_prediction_rows", 0))]
        + [
            int(document.get("validation_prediction_rows", 0))
            for document in attestations.values()
        ]
    )
    protected_test_rows = max(
        [int(config["protected_split_policy"].get("test_prediction_rows", 0))]
        + [
            int(document.get("test_prediction_rows", 0))
            for document in attestations.values()
        ]
    )
    if protected_validation_rows or protected_test_rows:
        raise RuntimeError("Protected Validation/Test predictions are forbidden")

    # Load fail-closed provenance before the expensive bootstrap.
    plm_reference_contract = required_rows(
        benchmark_root / "work/plm_reference_contract.tsv"
    )
    classical_reference_contract = required_rows(
        benchmark_root / "work/classical_reference_contract.tsv"
    )
    normalized_contracts = normalize_registry_rows(
        [*plm_reference_contract, *classical_reference_contract]
    )
    validate_reference_contracts(normalized_contracts)
    profile_members = normalize_registry_rows(
        required_rows(benchmark_root / "work/profile_members.tsv")
    )
    profile_inclusion = normalize_registry_rows(
        required_rows(benchmark_root / "work/profile_inclusion_ledger.tsv")
    )
    psiblast_seeds = normalize_registry_rows(
        required_rows(benchmark_root / "work/psiblast_seed_ledger.tsv")
    )
    profile_artifacts = normalize_registry_rows(
        required_rows(benchmark_root / "work/profile_artifact_registry.tsv")
    )
    if any(row.get("receipt_status", "").upper() != "PASS" for row in profile_artifacts):
        raise RuntimeError("A profile artifact receipt is not PASS")
    runtime_resources = normalize_registry_rows(
        required_rows(benchmark_root / "work/runtime_resources.tsv")
    )
    raw_receipts = normalize_registry_rows(
        required_rows(benchmark_root / "work/raw_receipt_ledger.tsv")
    )
    raw_receipt_path = benchmark_root / "work/raw_receipt_ledger.tsv"
    if attestations["classical"].get("raw_receipt_ledger_sha256") != sha256_file(
        raw_receipt_path
    ):
        raise RuntimeError("Classical attestation is not bound to the raw receipt ledger")
    validate_raw_receipt_ledger(raw_receipts, benchmark_root)
    for name, rows in (
        ("plm_reference_contract.tsv", plm_reference_contract),
        ("classical_reference_contract.tsv", classical_reference_contract),
        ("profile_members.tsv", profile_members),
        ("profile_inclusion_ledger.tsv", profile_inclusion),
        ("psiblast_seed_ledger.tsv", psiblast_seeds),
        ("profile_artifact_registry.tsv", profile_artifacts),
        ("runtime_resources.tsv", runtime_resources),
        ("raw_receipt_ledger.tsv", raw_receipts),
    ):
        if not rows:
            raise RuntimeError(f"Required registry is empty: {name}")
    cohort_by_id = {row["protein_id"]: row for row in cohort}
    for registry_name, rows, id_field, fold_field in (
        ("profile_members.tsv", profile_members, "member_id", "member_fold"),
        ("psiblast_seed_ledger.tsv", psiblast_seeds, "seed_id", "seed_fold"),
        ("profile_inclusion_ledger.tsv", profile_inclusion, "subject_id", ""),
    ):
        for row in rows:
            evaluation_fold = int(row.get("evaluation_fold", row.get("fold", "0")))
            _, fit_folds = cyclic_fold_roles(evaluation_fold, fold_count, offset)
            protein_id = row.get(id_field, "")
            if protein_id not in cohort_by_id:
                raise RuntimeError(f"Unknown protein in {registry_name}: {protein_id}")
            observed_fold = int(
                row.get(fold_field, cohort_by_id[protein_id]["fold"])
                if fold_field
                else cohort_by_id[protein_id]["fold"]
            )
            if observed_fold != int(cohort_by_id[protein_id]["fold"]) or observed_fold not in fit_folds:
                raise RuntimeError(
                    f"Profile/reference member is outside fit folds in {registry_name}: {row}"
                )
            reference_kind = row.get("reference_kind", "")
            expected_flag = "is_djr" if reference_kind == "djr" else "is_vma"
            if reference_kind not in {"djr", "vma"} or cohort_by_id[protein_id][expected_flag] != "1":
                raise RuntimeError(f"Non-positive profile/reference member in {registry_name}: {row}")
    validate_profile_registries(
        benchmark_root,
        cohort_by_id,
        profile_members,
        psiblast_seeds,
        profile_inclusion,
        profile_artifacts,
        float(config["parameters"]["psiblast_inclusion_evalue"]),
    )
    pbs_path = benchmark_root / "work/pbs_job_resources.tsv"
    pbs_resources = read_tsv(pbs_path) if pbs_path.is_file() else []

    raw_scores = required_rows(benchmark_root / "work/scores/plm_scores.tsv") + required_rows(
        benchmark_root / "work/scores/classical_scores.tsv"
    )
    score_lookup: dict[tuple[str, str, int, str, str], tuple[float, str, int]] = {}
    for row in raw_scores:
        method = normalize_method(row["method"])
        if method not in ALL_METHODS:
            raise RuntimeError(f"Unexpected benchmark method: {row['method']}")
        try:
            evaluation_fold = int(row["evaluation_fold"])
            source_fold = int(row["source_fold"])
        except (KeyError, ValueError) as error:
            raise RuntimeError("Score table does not implement cyclic evaluation/source folds") from error
        role = row.get("role", "")
        if role not in {"calibration", "evaluation"}:
            raise RuntimeError(f"Invalid score role: {role}")
        key = (method, row["task"], evaluation_fold, role, row["protein_id"])
        if key in score_lookup:
            raise RuntimeError(f"Duplicate score row after method normalization: {key}")
        score = parse_score(row["score"])
        status = row["status"]
        if status not in {"ok", "no_hit"}:
            raise RuntimeError(f"Method failure cannot be encoded as a score: {key} {status}")
        if status == "no_hit" and score != -math.inf:
            raise RuntimeError(f"no_hit must be encoded as -inf: {key}")
        if status == "ok" and not math.isfinite(score):
            raise RuntimeError(f"ok score must be finite: {key}")
        score_lookup[key] = (score, status, source_fold)

    query_score_rows: list[dict[str, str]] = []
    used_score_keys: set[tuple[str, str, int, str, str]] = set()
    cycles: dict[str, dict[int, dict]] = defaultdict(dict)
    for task in TASKS:
        for evaluation_fold in range(1, fold_count + 1):
            calibration_fold, fit_folds = cyclic_fold_roles(evaluation_fold, fold_count, offset)
            role_rows = {
                "calibration": task_rows(
                    [row for row in cohort if int(row["fold"]) == calibration_fold], task
                ),
                "evaluation": task_rows(
                    [row for row in cohort if int(row["fold"]) == evaluation_fold], task
                ),
            }
            cycle = {
                "evaluation_fold": evaluation_fold,
                "calibration_fold": calibration_fold,
                "fit_folds": fit_folds,
                "calibration_rows": role_rows["calibration"],
                "evaluation_rows": role_rows["evaluation"],
                "calibration_scores": {},
                "evaluation_scores": {},
            }
            for role, rows in role_rows.items():
                for method in ALL_METHODS:
                    values = []
                    for row in rows:
                        key = (method, task, evaluation_fold, role, row["protein_id"])
                        if key not in score_lookup:
                            raise RuntimeError(f"Missing cyclic score row: {key}")
                        score, status, source_fold = score_lookup[key]
                        if source_fold != int(row["fold"]):
                            raise RuntimeError(f"Score source_fold disagrees with cohort: {key}")
                        values.append(score)
                        used_score_keys.add(key)
                        query_score_rows.append(
                            {
                                "protein_id": row["protein_id"],
                                "global_component_id": row["global_component_id"],
                                "evaluation_fold": str(evaluation_fold),
                                "source_fold": row["fold"],
                                "role": role,
                                "source_dataset": row["source_dataset"],
                                "task": task,
                                "label": row[TASKS[task]["label"]],
                                "method": method,
                                "score": score_text(score),
                                "status": status,
                            }
                        )
                    cycle[f"{role}_scores"][method] = np.asarray(values, dtype=np.float64)
            calibration_y = np.asarray(
                [int(row[TASKS[task]["label"]]) for row in role_rows["calibration"]],
                dtype=np.int64,
            )
            evaluation_y = np.asarray(
                [int(row[TASKS[task]["label"]]) for row in role_rows["evaluation"]],
                dtype=np.int64,
            )
            calibration_negative = calibration_y == 0
            evaluation_positive = evaluation_y == 1
            if not np.any(calibration_negative) or not np.any(evaluation_positive):
                raise RuntimeError(f"Empty calibration negative/evaluation positive class: {task} cycle {evaluation_fold}")
            cycle["calibration_y"] = calibration_y
            cycle["evaluation_y"] = evaluation_y
            cycle["calibration_negative_rows"] = [
                row for row, keep in zip(role_rows["calibration"], calibration_negative, strict=True) if keep
            ]
            cycle["evaluation_positive_rows"] = [
                row for row, keep in zip(role_rows["evaluation"], evaluation_positive, strict=True) if keep
            ]
            cycle["calibration_negative_scores"] = {
                method: values[calibration_negative]
                for method, values in cycle["calibration_scores"].items()
            }
            cycle["evaluation_positive_scores"] = {
                method: values[evaluation_positive]
                for method, values in cycle["evaluation_scores"].items()
            }
            cycles[task][evaluation_fold] = cycle
    extras = set(score_lookup) - used_score_keys
    if extras:
        raise RuntimeError(f"Unexpected score rows outside the cyclic cohort contract: {sorted(extras)[:5]}")

    # This audit is structural and score-independent.  It makes explicit where
    # the frozen folds cannot support an unconditional low-FPR interpretation.
    resolution_audit: dict[str, dict] = {}
    for task, task_cycles in cycles.items():
        calibration_singletons: list[dict[str, int | str]] = []
        evaluation_singletons: list[dict[str, int | str]] = []
        zero_fp_cycles: list[int] = []
        low_positive_folds: list[dict[str, int]] = []
        for evaluation_fold, cycle in sorted(task_cycles.items()):
            calibration_rows = cycle["calibration_negative_rows"]
            calibration_weights = source_component_weights(calibration_rows)
            calibration_status, _ = calibration_resolution_status(
                calibration_rows, calibration_weights, primary_specificity
            )
            if "ZERO_FP" in calibration_status:
                zero_fp_cycles.append(evaluation_fold)
            for source in sorted({row["source_dataset"] for row in calibration_rows}):
                source_indices = [
                    index
                    for index, row in enumerate(calibration_rows)
                    if row["source_dataset"] == source
                ]
                source_rows = [calibration_rows[index] for index in source_indices]
                if len({row["global_component_id"] for row in source_rows}) == 1:
                    source_status, minimum_row_mass = calibration_resolution_status(
                        source_rows,
                        calibration_weights[np.asarray(source_indices, dtype=np.int64)],
                        primary_specificity,
                    )
                    calibration_singletons.append(
                        {
                            "evaluation_fold": evaluation_fold,
                            "calibration_fold": int(cycle["calibration_fold"]),
                            "source": source,
                            "records": len(source_rows),
                            "components": 1,
                            "minimum_global_row_fpr_mass": minimum_row_mass,
                            "resolution_status": source_status,
                        }
                    )
            evaluation_negative_rows = [
                row
                for row, label in zip(
                    cycle["evaluation_rows"], cycle["evaluation_y"], strict=True
                )
                if not label
            ]
            for source in sorted({row["source_dataset"] for row in evaluation_negative_rows}):
                source_rows = [
                    row for row in evaluation_negative_rows if row["source_dataset"] == source
                ]
                if len({row["global_component_id"] for row in source_rows}) == 1:
                    evaluation_singletons.append(
                        {
                            "evaluation_fold": evaluation_fold,
                            "source": source,
                            "records": len(source_rows),
                            "components": 1,
                            "resolution_status": evaluation_resolution_status(source_rows),
                        }
                    )
            positive_component_count = len(
                {
                    row["global_component_id"]
                    for row in cycle["evaluation_positive_rows"]
                }
            )
            if positive_component_count < 20:
                low_positive_folds.append(
                    {
                        "evaluation_fold": evaluation_fold,
                        "positive_components": positive_component_count,
                        "positive_records": len(cycle["evaluation_positive_rows"]),
                    }
                )
        conditional = bool(calibration_singletons or evaluation_singletons)
        resolution_audit[task] = {
            "primary_sensitivity_inference_status": (
                "CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED"
                if conditional
                else "DESCRIPTIVE_PAIRED_COMPONENT_BOOTSTRAP"
            ),
            "primary_zero_fp_granularity_cycles": zero_fp_cycles,
            "calibration_singleton_negative_sources": calibration_singletons,
            "evaluation_singleton_negative_sources": evaluation_singletons,
            "low_positive_component_folds": low_positive_folds,
            "bootstrap_caveat": (
                "A one-component fold/source stratum has fixed bootstrap multiplicity one, "
                "so its between-component calibration/evaluation variation is not estimable."
                if conditional
                else "No single-component calibration/evaluation negative source was observed."
            ),
        }

    thresholds: list[dict[str, str]] = []
    ladder_rows: list[dict[str, str]] = []
    metrics_cycle: list[dict[str, str]] = []
    primary_metrics: list[dict[str, str]] = []
    source_specificity: list[dict[str, str]] = []
    calibration_source_summary: list[dict[str, str]] = []
    threshold_lookup: dict[tuple[str, str, int, float], float] = {}
    fold_ap_lookup: dict[tuple[str, str], list[float]] = {}
    point_sensitivity: dict[tuple[str, str], float] = {}

    for task in TASKS:
        pooled_rows = [
            row
            for evaluation_fold in range(1, fold_count + 1)
            for row in cycles[task][evaluation_fold]["evaluation_rows"]
        ]
        pooled_y = np.asarray(
            [int(row[TASKS[task]["label"]]) for row in pooled_rows], dtype=np.int64
        )
        pooled_component_weights = component_weights(pooled_rows)
        for method in ALL_METHODS:
            fold_aps: list[float] = []
            sensitivity_by_specificity: dict[float, list[float]] = {
                specificity: [] for specificity in specificities
            }
            record_sensitivity_by_specificity: dict[float, list[float]] = {
                specificity: [] for specificity in specificities
            }
            evaluation_specificity_by_specificity: dict[float, list[float]] = {
                specificity: [] for specificity in specificities
            }
            pooled_scores = []
            for evaluation_fold in range(1, fold_count + 1):
                cycle = cycles[task][evaluation_fold]
                evaluation_rows = cycle["evaluation_rows"]
                evaluation_y = cycle["evaluation_y"]
                evaluation_scores = cycle["evaluation_scores"][method]
                pooled_scores.extend(evaluation_scores.tolist())
                fold_ap = checked_ap(
                    evaluation_y,
                    evaluation_scores,
                    component_weights(evaluation_rows),
                )
                fold_aps.append(fold_ap)

                negative_rows = cycle["calibration_negative_rows"]
                negative_scores = cycle["calibration_negative_scores"][method]
                negative_weights = source_component_weights(negative_rows)
                positive_mask = evaluation_y == 1
                negative_evaluation_mask = evaluation_y == 0
                positive_rows = [
                    row
                    for row, keep in zip(evaluation_rows, positive_mask, strict=True)
                    if keep
                ]
                positive_weights = component_weights(positive_rows)
                for specificity in specificities:
                    threshold, achieved_fpr = conservative_threshold(
                        negative_scores, negative_weights, specificity
                    )
                    calibration_status, minimum_negative_row_mass = (
                        calibration_resolution_status(
                            negative_rows, negative_weights, specificity
                        )
                    )
                    threshold_lookup[(task, method, evaluation_fold, specificity)] = threshold
                    prediction = evaluation_scores >= threshold
                    sensitivity = float(
                        np.average(prediction[positive_mask], weights=positive_weights)
                    )
                    record_sensitivity = float(np.mean(prediction[positive_mask]))
                    if not np.any(negative_evaluation_mask):
                        raise RuntimeError(f"No evaluation negatives: {task} cycle {evaluation_fold}")
                    evaluation_negative_rows = [
                        row
                        for row, keep in zip(
                            evaluation_rows, negative_evaluation_mask, strict=True
                        )
                        if keep
                    ]
                    observed_specificity = 1.0 - float(
                        np.average(
                            prediction[negative_evaluation_mask],
                            weights=source_component_weights(evaluation_negative_rows),
                        )
                    )
                    sensitivity_by_specificity[specificity].append(sensitivity)
                    record_sensitivity_by_specificity[specificity].append(record_sensitivity)
                    evaluation_specificity_by_specificity[specificity].append(
                        observed_specificity
                    )
                    status = endpoint_status(specificity, primary_specificity)
                    thresholds.append(
                        {
                            "task": task,
                            "method": method,
                            "track": METHOD_SPECS[method]["track"],
                            "specificity_target": f"{specificity:.4f}",
                            "evaluation_fold": str(evaluation_fold),
                            "heldout_fold": str(evaluation_fold),
                            "calibration_fold": str(cycle["calibration_fold"]),
                            "calibration_role": "calibration",
                            "evaluation_role": "evaluation",
                            "fit_folds": ",".join(map(str, cycle["fit_folds"])),
                            "threshold": score_text(threshold),
                            "calibration_negative_records": str(len(negative_rows)),
                            "calibration_negative_components": str(
                                len({row["global_component_id"] for row in negative_rows})
                            ),
                            "calibration_negative_sources": str(
                                len({row["source_dataset"] for row in negative_rows})
                            ),
                            "calibration_achieved_source_balanced_fpr": f"{achieved_fpr:.17g}",
                            "minimum_nonzero_negative_row_fpr_mass": f"{minimum_negative_row_mass:.17g}",
                            "calibration_resolution_status": calibration_status,
                            "endpoint_status": status,
                        }
                    )
                    ladder_rows.append(
                        {
                            "task": task,
                            "method": method,
                            "track": METHOD_SPECS[method]["track"],
                            "evaluation_fold": str(evaluation_fold),
                            "calibration_fold": str(cycle["calibration_fold"]),
                            "specificity_target": f"{specificity:.4f}",
                            "component_balanced_sensitivity": f"{sensitivity:.17g}",
                            "record_sensitivity": f"{record_sensitivity:.17g}",
                            "observed_source_balanced_specificity": f"{observed_specificity:.17g}",
                            "calibration_resolution_status": calibration_status,
                            "endpoint_status": status,
                        }
                    )
                    for source in sorted(
                        {row["source_dataset"] for row in evaluation_negative_rows}
                    ):
                        source_indices = np.asarray(
                            [
                                index
                                for index, row in enumerate(evaluation_rows)
                                if not evaluation_y[index]
                                and row["source_dataset"] == source
                            ],
                            dtype=np.int64,
                        )
                        local_rows = [evaluation_rows[int(index)] for index in source_indices]
                        local_specificity = 1.0 - float(
                            np.average(
                                prediction[source_indices], weights=component_weights(local_rows)
                            )
                        )
                        source_specificity.append(
                            {
                                "task": task,
                                "method": method,
                                "track": METHOD_SPECS[method]["track"],
                                "evaluation_fold": str(evaluation_fold),
                                "specificity_target": f"{specificity:.4f}",
                                "negative_source": source,
                                "records": str(len(local_rows)),
                                "components": str(
                                    len({row["global_component_id"] for row in local_rows})
                                ),
                                "observed_component_specificity": f"{local_specificity:.17g}",
                                "evaluation_resolution_status": evaluation_resolution_status(
                                    local_rows
                                ),
                                "endpoint_status": status,
                            }
                        )
                    if math.isclose(specificity, primary_specificity):
                        metrics_cycle.append(
                            {
                                "task": task,
                                "method": method,
                                "track": METHOD_SPECS[method]["track"],
                                "evaluation_fold": str(evaluation_fold),
                                "calibration_fold": str(cycle["calibration_fold"]),
                                "component_balanced_ap": f"{fold_ap:.17g}",
                                "threshold_99.5": score_text(threshold),
                                "calibration_achieved_fpr": f"{achieved_fpr:.17g}",
                                "component_sensitivity_99.5": f"{sensitivity:.17g}",
                                "evaluation_positive_records": str(int(positive_mask.sum())),
                                "evaluation_positive_components": str(
                                    len({row["global_component_id"] for row in positive_rows})
                                ),
                                "evaluation_negative_records": str(
                                    len(evaluation_negative_rows)
                                ),
                                "evaluation_negative_components": str(
                                    len(
                                        {
                                            row["global_component_id"]
                                            for row in evaluation_negative_rows
                                        }
                                    )
                                ),
                                "calibration_negative_records": str(len(negative_rows)),
                                "calibration_negative_components": str(
                                    len({row["global_component_id"] for row in negative_rows})
                                ),
                                "calibration_resolution_status": calibration_status,
                                "primary_sensitivity_inference_status": resolution_audit[
                                    task
                                ]["primary_sensitivity_inference_status"],
                            }
                        )
                        for source in sorted(
                            {row["source_dataset"] for row in negative_rows}
                        ):
                            source_indices = np.asarray(
                                [
                                    index
                                    for index, row in enumerate(negative_rows)
                                    if row["source_dataset"] == source
                                ],
                                dtype=np.int64,
                            )
                            source_weight = float(negative_weights[source_indices].sum())
                            false_weight = float(
                                negative_weights[source_indices][
                                    negative_scores[source_indices] >= threshold
                                ].sum()
                            )
                            source_rows = [negative_rows[int(index)] for index in source_indices]
                            source_status, minimum_source_row_mass = (
                                calibration_resolution_status(
                                    source_rows,
                                    negative_weights[source_indices],
                                    primary_specificity,
                                )
                            )
                            calibration_source_summary.append(
                                {
                                    "task": task,
                                    "method": method,
                                    "track": METHOD_SPECS[method]["track"],
                                    "evaluation_fold": str(evaluation_fold),
                                    "calibration_fold": str(cycle["calibration_fold"]),
                                    "specificity_target": f"{primary_specificity:.4f}",
                                    "negative_source": source,
                                    "records": str(len(source_rows)),
                                    "components": str(
                                        len(
                                            {
                                                row["global_component_id"]
                                                for row in source_rows
                                            }
                                        )
                                    ),
                                    "assigned_source_weight": f"{source_weight:.17g}",
                                    "minimum_nonzero_global_row_fpr_mass": f"{minimum_source_row_mass:.17g}",
                                    "false_positive_weight_contribution": f"{false_weight:.17g}",
                                    "observed_component_specificity_within_source": f"{1.0 - false_weight / source_weight:.17g}",
                                    "threshold": score_text(threshold),
                                    "calibration_source_resolution_status": source_status,
                                    "no_hit_records": str(
                                        int(np.isneginf(negative_scores[source_indices]).sum())
                                    ),
                                }
                            )

            fold_ap_lookup[(task, method)] = fold_aps
            macro_sensitivity = float(
                np.mean(sensitivity_by_specificity[primary_specificity])
            )
            point_sensitivity[(task, method)] = macro_sensitivity
            pooled_score_array = np.asarray(pooled_scores, dtype=np.float64)
            primary_metrics.append(
                {
                    "task": task,
                    "method": method,
                    "track": METHOD_SPECS[method]["track"],
                    "primary_eligible": METHOD_SPECS[method]["primary_eligible"],
                    "records": str(len(pooled_rows)),
                    "positive_records": str(int(pooled_y.sum())),
                    "positive_components": str(
                        len(
                            {
                                row["global_component_id"]
                                for row, label in zip(pooled_rows, pooled_y, strict=True)
                                if label
                            }
                        )
                    ),
                    "fold_macro_component_ap": f"{float(np.mean(fold_aps)):.17g}",
                    "fold_component_ap_min": f"{min(fold_aps):.17g}",
                    "fold_component_ap_max": f"{max(fold_aps):.17g}",
                    "fold_component_ap_values": json.dumps(fold_aps),
                    "pooled_raw_component_ap_secondary": f"{checked_ap(pooled_y, pooled_score_array, pooled_component_weights):.17g}",
                    "pooled_raw_record_ap_secondary": f"{checked_ap(pooled_y, pooled_score_array):.17g}",
                    "primary_specificity_target": f"{primary_specificity:.4f}",
                    "fold_macro_component_sensitivity_at_primary_specificity": f"{macro_sensitivity:.17g}",
                    "fold_component_sensitivity_min": f"{min(sensitivity_by_specificity[primary_specificity]):.17g}",
                    "fold_component_sensitivity_max": f"{max(sensitivity_by_specificity[primary_specificity]):.17g}",
                    "fold_macro_record_sensitivity_at_primary_specificity": f"{float(np.mean(record_sensitivity_by_specificity[primary_specificity])):.17g}",
                    "fold_macro_observed_source_balanced_specificity": f"{float(np.mean(evaluation_specificity_by_specificity[primary_specificity])):.17g}",
                    "primary_sensitivity_inference_status": resolution_audit[task][
                        "primary_sensitivity_inference_status"
                    ],
                    "primary_zero_fp_granularity_cycles": json.dumps(
                        resolution_audit[task]["primary_zero_fp_granularity_cycles"]
                    ),
                    "calibration_singleton_negative_source_count": str(
                        len(
                            resolution_audit[task][
                                "calibration_singleton_negative_sources"
                            ]
                        )
                    ),
                    "evaluation_singleton_negative_source_count": str(
                        len(
                            resolution_audit[task][
                                "evaluation_singleton_negative_sources"
                            ]
                        )
                    ),
                    "no_hit_evaluation_records": str(int(np.isneginf(pooled_score_array).sum())),
                }
            )

    # Parse the raw BLAST evidence before starting the expensive bootstrap so a
    # missing/malformed classical artifact fails immediately rather than after it.
    distance_strata_by_task: dict[str, dict[str, str]] = {}
    for task in TASKS:
        evaluation_rows = [
            row
            for fold in range(1, fold_count + 1)
            for row in cycles[task][fold]["evaluation_rows"]
        ]
        distance_strata_by_task[task] = blast_local_distance_strata(
            benchmark_root, task, evaluation_rows, fold_count
        )

    bootstrap_replicates = int(config["parameters"]["bootstrap_replicates"])
    bootstrap_methods = ["esmc6b_cosine", *CLASSICAL_ANCHORS]
    sensitivity_bootstrap, ap_bootstrap = bootstrap_primary_metrics_global(
        cohort,
        cycles,
        bootstrap_methods,
        primary_specificity,
        bootstrap_replicates,
        int(config["seed"]) + 90_000,
    )
    paired_deltas: list[dict[str, str]] = []
    power_mde: list[dict[str, str]] = []
    for task in TASKS:
        positive_components_by_fold = [
            len(
                {
                    row["global_component_id"]
                    for row in cycles[task][fold]["evaluation_positive_rows"]
                }
            )
            for fold in range(1, fold_count + 1)
        ]
        for comparator in CLASSICAL_ANCHORS:
            delta = (
                sensitivity_bootstrap[task]["esmc6b_cosine"]
                - sensitivity_bootstrap[task][comparator]
            )
            ap_delta = (
                ap_bootstrap[task]["esmc6b_cosine"]
                - ap_bootstrap[task][comparator]
            )
            ap_deltas = np.asarray(fold_ap_lookup[(task, "esmc6b_cosine")]) - np.asarray(
                fold_ap_lookup[(task, comparator)]
            )
            point_delta = point_sensitivity[(task, "esmc6b_cosine")] - point_sensitivity[
                (task, comparator)
            ]
            paired_deltas.append(
                {
                    "task": task,
                    "anchor_method": "esmc6b_cosine",
                    "comparator_method": comparator,
                    "baseline_method": comparator,
                    "comparison_registry_status": "PRE_REGISTERED_CONTROLLED_ANCHOR_COMPARISON",
                    "metric": "fold_macro_component_sensitivity_at_0.995_specificity",
                    "sensitivity_metric": "fold_macro_component_sensitivity_at_0.995_specificity",
                    "ap_metric": "fold_macro_component_balanced_average_precision",
                    "point_delta_component_sensitivity": f"{point_delta:.17g}",
                    "bootstrap_delta_ci95_low": f"{float(np.quantile(delta, 0.025)):.17g}",
                    "bootstrap_delta_ci95_high": f"{float(np.quantile(delta, 0.975)):.17g}",
                    "bootstrap_replicates": str(len(delta)),
                    "point_delta_fold_macro_component_ap": f"{float(np.mean(ap_deltas)):.17g}",
                    "bootstrap_ap_delta_ci95_low": f"{float(np.quantile(ap_delta, 0.025)):.17g}",
                    "bootstrap_ap_delta_ci95_high": f"{float(np.quantile(ap_delta, 0.975)):.17g}",
                    "fold_ap_delta_min": f"{float(np.min(ap_deltas)):.17g}",
                    "fold_ap_delta_max": f"{float(np.max(ap_deltas)):.17g}",
                    "ap_inference_status": "PAIRED_COMPONENT_BOOTSTRAP_CI_NO_NULL_P_VALUE",
                    "sensitivity_inference_status": resolution_audit[task][
                        "primary_sensitivity_inference_status"
                    ],
                    "sensitivity_resolution_note": resolution_audit[task][
                        "bootstrap_caveat"
                    ],
                    "inference_status": "METRIC_SPECIFIC_STATUS_REQUIRED",
                }
            )
            bootstrap_sd = float(np.std(delta, ddof=1))
            power_mde.append(
                {
                    "task": task,
                    "metric": "fold_macro_component_sensitivity_at_0.995_specificity",
                    "anchor_method": "esmc6b_cosine",
                    "comparator_method": comparator,
                    "evaluation_positive_components": str(sum(positive_components_by_fold)),
                    "positive_components_by_fold": json.dumps(positive_components_by_fold),
                    "bootstrap_replicates": str(len(delta)),
                    "paired_bootstrap_delta_sd": f"{bootstrap_sd:.17g}",
                    "mde_80pct_two_sided_normal_approx": f"{(1.959963984540054 + 0.8416212335729143) * bootstrap_sd:.17g}",
                    "nominal_smallest_one_component_fold_macro_increment": f"{1.0 / fold_count / max(positive_components_by_fold):.17g}",
                    "inference_status": "DESCRIPTIVE_BOOTSTRAP_SD_NORMAL_APPROXIMATION_NOT_FORMAL_POWER",
                }
            )

    # Positive-component discordance ledger for the pre-registered controlled anchors.
    rescue_rows: list[dict[str, str]] = []
    for task in TASKS:
        for evaluation_fold, cycle in cycles[task].items():
            positive_rows = cycle["evaluation_positive_rows"]
            component_indices: dict[str, list[int]] = defaultdict(list)
            for index, row in enumerate(cycle["evaluation_rows"]):
                if cycle["evaluation_y"][index] == 1:
                    component_indices[row["global_component_id"]].append(index)
            anchor_threshold = threshold_lookup[
                (task, "esmc6b_cosine", evaluation_fold, primary_specificity)
            ]
            for comparator in CLASSICAL_ANCHORS:
                comparator_threshold = threshold_lookup[
                    (task, comparator, evaluation_fold, primary_specificity)
                ]
                for component, indices in sorted(component_indices.items()):
                    index_array = np.asarray(indices, dtype=np.int64)
                    anchor_fraction = float(
                        np.mean(
                            cycle["evaluation_scores"]["esmc6b_cosine"][index_array]
                            >= anchor_threshold
                        )
                    )
                    comparator_fraction = float(
                        np.mean(
                            cycle["evaluation_scores"][comparator][index_array]
                            >= comparator_threshold
                        )
                    )
                    if (anchor_fraction > 0) != (comparator_fraction > 0):
                        rescue_rows.append(
                            {
                                "task": task,
                                "positive_component": component,
                                "evaluation_fold": str(evaluation_fold),
                                "anchor_method": "esmc6b_cosine",
                                "comparator_method": comparator,
                                "direction": (
                                    "esmc6b_cosine_only"
                                    if anchor_fraction > 0
                                    else "classical_anchor_only"
                                ),
                                "anchor_record_fraction_detected": f"{anchor_fraction:.17g}",
                                "comparator_record_fraction_detected": f"{comparator_fraction:.17g}",
                                "component_record_count": str(len(index_array)),
                            }
                        )

    distance_rows: list[dict[str, str]] = []
    for task in TASKS:
        evaluation_rows = [
            row
            for fold in range(1, fold_count + 1)
            for row in cycles[task][fold]["evaluation_rows"]
        ]
        strata = distance_strata_by_task[task]
        score_by_method: dict[str, dict[str, float]] = {
            method: {} for method in ALL_METHODS
        }
        fold_by_id: dict[str, int] = {}
        label_by_id: dict[str, int] = {}
        row_by_id: dict[str, dict[str, str]] = {}
        for evaluation_fold, cycle in cycles[task].items():
            for index, row in enumerate(cycle["evaluation_rows"]):
                protein_id = row["protein_id"]
                fold_by_id[protein_id] = evaluation_fold
                label_by_id[protein_id] = int(cycle["evaluation_y"][index])
                row_by_id[protein_id] = row
                for method in ALL_METHODS:
                    score_by_method[method][protein_id] = float(
                        cycle["evaluation_scores"][method][index]
                    )
        positive_ids = [protein_id for protein_id, label in label_by_id.items() if label]
        for stratum in sorted({strata[protein_id] for protein_id in positive_ids}):
            local_ids = [protein_id for protein_id in positive_ids if strata[protein_id] == stratum]
            local_rows = [row_by_id[protein_id] for protein_id in local_ids]
            weights = component_weights(local_rows)
            for method in ALL_METHODS:
                prediction = np.asarray(
                    [
                        score_by_method[method][protein_id]
                        >= threshold_lookup[
                            (
                                task,
                                method,
                                fold_by_id[protein_id],
                                primary_specificity,
                            )
                        ]
                        for protein_id in local_ids
                    ],
                    dtype=bool,
                )
                component_count = len(
                    {row["global_component_id"] for row in local_rows}
                )
                distance_rows.append(
                    {
                        "task": task,
                        "method": method,
                        "track": METHOD_SPECS[method]["track"],
                        "distance_stratum": stratum,
                        "positive_records": str(len(local_rows)),
                        "positive_components": str(component_count),
                        "component_balanced_sensitivity_at_99.5pct_specificity": f"{float(np.average(prediction, weights=weights)):.17g}",
                        "inference_status": (
                            "DESCRIPTIVE_LOW_N" if component_count < 20 else "DESCRIPTIVE"
                        ),
                        "stratum_caveat": "BLASTP best local query coverage and identity; not a global evolutionary-distance estimate",
                    }
                )

    # Provenance registries are copied and also merged into queryable union tables.
    registry = method_registry(profile_members)
    profile_summary = profile_summary_rows(
        profile_members, psiblast_seeds, profile_artifacts
    )
    runtime_cost = runtime_cost_rows(runtime_resources, pbs_resources)
    plm_wall_seconds = attestations["plm"].get("wall_seconds")
    if plm_wall_seconds is not None:
        runtime_cost.append(
            {
                "record_kind": "plm_combined_scoring_runtime",
                "method": "PLM_STAGE_COMBINED",
                "stage_count": "1",
                "summed_stage_wall_seconds": f"{float(plm_wall_seconds):.17g}",
                "maximum_stage_wall_seconds": f"{float(plm_wall_seconds):.17g}",
                "ok_stage_count": "1",
                "reused_stage_count": "0",
                "failed_stage_count": "0",
                "cost_caveat": "combined PLM scoring/fitting receipt; precomputed embedding generation cost is excluded and cannot be allocated per PLM method",
            }
        )

    query_score_rows.sort(
        key=lambda row: (
            row["task"],
            row["method"],
            int(row["evaluation_fold"]),
            row["role"],
            row["protein_id"],
        )
    )
    thresholds.sort(
        key=lambda row: (
            row["task"], row["method"], int(row["evaluation_fold"]), float(row["specificity_target"])
        )
    )
    ladder_rows.sort(
        key=lambda row: (
            row["task"], row["method"], int(row["evaluation_fold"]), float(row["specificity_target"])
        )
    )
    metrics_cycle.sort(
        key=lambda row: (row["task"], row["method"], int(row["evaluation_fold"]))
    )
    primary_metrics.sort(key=lambda row: (row["task"], row["method"]))
    paired_deltas.sort(key=lambda row: (row["task"], row["comparator_method"]))

    write_tsv(results / "query_scores.tsv", query_score_rows, list(query_score_rows[0]))
    write_tsv(results / "thresholds.tsv", thresholds, list(thresholds[0]))
    write_tsv(
        results / "metrics_specificity_ladder.tsv", ladder_rows, list(ladder_rows[0])
    )
    write_tsv(results / "metrics_cycle.tsv", metrics_cycle, list(metrics_cycle[0]))
    write_tsv(results / "fold_metrics.tsv", metrics_cycle, list(metrics_cycle[0]))
    write_tsv(results / "metrics_primary.tsv", primary_metrics, list(primary_metrics[0]))
    write_tsv(
        results / "source_specificity.tsv", source_specificity, list(source_specificity[0])
    )
    write_tsv(
        results / "calibration_source_summary.tsv",
        calibration_source_summary,
        list(calibration_source_summary[0]),
    )
    write_tsv(results / "paired_deltas.tsv", paired_deltas, list(paired_deltas[0]))
    write_tsv(results / "power_mde.tsv", power_mde, list(power_mde[0]))
    write_tsv(
        results / "rescue_hits.tsv",
        rescue_rows,
        list(rescue_rows[0])
        if rescue_rows
        else [
            "task",
            "positive_component",
            "evaluation_fold",
            "anchor_method",
            "comparator_method",
            "direction",
            "anchor_record_fraction_detected",
            "comparator_record_fraction_detected",
            "component_record_count",
        ],
    )
    write_tsv(results / "distance_strata.tsv", distance_rows, list(distance_rows[0]))
    write_tsv(results / "method_registry.tsv", registry, list(registry[0]))
    write_tsv(results / "profile_summary.tsv", profile_summary, list(profile_summary[0]))
    write_tsv(
        results / "runtime_cost.tsv",
        runtime_cost,
        [
            "record_kind",
            "method",
            "reference_kind",
            "stage_count",
            "summed_stage_wall_seconds",
            "maximum_stage_wall_seconds",
            "ok_stage_count",
            "reused_stage_count",
            "failed_stage_count",
            "job_id",
            "job_name",
            "pbs_wall",
            "pbs_cput",
            "pbs_mem",
            "cost_caveat",
        ],
    )

    write_union_tsv(
        results / "reference_contract.tsv",
        [
            ("plm_reference_contract.tsv", plm_reference_contract),
            ("classical_reference_contract.tsv", classical_reference_contract),
        ],
    )
    write_union_tsv(
        results / "seed_profile_registry.tsv",
        [
            ("psiblast_seed_ledger.tsv", psiblast_seeds),
            ("profile_artifact_registry.tsv", profile_artifacts),
            ("profile_members.tsv", profile_members),
        ],
    )
    for name, rows in (
        ("plm_reference_contract.tsv", normalize_registry_rows(plm_reference_contract)),
        ("classical_reference_contract.tsv", normalize_registry_rows(classical_reference_contract)),
        ("psiblast_seed_ledger.tsv", psiblast_seeds),
        ("profile_artifact_registry.tsv", profile_artifacts),
        ("profile_members.tsv", profile_members),
        ("profile_inclusion_ledger.tsv", profile_inclusion),
        ("runtime_resources.tsv", runtime_resources),
        ("raw_receipt_ledger.tsv", raw_receipts),
    ):
        if not rows:
            raise RuntimeError(f"Required registry is empty: {name}")
        write_tsv(results / name, rows, list(rows[0]))
    if pbs_resources:
        write_tsv(results / "pbs_job_resources.tsv", pbs_resources, list(pbs_resources[0]))
    for name in (
        "supervised_fit_contract.tsv",
        "scores/supervised_head_diagnostics.tsv",
    ):
        source = benchmark_root / "work" / name
        if not source.is_file():
            raise FileNotFoundError(f"Required PLM receipt is missing: {source}")
        shutil.copyfile(source, results / Path(name).name)
    for name in ("plm_reproduction.json", "classical_attestation.json"):
        source = benchmark_root / "work" / name
        if not source.is_file():
            raise FileNotFoundError(f"Required attestation is missing: {source}")
        shutil.copyfile(source, results / name)

    metrics_by_key = {
        (row["task"], row["method"]): row for row in primary_metrics
    }
    delta_by_key = {
        (row["task"], row["comparator_method"]): row for row in paired_deltas
    }
    summary = {
        "status": "PROVISIONAL_PENDING_VALIDATION",
        "benchmark_id": config["benchmark_id"],
        "design_id": config["design_id"],
        "title": config["title"],
        "primary_anchor_method": "esmc6b_cosine",
        "pre_registered_classical_anchors": CLASSICAL_ANCHORS,
        "controlled_primary_methods": CONTROLLED_PRIMARY,
        "resource_augmented_secondary_methods": RESOURCE_AUGMENTED_SECONDARY,
        "metadata_secondary_methods": METADATA_SECONDARY,
        "operational_descriptive_methods": OPERATIONAL_DESCRIPTIVE,
        "operational_supervised_primary_eligible": False,
        "primary_specificity": primary_specificity,
        "primary_average_precision_estimand": "mean of five evaluation-fold component-balanced AP values",
        "pooled_raw_ap_status": "SECONDARY",
        "bootstrap_replicates": bootstrap_replicates,
        "bootstrap_contract": "one stratified global_component_id multiplicity draw per replicate, reused across every cycle/task/method and both primary metrics; each calibration threshold recalculated",
        "paired_inference": "95% paired bootstrap delta intervals for fold-macro component AP and calibrated sensitivity; sensitivity intervals are conditional where resolution_audit reports singleton negative-source strata; no bootstrap P values or Holm correction",
        "resolution_audit": resolution_audit,
        "registered_comparisons": paired_deltas,
        "fpm_status": "NOT_ESTIMABLE",
        "specificity_0.999_status": "RESOLUTION_LIMITED_SECONDARY",
        "validation_prediction_rows": protected_validation_rows,
        "test_prediction_rows": protected_test_rows,
    }
    atomic_json(results / "summary.json", summary)

    report_lines = [
        f"# {config['title']}",
        "",
        "This is an internal cyclic component-cross-fitted development comparison, not an external superiority claim.",
        "The headline is fixed in advance: ESM-C 6B cosine retrieval is compared separately with each registered classical anchor; no post-hoc best baseline is selected.",
        "",
        "## Empirical resolution audit",
        "",
        "The endpoint remains frozen at 99.5% specificity, but its empirical resolution is reported separately rather than being treated as unconditional low-FPR evidence.",
        "",
        "| Task | Sensitivity inference status | Zero-FP granularity cycles | Singleton calibration sources | Singleton evaluation sources | Low-positive-component folds |",
        "|---|---|---|---|---|---|",
    ]
    for task in TASKS:
        audit = resolution_audit[task]
        zero_fp = ",".join(
            map(str, audit["primary_zero_fp_granularity_cycles"])
        ) or "none"
        calibration_singletons = "; ".join(
            f"cycle {row['evaluation_fold']} / cal fold {row['calibration_fold']}: "
            f"{row['source']} {row['records']}/{row['components']} records/components"
            for row in audit["calibration_singleton_negative_sources"]
        ) or "none"
        evaluation_singletons = "; ".join(
            f"fold {row['evaluation_fold']}: {row['source']} "
            f"{row['records']}/{row['components']} records/components"
            for row in audit["evaluation_singleton_negative_sources"]
        ) or "none"
        low_positive = "; ".join(
            f"fold {row['evaluation_fold']}: {row['positive_records']}/"
            f"{row['positive_components']} records/components"
            for row in audit["low_positive_component_folds"]
        ) or "none"
        report_lines.append(
            f"| {task} | {audit['primary_sensitivity_inference_status']} | "
            f"{zero_fp} | {calibration_singletons} | {evaluation_singletons} | "
            f"{low_positive} |"
        )
    report_lines.extend(
        [
            "",
            "In particular, fold 3 contains 62 cellular-DJR negative records but only one global component. In cycle 2 this is the H2 calibration source: each row carries 1/62 of the negative mass, so 99%, 99.5%, and 99.9% all require zero empirical false positives. The same source is a single independent negative component when fold 3 is evaluated.",
            "A one-component fold/source stratum has bootstrap multiplicity fixed at one. Its between-component calibration/evaluation variation is therefore not estimable; affected sensitivity delta intervals are conditional on that observed component. Fold 2 also has only 18 independent VMA-positive components (119 records), so fold ranges and component counts must accompany aggregate values.",
            "",
            "## Controlled primary comparisons",
            "",
            "AP is the macro-average of five evaluation-fold component-balanced AP values. Sensitivity uses each cycle's dedicated calibration fold at 99.5% source-balanced specificity; its interval is the paired global-component bootstrap delta interval, subject to the resolution status above.",
            "",
            "| Task | Classical anchor | ESM-C cosine AP | Anchor AP | AP delta (95% CI) | ESM-C sensitivity | Anchor sensitivity | Sensitivity delta (95% CI) | Sensitivity status |",
            "|---|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for task in TASKS:
        anchor_metric = metrics_by_key[(task, "esmc6b_cosine")]
        for comparator in CLASSICAL_ANCHORS:
            comparator_metric = metrics_by_key[(task, comparator)]
            delta = delta_by_key[(task, comparator)]
            report_lines.append(
                f"| {task} | {comparator} | "
                f"{float(anchor_metric['fold_macro_component_ap']):.4f} | "
                f"{float(comparator_metric['fold_macro_component_ap']):.4f} | "
                f"{float(delta['point_delta_fold_macro_component_ap']):+.4f} "
                f"({float(delta['bootstrap_ap_delta_ci95_low']):+.4f}, "
                f"{float(delta['bootstrap_ap_delta_ci95_high']):+.4f}) | "
                f"{float(anchor_metric['fold_macro_component_sensitivity_at_primary_specificity']):.4f} | "
                f"{float(comparator_metric['fold_macro_component_sensitivity_at_primary_specificity']):.4f} | "
                f"{float(delta['point_delta_component_sensitivity']):+.4f} "
                f"({float(delta['bootstrap_delta_ci95_low']):+.4f}, "
                f"{float(delta['bootstrap_delta_ci95_high']):+.4f}) | "
                f"{delta['sensitivity_inference_status']} |"
            )

    separated_groups = [
        (
            "Other controlled-primary PLM comparator",
            ["esm2_650m_cosine"],
            "This controlled PLM comparator is not substituted for a registered classical anchor.",
        ),
        (
            "Resource-augmented secondary",
            RESOURCE_AUGMENTED_SECONDARY,
            "PSI-BLAST uses iterative positive-database enrichment and remains secondary.",
        ),
        (
            "Metadata-grouped secondary",
            METADATA_SECONDARY,
            "Family-grouped HMMER uses frozen grouping metadata and remains secondary.",
        ),
        (
            "Operational supervised descriptive only",
            OPERATIONAL_DESCRIPTIVE,
            "The supervised ESM-C system learns from labelled negatives and is not primary-eligible.",
        ),
    ]
    for heading, methods, caveat in separated_groups:
        report_lines.extend(
            [
                "",
                f"## {heading}",
                "",
                caveat,
                "",
                "| Method | Task | Fold-macro component AP (fold range) | Sensitivity@99.5% (fold range) |",
                "|---|---|---:|---:|",
            ]
        )
        for method in methods:
            for task in TASKS:
                row = metrics_by_key[(task, method)]
                report_lines.append(
                    f"| {method} | {task} | "
                    f"{float(row['fold_macro_component_ap']):.4f} "
                    f"({float(row['fold_component_ap_min']):.4f}–{float(row['fold_component_ap_max']):.4f}) | "
                    f"{float(row['fold_macro_component_sensitivity_at_primary_specificity']):.4f} "
                    f"({float(row['fold_component_sensitivity_min']):.4f}–{float(row['fold_component_sensitivity_max']):.4f}) |"
                )
    report_lines.extend(
        [
            "",
            "PSI-BLAST is resource-augmented secondary evidence, family-grouped HMMER is metadata secondary evidence, and supervised ESM-C is operational descriptive evidence only.",
            "Pooled raw AP is retained only as a secondary diagnostic. The 99.9% ladder is `RESOLUTION_LIMITED_SECONDARY`, and FP-per-million is not estimable from this cohort.",
            f"Uncertainty for both primary metrics used {bootstrap_replicates:,} paired global-component replicates. Only delta 95% intervals are reported; no bootstrap sign fraction is presented as a P value and no Holm adjustment is generated.",
            "Source-specific calibration/evaluation checks, distance strata, approximate MDE, profile construction, reference contracts, and runtime receipts are in the accompanying TSV files.",
            "",
        ]
    )
    (results / "REPORT.md").write_text("\n".join(report_lines), encoding="utf-8")
    print(
        f"PASS summarized {len(query_score_rows)} cyclic role-specific scores; "
        f"{bootstrap_replicates} paired component replicates"
    )


if __name__ == "__main__":
    main()
