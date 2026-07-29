#!/usr/bin/env python3
"""Independently validate schema-5 eight-model/mixed-head results."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import yaml


ANALYSIS_ID = "project_v0_validation_family_robustness_schema5_mixed_heads"
MODELS = (
    "esm2_650m",
    "esm2_3b",
    "esmc_300m",
    "esmc_600m",
    "esmc_6b",
    "prott5_xl",
    "prostt5",
    "esm3_open_1_4b",
)
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
EXPECTED_BINARY = {
    ("viral_vma_djr", "head1"): (1, "djr"),
    ("viral_vma_djr", "head2"): (1, "viral_morphogenesis_associated"),
    ("cellular_djr_none", "head1"): (1, "djr"),
    ("cellular_djr_none", "head2"): (0, "none"),
    ("background_non_djr", "head1"): (0, "non_djr"),
    ("hard_non_djr", "head1"): (0, "non_djr"),
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
WEIGHTING = "equal_dependence_block_then_source_cluster_then_member"
REFERENCE = "esmc_6b"
CONTEXTUAL_REFERENCE = "esm2_650m"
TOLERANCE = 1e-12
KNOWN_H3_CLASSES = ("Nucleocytoviricota", "Preplasmiviricota")
SCHEMA4_CANONICAL_MODELS = ("esm2_650m", "esmc_6b")
SCHEMA4_CANONICAL_CACHE_POLICY = (
    "checksum_bound_schema4_serialized_rows_after_legacy_operator_exact_numeric_replay"
)
PROTOCOL_AMENDMENT = "D_h3_rare_subgroup_transparency_no_model_change"
AMENDMENT_C_RESULT_CHECKSUMS_SHA256 = (
    "aa9f3cef647487d4eaec7749ceeb49c58085657a38d0d99c7577f3655448e72c"
)
AMENDMENT_C_VALIDATION_SHA256 = (
    "2b63cecae7788cce3d4c8ef96d48bf1becfbe8d74b9e9c084b2ab69a47542bcb"
)
SCHEMA3_FAMILY_MEMBER_MANIFEST_SHA256 = (
    "8cd9e9ce45ad965eb745cc4ecdf08d7e3205f57b830bca00bcf0041e5bcdf541"
)
H3_RARE_ENDPOINT_CONTRACT = {
    "Produgelaviricota_reject_recall": {
        "endpoint_role": "descriptive_subgroup",
        "diagnostic_group": "rare_formal_phylum_rejection",
        "truth_label": "Produgelaviricota",
        "expected_records": 7,
        "expected_parents": 2,
        "expected_dependence_blocks": 2,
        "bootstrap_seed_offset": 6_100,
        "interpretation": (
            "rare_formal_phylum_rejection_descriptive_not_general_unknown_detection"
        ),
    },
    "literature_unclassified_reject_recall": {
        "endpoint_role": "descriptive_single_record_subgroup",
        "diagnostic_group": "literature_unclassified_rejection",
        "truth_label": "literature-unclassified",
        "expected_records": 1,
        "expected_parents": 1,
        "expected_dependence_blocks": 1,
        "bootstrap_seed_offset": 6_110,
        "interpretation": "single_record_descriptive_only_no_generalization",
    },
    "rare_or_unclassified_reject_recall": {
        "endpoint_role": "secondary_pooled_diagnostic",
        "diagnostic_group": "small_prespecified_rejection",
        "truth_label": "unknown/other",
        "expected_records": 8,
        "expected_parents": 3,
        "expected_dependence_blocks": 3,
        "bootstrap_seed_offset": 6_100,
        "interpretation": (
            "secondary_pooled_small_prespecified_diagnostic_"
            "not_general_unknown_detection"
        ),
    },
}
AMENDMENT_D_BYTE_EQUIVALENT_ARTIFACTS = (
    "single_model_predictions.tsv",
    "system_predictions.tsv",
    "system_expected_path_predictions.tsv",
    "system_registry.tsv",
    "train_cv_candidate_summary.tsv",
    "accuracy_cost_pareto.tsv",
    "candidate_nomination.tsv",
)
LEGACY_OPERATOR_ID = "schema4_job_4968695_python3117_blas_threads4"
LEGACY_OPERATOR_ENV = {
    "OMP_NUM_THREADS": "4",
    "MKL_NUM_THREADS": "4",
    "OPENBLAS_NUM_THREADS": "4",
    "PYTHONHASHSEED": "20260724",
    "SCHEMA5_LEGACY_OPERATOR_ID": LEGACY_OPERATOR_ID,
    "SCHEMA5_PBS_NCPUS": "4",
    "SCHEMA5_PBS_MEMORY_GB": "32",
    "SCHEMA5_PYTHON_MODULE": "Python/3.11.7",
}
LEGACY_OPERATOR_DIAGNOSTIC_JOBS = {
    "schema4_canonical": {
        "job_id": 4968695,
        "overall_exit_status": 1,
        "role": "canonical_prediction_generation_and_validation_valid_then_later_job_step_failed_threads4",
    },
    "first_schema5_failure": {
        "job_id": 4968800,
        "role": "pre_metric_exact_continuity_failure_threads12",
    },
    "flawed_aggregation": {
        "job_id": 4968804,
        "role": "maximum_absolute_row_relative_value_misread_as_global",
    },
    "amendment_b_failure": {
        "job_id": 4968816,
        "role": "pre_metric_raw_tolerance_failure_threads12",
    },
    "corrected_threads12": {
        "job_id": 4968818,
        "role": "all_92844_row_numeric_aggregation_threads12_record_payload_defect_disclosed",
    },
    "exact_threads4_replay": {
        "job_id": 4968820,
        "overall_exit_status": 0,
        "role": "all_92844_keys_five_numeric_fields_exact_finite_test0_diagnostic_only",
    },
}
SCHEMA4_NUMERIC_TOLERANCES = {
    "member_probability": (5e-7, 1e-6),
    "member_raw_decision_score": (1e-5, 1e-6),
    "representative_probability": (5e-7, 1e-6),
    "representative_raw_decision_score": (1e-5, 1e-6),
    "threshold": (0.0, 0.0),
}
SCHEMA4_KEY_FIELDS = ("model_id", "protein_id", "head")
SCHEMA4_SEMANTIC_FIELDS = (
    "source_dataset",
    "paired_representative_id",
    "paired_representative_protein_id",
    "source_cluster_id",
    "source_cluster_key",
    "dependence_block_id",
    "train_relationship_stratum",
    "truth_label",
    "expected_prediction",
    "member_prediction",
    "member_predicted_label",
    "member_correct",
    "representative_prediction",
    "representative_predicted_label",
    "representative_correct",
    "applicable_to_source",
    "metric_eligible",
    "test_record",
)
REQUIRED = {
    "single_model_predictions.tsv",
    "system_predictions.tsv",
    "system_expected_path_predictions.tsv",
    "system_registry.tsv",
    "source_head_summary.tsv",
    "source_path_summary.tsv",
    "strict_cluster_summary.tsv",
    "h3_class_summary.tsv",
    "path_bootstrap_replicates.tsv",
    "pairwise_source_path_delta.tsv",
    "contextual_source_path_delta.tsv",
    "train_cv_candidate_summary.tsv",
    "accuracy_cost_pareto.tsv",
    "candidate_nomination.tsv",
    "model_cost_registry.tsv",
    "materialization_summary.tsv",
    "schema4_recomputation_audit.tsv",
    "schema4_recomputation_audit_summary.tsv",
    "legacy_numerical_operator_runtime.json",
    "summary.json",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise RuntimeError(f"Missing TSV header: {path}")
        return list(reader)


def _flag(value: Any) -> int:
    text = str(value).strip().lower()
    if text in {"1", "true", "yes"}:
        return 1
    if text in {"0", "false", "no", ""}:
        return 0
    raise RuntimeError(f"Invalid Boolean value: {value!r}")


def _close(left: Any, right: Any, tolerance: float = TOLERANCE) -> bool:
    if str(left) == "" and str(right) == "":
        return True
    return abs(float(left) - float(right)) <= tolerance


def _prediction_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return tuple(str(row[field]) for field in SCHEMA4_KEY_FIELDS)  # type: ignore[return-value]


def _prediction_rows_sha256(rows: list[Mapping[str, Any]]) -> str:
    ordered = sorted(rows, key=_prediction_key)
    fields = sorted(set().union(*(set(row) for row in ordered)))
    digest = hashlib.sha256()
    for row in ordered:
        values = [str(row.get(field, "")) for field in fields]
        digest.update(
            (json.dumps(values, ensure_ascii=True, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
        )
    return digest.hexdigest()


def _binary_label(head: str, prediction: int) -> str:
    if head == "head1":
        return "djr" if prediction else "non_djr"
    if head == "head2":
        return "viral_morphogenesis_associated" if prediction else "none"
    raise RuntimeError(f"Not a binary head: {head}")


def _derive_recomputed_decisions(row: Mapping[str, Any]) -> None:
    source, head = str(row["source_dataset"]), str(row["head"])
    if (
        source not in APPLICABLE_HEADS
        or head not in APPLICABLE_HEADS[source]
        or _flag(row["applicable_to_source"]) != 1
        or _flag(row["test_record"]) != 0
    ):
        raise RuntimeError(f"Illegal audit source/head/Test semantics: {_prediction_key(row)}")
    threshold = float(row["threshold"])
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise RuntimeError(f"Invalid audit threshold: {_prediction_key(row)}")
    for role in ("member", "representative"):
        probability = float(row[f"{role}_probability"])
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise RuntimeError(f"Invalid audit probability: {_prediction_key(row)}/{role}")
        raw = str(row[f"{role}_raw_decision_score"])
        if head == "head3_phylum":
            if raw != "":
                raise RuntimeError(f"H3 raw score must be blank: {_prediction_key(row)}")
            prediction = str(row[f"{role}_prediction"])
            if (
                (probability < threshold and prediction != "unknown/other")
                or (probability >= threshold and prediction not in KNOWN_H3_CLASSES)
                or str(row[f"{role}_predicted_label"]) != prediction
            ):
                raise RuntimeError(f"H3 audit reject/call mismatch: {_prediction_key(row)}/{role}")
        else:
            if raw == "" or not math.isfinite(float(raw)):
                raise RuntimeError(f"Binary audit raw score is invalid: {_prediction_key(row)}")
            prediction = int(probability >= threshold)
            if (
                _flag(row[f"{role}_prediction"]) != prediction
                or str(row[f"{role}_predicted_label"]) != _binary_label(head, prediction)
            ):
                raise RuntimeError(f"Binary audit call mismatch: {_prediction_key(row)}/{role}")
    eligible = _flag(row["metric_eligible"])
    if head == "head3_phylum":
        truth = str(row["truth_label"])
        if eligible:
            if not truth or str(row["expected_prediction"]) != truth:
                raise RuntimeError(f"Eligible H3 audit truth mismatch: {_prediction_key(row)}")
            for role in ("member", "representative"):
                expected = int(str(row[f"{role}_prediction"]) == truth)
                if _flag(row[f"{role}_correct"]) != expected:
                    raise RuntimeError(f"H3 audit correctness mismatch: {_prediction_key(row)}/{role}")
        elif any(
            str(row[field]) != ""
            for field in ("truth_label", "expected_prediction", "member_correct", "representative_correct")
        ):
            raise RuntimeError(f"Ineligible H3 audit fields are nonblank: {_prediction_key(row)}")
    else:
        expected, truth = EXPECTED_BINARY[(source, head)]
        if (
            eligible != 1
            or _flag(row["expected_prediction"]) != expected
            or str(row["truth_label"]) != truth
        ):
            raise RuntimeError(f"Binary audit truth mismatch: {_prediction_key(row)}")
        for role in ("member", "representative"):
            correct = int(_flag(row[f"{role}_prediction"]) == expected)
            if _flag(row[f"{role}_correct"]) != correct:
                raise RuntimeError(f"Binary audit correctness mismatch: {_prediction_key(row)}/{role}")


def _verify_schema4_prediction_binding(config: Mapping[str, Any]) -> str:
    manifest = Path(config["schema4_result_checksums"])
    prediction_path = Path(config["schema4_result_dir"]) / "predictions.tsv"
    if manifest.parent != prediction_path.parent:
        raise RuntimeError("Schema-4 prediction cache path is outside its frozen result bundle")
    entries: dict[str, str] = {}
    for line_number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split(maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError(f"Malformed schema-4 checksum line: {line_number}")
        expected, name = parts[0].lower(), parts[1].strip().lstrip("*")
        if Path(name).name != name or name in entries:
            raise RuntimeError("Unsafe/duplicate schema-4 checksum target")
        entries[name] = expected
    observed = _sha256(prediction_path)
    if entries.get("predictions.tsv") != observed:
        raise RuntimeError("Schema-4 prediction cache is not checksum-bound")
    validation = json.loads(Path(config["schema4_validation"]).read_text(encoding="utf-8"))
    if validation.get("status") != "PASS" or validation.get("counts", {}).get("test_records") != 0:
        raise RuntimeError("Schema-4 cache validation is not PASS/Test=0")
    return observed


def _validate_schema4_canonical_cache(
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    single: list[dict[str, str]],
    audit_rows: list[dict[str, str]],
    audit_summary_rows: list[dict[str, str]],
) -> dict[str, Any]:
    canonical_path = Path(config["schema4_result_dir"]) / "predictions.tsv"
    old_rows = _read(canonical_path)
    selected = [row for row in single if row["model_id"] in SCHEMA4_CANONICAL_MODELS]
    old_keys = [_prediction_key(row) for row in old_rows]
    new_keys = [_prediction_key(row) for row in selected]
    audit_keys = [_prediction_key(row) for row in audit_rows]
    expected_count = int(config["schema4_expected_prediction_rows"])
    if (
        len(old_rows) != expected_count
        or len(selected) != expected_count
        or len(audit_rows) != expected_count
        or len(set(old_keys)) != expected_count
        or len(set(new_keys)) != expected_count
        or len(set(audit_keys)) != expected_count
        or set(old_keys) != set(new_keys)
        or set(old_keys) != set(audit_keys)
        or {key[0] for key in old_keys} != set(SCHEMA4_CANONICAL_MODELS)
    ):
        raise RuntimeError("Schema-4 canonical/cache/audit key coverage mismatch")
    expected_fields = set(SCHEMA4_KEY_FIELDS) | set(SCHEMA4_SEMANTIC_FIELDS) | set(
        SCHEMA4_NUMERIC_TOLERANCES
    )
    if any(set(row) != expected_fields for row in old_rows + selected):
        raise RuntimeError("Canonical prediction field schema mismatch")
    old = dict(zip(old_keys, old_rows))
    new = dict(zip(new_keys, selected))
    audit = dict(zip(audit_keys, audit_rows))
    numeric_stats: dict[str, dict[str, Any]] = {
        field: {
            "absolute_tolerance": absolute,
            "relative_tolerance": relative,
            "comparisons": 0,
            "blank_pairs": 0,
            "nonexact_comparisons": 0,
            "max_absolute_delta": 0.0,
            "max_absolute_delta_key": "",
            "max_relative_delta": 0.0,
            "max_relative_delta_key": "",
            "max_tolerance_ratio": 0.0,
            "max_tolerance_ratio_key": "",
        }
        for field, (absolute, relative) in SCHEMA4_NUMERIC_TOLERANCES.items()
    }
    expected_audit_fields = set(SCHEMA4_KEY_FIELDS) | {
        f"recomputed_{field}" for field in SCHEMA4_SEMANTIC_FIELDS
    } | {"semantic_fields_exact", "derived_decisions_exact", "audit_status"}
    for field in SCHEMA4_NUMERIC_TOLERANCES:
        expected_audit_fields.update(
            {
                f"canonical_{field}",
                f"recomputed_{field}",
                f"{field}_exact_replay",
                f"{field}_blank_parity",
                f"{field}_absolute_delta",
                f"{field}_relative_delta",
                f"{field}_tolerance_limit",
                f"{field}_tolerance_ratio",
                f"{field}_within_tolerance",
            }
        )
    if any(set(row) != expected_audit_fields for row in audit_rows):
        raise RuntimeError("Row-level schema-4 audit field schema mismatch")
    recomputed_rows: list[dict[str, str]] = []
    semantic_comparisons = 0
    for key in sorted(old):
        canonical, emitted, evidence = old[key], new[key], audit[key]
        if canonical != emitted:
            raise RuntimeError(f"Schema-4 canonical row not preserved exactly: {key}")
        if (
            evidence["audit_status"] != "PASS"
            or _flag(evidence["semantic_fields_exact"]) != 1
            or _flag(evidence["derived_decisions_exact"]) != 1
        ):
            raise RuntimeError(f"Schema-4 row audit did not pass: {key}")
        fresh: dict[str, str] = {field: key[index] for index, field in enumerate(SCHEMA4_KEY_FIELDS)}
        for field in SCHEMA4_SEMANTIC_FIELDS:
            semantic_comparisons += 1
            fresh[field] = evidence[f"recomputed_{field}"]
            if canonical[field] != fresh[field]:
                raise RuntimeError(f"Schema-4 audit semantic mismatch: {key}/{field}")
        for field, (absolute_tolerance, relative_tolerance) in SCHEMA4_NUMERIC_TOLERANCES.items():
            left_text = canonical[field]
            right_text = evidence[f"recomputed_{field}"]
            fresh[field] = right_text
            if evidence[f"canonical_{field}"] != left_text:
                raise RuntimeError(f"Schema-4 audit canonical value mismatch: {key}/{field}")
            exact_replay = left_text == right_text
            if not exact_replay or _flag(evidence[f"{field}_exact_replay"]) != 1:
                raise RuntimeError(
                    f"Schema-4 legacy-operator exact numeric replay failure: {key}/{field}"
                )
            blank_parity = (left_text == "") == (right_text == "")
            if not blank_parity or _flag(evidence[f"{field}_blank_parity"]) != 1:
                raise RuntimeError(f"Schema-4 audit blank parity mismatch: {key}/{field}")
            stats = numeric_stats[field]
            if left_text == "":
                stats["blank_pairs"] += 1
                if (
                    any(
                        evidence[f"{field}_{suffix}"] != ""
                        for suffix in (
                            "absolute_delta",
                            "relative_delta",
                            "tolerance_limit",
                            "tolerance_ratio",
                        )
                    )
                    or _flag(evidence[f"{field}_within_tolerance"]) != 1
                ):
                    raise RuntimeError(f"Schema-4 blank audit numeric fields are nonblank: {key}/{field}")
                continue
            left, right = float(left_text), float(right_text)
            if not math.isfinite(left) or not math.isfinite(right):
                raise RuntimeError(f"Schema-4 audit contains non-finite values: {key}/{field}")
            if "probability" in field and (not 0.0 <= left <= 1.0 or not 0.0 <= right <= 1.0):
                raise RuntimeError(f"Schema-4 audit probability outside [0,1]: {key}/{field}")
            delta = abs(right - left)
            relative_delta = delta / max(abs(left), abs(right), np.finfo(np.float64).tiny)
            tolerance_limit = absolute_tolerance + relative_tolerance * abs(left)
            tolerance_ratio = (
                0.0
                if delta == 0.0
                else math.inf if tolerance_limit == 0.0 else delta / tolerance_limit
            )
            if (
                not _close(evidence[f"{field}_absolute_delta"], delta)
                or not _close(evidence[f"{field}_relative_delta"], relative_delta)
                or not _close(evidence[f"{field}_tolerance_limit"], tolerance_limit)
                or not _close(evidence[f"{field}_tolerance_ratio"], tolerance_ratio)
                or _flag(evidence[f"{field}_within_tolerance"]) != 1
                or delta > tolerance_limit
            ):
                raise RuntimeError(f"Schema-4 audit upper-bound failure: {key}/{field}")
            stats["comparisons"] += 1
            stats["nonexact_comparisons"] += int(not exact_replay)
            key_text = "|".join(key)
            for metric, value in (
                ("absolute_delta", delta),
                ("relative_delta", relative_delta),
                ("tolerance_ratio", tolerance_ratio),
            ):
                maximum = f"max_{metric}"
                if value > float(stats[maximum]):
                    stats[maximum] = value
                    stats[f"{maximum}_key"] = key_text
        _derive_recomputed_decisions(fresh)
        recomputed_rows.append(fresh)

    cache = summary.get("schema4_canonical_prediction_cache")
    if not isinstance(cache, dict):
        raise RuntimeError("Missing schema-4 canonical cache provenance")
    fixed_cache = {
        "status": "PASS",
        "policy": SCHEMA4_CANONICAL_CACHE_POLICY,
        "canonical_models": list(SCHEMA4_CANONICAL_MODELS),
        "canonical_source": str(canonical_path),
        "canonical_source_sha256": _sha256(canonical_path),
        "prediction_keys": expected_count,
        "canonicalized_rows": expected_count,
        "row_level_audit_rows": expected_count,
        "prediction_fields": len(expected_fields),
        "semantic_fields": list(SCHEMA4_SEMANTIC_FIELDS),
        "semantic_comparisons": semantic_comparisons,
        "semantic_mismatches": 0,
        "derived_decision_mismatches": 0,
        "exact_numeric_string_replay_required": True,
        "exact_numeric_string_comparisons": expected_count
        * len(SCHEMA4_NUMERIC_TOLERANCES),
        "numeric_string_mismatches": 0,
        "legacy_numerical_operator_id": LEGACY_OPERATOR_ID,
        "amendment_b_tolerances_retained_as_upper_bound": True,
        "test_records": 0,
        "recomputed_prediction_rows_sha256": _prediction_rows_sha256(recomputed_rows),
        "canonical_prediction_rows_sha256": _prediction_rows_sha256(selected),
        "canonicalization": "all_rows_substituted_only_after_complete_audit_pass",
        "interpretation": (
            "legacy_four_thread_operator_exact_numeric_replay_no_endpoint_or_model_change"
        ),
    }
    for field, expected in fixed_cache.items():
        if cache.get(field) != expected:
            raise RuntimeError(f"Schema-4 cache summary mismatch: {field}")
    cached_numeric = cache.get("numeric_fields")
    if not isinstance(cached_numeric, dict) or set(cached_numeric) != set(numeric_stats):
        raise RuntimeError("Schema-4 cache numeric summary fields mismatch")
    numeric_summary = {row["audit_item"]: row for row in audit_summary_rows}
    expected_summary_items = {
        "prediction_keys",
        "semantic_fields",
        "derived_decisions",
        "exact_numeric_string_replay",
        "test_records",
        *SCHEMA4_NUMERIC_TOLERANCES,
    }
    if len(numeric_summary) != len(audit_summary_rows) or set(numeric_summary) != expected_summary_items:
        raise RuntimeError("Schema-4 aggregate audit table is incomplete/duplicated")
    for row in audit_summary_rows:
        if (
            row["status"] != "PASS"
            or row["policy"] != SCHEMA4_CANONICAL_CACHE_POLICY
            or row["canonical_source_sha256"] != fixed_cache["canonical_source_sha256"]
        ):
            raise RuntimeError("Schema-4 aggregate audit common provenance mismatch")
    contract_expectations = {
        "prediction_keys": (expected_count, 0),
        "semantic_fields": (semantic_comparisons, 0),
        "derived_decisions": (expected_count, 0),
        "exact_numeric_string_replay": (
            expected_count * len(SCHEMA4_NUMERIC_TOLERANCES),
            0,
        ),
        "test_records": (expected_count, 0),
    }
    for item, (comparisons, mismatches) in contract_expectations.items():
        row = numeric_summary[item]
        if int(row["comparisons"]) != comparisons or int(row["mismatches"]) != mismatches:
            raise RuntimeError(f"Schema-4 aggregate contract mismatch: {item}")
    for field, stats in numeric_stats.items():
        cached = cached_numeric[field]
        row = numeric_summary[field]
        for integer_field in ("comparisons", "blank_pairs", "nonexact_comparisons"):
            if int(cached[integer_field]) != int(stats[integer_field]) or int(row[integer_field]) != int(stats[integer_field]):
                raise RuntimeError(f"Schema-4 numeric audit count mismatch: {field}/{integer_field}")
        for value_field in (
            "absolute_tolerance",
            "relative_tolerance",
            "max_absolute_delta",
            "max_relative_delta",
            "max_tolerance_ratio",
        ):
            if not _close(cached[value_field], stats[value_field]) or not _close(row[value_field], stats[value_field]):
                raise RuntimeError(f"Schema-4 numeric audit value mismatch: {field}/{value_field}")
        for key_field in (
            "max_absolute_delta_key",
            "max_relative_delta_key",
            "max_tolerance_ratio_key",
        ):
            if cached[key_field] != stats[key_field] or row[key_field] != stats[key_field]:
                raise RuntimeError(f"Schema-4 numeric audit maximum key mismatch: {field}/{key_field}")
        if int(row["mismatches"]) != 0:
            raise RuntimeError(f"Schema-4 numeric audit reports a mismatch: {field}")
        if row["comparison_kind"] != (
            "exact_serialized_equality_with_fixed_amendment_b_upper_bound"
        ):
            raise RuntimeError(f"Schema-4 numeric comparison policy changed: {field}")
    return {
        "prediction_keys": expected_count,
        "row_level_audit_rows": len(audit_rows),
        "aggregate_audit_rows": len(audit_summary_rows),
        "canonical_source_sha256": fixed_cache["canonical_source_sha256"],
        "recomputed_prediction_rows_sha256": fixed_cache[
            "recomputed_prediction_rows_sha256"
        ],
        "numeric_fields": numeric_stats,
        "exact_numeric_string_comparisons": fixed_cache[
            "exact_numeric_string_comparisons"
        ],
        "numeric_string_mismatches": 0,
        "legacy_numerical_operator_id": LEGACY_OPERATOR_ID,
        "test_records": 0,
    }


def _verify_result(directory: Path) -> dict[str, str]:
    manifest = directory / "CHECKSUMS.sha256"
    verified: dict[str, str] = {}
    for line_number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split(maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError(f"Malformed result manifest line {line_number}")
        expected, name = parts[0].lower(), parts[1].strip().lstrip("*")
        target = directory / name
        if Path(name).name != name or name in verified or not target.is_file() or _sha256(target) != expected:
            raise RuntimeError(f"Unsafe, missing, or mismatched result artifact: {name}")
        verified[name] = expected
    if set(verified) != REQUIRED:
        raise RuntimeError(f"Schema-5 exact result contract differs: {sorted(set(verified) ^ REQUIRED)}")
    return verified


def _validate_legacy_operator_runtime(
    config: Mapping[str, Any],
    config_path: Path,
    result_dir: Path,
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Independently validate the checksum-bound runtime attestation."""

    runtime_path = result_dir / "legacy_numerical_operator_runtime.json"
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    operator = config["legacy_schema4_numerical_operator"]
    runtime_sha256 = _sha256(runtime_path)
    if (
        runtime.get("schema_version") != 1
        or runtime.get("status") != "PASS"
        or runtime.get("operator_id") != LEGACY_OPERATOR_ID
        or runtime.get("cache_policy") != SCHEMA4_CANONICAL_CACHE_POLICY
        or runtime.get("canonical_schema4_job") != 4968695
        or runtime.get("canonical_schema4_job_overall_status")
        != "Exit1_after_valid_prediction_generation_and_independent_prediction_validation"
        or runtime.get("exact_numeric_string_replay_required") is not True
        or runtime.get("amendment_b_tolerances_retained_as_upper_bound") is not True
    ):
        raise RuntimeError("Legacy numerical-operator runtime boundary changed")
    environment = runtime.get("environment")
    if not isinstance(environment, dict) or any(
        environment.get(key) != expected for key, expected in LEGACY_OPERATOR_ENV.items()
    ) or environment.get("VIRTUAL_ENV") != operator["venv_root"]:
        raise RuntimeError("Legacy numerical-operator runtime environment mismatch")
    pbs = runtime.get("pbs")
    if (
        not isinstance(pbs, dict)
        or not str(pbs.get("job_id", "")).strip()
        or int(pbs.get("ncpus", -1)) != 4
        or int(pbs.get("memory_gb", -1)) != 32
    ):
        raise RuntimeError("Legacy numerical-operator PBS attestation mismatch")
    python = runtime.get("python")
    if (
        not isinstance(python, dict)
        or python.get("module") != "Python/3.11.7"
        or python.get("version") != "3.11.7"
        or python.get("executable") != python.get("configured_venv_python")
    ):
        raise RuntimeError("Legacy numerical-operator Python attestation mismatch")

    preload = runtime.get("runtime_preload_modules")
    if (
        not isinstance(preload, list)
        or [row.get("module") for row in preload]
        != ["scipy.linalg", "sklearn.linear_model"]
        or any(
            not str(row.get("package_version", ""))
            or not Path(str(row.get("module_file", ""))).is_absolute()
            for row in preload
        )
    ):
        raise RuntimeError("Legacy numerical-operator preload attestation mismatch")

    pools = runtime.get("threadpools")
    expected_pool_count = int(operator["required_threadpool_count"])
    expected_api_counts = {
        str(key): int(value)
        for key, value in operator["required_threadpool_user_api_counts"].items()
    }
    if not isinstance(pools, list):
        raise RuntimeError("Legacy numerical-operator threadpool list is missing")
    observed_api_counts = dict(
        sorted(Counter(str(pool.get("user_api", "")) for pool in pools).items())
    )
    for pool in pools:
        filepath = str(pool.get("filepath", ""))
        if (
            int(pool.get("num_threads", -1)) != 4
            or not str(pool.get("internal_api", ""))
            or not str(pool.get("version", ""))
            or not Path(filepath).is_absolute()
            or pool.get("file_basename") != Path(filepath).name
        ):
            raise RuntimeError("Legacy numerical-operator threadpool record mismatch")
    if (
        len(pools) != expected_pool_count
        or int(runtime.get("threadpool_count", -1)) != expected_pool_count
        or observed_api_counts != expected_api_counts
        or runtime.get("threadpool_user_api_counts") != expected_api_counts
    ):
        raise RuntimeError("Legacy numerical-operator threadpool topology mismatch")

    validator_path = Path(__file__).resolve()
    scorer_path = validator_path.with_name(
        validator_path.name.replace("validate_", "score_", 1)
    )
    launcher_path = Path(__file__).resolve().with_name(
        "run_validation_family_robustness_v0_schema5_mixed_heads.pbs"
    )
    expected_lineage = {
        "config": _sha256(config_path),
        "protocol": _sha256(Path(config["protocol"])),
        "scorer": _sha256(scorer_path),
        "pbs_launcher": _sha256(launcher_path),
    }
    if runtime.get("lineage_sha256") != expected_lineage:
        raise RuntimeError("Legacy numerical-operator runtime source lineage mismatch")
    summary_runtime = summary.get("legacy_numerical_operator_runtime")
    if not isinstance(summary_runtime, dict) or summary_runtime != {
        "status": "PASS",
        "operator_id": LEGACY_OPERATOR_ID,
        "artifact": runtime_path.name,
        "artifact_sha256": runtime_sha256,
        "pbs_job_id": pbs["job_id"],
        "python_version": "3.11.7",
        "runtime_preload_modules": ["scipy.linalg", "sklearn.linear_model"],
        "threadpool_count": expected_pool_count,
        "exact_numeric_string_replay_required": True,
    }:
        raise RuntimeError("Legacy numerical-operator summary binding mismatch")
    if (
        summary.get("lineage_sha256", {}).get("legacy_numerical_operator_runtime")
        != runtime_sha256
    ):
        raise RuntimeError("Legacy numerical-operator runtime checksum is not in summary lineage")
    return {
        "status": "PASS",
        "operator_id": LEGACY_OPERATOR_ID,
        "runtime_sha256": runtime_sha256,
        "pbs_job_id": pbs["job_id"],
        "python_version": "3.11.7",
        "runtime_preload_modules": ["scipy.linalg", "sklearn.linear_model"],
        "threadpool_count": expected_pool_count,
        "threadpool_user_api_counts": expected_api_counts,
    }


def _bootstrap(rep: np.ndarray, member: np.ndarray, replicates: int, seed: int):
    rng = np.random.default_rng(seed)
    rep_boot = np.empty(replicates, dtype=float)
    member_boot = np.empty(replicates, dtype=float)
    for start in range(0, replicates, 256):
        stop = min(start + 256, replicates)
        selected = rng.integers(0, len(member), size=(stop - start, len(member)))
        rep_boot[start:stop] = rep[selected].mean(axis=1)
        member_boot[start:stop] = member[selected].mean(axis=1)
    return rep_boot, member_boot, member_boot - rep_boot


def _nested(rows: list[dict[str, str]], replicates: int, seed: int):
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["dependence_block_id"], row["source_cluster_key"])].append(row)
    if not grouped:
        raise RuntimeError("Cannot validate an empty endpoint")
    rep_by_block: dict[str, list[float]] = defaultdict(list)
    member_by_block: dict[str, list[float]] = defaultdict(list)
    cluster_all: list[int] = []
    for (block, _cluster), records in sorted(grouped.items()):
        rep = {_flag(row["representative_correct"]) for row in records}
        if len(rep) != 1:
            raise RuntimeError("Representative call changed inside cluster")
        members = [_flag(row["member_correct"]) for row in records]
        rep_by_block[block].append(float(next(iter(rep))))
        member_by_block[block].append(float(np.mean(members)))
        cluster_all.append(int(all(members)))
    blocks = sorted(member_by_block)
    rep = np.asarray([np.mean(rep_by_block[block]) for block in blocks], dtype=float)
    member = np.asarray([np.mean(member_by_block[block]) for block in blocks], dtype=float)
    boot = _bootstrap(rep, member, replicates, seed)
    return {
        "representative_value": float(rep.mean()),
        "representative_ci_low": float(np.quantile(boot[0], 0.025)),
        "representative_ci_high": float(np.quantile(boot[0], 0.975)),
        "member_value": float(member.mean()),
        "member_ci_low": float(np.quantile(boot[1], 0.025)),
        "member_ci_high": float(np.quantile(boot[1], 0.975)),
        "delta_members_minus_representative": float(member.mean() - rep.mean()),
        "delta_ci_low": float(np.quantile(boot[2], 0.025)),
        "delta_ci_high": float(np.quantile(boot[2], 0.975)),
        "n_member_records": len(rows),
        "n_source_clusters": len(grouped),
        "n_dependence_blocks": len(blocks),
        "clusters_all_members_correct": sum(cluster_all),
        "proportion_clusters_all_members_correct": float(np.mean(cluster_all)),
    }, boot


def _compare_summary(observed: Mapping[str, str], expected: Mapping[str, Any]) -> None:
    for field in (
        "n_member_records",
        "n_source_clusters",
        "n_dependence_blocks",
        "clusters_all_members_correct",
    ):
        if int(observed[field]) != int(expected[field]):
            raise RuntimeError(f"Endpoint support mismatch: {field}")
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
        if not _close(observed[field], expected[field]):
            raise RuntimeError(f"Endpoint value mismatch: {field}")


def _validate_recomposition(
    single: list[dict[str, str]],
    systems: list[dict[str, str]],
    registry: list[dict[str, str]],
    candidates: list[dict[str, str]],
) -> None:
    base = {(row["model_id"], row["protein_id"], row["head"]): row for row in single}
    if len(base) != len(single):
        raise RuntimeError("Duplicate base prediction")
    system_spec = {row["system_id"]: row for row in registry}
    if len(system_spec) != 17 or sum(_flag(row["unique_prediction_system"]) for row in registry) != 16:
        raise RuntimeError("System registry is not 8+9 labels / 16 unique")
    for model in MODELS:
        row = system_spec.get(model)
        if not row or {row["head1_model"], row["head2_model"], row["head3_model"]} != {model}:
            raise RuntimeError("Homogeneous system registry mapping changed")
    for candidate in candidates:
        row = system_spec.get(candidate["candidate_id"])
        if not row or (
            row["head1_model"] != candidate["head1_model"]
            or row["head2_model"] != candidate["head2_model"]
            or row["head3_model"] != candidate["head3_model"]
        ):
            raise RuntimeError("Primary mixed-candidate registry mapping changed")
    value_fields = [
        field
        for field in single[0]
        if field not in {"model_id"}
    ]
    seen: set[tuple[str, str, str]] = set()
    for row in systems:
        key = (row["system_id"], row["protein_id"], row["head"])
        if key in seen:
            raise RuntimeError("Duplicate recomposed prediction")
        seen.add(key)
        spec = system_spec[row["system_id"]]
        mapping = {
            "head1": spec["head1_model"],
            "head2": spec["head2_model"],
            "head3_phylum": spec["head3_model"],
        }
        origin = mapping[row["head"]]
        if row["head_model_id"] != origin:
            raise RuntimeError("Recomposed head provenance is wrong")
        expected = base[(origin, row["protein_id"], row["head"])]
        for field in value_fields:
            if str(row.get(field, "")) != str(expected.get(field, "")):
                raise RuntimeError(f"Recomposed value mismatch: {key}/{field}")
    if len(seen) != len(single) * len(registry) // len(MODELS):
        raise RuntimeError("Recomposed prediction row count mismatch")


def _validate_paths(systems: list[dict[str, str]], paths: list[dict[str, str]]) -> None:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in systems:
        grouped[(row["system_id"], row["protein_id"])].append(row)
    index = {(row["system_id"], row["protein_id"]): row for row in paths}
    if len(index) != len(paths) or set(index) != set(grouped):
        raise RuntimeError("Path rows are not one-to-one with system/protein")
    for key, records in grouped.items():
        source = records[0]["source_dataset"]
        eligible = [row for row in records if _flag(row["metric_eligible"]) == 1]
        eligible.sort(key=lambda row: APPLICABLE_HEADS[source].index(row["head"]))
        path = index[key]
        if (
            path["expected_path"] != ">".join(row["truth_label"] for row in eligible)
            or path["member_observed_path"]
            != ">".join(row["member_predicted_label"] for row in eligible)
            or path["representative_observed_path"]
            != ">".join(row["representative_predicted_label"] for row in eligible)
            or _flag(path["member_correct"])
            != int(all(_flag(row["member_correct"]) for row in eligible))
            or _flag(path["representative_correct"])
            != int(all(_flag(row["representative_correct"]) for row in eligible))
            or int(path["n_applicable_heads"]) != len(eligible)
        ):
            raise RuntimeError(f"Path recomposition mismatch: {key}")


def _holm(p_values: Mapping[str, float]) -> dict[str, float]:
    ordered = sorted(p_values, key=lambda key: (p_values[key], key))
    count, running, result = len(ordered), 0.0, {}
    for rank, key in enumerate(ordered):
        running = max(running, min(1.0, (count - rank) * p_values[key]))
        result[key] = running
    return result


def _weighted_f1_point(rows: list[dict[str, str]], target: str, role: str) -> float:
    clusters_by_block: dict[str, set[str]] = defaultdict(set)
    records_by_cluster: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        block, cluster = row["dependence_block_id"], row["source_cluster_key"]
        clusters_by_block[block].add(cluster)
        records_by_cluster[(block, cluster)] += 1
    tp = fp = fn = 0.0
    for row in rows:
        block, cluster = row["dependence_block_id"], row["source_cluster_key"]
        weight = 1.0 / len(clusters_by_block[block]) / records_by_cluster[(block, cluster)]
        truth = row["truth_label"] == target
        predicted = row[f"{role}_predicted_label"] == target
        if truth and predicted:
            tp += weight
        elif not truth and predicted:
            fp += weight
        elif truth:
            fn += weight
    denominator = 2 * tp + fp + fn
    return 0.0 if denominator == 0 else 2 * tp / denominator


def _f1_contributions(rows: list[dict[str, str]], target: str):
    blocks = sorted({row["dependence_block_id"] for row in rows})
    block_index = {block: index for index, block in enumerate(blocks)}
    clusters_by_block: dict[str, set[str]] = defaultdict(set)
    records_by_cluster: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        block, cluster = row["dependence_block_id"], row["source_cluster_key"]
        clusters_by_block[block].add(cluster)
        records_by_cluster[(block, cluster)] += 1
    rep = np.zeros((len(blocks), 3), dtype=float)
    member = np.zeros_like(rep)
    for row in rows:
        block, cluster = row["dependence_block_id"], row["source_cluster_key"]
        weight = 1.0 / len(clusters_by_block[block]) / records_by_cluster[(block, cluster)]
        truth = row["truth_label"] == target
        for role, matrix in (("representative", rep), ("member", member)):
            predicted = row[f"{role}_predicted_label"] == target
            if truth and predicted:
                column = 0
            elif not truth and predicted:
                column = 1
            elif truth:
                column = 2
            else:
                continue
            matrix[block_index[block], column] += weight
    return blocks, rep, member


def _f1_from_confusion(contribution: np.ndarray) -> np.ndarray:
    denominator = 2 * contribution[..., 0] + contribution[..., 1] + contribution[..., 2]
    return np.divide(
        2 * contribution[..., 0],
        denominator,
        out=np.zeros_like(denominator),
        where=denominator != 0,
    )


def _f1_metric(rows: list[dict[str, str]], target: str, replicates: int, seed: int):
    blocks, rep, member = _f1_contributions(rows, target)
    rep_value = float(_f1_from_confusion(rep.sum(axis=0)))
    member_value = float(_f1_from_confusion(member.sum(axis=0)))
    rng = np.random.default_rng(seed)
    rep_boot = np.empty(replicates, dtype=float)
    member_boot = np.empty(replicates, dtype=float)
    for start in range(0, replicates, 256):
        stop = min(start + 256, replicates)
        selected = rng.integers(0, len(blocks), size=(stop - start, len(blocks)))
        rep_boot[start:stop] = _f1_from_confusion(rep[selected].sum(axis=1))
        member_boot[start:stop] = _f1_from_confusion(member[selected].sum(axis=1))
    delta = member_boot - rep_boot
    return {
        "representative_value": rep_value,
        "representative_ci_low": float(np.quantile(rep_boot, 0.025)),
        "representative_ci_high": float(np.quantile(rep_boot, 0.975)),
        "member_value": member_value,
        "member_ci_low": float(np.quantile(member_boot, 0.025)),
        "member_ci_high": float(np.quantile(member_boot, 0.975)),
        "delta_members_minus_representative": member_value - rep_value,
        "delta_ci_low": float(np.quantile(delta, 0.025)),
        "delta_ci_high": float(np.quantile(delta, 0.975)),
    }


def _macro_f1_metric(
    rows: list[dict[str, str]], targets: tuple[str, ...], replicates: int, seed: int
):
    contributions = [_f1_contributions(rows, target) for target in targets]
    blocks = contributions[0][0]
    if any(item[0] != blocks for item in contributions[1:]):
        raise RuntimeError("H3 macro-F1 target block sets differ")
    rep = np.stack([item[1] for item in contributions])
    member = np.stack([item[2] for item in contributions])

    def macro(value: np.ndarray) -> np.ndarray:
        return _f1_from_confusion(value).mean(axis=0)

    rep_value = float(macro(rep.sum(axis=1)))
    member_value = float(macro(member.sum(axis=1)))
    rng = np.random.default_rng(seed)
    rep_boot = np.empty(replicates, dtype=float)
    member_boot = np.empty(replicates, dtype=float)
    for start in range(0, replicates, 256):
        stop = min(start + 256, replicates)
        selected = rng.integers(0, len(blocks), size=(stop - start, len(blocks)))
        rep_values = np.stack([rep[:, index, :].sum(axis=1) for index in selected])
        member_values = np.stack([member[:, index, :].sum(axis=1) for index in selected])
        rep_boot[start:stop] = macro(np.moveaxis(rep_values, 1, 0))
        member_boot[start:stop] = macro(np.moveaxis(member_values, 1, 0))
    delta = member_boot - rep_boot
    return {
        "representative_value": rep_value,
        "representative_ci_low": float(np.quantile(rep_boot, 0.025)),
        "representative_ci_high": float(np.quantile(rep_boot, 0.975)),
        "member_value": member_value,
        "member_ci_low": float(np.quantile(member_boot, 0.025)),
        "member_ci_high": float(np.quantile(member_boot, 0.975)),
        "delta_members_minus_representative": member_value - rep_value,
        "delta_ci_low": float(np.quantile(delta, 0.025)),
        "delta_ci_high": float(np.quantile(delta, 0.975)),
    }


def _compare_h3_metric(observed: Mapping[str, str], expected: Mapping[str, float]) -> None:
    for field, value in expected.items():
        if not _close(observed[field], value):
            raise RuntimeError(f"H3 metric/bootstrap mismatch: {field}")


def _load_h3_rare_subgroups(
    config: Mapping[str, Any], expected_manifest_sha256: str
) -> dict[str, str]:
    """Independently reconstruct the frozen 7+1 H3 subgroup join."""

    schema4_config = yaml.safe_load(
        Path(str(config["schema4_config"])).read_text(encoding="utf-8")
    )
    manifest = Path(schema4_config["schema3"]["family_member_manifest"])
    manifest_sha256 = _sha256(manifest)
    if (
        manifest_sha256 != expected_manifest_sha256
        or manifest_sha256 != SCHEMA3_FAMILY_MEMBER_MANIFEST_SHA256
        or manifest_sha256 != str(config["schema3_family_member_manifest_sha256"])
    ):
        raise RuntimeError("Frozen H3 subgroup manifest differs from result lineage")
    mapping: dict[str, str] = {}
    support: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _read(manifest):
        if (
            row["source_dataset"] != "viral_vma_djr"
            or _flag(row.get("h3_analysis_included", "0")) != 1
            or row.get("head3_operational_label") != "unknown/other"
        ):
            continue
        if (
            row.get("head3_status") == "rare_formal_unknown_diagnostic"
            and row.get("head3_phylum_label") == "Produgelaviricota"
        ):
            subgroup = "Produgelaviricota"
        elif row.get("head3_status") == "literature_unclassified_unknown_diagnostic":
            subgroup = "literature-unclassified"
        else:
            raise RuntimeError(
                f"Unrecognized eligible frozen H3 unknown subgroup: {row['protein_id']}"
            )
        if row["protein_id"] in mapping:
            raise RuntimeError("Duplicate frozen H3 subgroup protein ID")
        mapping[row["protein_id"]] = subgroup
        support[subgroup].append(row)
    observed = {
        subgroup: (
            len(rows),
            len(
                {
                    row.get("source_cluster_key")
                    or f"{row['source_dataset']}::{row['source_cluster_id']}"
                    for row in rows
                }
            ),
            len({row["dependence_block_id"] for row in rows}),
        )
        for subgroup, rows in support.items()
    }
    if observed != {
        "Produgelaviricota": (7, 2, 2),
        "literature-unclassified": (1, 1, 1),
    } or len(mapping) != 8:
        raise RuntimeError(f"Frozen H3 subgroup support changed: {observed}")
    return mapping


def _raw_reject_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    representative_by_parent: dict[tuple[str, str], int] = {}
    member_k = 0
    for row in rows:
        member_k += int(row["member_predicted_label"] == "unknown/other")
        parent = (row["dependence_block_id"], row["source_cluster_key"])
        value = int(row["representative_predicted_label"] == "unknown/other")
        if parent in representative_by_parent and representative_by_parent[parent] != value:
            raise RuntimeError("H3 representative reject call changed inside a parent")
        representative_by_parent[parent] = value
    return {
        "raw_member_reject_k": member_k,
        "raw_member_reject_n": len(rows),
        "raw_representative_reject_k": sum(representative_by_parent.values()),
        "raw_representative_reject_n": len(representative_by_parent),
    }


def validate(config_path: Path, output_path: Path | None = None) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if (
        config.get("schema_version") != 5
        or config.get("analysis_id") != ANALYSIS_ID
        or tuple(config.get("models", ())) != MODELS
        or config.get("selection_feedback_permitted") is not False
        or config.get("released_v0_feedback_permitted") is not False
        or config.get("train_cv_candidate_nomination_permitted") is not True
        or config.get("schema5_robustness_reranking_permitted") is not False
        or config.get("model_state") != "frozen"
        or config.get("test_policy") != "no_test_vector_selection_or_performance_scoring"
        or int(config.get("bootstrap_replicates", 0)) != 10_000
        or int(config.get("bootstrap_seed", 0)) != 20260728
        or config.get("multiple_comparison_family")
        != "eight_nontrivial_primary_mixed_candidates_vs_all_esmc_6b"
        or config.get("contextual_reference_model_id") != CONTEXTUAL_REFERENCE
        or config.get("protocol_amendment") != PROTOCOL_AMENDMENT
        or config.get("schema4_prediction_cache_policy")
        != SCHEMA4_CANONICAL_CACHE_POLICY
        or int(config.get("schema4_expected_prediction_rows", 0)) != 92_844
        or config.get("schema4_recomputation_tolerances")
        != {
            "probability": {"absolute": 5e-7, "relative": 1e-6},
            "raw_decision_score": {"absolute": 1e-5, "relative": 1e-6},
            "threshold": {"absolute": 0.0, "relative": 0.0},
        }
    ):
        raise RuntimeError("Schema-5 validation boundary mismatch")
    expected_h3_config = {
        "derivation": "frozen_family_manifest_join_to_existing_per_record_predictions",
        "model_inference_repeated_for_subgroups": False,
        "refit_recalibration_or_threshold_change_permitted": False,
        "prediction_threshold_cv_nomination_equivalence_to_amendment_c_required": True,
        "subgroup_fields": ["head3_status", "head3_phylum_label"],
        "raw_reject_counts_required": True,
        "endpoints": {
            endpoint: {
                field: contract[field]
                for field in (
                    "endpoint_role",
                    "expected_records",
                    "expected_parents",
                    "expected_dependence_blocks",
                    "bootstrap_seed_offset",
                    "interpretation",
                )
            }
            for endpoint, contract in H3_RARE_ENDPOINT_CONTRACT.items()
        },
    }
    if config.get("h3_rare_endpoint_contract") != expected_h3_config:
        raise RuntimeError("Amendment-D H3 rare-endpoint validation boundary changed")
    if (
        tuple(config.get("amendment_d_required_byte_equivalent_artifacts", ()))
        != AMENDMENT_D_BYTE_EQUIVALENT_ARTIFACTS
        or not str(config.get("amendment_c_result_dir", "")).endswith(
            "/schema5_v1/results"
        )
        or not str(config.get("amendment_c_validation", "")).endswith(
            "/schema5_v1/validation.json"
        )
        or config.get("amendment_c_result_checksums_sha256")
        != AMENDMENT_C_RESULT_CHECKSUMS_SHA256
        or config.get("amendment_c_validation_sha256")
        != AMENDMENT_C_VALIDATION_SHA256
        or config.get("schema3_family_member_manifest_sha256")
        != SCHEMA3_FAMILY_MEMBER_MANIFEST_SHA256
    ):
        raise RuntimeError("Amendment-C byte-equivalence validation boundary changed")
    expected_operator = {
        "operator_id": LEGACY_OPERATOR_ID,
        "canonical_schema4_job": 4968695,
        "pbs_ncpus": 4,
        "pbs_memory_gb": 32,
        "omp_num_threads": 4,
        "mkl_num_threads": 4,
        "openblas_num_threads": 4,
        "pythonhashseed": 20260724,
        "python_module": "Python/3.11.7",
        "python_version": "3.11.7",
        "venv_root": "/aptmp/hongda/DJRMCP_Develope/project-V0__data-curation-V3__final-minimization__20260724/05_archived_paths/.venv-v0",
        "runtime_preload_modules": ["scipy.linalg", "sklearn.linear_model"],
        "required_threadpool_count": 3,
        "required_threadpool_user_api_counts": {"blas": 2, "openmp": 1},
        "exact_numeric_string_replay_required": True,
        "amendment_b_tolerances_retained_as_upper_bound": True,
        "diagnostic_jobs": LEGACY_OPERATOR_DIAGNOSTIC_JOBS,
    }
    if config.get("legacy_schema4_numerical_operator") != expected_operator:
        raise RuntimeError("Legacy schema-4 numerical-operator validation boundary changed")
    for shard, spec in config["inputs"].items():
        if (
            _sha256(Path(spec["manifest"])) != spec["manifest_sha256"]
            or _sha256(Path(spec["fasta"])) != spec["fasta_sha256"]
            or len(_read(Path(spec["manifest"]))) != int(spec["expected_records"])
        ):
            raise RuntimeError(f"Frozen schema-5 input identity mismatch: {shard}")
    if (
        _sha256(Path(config["schema4_result_checksums"]))
        != config["schema4_result_checksums_sha256"]
        or _sha256(Path(config["schema4_validation"]))
        != config["schema4_validation_sha256"]
    ):
        raise RuntimeError("Schema-4 continuity lineage mismatch")
    schema4_prediction_sha256 = _verify_schema4_prediction_binding(config)
    result_dir = Path(config["result_dir"])
    verified = _verify_result(result_dir)
    summary = json.loads((result_dir / "summary.json").read_text(encoding="utf-8"))
    if (
        summary.get("schema_version") != 5
        or summary.get("analysis_id") != ANALYSIS_ID
        or summary.get("status") != "complete_eight_model_nine_candidate_four_source"
        or summary.get("test_vectors_selected_for_inference") != 0
        or summary.get("test_predictions_or_metrics_computed") != 0
        or summary.get("released_v0_artifacts_modified") != 0
        or summary.get("schema5_robustness_reranking_permitted") is not False
        or summary.get("lineage_sha256", {}).get("config") != _sha256(config_path)
        or summary.get("lineage_sha256", {}).get("schema4_predictions")
        != schema4_prediction_sha256
        or summary.get("lineage_sha256", {}).get("schema3_family_manifest")
        != SCHEMA3_FAMILY_MEMBER_MANIFEST_SHA256
    ):
        raise RuntimeError("Schema-5 summary boundary or lineage mismatch")
    expected_h3_summary_contract = {
        "derivation": "frozen_family_manifest_join_to_existing_per_record_predictions",
        "model_inference_repeated_for_subgroups": False,
        "refit_recalibration_or_threshold_change_permitted": False,
        "prediction_threshold_cv_nomination_equivalence_to_amendment_c_required": True,
        "subgroup_support": {
            "Produgelaviricota": {"records": 7, "parents": 2, "dependence_blocks": 2},
            "literature-unclassified": {
                "records": 1,
                "parents": 1,
                "dependence_blocks": 1,
                "interpretation": "single_record_descriptive_only_no_generalization",
            },
        },
        "pooled_endpoint_role": "secondary_pooled_diagnostic",
        "raw_reject_counts_reported": True,
    }
    if summary.get("h3_rare_endpoint_contract") != expected_h3_summary_contract:
        raise RuntimeError("Amendment-D H3 endpoint summary contract changed")
    amendment_c_result_dir = Path(config["amendment_c_result_dir"])
    amendment_c_validation = Path(config["amendment_c_validation"])
    if (
        _sha256(amendment_c_result_dir / "CHECKSUMS.sha256")
        != AMENDMENT_C_RESULT_CHECKSUMS_SHA256
        or _sha256(amendment_c_validation) != AMENDMENT_C_VALIDATION_SHA256
    ):
        raise RuntimeError("Retained Amendment-C generation identity changed")
    amendment_c_verified = _verify_result(amendment_c_result_dir)
    expected_equivalence = {
        name: amendment_c_verified[name]
        for name in AMENDMENT_D_BYTE_EQUIVALENT_ARTIFACTS
    }
    for name, expected_sha256 in expected_equivalence.items():
        if verified.get(name) != expected_sha256:
            raise RuntimeError(
                f"Amendment-D changed a prediction/threshold/CV/order artifact: {name}"
            )
    if summary.get("amendment_c_byte_equivalence") != {
        "status": "PASS",
        "source_result_dir": str(amendment_c_result_dir),
        "source_checksums_sha256": _sha256(
            amendment_c_result_dir / "CHECKSUMS.sha256"
        ),
        "source_validation_sha256": _sha256(amendment_c_validation),
        "artifacts": expected_equivalence,
        "interpretation": (
            "predictions_thresholds_cv_scores_and_candidate_order_byte_equivalent"
        ),
    }:
        raise RuntimeError("Amendment-C byte-equivalence summary changed")
    h3_rare_subgroups = _load_h3_rare_subgroups(
        config, str(summary["lineage_sha256"]["schema3_family_manifest"])
    )
    legacy_operator_validation = _validate_legacy_operator_runtime(
        config, config_path, result_dir, summary
    )

    single = _read(result_dir / "single_model_predictions.tsv")
    systems = _read(result_dir / "system_predictions.tsv")
    paths = _read(result_dir / "system_expected_path_predictions.tsv")
    registry = _read(result_dir / "system_registry.tsv")
    heads = _read(result_dir / "source_head_summary.tsv")
    path_summary = _read(result_dir / "source_path_summary.tsv")
    strict = _read(result_dir / "strict_cluster_summary.tsv")
    h3_summary = _read(result_dir / "h3_class_summary.tsv")
    path_bootstrap = _read(result_dir / "path_bootstrap_replicates.tsv")
    pairwise = _read(result_dir / "pairwise_source_path_delta.tsv")
    contextual = _read(result_dir / "contextual_source_path_delta.tsv")
    cv_rows = _read(result_dir / "train_cv_candidate_summary.tsv")
    pareto = _read(result_dir / "accuracy_cost_pareto.tsv")
    nomination = _read(result_dir / "candidate_nomination.tsv")
    materialization = _read(result_dir / "materialization_summary.tsv")
    model_costs = _read(result_dir / "model_cost_registry.tsv")
    schema4_audit = _read(result_dir / "schema4_recomputation_audit.tsv")
    schema4_audit_summary = _read(
        result_dir / "schema4_recomputation_audit_summary.tsv"
    )

    if any(_flag(row["test_record"]) for row in single + systems + paths):
        raise RuntimeError("Test record reached schema-5 outputs")
    if {row["model_id"] for row in single} != set(MODELS):
        raise RuntimeError("Eight homogeneous model predictions are incomplete")
    for row in single:
        if row["head"] not in APPLICABLE_HEADS[row["source_dataset"]]:
            raise RuntimeError("N/A source/head emitted as a prediction")
    if any(
        row["source_dataset"] in {"background_non_djr", "hard_non_djr"}
        and row["head"] != "head1"
        for row in systems
    ):
        raise RuntimeError("Background/HardNeg H2/H3 must be absent")
    _validate_recomposition(single, systems, registry, config["primary_mixed_candidates"])
    _validate_paths(systems, paths)

    system_ids = {row["system_id"] for row in registry}
    expected_head_keys = {
        (system, source, head)
        for system in system_ids
        for source in SOURCES
        for head in APPLICABLE_HEADS[source]
    }
    observed_head_keys = {
        (row["system_id"], row["source_dataset"], row["head"]) for row in heads
    }
    expected_path_keys = {(system, source) for system in system_ids for source in SOURCES}
    observed_path_keys = {(row["system_id"], row["source_dataset"]) for row in path_summary}
    expected_strict_keys = expected_head_keys | {
        (system, source, PATH_ID) for system, source in expected_path_keys
    }
    observed_strict_keys = {
        (row["system_id"], row["source_dataset"], row["endpoint_id"]) for row in strict
    }
    if (
        observed_head_keys != expected_head_keys
        or len(heads) != len(expected_head_keys)
        or observed_path_keys != expected_path_keys
        or len(path_summary) != len(expected_path_keys)
        or observed_strict_keys != expected_strict_keys
        or len(strict) != len(expected_strict_keys)
    ):
        raise RuntimeError("Source/head/path/strict endpoint matrices are incomplete or duplicated")

    replicates = int(config["bootstrap_replicates"])
    base_seed = int(config["bootstrap_seed"])
    strict_index = {
        (row["system_id"], row["source_dataset"], row["endpoint_id"]): row
        for row in strict
    }
    path_boot: dict[tuple[str, str], np.ndarray] = {}
    recomputed_endpoints = 0
    for observed in heads:
        selected = [
            row
            for row in systems
            if row["system_id"] == observed["system_id"]
            and row["source_dataset"] == observed["source_dataset"]
            and row["head"] == observed["head"]
            and _flag(row["metric_eligible"]) == 1
        ]
        values, _boot = _nested(
            selected,
            replicates,
            base_seed + HEAD_SEED_OFFSET[(observed["source_dataset"], observed["head"])],
        )
        _compare_summary(observed, values)
        strict_row = strict_index[(observed["system_id"], observed["source_dataset"], observed["head"])]
        if (
            int(strict_row["n_clusters"]) != values["n_source_clusters"]
            or int(strict_row["clusters_all_members_correct"])
            != values["clusters_all_members_correct"]
            or not _close(
                strict_row["proportion_clusters_all_members_correct"],
                values["proportion_clusters_all_members_correct"],
            )
        ):
            raise RuntimeError("Strict head-cluster endpoint mismatch")
        recomputed_endpoints += 1
    for observed in path_summary:
        selected = [
            row
            for row in paths
            if row["system_id"] == observed["system_id"]
            and row["source_dataset"] == observed["source_dataset"]
        ]
        local_seed = base_seed + PATH_SEED_OFFSET[observed["source_dataset"]]
        values, boot = _nested(selected, replicates, local_seed)
        _compare_summary(observed, values)
        path_boot[(observed["system_id"], observed["source_dataset"])] = boot[1]
        stored = sorted(
            [
                row
                for row in path_bootstrap
                if row["system_id"] == observed["system_id"]
                and row["source_dataset"] == observed["source_dataset"]
            ],
            key=lambda row: int(row["bootstrap_index"]),
        )
        if len(stored) != replicates:
            raise RuntimeError("Stored path bootstrap is incomplete")
        for index, row in enumerate(stored):
            if not (
                _close(row["representative_value"], boot[0][index])
                and _close(row["member_value"], boot[1][index])
                and _close(row["delta_member_minus_representative"], boot[2][index])
            ):
                raise RuntimeError("Stored path bootstrap differs from independent recomputation")
        strict_row = strict_index[(observed["system_id"], observed["source_dataset"], PATH_ID)]
        if (
            int(strict_row["n_clusters"]) != values["n_source_clusters"]
            or int(strict_row["clusters_all_members_correct"])
            != values["clusters_all_members_correct"]
            or not _close(
                strict_row["proportion_clusters_all_members_correct"],
                values["proportion_clusters_all_members_correct"],
            )
        ):
            raise RuntimeError("Strict path-cluster endpoint mismatch")
        recomputed_endpoints += 1

    expected_h3_endpoints = {
        "Nucleocytoviricota_f1",
        "Preplasmiviricota_f1",
        "known_two_phylum_macro_f1",
        "Produgelaviricota_reject_recall",
        "literature_unclassified_reject_recall",
        "rare_or_unclassified_reject_recall",
    }
    if len(h3_summary) != 17 * len(expected_h3_endpoints):
        raise RuntimeError("H3 separated endpoint table has the wrong size")
    h3_index = {(row["system_id"], row["endpoint_id"]): row for row in h3_summary}
    for system_id in {row["system_id"] for row in registry}:
        observed_endpoints = {endpoint for (system, endpoint) in h3_index if system == system_id}
        if observed_endpoints != expected_h3_endpoints:
            raise RuntimeError("H3 separated endpoint set is incomplete")
        h3_rows = [
            row
            for row in systems
            if row["system_id"] == system_id
            and row["source_dataset"] == "viral_vma_djr"
            and row["head"] == "head3_phylum"
            and _flag(row["metric_eligible"]) == 1
        ]
        known = [
            row
            for row in h3_rows
            if row["truth_label"] in {"Nucleocytoviricota", "Preplasmiviricota"}
        ]
        labels = ("Nucleocytoviricota", "Preplasmiviricota")
        for class_index, label in enumerate(labels):
            expected = _f1_metric(
                known, label, replicates, base_seed + 6_000 + class_index
            )
            row = h3_index[(system_id, f"{label}_f1")]
            _compare_h3_metric(row, expected)
            if (
                row["endpoint_role"] != "primary_known_class"
                or any(
                    row[field] != ""
                    for field in (
                        "raw_member_reject_k",
                        "raw_member_reject_n",
                        "raw_representative_reject_k",
                        "raw_representative_reject_n",
                    )
                )
            ):
                raise RuntimeError("Known-class H3 endpoint/display role changed")
        macro = h3_index[(system_id, "known_two_phylum_macro_f1")]
        _compare_h3_metric(
            macro,
            _macro_f1_metric(known, labels, replicates, base_seed + 6_020),
        )
        if macro["endpoint_role"] != "primary_known_macro":
            raise RuntimeError("Known H3 macro endpoint role changed")
        unknown = [row for row in h3_rows if row["truth_label"] not in labels]
        if len(unknown) != 8 or len({row["source_cluster_key"] for row in unknown}) != 3:
            raise RuntimeError("Rare H3 family must remain 8 relations / 3 parents")
        if set(h3_rare_subgroups) != {row["protein_id"] for row in unknown}:
            raise RuntimeError("Frozen H3 subgroup join does not exactly cover unknown rows")
        subgroup_rows = {
            "Produgelaviricota_reject_recall": [
                row
                for row in unknown
                if h3_rare_subgroups[row["protein_id"]] == "Produgelaviricota"
            ],
            "literature_unclassified_reject_recall": [
                row
                for row in unknown
                if h3_rare_subgroups[row["protein_id"]] == "literature-unclassified"
            ],
            "rare_or_unclassified_reject_recall": unknown,
        }
        for endpoint_id, selected in subgroup_rows.items():
            contract = H3_RARE_ENDPOINT_CONTRACT[endpoint_id]
            if (
                len(selected) != contract["expected_records"]
                or len({row["source_cluster_key"] for row in selected})
                != contract["expected_parents"]
                or len({row["dependence_block_id"] for row in selected})
                != contract["expected_dependence_blocks"]
            ):
                raise RuntimeError(f"Rare H3 subgroup support changed: {endpoint_id}")
            values, _boot = _nested(
                selected,
                replicates,
                base_seed + int(contract["bootstrap_seed_offset"]),
            )
            observed = h3_index[(system_id, endpoint_id)]
            single_block = int(contract["expected_dependence_blocks"]) == 1
            ci_fields = (
                "representative_ci_low",
                "representative_ci_high",
                "member_ci_low",
                "member_ci_high",
                "delta_ci_low",
                "delta_ci_high",
            )
            expected_values = dict(values)
            if single_block:
                expected_values.update({field: "" for field in ci_fields})
            _compare_summary(observed, expected_values)
            if single_block:
                if (
                    any(observed[field] != "" for field in ci_fields)
                    or int(observed["bootstrap_replicates"]) != 0
                    or observed["bootstrap_status"]
                    != "point_only_ci_not_estimable_single_block"
                ):
                    raise RuntimeError("Single-record H3 subgroup must be point-only")
            else:
                if (
                    any(not _close(observed[field], values[field]) for field in ci_fields)
                    or int(observed["bootstrap_replicates"]) != replicates
                    or observed["bootstrap_status"]
                    != "complete_fixed_seed_nested_block_bootstrap"
                ):
                    raise RuntimeError("Rare H3 subgroup bootstrap mismatch")
            if (
                observed["diagnostic_group"] != contract["diagnostic_group"]
                or observed["truth_label"] != contract["truth_label"]
                or observed["metric"] != "reject_recall"
                or observed["endpoint_role"] != contract["endpoint_role"]
                or observed["interpretation"] != contract["interpretation"]
                or int(observed["n_truth_records"]) != len(selected)
                or int(observed["n_evaluation_records"]) != len(selected)
                or int(observed["bootstrap_seed"])
                != base_seed + int(contract["bootstrap_seed_offset"])
                or observed["bootstrap_unit"] != "dependence_block"
                or observed["weighting"] != WEIGHTING
            ):
                raise RuntimeError(f"Rare H3 endpoint semantics changed: {endpoint_id}")
            raw = _raw_reject_counts(selected)
            if any(int(observed[field]) != value for field, value in raw.items()):
                raise RuntimeError(f"Rare H3 raw reject count mismatch: {endpoint_id}")
        recomputed_endpoints += len(expected_h3_endpoints)

    h3_subgroup_rows = [
        row
        for row in h3_summary
        if row["endpoint_id"]
        in {
            "Produgelaviricota_reject_recall",
            "literature_unclassified_reject_recall",
        }
    ]
    if (
        len(h3_summary) != 102
        or len(h3_subgroup_rows) != 34
        or summary.get("record_counts", {}).get("h3_endpoint_rows") != 102
        or summary.get("record_counts", {}).get("h3_subgroup_endpoint_rows") != 34
    ):
        raise RuntimeError("Amendment-D H3 endpoint record counts changed")

    if len(pairwise) != 36:
        raise RuntimeError("Primary pairwise table must be 9 candidates x 4 sources")
    candidate_ids = {row["candidate_id"] for row in config["primary_mixed_candidates"]}
    expected_pairwise_keys = {(candidate, source) for candidate in candidate_ids for source in SOURCES}
    observed_pairwise_keys = {(row["candidate_id"], row["source_dataset"]) for row in pairwise}
    if observed_pairwise_keys != expected_pairwise_keys or len(observed_pairwise_keys) != len(pairwise):
        raise RuntimeError("Primary pairwise key matrix is incomplete or duplicated")
    point = {
        (row["system_id"], row["source_dataset"]): float(row["member_value"])
        for row in path_summary
    }
    for source in SOURCES:
        source_rows = [row for row in pairwise if row["source_dataset"] == source]
        raw_p: dict[str, float] = {}
        expected_delta: dict[str, np.ndarray] = {}
        for row in source_rows:
            candidate = row["candidate_id"]
            delta = path_boot[(candidate, source)] - path_boot[(REFERENCE, source)]
            expected_delta[candidate] = delta
            positive = candidate == "h12_esmc_6b__h3_esmc_6b"
            p = 1.0 if positive else (1.0 + np.count_nonzero(delta >= 0)) / (len(delta) + 1.0)
            if not positive:
                raw_p[candidate] = float(p)
            if (
                row["reference_system_id"] != REFERENCE
                or _flag(row["positive_control"]) != int(positive)
                or row["holm_family"] != f"eight_nontrivial_candidates__{source}"
                or int(row["bootstrap_replicates"]) != replicates
                or int(row["bootstrap_seed"]) != base_seed + PATH_SEED_OFFSET[source]
                or not _close(
                    row["delta_candidate_minus_reference"],
                    point[(candidate, source)] - point[(REFERENCE, source)],
                )
                or not _close(row["delta_ci_low"], np.quantile(delta, 0.025))
                or not _close(row["delta_ci_high"], np.quantile(delta, 0.975))
                or not _close(row["one_sided_inferiority_p"], p)
            ):
                raise RuntimeError("Primary paired source delta mismatch")
        adjusted = _holm(raw_p)
        for row in source_rows:
            candidate = row["candidate_id"]
            expected = 1.0 if candidate == "h12_esmc_6b__h3_esmc_6b" else adjusted[candidate]
            expected_status = (
                "positive_control_exact_equivalence"
                if candidate == "h12_esmc_6b__h3_esmc_6b"
                else (
                    "source_specific_inferiority_warning"
                    if expected < 0.05 and float(row["delta_ci_high"]) < 0.0
                    else "no_established_source_specific_inferiority"
                )
            )
            if (
                not _close(row["holm_adjusted_p"], expected)
                or row["diagnostic_status"] != expected_status
            ):
                raise RuntimeError("Holm-adjusted source comparison mismatch")

    if len(contextual) != 27:
        raise RuntimeError("Contextual table must be 9 candidates x 3 nonviral sources")
    contextual_sources = {"cellular_djr_none", "background_non_djr", "hard_non_djr"}
    expected_contextual_keys = {
        (candidate, source) for candidate in candidate_ids for source in contextual_sources
    }
    observed_contextual_keys = {
        (row["candidate_id"], row["source_dataset"]) for row in contextual
    }
    if observed_contextual_keys != expected_contextual_keys or len(observed_contextual_keys) != len(contextual):
        raise RuntimeError("Contextual pairwise key matrix is incomplete or duplicated")
    for row in contextual:
        candidate, source = row["candidate_id"], row["source_dataset"]
        delta = path_boot[(candidate, source)] - path_boot[(CONTEXTUAL_REFERENCE, source)]
        if (
            row["contextual_reference_system_id"] != CONTEXTUAL_REFERENCE
            or int(row["bootstrap_replicates"]) != replicates
            or int(row["bootstrap_seed"]) != base_seed + PATH_SEED_OFFSET[source]
            or not _close(
                row["delta_candidate_minus_reference"],
                point[(candidate, source)] - point[(CONTEXTUAL_REFERENCE, source)],
            )
            or not _close(row["delta_ci_low"], np.quantile(delta, 0.025))
            or not _close(row["delta_ci_high"], np.quantile(delta, 0.975))
            or row["comparison_role"]
            != "descriptive_context_only_not_reranking_not_holm_family"
        ):
            raise RuntimeError("Contextual 650M delta mismatch")

    # Independently reconstruct the nine Train-only fold scores.  Robustness
    # values are deliberately absent from this calculation.
    fold_rows = _read(Path(config["comparison_summary"]).with_name("fold_scores.tsv"))
    fold = {(row["model_id"], row["head"], int(row["fold"])): float(row["score"]) for row in fold_rows}
    weights = config["score_weights"]
    cv_index = {row["candidate_id"]: row for row in cv_rows}
    candidate_values: dict[str, np.ndarray] = {}
    for candidate in config["primary_mixed_candidates"]:
        candidate_id = candidate["candidate_id"]
        h12, h3 = candidate["head1_model"], candidate["head3_model"]
        values = np.asarray(
            [
                weights["head1_ap"] * fold[(h12, "head1", index)]
                + weights["head2_ap"] * fold[(h12, "head2", index)]
                + weights["head3_known_macro_f1"] * fold[(h3, "head3_phylum", index)]
                for index in range(1, 6)
            ]
        )
        candidate_values[candidate_id] = values
        observed = cv_index[candidate_id]
        if not _close(observed["mean_train_cv_score"], values.mean()):
            raise RuntimeError("Train-only mixed-candidate CV score mismatch")
        for index in range(5):
            if not _close(observed[f"fold{index + 1}_score"], values[index]):
                raise RuntimeError("Train-only mixed-candidate fold score mismatch")
    best_id = min(candidate_values, key=lambda key: (-candidate_values[key].mean(), key))
    for candidate_id, values in candidate_values.items():
        delta = candidate_values[best_id] - values
        paired_se = float(delta.std(ddof=1) / math.sqrt(5))
        within = int(candidate_values[best_id].mean() - values.mean() <= paired_se + 1e-15)
        if (
            cv_index[candidate_id]["best_mean_candidate_id"] != best_id
            or _flag(cv_index[candidate_id]["within_one_paired_se"]) != within
            or not _close(cv_index[candidate_id]["paired_delta_se_vs_best"], paired_se)
        ):
            raise RuntimeError("Paired one-SE candidate set mismatch")
    if len(pareto) != 9 or len(nomination) != 1:
        raise RuntimeError("Candidate Pareto/nomination table size mismatch")
    cost_index = {row["model_id"]: row for row in model_costs}
    comparison = {
        row["model_id"]: row
        for row in _read(Path(config["comparison_summary"]).with_name("model_comparison.tsv"))
    }
    if set(cost_index) != set(MODELS):
        raise RuntimeError("Model cost registry key set mismatch")
    for model_id, observed in cost_index.items():
        source = comparison[model_id]
        if (
            not _close(observed["gpu_seconds_per_sequence"], source["gpu_seconds_per_sequence"])
            or int(observed["peak_gpu_memory_bytes"]) != int(source["peak_gpu_memory_bytes"])
            or observed["resolved_model_revision"] != source["resolved_model_revision"]
            or int(observed["representative_benchmark_h3_unknown_diagnostic_n"]) != 5
        ):
            raise RuntimeError("Frozen model deployment-cost evidence mismatch")
    pareto_index = {row["candidate_id"]: row for row in pareto}
    one_se = [row for row in cv_rows if _flag(row["within_one_paired_se"])]
    expected_frontier: list[dict[str, str]] = []
    for row in cv_rows:
        candidate = next(
            item for item in config["primary_mixed_candidates"] if item["candidate_id"] == row["candidate_id"]
        )
        h12, h3 = candidate["head1_model"], candidate["head3_model"]
        base_cost = float(cost_index[h12]["gpu_seconds_per_sequence"])
        conditional = 0.0 if h12 == h3 else float(cost_index[h3]["gpu_seconds_per_sequence"])
        peak = max(
            int(cost_index[h12]["peak_gpu_memory_bytes"]),
            int(cost_index[h3]["peak_gpu_memory_bytes"]),
        )
        if (
            not _close(row["always_on_gpu_seconds_per_sequence"], base_cost)
            or not _close(row["conditional_h3_gpu_seconds_per_sequence"], conditional)
            or not _close(row["worst_case_gpu_seconds_per_sequence"], base_cost + conditional)
            or int(row["peak_gpu_memory_bytes"]) != peak
        ):
            raise RuntimeError("Candidate deployment-cost composition mismatch")
        dominated = False
        if _flag(row["within_one_paired_se"]):
            for other in one_se:
                if other["candidate_id"] == row["candidate_id"]:
                    continue
                no_worse = (
                    float(other["mean_train_cv_score"]) >= float(row["mean_train_cv_score"])
                    and float(other["always_on_gpu_seconds_per_sequence"])
                    <= float(row["always_on_gpu_seconds_per_sequence"])
                    and float(other["worst_case_gpu_seconds_per_sequence"])
                    <= float(row["worst_case_gpu_seconds_per_sequence"])
                    and int(other["peak_gpu_memory_bytes"]) <= int(row["peak_gpu_memory_bytes"])
                )
                strict_better = (
                    float(other["mean_train_cv_score"]) > float(row["mean_train_cv_score"])
                    or float(other["always_on_gpu_seconds_per_sequence"])
                    < float(row["always_on_gpu_seconds_per_sequence"])
                    or float(other["worst_case_gpu_seconds_per_sequence"])
                    < float(row["worst_case_gpu_seconds_per_sequence"])
                    or int(other["peak_gpu_memory_bytes"]) < int(row["peak_gpu_memory_bytes"])
                )
                dominated |= no_worse and strict_better
        expected_pareto = int(_flag(row["within_one_paired_se"]) and not dominated)
        if (
            _flag(pareto_index[row["candidate_id"]]["one_se_cost_accuracy_pareto"])
            != expected_pareto
            or _flag(pareto_index[row["candidate_id"]]["robustness_used_for_pareto_or_ordering"])
        ):
            raise RuntimeError("Train-CV/cost Pareto reconstruction mismatch")
        if expected_pareto:
            expected_frontier.append(row)
    expected_nominee = min(
        expected_frontier,
        key=lambda row: (
            float(row["always_on_gpu_seconds_per_sequence"]),
            float(row["worst_case_gpu_seconds_per_sequence"]),
            int(row["peak_gpu_memory_bytes"]),
            row["candidate_id"],
        ),
    )["candidate_id"]
    nominee = nomination[0]
    if (
        nominee["candidate_id"] != expected_nominee
        or _flag(nominee["robustness_used_for_candidate_ordering"])
    ):
        raise RuntimeError("Nomination was not the independent Train-CV/cost result")
    warning_sources = sorted(
        row["source_dataset"]
        for row in pairwise
        if row["candidate_id"] == expected_nominee
        and row["diagnostic_status"] == "source_specific_inferiority_warning"
    )
    expected_status = (
        "recommended_for_external_confirmation_with_source_warning"
        if warning_sources
        else "recommended_for_external_confirmation"
    )
    if (
        nominee["nomination_status"] != expected_status
        or int(nominee["source_specific_warning_count"]) != len(warning_sources)
        or nominee["source_specific_warnings"] != ";".join(warning_sources)
    ):
        raise RuntimeError("Nominee source-warning annotation mismatch")
    if _flag(nominee["released_v0_change_permitted"]) or not _flag(
        nominee["prospective_external_confirmation_required"]
    ):
        raise RuntimeError("Nominee was misrepresented as a V0 replacement")

    if len(materialization) != 24:
        raise RuntimeError("Normalized embedding attestation summary must contain 24 rows")
    keys = {(row["model_id"], row["shard_id"]) for row in materialization}
    if keys != {(model, shard) for model in MODELS for shard in config["inputs"]}:
        raise RuntimeError("Normalized embedding attestation key set mismatch")
    if (
        sum(row["attestation_kind"] == "materialization" for row in materialization) != 18
        or sum(row["attestation_kind"] == "reuse" for row in materialization) != 6
        or any(int(row["test_records_embedded"]) for row in materialization)
    ):
        raise RuntimeError("Materialization/reuse/Test attestation counts mismatch")
    for row in materialization:
        directory = Path(row["embedding_output"])
        evidence = Path(row["receipt_or_attestation"])
        attestation = json.loads(evidence.read_text(encoding="utf-8")) if evidence.is_file() else {}
        source_evidence = Path(str(attestation.get("source_receipt_or_attestation", "")))
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        expected_records = int(config["inputs"][row["shard_id"]]["expected_records"])
        if (
            _sha256(directory / "CHECKSUMS.sha256") != row["embedding_checksums_sha256"]
            or not evidence.is_file()
            or _sha256(evidence) != row["receipt_or_attestation_sha256"]
            or row["manifest_sha256"] != config["inputs"][row["shard_id"]]["manifest_sha256"]
            or row["fasta_sha256"] != config["inputs"][row["shard_id"]]["fasta_sha256"]
            or attestation.get("model_id") != row["model_id"]
            or attestation.get("shard_id") != row["shard_id"]
            or attestation.get("attestation_kind") != row["attestation_kind"]
            or int(attestation.get("embedded_records", -1)) != expected_records
            or int(attestation.get("test_records_embedded", -1)) != 0
            or int(attestation.get("prediction_or_metric_records_created", -1)) != 0
            or attestation.get("embedding_output") != str(directory)
            or attestation.get("embedding_checksums_sha256")
            != row["embedding_checksums_sha256"]
            or not source_evidence.is_file()
            or _sha256(source_evidence)
            != attestation.get("source_receipt_or_attestation_sha256")
            or metadata.get("status") != "complete"
            or int(metadata.get("completed_records", -1)) != expected_records
            or metadata.get("manifest_sha256") != row["manifest_sha256"]
            or metadata.get("fasta_sha256") != row["fasta_sha256"]
            or metadata.get("resolved_model_revision")
            != attestation.get("resolved_model_revision")
        ):
            raise RuntimeError("Embedding attestation checksum changed")
        if row["attestation_kind"] == "materialization" and (
            attestation.get("config_sha256")
            != config["embedding_materialization_config_sha256"]
            or attestation.get("protocol_sha256")
            != config["embedding_materialization_protocol_sha256"]
            or float(attestation.get("gpu_seconds", -1)) <= 0
            or float(attestation.get("wall_seconds", -1)) <= 0
            or int(attestation.get("peak_gpu_memory_bytes", -1)) <= 0
            or not _close(row["gpu_seconds"], attestation.get("gpu_seconds", -1))
            or not _close(row["wall_seconds"], attestation.get("wall_seconds", -1))
            or int(row["peak_gpu_memory_bytes"])
            != int(attestation.get("peak_gpu_memory_bytes", -1))
        ):
            raise RuntimeError("Materialization resource/snapshot attestation mismatch")
    if len(model_costs) != 8:
        raise RuntimeError("Representative benchmark H3 diagnostic registry is incomplete")

    schema4_cache_validation = _validate_schema4_canonical_cache(
        config, summary, single, schema4_audit, schema4_audit_summary
    )
    if (
        summary.get("record_counts", {}).get("schema4_recomputation_audit_rows")
        != schema4_cache_validation["row_level_audit_rows"]
        or summary.get("record_counts", {}).get(
            "schema4_recomputation_audit_summary_rows"
        )
        != schema4_cache_validation["aggregate_audit_rows"]
    ):
        raise RuntimeError("Schema-4 audit record counts differ from the result summary")

    payload: dict[str, Any] = {
        "schema_version": 5,
        "analysis_id": ANALYSIS_ID,
        "status": "PASS",
        "validated_result_status": summary["status"],
        "gates": {
            "checksum_exact_bundle": "PASS",
            "eight_models_three_embedding_shards": "PASS",
            "eighteen_materialization_plus_six_reuse_attestations": "PASS",
            "applicable_heads_only_na_absent": "PASS",
            "mixed_heads_recomposed_from_real_per_record_predictions": "PASS",
            "all_6b_positive_control_exact": "PASS",
            "expected_paths_independently_rederived": "PASS",
            "fixed_seed_nested_bootstrap_independently_recomputed": "PASS",
            "strict_cluster_endpoints_recomputed": "PASS",
            "source_specific_holm_diagnostics_recomputed": "PASS",
            "contextual_650m_deltas_descriptive_only": "PASS",
            "train_only_cv_one_se_nomination_recomputed": "PASS",
            "schema5_robustness_not_used_for_reranking": "PASS",
            "schema4_two_model_per_record_continuity": "PASS",
            "schema4_canonical_cache_full_recomputation_audit": "PASS",
            "schema4_legacy_operator_runtime_and_exact_numeric_replay": "PASS",
            "amendment_c_predictions_threshold_cv_order_byte_equivalent": "PASS",
            "h3_rare_subgroups_independently_recomputed": "PASS",
            "test_record_count_zero": "PASS",
            "released_v0_unchanged_external_confirmation_required": "PASS",
        },
        "counts": {
            "verified_artifacts": len(verified),
            "single_model_predictions": len(single),
            "system_predictions": len(systems),
            "path_predictions": len(paths),
            "recomputed_endpoints": recomputed_endpoints,
            "path_bootstrap_rows": len(path_bootstrap),
            "h3_endpoint_rows": len(h3_summary),
            "h3_subgroup_endpoint_rows": len(h3_subgroup_rows),
            "amendment_c_byte_equivalent_artifacts": len(expected_equivalence),
            "primary_pairwise_rows": len(pairwise),
            "contextual_pairwise_rows": len(contextual),
            "embedding_attestations": len(materialization),
            "schema4_recomputation_audit_rows": schema4_cache_validation[
                "row_level_audit_rows"
            ],
            "schema4_recomputation_audit_summary_rows": schema4_cache_validation[
                "aggregate_audit_rows"
            ],
            "schema4_exact_numeric_string_comparisons": schema4_cache_validation[
                "exact_numeric_string_comparisons"
            ],
            "schema4_numeric_string_mismatches": schema4_cache_validation[
                "numeric_string_mismatches"
            ],
            "test_records": 0,
        },
        "schema4_canonical_prediction_cache": schema4_cache_validation,
        "legacy_numerical_operator_runtime": legacy_operator_validation,
        "input_sha256": {
            "config": _sha256(config_path),
            "result_checksums": _sha256(result_dir / "CHECKSUMS.sha256"),
            "schema4_result_checksums": _sha256(Path(config["schema4_result_checksums"])),
            "schema4_validation": _sha256(Path(config["schema4_validation"])),
            "schema4_predictions": schema4_prediction_sha256,
            "legacy_numerical_operator_runtime": legacy_operator_validation[
                "runtime_sha256"
            ],
            "amendment_c_result_checksums": _sha256(
                amendment_c_result_dir / "CHECKSUMS.sha256"
            ),
            "amendment_c_validation": _sha256(amendment_c_validation),
            "schema3_family_manifest": SCHEMA3_FAMILY_MEMBER_MANIFEST_SHA256,
        },
    }
    destination = output_path or result_dir.with_name("validation.json")
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite validation: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.tmp-{os.getpid()}")
    if temporary.exists():
        raise FileExistsError(f"Validation staging path already exists: {temporary}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/validation_family_robustness_v0_schema5_mixed_heads.yaml"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.config, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
