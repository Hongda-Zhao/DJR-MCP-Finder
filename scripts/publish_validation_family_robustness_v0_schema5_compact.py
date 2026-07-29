#!/usr/bin/env python3
"""Publish checksum-bound schema-5 result and figure compact cores.

The command is read-only unless ``--publish`` is supplied.  Publication is
allowed only after the complete scorer bundle, independent validation, and
complete publication-figure bundle all pass their own manifests and mutual
lineage checks.  The two active destinations come only from the frozen
schema-5 config; source-directory overrides never change publication targets.

The compact result deliberately excludes per-record predictions, the 10,000
bootstrap replicate table, and the 92,844-row canonical-cache audit.  Their
checksums remain bound through the copied validation, QA, and compact source
receipt.  No source artifact is moved, modified, or deleted.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence

import yaml


PROJECT_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_DIR / "src"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from djrmcp_finder.archive import ArchiveError, _atomic_rename_noreplace  # noqa: E402


SCHEMA_VERSION = 5
ANALYSIS_ID = "project_v0_validation_family_robustness_schema5_mixed_heads"
RESULT_STATUS = "complete_eight_model_nine_candidate_four_source"
PROTOCOL_AMENDMENT = "D_h3_rare_subgroup_transparency_no_model_change"
FIGURE_BASENAME = "validation_family_robustness_v0_schema5_mixed_heads"
COMPACT_METADATA_NAME = "COMPACT.json"
AMENDMENT_C_RESULT_CHECKSUMS_SHA256 = (
    "aa9f3cef647487d4eaec7749ceeb49c58085657a38d0d99c7577f3655448e72c"
)
AMENDMENT_C_VALIDATION_SHA256 = (
    "2b63cecae7788cce3d4c8ef96d48bf1becfbe8d74b9e9c084b2ab69a47542bcb"
)
SCHEMA3_FAMILY_MEMBER_MANIFEST_SHA256 = (
    "8cd9e9ce45ad965eb745cc4ecdf08d7e3205f57b830bca00bcf0041e5bcdf541"
)

H3_PRIMARY_ENDPOINTS = frozenset(
    {
        "Nucleocytoviricota_f1",
        "Preplasmiviricota_f1",
        "Produgelaviricota_reject_recall",
        "literature_unclassified_reject_recall",
    }
)
H3_SUPPORT_ENDPOINTS = frozenset(
    {
        "known_two_phylum_macro_f1",
        "rare_or_unclassified_reject_recall",
    }
)
H3_RESULT_ENDPOINTS = H3_PRIMARY_ENDPOINTS | H3_SUPPORT_ENDPOINTS
AMENDMENT_C_BYTE_EQUIVALENT_ARTIFACTS = (
    "single_model_predictions.tsv",
    "system_predictions.tsv",
    "system_expected_path_predictions.tsv",
    "system_registry.tsv",
    "train_cv_candidate_summary.tsv",
    "accuracy_cost_pareto.tsv",
    "candidate_nomination.tsv",
)

# This is an explicit partition.  Any new scorer artifact that is in neither
# set aborts publication until its active/archive role has been reviewed.
COMPACT_RESULT_SOURCE_FILES = frozenset(
    {
        "summary.json",
        "system_registry.tsv",
        "source_head_summary.tsv",
        "source_path_summary.tsv",
        "strict_cluster_summary.tsv",
        "h3_class_summary.tsv",
        "pairwise_source_path_delta.tsv",
        "contextual_source_path_delta.tsv",
        "train_cv_candidate_summary.tsv",
        "accuracy_cost_pareto.tsv",
        "candidate_nomination.tsv",
        "model_cost_registry.tsv",
        "materialization_summary.tsv",
        "schema4_recomputation_audit_summary.tsv",
        "legacy_numerical_operator_runtime.json",
    }
)
EXCLUDED_HIGH_VOLUME_RESULT_FILES = frozenset(
    {
        "single_model_predictions.tsv",
        "system_predictions.tsv",
        "system_expected_path_predictions.tsv",
        "path_bootstrap_replicates.tsv",
        "schema4_recomputation_audit.tsv",
    }
)
EXPECTED_FULL_RESULT_FILES = (
    COMPACT_RESULT_SOURCE_FILES | EXCLUDED_HIGH_VOLUME_RESULT_FILES
)

FIGURE_EXPORTS = (
    f"{FIGURE_BASENAME}.svg",
    f"{FIGURE_BASENAME}.pdf",
    f"{FIGURE_BASENAME}.png",
    f"{FIGURE_BASENAME}.tiff",
)
FIGURE_SOURCE_DATA_FILES = frozenset(
    {
        "source_data/panel_a_evidence.tsv",
        "source_data/panel_b_homogeneous.tsv",
        "source_data/panel_c_mixed_candidates.tsv",
        "source_data/panel_d_accuracy_cost_pareto.tsv",
        "source_data/panel_d_h3_boundary.tsv",
    }
)
COMPACT_FIGURE_SOURCE_FILES = frozenset(
    {
        FIGURE_EXPORTS[0],
        FIGURE_EXPORTS[1],
        FIGURE_EXPORTS[2],
        "QA.json",
        "figure_manifest.tsv",
    }
    | FIGURE_SOURCE_DATA_FILES
)

REQUIRED_VALIDATION_GATES = frozenset(
    {
        "checksum_exact_bundle",
        "eight_models_three_embedding_shards",
        "eighteen_materialization_plus_six_reuse_attestations",
        "applicable_heads_only_na_absent",
        "mixed_heads_recomposed_from_real_per_record_predictions",
        "all_6b_positive_control_exact",
        "expected_paths_independently_rederived",
        "fixed_seed_nested_bootstrap_independently_recomputed",
        "strict_cluster_endpoints_recomputed",
        "source_specific_holm_diagnostics_recomputed",
        "contextual_650m_deltas_descriptive_only",
        "train_only_cv_one_se_nomination_recomputed",
        "schema5_robustness_not_used_for_reranking",
        "schema4_canonical_cache_full_recomputation_audit",
        "schema4_legacy_operator_runtime_and_exact_numeric_replay",
        "schema4_two_model_per_record_continuity",
        "h3_rare_subgroups_independently_recomputed",
        "amendment_c_predictions_threshold_cv_order_byte_equivalent",
        "test_record_count_zero",
        "released_v0_unchanged_external_confirmation_required",
    }
)


class CompactPublishError(ArchiveError):
    """Raised when compact publication cannot complete without ambiguity."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _require_real_file(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise CompactPublishError(f"Expected a real regular file: {path}")


def _require_real_directory(path: Path) -> None:
    if not path.is_dir() or path.is_symlink():
        raise CompactPublishError(f"Expected a real directory: {path}")


def _require_absent(path: Path) -> None:
    if os.path.lexists(path):
        raise CompactPublishError(f"Refusing to overwrite existing target: {path}")


def _safe_relative(
    raw: str, *, flat: bool = False, checksum_target: bool = False
) -> PurePosixPath:
    value = raw.strip()
    if checksum_target:
        value = value.lstrip("*")
    raw_parts = value.split("/")
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or any(character in value for character in "\x00\n\r\t")
        or any(part in {"", ".", ".."} for part in raw_parts)
        or (flat and len(path.parts) != 1)
    ):
        raise CompactPublishError(f"Unsafe relative artifact path: {raw!r}")
    return path


def _resolve_source(project_root: Path, value: Any) -> Path:
    path = Path(str(value))
    return _lexical_absolute(path if path.is_absolute() else project_root / path)


def _active_destination(project_root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str):
        raise CompactPublishError(f"{label} must be a relative string path")
    relative = _safe_relative(value)
    destination = _lexical_absolute(project_root.joinpath(*relative.parts))
    try:
        destination.relative_to(project_root)
    except ValueError as exc:
        raise CompactPublishError(f"{label} escaped the project root") from exc
    return destination


def _assert_no_existing_symlink_ancestor(project_root: Path, path: Path) -> None:
    try:
        relative = path.relative_to(project_root)
    except ValueError as exc:
        raise CompactPublishError(f"Active path escaped project root: {path}") from exc
    cursor = project_root
    if cursor.is_symlink():
        raise CompactPublishError(f"Project root may not be a symlink: {cursor}")
    for part in relative.parts:
        cursor = cursor / part
        if os.path.lexists(cursor) and cursor.is_symlink():
            raise CompactPublishError(f"Active path contains a symlink: {cursor}")


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _verify_bundle(directory: Path) -> dict[str, str]:
    """Verify a complete recursive bundle and reject untracked entries."""

    _require_real_directory(directory)
    manifest = directory / "CHECKSUMS.sha256"
    _require_real_file(manifest)
    verified: dict[str, str] = {}
    for line_number, raw in enumerate(
        manifest.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not raw.strip():
            continue
        parts = raw.split(maxsplit=1)
        if len(parts) != 2:
            raise CompactPublishError(
                f"Malformed checksum line {manifest}:{line_number}"
            )
        expected, raw_name = parts[0], parts[1]
        relative = _safe_relative(raw_name, checksum_target=True)
        name = relative.as_posix()
        if (
            len(expected) != 64
            or expected != expected.lower()
            or any(character not in "0123456789abcdef" for character in expected)
            or name == "CHECKSUMS.sha256"
            or name in verified
        ):
            raise CompactPublishError(
                f"Invalid or duplicate checksum entry {manifest}:{line_number}"
            )
        target = directory.joinpath(*relative.parts)
        cursor = directory
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise CompactPublishError(f"Checksum target contains a symlink: {cursor}")
        _require_real_file(target)
        observed = _sha256(target)
        if observed != expected:
            raise CompactPublishError(
                f"Checksum mismatch for {target}: expected {expected}, observed {observed}"
            )
        verified[name] = expected
    if not verified:
        raise CompactPublishError(f"Empty checksum manifest: {manifest}")

    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for entry in directory.rglob("*"):
        relative = entry.relative_to(directory).as_posix()
        if entry.is_symlink():
            raise CompactPublishError(f"Bundle contains a symlink: {entry}")
        if entry.is_dir():
            actual_directories.add(relative)
        elif entry.is_file():
            if relative != "CHECKSUMS.sha256":
                actual_files.add(relative)
        else:
            raise CompactPublishError(f"Bundle contains a non-regular entry: {entry}")
    expected_directories = {
        PurePosixPath(*PurePosixPath(name).parts[:index]).as_posix()
        for name in verified
        for index in range(1, len(PurePosixPath(name).parts))
    }
    if actual_files != set(verified) or actual_directories != expected_directories:
        raise CompactPublishError(
            f"Manifest inventory mismatch in {directory}: "
            f"untracked_files={sorted(actual_files - set(verified))}, "
            f"missing_files={sorted(set(verified) - actual_files)}, "
            f"untracked_directories={sorted(actual_directories - expected_directories)}"
        )
    return verified


def _read_json(path: Path) -> dict[str, Any]:
    _require_real_file(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompactPublishError(f"Could not parse JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CompactPublishError(f"JSON root is not an object: {path}")
    return payload


def _read_tsv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    _require_real_file(path)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise CompactPublishError(f"TSV has no header: {path}")
        fields = tuple(reader.fieldnames)
        rows = list(reader)
    if not rows:
        raise CompactPublishError(f"TSV has no records: {path}")
    return fields, rows


def _require_fields(payload: Mapping[str, Any], expected: Mapping[str, Any], label: str) -> None:
    for field, value in expected.items():
        if payload.get(field) != value:
            raise CompactPublishError(
                f"{label} mismatch for {field}: expected {value!r}, "
                f"observed {payload.get(field)!r}"
            )


def _validate_summary(
    summary: dict[str, Any],
    config: dict[str, Any],
    identities: Mapping[str, str],
) -> None:
    _require_fields(
        summary,
        {
            "schema_version": SCHEMA_VERSION,
            "analysis_id": ANALYSIS_ID,
            "status": RESULT_STATUS,
            "model_state": "frozen",
            "selection_feedback_permitted": False,
            "released_v0_feedback_permitted": False,
            "schema5_robustness_reranking_permitted": False,
            "training_operations": 0,
            "calibration_fit_operations": 0,
            "threshold_optimization_operations": 0,
            "test_vectors_selected_for_inference": 0,
            "test_predictions_or_metrics_computed": 0,
            "released_v0_artifacts_modified": 0,
            "nomination_primary_evidence": "train_only_shared_five_fold_cv",
            "robustness_role_in_nomination": "source_specific_warning_not_reranking",
        },
        "schema-5 summary",
    )
    lineage = summary.get("lineage_sha256")
    if not isinstance(lineage, dict):
        raise CompactPublishError("Schema-5 summary has no lineage map")
    expected_lineage = {
        "config": identities["config"],
        "protocol": identities["protocol"],
        "comparison_summary": identities["comparison_summary"],
        "schema3_family_manifest": config[
            "schema3_family_member_manifest_sha256"
        ],
        "schema4_result_checksums": config["schema4_result_checksums_sha256"],
        "schema4_validation": config["schema4_validation_sha256"],
    }
    _require_fields(lineage, expected_lineage, "schema-5 result lineage")
    expected_h3_contract = {
        "derivation": "frozen_family_manifest_join_to_existing_per_record_predictions",
        "model_inference_repeated_for_subgroups": False,
        "refit_recalibration_or_threshold_change_permitted": False,
        "prediction_threshold_cv_nomination_equivalence_to_amendment_c_required": True,
        "subgroup_support": {
            "Produgelaviricota": {
                "records": 7,
                "parents": 2,
                "dependence_blocks": 2,
            },
            "literature-unclassified": {
                "records": 1,
                "parents": 1,
                "dependence_blocks": 1,
                "interpretation": (
                    "single_record_descriptive_only_no_generalization"
                ),
            },
        },
        "pooled_endpoint_role": "secondary_pooled_diagnostic",
        "raw_reject_counts_reported": True,
    }
    if summary.get("h3_rare_endpoint_contract") != expected_h3_contract:
        raise CompactPublishError("Schema-5 Amendment-D H3 endpoint contract changed")
    counts = summary.get("record_counts", {})
    if (
        counts.get("test_records") != 0
        or counts.get("schema4_continuity_predictions") != 92_844
        or counts.get("schema4_recomputation_audit_rows") != 92_844
        or counts.get("schema4_recomputation_audit_summary_rows") != 10
        or counts.get("h3_endpoint_rows") != 102
        or counts.get("h3_subgroup_endpoint_rows") != 34
    ):
        raise CompactPublishError("Schema-5 Test/continuity record counts changed")
    audit = summary.get("schema4_canonical_prediction_cache", {})
    _require_fields(
        audit,
        {
            "status": "PASS",
            "prediction_keys": 92_844,
            "canonicalized_rows": 92_844,
            "row_level_audit_rows": 92_844,
            "semantic_mismatches": 0,
            "derived_decision_mismatches": 0,
            "exact_numeric_string_replay_required": True,
            "exact_numeric_string_comparisons": 464_220,
            "numeric_string_mismatches": 0,
            "legacy_numerical_operator_id": (
                "schema4_job_4968695_python3117_blas_threads4"
            ),
            "test_records": 0,
        },
        "schema-4 canonical cache audit",
    )
    schema4_prediction_sha256 = lineage.get("schema4_predictions")
    if (
        not isinstance(schema4_prediction_sha256, str)
        or len(schema4_prediction_sha256) != 64
        or any(character not in "0123456789abcdef" for character in schema4_prediction_sha256)
        or audit.get("canonical_source_sha256") != schema4_prediction_sha256
        or audit.get("policy") != config["schema4_prediction_cache_policy"]
    ):
        raise CompactPublishError("Schema-4 canonical prediction lineage changed")
    runtime = summary.get("legacy_numerical_operator_runtime", {})
    _require_fields(
        runtime,
        {
            "status": "PASS",
            "operator_id": "schema4_job_4968695_python3117_blas_threads4",
            "artifact": "legacy_numerical_operator_runtime.json",
            "python_version": "3.11.7",
            "runtime_preload_modules": ["scipy.linalg", "sklearn.linear_model"],
            "threadpool_count": 3,
            "exact_numeric_string_replay_required": True,
        },
        "legacy numerical-operator result summary",
    )


def _validate_amendment_c_equivalence(
    summary: Mapping[str, Any],
    amendment_c_dir: Path,
    amendment_c_files: Mapping[str, str],
    amendment_c_manifest_sha256: str,
    amendment_c_validation_sha256: str,
) -> None:
    expected_artifacts = {
        name: amendment_c_files[name] for name in AMENDMENT_C_BYTE_EQUIVALENT_ARTIFACTS
    }
    expected = {
        "status": "PASS",
        "source_result_dir": str(amendment_c_dir),
        "source_checksums_sha256": amendment_c_manifest_sha256,
        "source_validation_sha256": amendment_c_validation_sha256,
        "artifacts": expected_artifacts,
        "interpretation": (
            "predictions_thresholds_cv_scores_and_candidate_order_byte_equivalent"
        ),
    }
    if summary.get("amendment_c_byte_equivalence") != expected:
        raise CompactPublishError(
            "Amendment-D result lost exact prediction/threshold/CV equivalence to Amendment C"
        )


def _validate_audit_summary(path: Path, summary: Mapping[str, Any]) -> None:
    _fields, rows = _read_tsv(path)
    audit = summary["schema4_canonical_prediction_cache"]
    indexed = {row.get("audit_item", ""): row for row in rows}
    numeric_fields = audit.get("numeric_fields", {})
    expected_items = {
        "prediction_keys",
        "semantic_fields",
        "derived_decisions",
        "exact_numeric_string_replay",
        "test_records",
        *numeric_fields,
    }
    if len(rows) != 10 or len(indexed) != len(rows) or set(indexed) != expected_items:
        raise CompactPublishError("Canonical-cache aggregate audit item set changed")
    for row in rows:
        if (
            row.get("status") != "PASS"
            or row.get("policy") != audit["policy"]
            or row.get("canonical_source_sha256") != audit["canonical_source_sha256"]
        ):
            raise CompactPublishError("Aggregate audit common provenance changed")
    fixed = {
        "prediction_keys": (audit["prediction_keys"], 0),
        "semantic_fields": (audit["semantic_comparisons"], audit["semantic_mismatches"]),
        "derived_decisions": (
            audit["prediction_keys"],
            audit["derived_decision_mismatches"],
        ),
        "exact_numeric_string_replay": (
            audit["exact_numeric_string_comparisons"],
            audit["numeric_string_mismatches"],
        ),
        "test_records": (audit["prediction_keys"], audit["test_records"]),
    }
    for item, (comparisons, mismatches) in fixed.items():
        if (
            int(indexed[item]["comparisons"]) != int(comparisons)
            or int(indexed[item]["mismatches"]) != int(mismatches)
        ):
            raise CompactPublishError(f"Aggregate audit contract changed: {item}")
    for field, values in numeric_fields.items():
        row = indexed[field]
        for integer_field in ("comparisons", "blank_pairs", "nonexact_comparisons"):
            if int(row[integer_field]) != int(values[integer_field]):
                raise CompactPublishError(
                    f"Aggregate numeric count changed: {field}/{integer_field}"
                )
        for numeric_field in (
            "absolute_tolerance",
            "relative_tolerance",
            "max_absolute_delta",
            "max_relative_delta",
            "max_tolerance_ratio",
        ):
            if float(row[numeric_field]) != float(values[numeric_field]):
                raise CompactPublishError(
                    f"Aggregate numeric value changed: {field}/{numeric_field}"
                )
        for key_field in (
            "max_absolute_delta_key",
            "max_relative_delta_key",
            "max_tolerance_ratio_key",
        ):
            if row[key_field] != str(values[key_field]):
                raise CompactPublishError(
                    f"Aggregate numeric key changed: {field}/{key_field}"
                )
        if int(row["mismatches"]) != 0:
            raise CompactPublishError(f"Aggregate numeric mismatch reported: {field}")


def _validate_h3_class_summary(path: Path, registry_path: Path) -> None:
    """Require the complete Amendment-D H3 endpoint matrix and raw supports."""

    fields, rows = _read_tsv(path)
    required_fields = {
        "system_id",
        "endpoint_id",
        "endpoint_role",
        "diagnostic_group",
        "truth_label",
        "metric",
        "n_truth_records",
        "n_source_clusters",
        "n_dependence_blocks",
        "raw_member_reject_k",
        "raw_member_reject_n",
        "raw_representative_reject_k",
        "raw_representative_reject_n",
        "interpretation",
    }
    if not required_fields <= set(fields):
        raise CompactPublishError(
            "Amendment-D H3 summary lacks reviewed subgroup-support fields"
        )

    _registry_fields, registry_rows = _read_tsv(registry_path)
    systems = {row["system_id"] for row in registry_rows}
    if len(systems) != 17 or len(registry_rows) != 17:
        raise CompactPublishError("Schema-5 system registry is not the reviewed 17 systems")
    indexed = {(row["system_id"], row["endpoint_id"]): row for row in rows}
    expected_keys = {
        (system_id, endpoint_id)
        for system_id in systems
        for endpoint_id in H3_RESULT_ENDPOINTS
    }
    if len(rows) != 102 or len(indexed) != len(rows) or set(indexed) != expected_keys:
        raise CompactPublishError("Amendment-D H3 endpoint matrix is not exact 17 x 6")

    expected_roles = {
        "Nucleocytoviricota_f1": "primary_known_class",
        "Preplasmiviricota_f1": "primary_known_class",
        "known_two_phylum_macro_f1": "primary_known_macro",
        "Produgelaviricota_reject_recall": "descriptive_subgroup",
        "literature_unclassified_reject_recall": (
            "descriptive_single_record_subgroup"
        ),
        "rare_or_unclassified_reject_recall": "secondary_pooled_diagnostic",
    }
    support = {
        "Produgelaviricota_reject_recall": (7, 2, 2),
        "literature_unclassified_reject_recall": (1, 1, 1),
        "rare_or_unclassified_reject_recall": (8, 3, 3),
    }
    raw_fields = (
        "raw_member_reject_k",
        "raw_member_reject_n",
        "raw_representative_reject_k",
        "raw_representative_reject_n",
    )
    for row in rows:
        endpoint = row["endpoint_id"]
        if row["endpoint_role"] != expected_roles[endpoint]:
            raise CompactPublishError(f"H3 endpoint role changed: {endpoint}")
        if endpoint not in support:
            if any(row[field] != "" for field in raw_fields):
                raise CompactPublishError(
                    f"Known-class H3 endpoint acquired reject-count fields: {endpoint}"
                )
            continue
        records, parents, blocks = support[endpoint]
        try:
            observed = (
                int(row["n_truth_records"]),
                int(row["n_source_clusters"]),
                int(row["n_dependence_blocks"]),
                int(row["raw_member_reject_k"]),
                int(row["raw_member_reject_n"]),
                int(row["raw_representative_reject_k"]),
                int(row["raw_representative_reject_n"]),
            )
        except ValueError as exc:
            raise CompactPublishError(
                f"H3 subgroup support is not integral: {endpoint}"
            ) from exc
        truth_n, parent_n, block_n, member_k, member_n, rep_k, rep_n = observed
        if (
            (truth_n, parent_n, block_n, member_n, rep_n)
            != (records, parents, blocks, records, parents)
            or not 0 <= member_k <= member_n
            or not 0 <= rep_k <= rep_n
        ):
            raise CompactPublishError(f"H3 subgroup support changed: {endpoint}")
        if endpoint == "rare_or_unclassified_reject_recall" and (
            "secondary" not in row["endpoint_role"]
            or "not_general_unknown_detection" not in row["interpretation"]
        ):
            raise CompactPublishError("Pooled H3 endpoint lost its secondary-only guard")
        if endpoint == "literature_unclassified_reject_recall" and (
            "single_record" not in row["interpretation"]
            or "no_generalization" not in row["interpretation"]
        ):
            raise CompactPublishError(
                "Literature-unclassified H3 endpoint lost its n=1 guard"
            )


def _validate_independent_validation(
    validation: dict[str, Any],
    config: dict[str, Any],
    identities: Mapping[str, str],
    result_manifest_sha256: str,
    result_file_count: int,
    schema4_prediction_sha256: str,
    runtime_sha256: str,
    amendment_c_manifest_sha256: str,
    amendment_c_validation_sha256: str,
) -> None:
    _require_fields(
        validation,
        {
            "schema_version": SCHEMA_VERSION,
            "analysis_id": ANALYSIS_ID,
            "status": "PASS",
            "validated_result_status": RESULT_STATUS,
        },
        "independent schema-5 validation",
    )
    counts = validation.get("counts", {})
    if (
        counts.get("test_records") != 0
        or counts.get("verified_artifacts") != result_file_count
        or counts.get("schema4_recomputation_audit_rows") != 92_844
        or counts.get("schema4_recomputation_audit_summary_rows") != 10
        or counts.get("schema4_exact_numeric_string_comparisons") != 464_220
        or counts.get("schema4_numeric_string_mismatches") != 0
        or counts.get("h3_endpoint_rows") != 102
        or counts.get("h3_subgroup_endpoint_rows") != 34
        or counts.get("amendment_c_byte_equivalent_artifacts") != 7
    ):
        raise CompactPublishError("Independent validation Test/artifact count changed")
    gates = validation.get("gates", {})
    if set(gates) != set(REQUIRED_VALIDATION_GATES) or any(
        gates[gate] != "PASS" for gate in REQUIRED_VALIDATION_GATES
    ):
        raise CompactPublishError("Independent validation gate set is not exact PASS")
    cache = validation.get("schema4_canonical_prediction_cache", {})
    _require_fields(
        cache,
        {
            "prediction_keys": 92_844,
            "row_level_audit_rows": 92_844,
            "aggregate_audit_rows": 10,
            "canonical_source_sha256": schema4_prediction_sha256,
            "test_records": 0,
        },
        "independent canonical-cache validation",
    )
    runtime = validation.get("legacy_numerical_operator_runtime", {})
    _require_fields(
        runtime,
        {
            "status": "PASS",
            "operator_id": "schema4_job_4968695_python3117_blas_threads4",
            "runtime_sha256": runtime_sha256,
            "python_version": "3.11.7",
            "runtime_preload_modules": ["scipy.linalg", "sklearn.linear_model"],
            "threadpool_count": 3,
        },
        "independent legacy numerical-operator validation",
    )
    inputs = validation.get("input_sha256", {})
    _require_fields(
        inputs,
        {
            "config": identities["config"],
            "result_checksums": result_manifest_sha256,
            "schema3_family_manifest": config[
                "schema3_family_member_manifest_sha256"
            ],
            "schema4_result_checksums": config["schema4_result_checksums_sha256"],
            "schema4_validation": config["schema4_validation_sha256"],
            "schema4_predictions": schema4_prediction_sha256,
            "legacy_numerical_operator_runtime": runtime_sha256,
            "amendment_c_result_checksums": amendment_c_manifest_sha256,
            "amendment_c_validation": amendment_c_validation_sha256,
        },
        "independent validation input lineage",
    )


def _validate_figure_manifest(
    figure_dir: Path, figure_files: Mapping[str, str]
) -> None:
    fields, rows = _read_tsv(figure_dir / "figure_manifest.tsv")
    if fields != ("path", "role", "bytes", "sha256"):
        raise CompactPublishError("Figure manifest header changed")
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        relative = _safe_relative(row["path"]).as_posix()
        if relative in indexed:
            raise CompactPublishError(f"Duplicate figure-manifest path: {relative}")
        indexed[relative] = row
    expected = set(figure_files) - {"figure_manifest.tsv"}
    if set(indexed) != expected:
        raise CompactPublishError("Figure manifest does not describe the exact full generation")
    for name, row in indexed.items():
        target = figure_dir / name
        try:
            size = int(row["bytes"])
        except ValueError as exc:
            raise CompactPublishError(f"Invalid figure size for {name}") from exc
        if row["sha256"] != figure_files[name] or size != target.stat().st_size:
            raise CompactPublishError(f"Figure manifest identity mismatch: {name}")


def _validate_h3_figure_source_data(path: Path, qa: Mapping[str, Any]) -> None:
    fields, rows = _read_tsv(path)
    expected_fields = (
        "candidate_id",
        "head3_model",
        "endpoint_id",
        "display_label",
        "scope",
        "value",
        "ci_low",
        "ci_high",
        "n_relations",
        "n_evaluation_records",
        "n_parents",
        "n_dependence_blocks",
        "raw_member_k",
        "raw_member_n",
        "raw_representative_k",
        "raw_representative_n",
        "endpoint_role",
        "interpretation",
    )
    if fields != expected_fields:
        raise CompactPublishError("Amendment-D panel-d H3 source-data header changed")
    indexed = {row["endpoint_id"]: row for row in rows}
    expected = set(H3_PRIMARY_ENDPOINTS) | {
        "rare_or_unclassified_reject_recall",
        "representative_benchmark_rare_unknown_recall",
    }
    if len(rows) != 6 or len(indexed) != 6 or set(indexed) != expected:
        raise CompactPublishError("Amendment-D panel-d H3 source-data is not exact six rows")
    if (
        {row["candidate_id"] for row in rows} != {qa.get("train_cv_nominee")}
        or {row["head3_model"] for row in rows} != {qa.get("h3_nominee_model")}
    ):
        raise CompactPublishError("Panel-d H3 source data changed nominee/model")

    roles = {
        "Nucleocytoviricota_f1": "primary_known_class",
        "Preplasmiviricota_f1": "primary_known_class",
        "Produgelaviricota_reject_recall": "descriptive_subgroup",
        "literature_unclassified_reject_recall": (
            "descriptive_single_record_subgroup"
        ),
        "rare_or_unclassified_reject_recall": "secondary_pooled_diagnostic",
        "representative_benchmark_rare_unknown_recall": (
            "secondary_external_benchmark_different_cohort"
        ),
    }
    scopes = {
        **{endpoint: "matched_family_member" for endpoint in H3_PRIMARY_ENDPOINTS},
        "rare_or_unclassified_reject_recall": "matched_family_member_secondary",
        "representative_benchmark_rare_unknown_recall": (
            "representative_benchmark_secondary"
        ),
    }
    for endpoint, row in indexed.items():
        if row["endpoint_role"] != roles[endpoint] or row["scope"] != scopes[endpoint]:
            raise CompactPublishError(f"Panel-d H3 endpoint role/scope changed: {endpoint}")
        try:
            value = float(row["value"])
        except ValueError as exc:
            raise CompactPublishError(f"Panel-d H3 value is invalid: {endpoint}") from exc
        if not 0.0 <= value <= 1.0:
            raise CompactPublishError(f"Panel-d H3 value escaped [0,1]: {endpoint}")

    supports = {
        "Produgelaviricota_reject_recall": (7, 2, 2),
        "literature_unclassified_reject_recall": (1, 1, 1),
        "rare_or_unclassified_reject_recall": (8, 3, 3),
    }
    for endpoint, (relations, parents, blocks) in supports.items():
        row = indexed[endpoint]
        try:
            values = tuple(
                int(row[field])
                for field in (
                    "n_relations",
                    "n_evaluation_records",
                    "n_parents",
                    "n_dependence_blocks",
                    "raw_member_k",
                    "raw_member_n",
                    "raw_representative_k",
                    "raw_representative_n",
                )
            )
        except ValueError as exc:
            raise CompactPublishError(
                f"Panel-d H3 subgroup support is invalid: {endpoint}"
            ) from exc
        relation_n, evaluation_n, parent_n, block_n, member_k, member_n, rep_k, rep_n = values
        if (
            (relation_n, evaluation_n, parent_n, block_n, member_n, rep_n)
            != (relations, relations, parents, blocks, relations, parents)
            or not 0 <= member_k <= member_n
            or not 0 <= rep_k <= rep_n
        ):
            raise CompactPublishError(
                f"Panel-d H3 subgroup support changed: {endpoint}"
            )
    literature = indexed["literature_unclassified_reject_recall"]
    if literature["ci_low"] != "" or literature["ci_high"] != "":
        raise CompactPublishError("Panel-d n=1 H3 row may not display a confidence interval")
    pooled = indexed["rare_or_unclassified_reject_recall"]
    if "secondary" not in pooled["display_label"].lower():
        raise CompactPublishError("Panel-d pooled H3 row lost its secondary label")
    benchmark = indexed["representative_benchmark_rare_unknown_recall"]
    if (
        benchmark["n_relations"] != "5"
        or benchmark["n_evaluation_records"] != "5"
        or benchmark["raw_representative_n"] != "5"
        or benchmark["raw_member_k"] != ""
        or benchmark["raw_member_n"] != ""
    ):
        raise CompactPublishError("Panel-d separate n=5 benchmark support changed")


def _validate_figure_qa(
    qa: dict[str, Any],
    result_files: Mapping[str, str],
    validation_sha256: str,
    identities: Mapping[str, str],
) -> None:
    _require_fields(
        qa,
        {
            "analysis_id": ANALYSIS_ID,
            "status": "pass",
            "protocol_amendment": PROTOCOL_AMENDMENT,
            "backend": "python_matplotlib_only",
            "exports": list(FIGURE_EXPORTS),
            "svg_text_editable": True,
            "result_checksum_manifest_verified": True,
            "independent_schema5_validation_verified": True,
            "config_sha256": identities["config"],
            "protocol_sha256": identities["protocol"],
            "comparison_summary_sha256": identities["comparison_summary"],
            "schema5_validation_sha256": validation_sha256,
            "cross_source_average_plotted": False,
            "robustness_used_for_candidate_ordering": False,
            "test_vectors_selected_for_inference": 0,
            "test_predictions_or_metrics_computed": 0,
            "na_ne_numeric_zero_have_distinct_encodings": True,
            "h3_representative_benchmark_rare_n": 5,
            "h3_matched_family_rare_relations_n": 8,
            "h3_matched_family_rare_parents_n": 3,
            "h3_matched_family_rare_blocks_n": 3,
            "h3_primary_endpoint_ids": [
                "Nucleocytoviricota_f1",
                "Preplasmiviricota_f1",
                "Produgelaviricota_reject_recall",
                "literature_unclassified_reject_recall",
            ],
            "h3_primary_display_rows": 4,
            "h3_produgelaviricota_relations_n": 7,
            "h3_produgelaviricota_parents_n": 2,
            "h3_produgelaviricota_blocks_n": 2,
            "h3_literature_unclassified_relations_n": 1,
            "h3_literature_unclassified_parents_n": 1,
            "h3_literature_unclassified_blocks_n": 1,
            "h3_raw_k_n_displayed": True,
            "h3_pooled_used_as_primary": False,
            "h3_pooled_secondary_only": True,
            "h3_single_block_ci_drawn": False,
            "h3_unknown_generalization_claim_permitted": False,
        },
        "schema-5 figure QA",
    )
    if qa.get("result_input_sha256") != dict(result_files):
        raise CompactPublishError("Figure QA is not bound to the exact full result manifest")
    expected_source_data_names = sorted(
        PurePosixPath(name).name for name in FIGURE_SOURCE_DATA_FILES
    )
    if qa.get("source_data_tables") != expected_source_data_names:
        raise CompactPublishError("Figure QA source-data inventory changed")


def _validate_config(config: dict[str, Any]) -> None:
    _require_fields(
        config,
        {
            "schema_version": SCHEMA_VERSION,
            "analysis_id": ANALYSIS_ID,
            "model_state": "frozen",
            "selection_feedback_permitted": False,
            "released_v0_feedback_permitted": False,
            "schema5_robustness_reranking_permitted": False,
            "test_policy": "no_test_vector_selection_or_performance_scoring",
            "protocol_amendment": PROTOCOL_AMENDMENT,
            "schema4_prediction_cache_policy": (
                "checksum_bound_schema4_serialized_rows_after_legacy_operator_"
                "exact_numeric_replay"
            ),
            "schema4_expected_prediction_rows": 92_844,
            "schema4_recomputation_tolerances": {
                "probability": {"absolute": 5e-7, "relative": 1e-6},
                "raw_decision_score": {"absolute": 1e-5, "relative": 1e-6},
                "threshold": {"absolute": 0.0, "relative": 0.0},
            },
        },
        "schema-5 config",
    )
    for field in (
        "protocol",
        "comparison_summary",
        "schema4_result_checksums_sha256",
        "schema4_validation_sha256",
        "schema3_family_member_manifest_sha256",
        "amendment_c_result_dir",
        "amendment_c_result_checksums_sha256",
        "amendment_c_validation",
        "amendment_c_validation_sha256",
        "amendment_d_required_byte_equivalent_artifacts",
        "analysis_root",
        "result_dir",
        "figure_dir",
        "active_compact_result_dir",
        "active_compact_figure_dir",
    ):
        if field not in config:
            raise CompactPublishError(f"Schema-5 config lacks {field}")
    analysis_root = _lexical_absolute(Path(str(config["analysis_root"])))
    result_dir = _lexical_absolute(Path(str(config["result_dir"])))
    figure_dir = _lexical_absolute(Path(str(config["figure_dir"])))
    if analysis_root.name != "schema5_v1_amendment_d" or analysis_root == Path("/"):
        raise CompactPublishError(
            f"Schema-5 Amendment-D analysis root has an invalid generation name: {analysis_root}"
        )
    legacy_schema5_analysis_root = analysis_root.with_name("schema5_v1")
    if result_dir != analysis_root / "results" or figure_dir != analysis_root / "figures":
        raise CompactPublishError(
            "Schema-5 Amendment-D result/figure destinations escaped their generation"
        )
    if (
        config["schema3_family_member_manifest_sha256"]
        != SCHEMA3_FAMILY_MEMBER_MANIFEST_SHA256
        or Path(str(config["amendment_c_result_dir"]))
        != legacy_schema5_analysis_root / "results"
        or config["amendment_c_result_checksums_sha256"]
        != AMENDMENT_C_RESULT_CHECKSUMS_SHA256
        or Path(str(config["amendment_c_validation"]))
        != legacy_schema5_analysis_root / "validation.json"
        or config["amendment_c_validation_sha256"]
        != AMENDMENT_C_VALIDATION_SHA256
        or config["amendment_d_required_byte_equivalent_artifacts"]
        != list(AMENDMENT_C_BYTE_EQUIVALENT_ARTIFACTS)
    ):
        raise CompactPublishError("Fixed schema3/Amendment-C lineage config boundary changed")
    expected_h3_config_contract = {
        "derivation": "frozen_family_manifest_join_to_existing_per_record_predictions",
        "model_inference_repeated_for_subgroups": False,
        "refit_recalibration_or_threshold_change_permitted": False,
        "prediction_threshold_cv_nomination_equivalence_to_amendment_c_required": True,
        "subgroup_fields": ["head3_status", "head3_phylum_label"],
        "raw_reject_counts_required": True,
        "endpoints": {
            "Produgelaviricota_reject_recall": {
                "endpoint_role": "descriptive_subgroup",
                "expected_records": 7,
                "expected_parents": 2,
                "expected_dependence_blocks": 2,
                "bootstrap_seed_offset": 6100,
                "interpretation": (
                    "rare_formal_phylum_rejection_descriptive_not_general_unknown_detection"
                ),
            },
            "literature_unclassified_reject_recall": {
                "endpoint_role": "descriptive_single_record_subgroup",
                "expected_records": 1,
                "expected_parents": 1,
                "expected_dependence_blocks": 1,
                "bootstrap_seed_offset": 6110,
                "interpretation": "single_record_descriptive_only_no_generalization",
            },
            "rare_or_unclassified_reject_recall": {
                "endpoint_role": "secondary_pooled_diagnostic",
                "expected_records": 8,
                "expected_parents": 3,
                "expected_dependence_blocks": 3,
                "bootstrap_seed_offset": 6100,
                "interpretation": (
                    "secondary_pooled_small_prespecified_diagnostic_not_general_unknown_detection"
                ),
            },
        },
    }
    if config.get("h3_rare_endpoint_contract") != expected_h3_config_contract:
        raise CompactPublishError("Schema-5 Amendment-D config H3 contract changed")

    for source, spec in config.get("inputs", {}).items():
        if not isinstance(spec, dict):
            raise CompactPublishError(f"Invalid schema-5 input source: {source}")
        for field in ("manifest", "fasta"):
            path = Path(str(spec.get(field)))
            if not path.is_absolute() or legacy_schema5_analysis_root not in path.parents:
                raise CompactPublishError(
                    f"Amendment-D input is not bound to the legacy read generation: "
                    f"{source}/{field}"
                )
    for source, registry in config.get("embedding_registries", {}).items():
        if not isinstance(registry, dict):
            raise CompactPublishError(f"Invalid embedding registry: {source}")
        for model, value in registry.items():
            path = Path(str(value))
            if (
                not path.is_absolute()
                or path == analysis_root
                or analysis_root in path.parents
            ):
                raise CompactPublishError(
                    f"Amendment-D embedding path is not external/read-only: {source}/{model}"
                )
    expected_receipts = {
        "receipt_root": legacy_schema5_analysis_root / "receipts",
        "materialization_receipt_dir": (
            legacy_schema5_analysis_root / "receipts" / "materialization"
        ),
        "reuse_attestation_dir": legacy_schema5_analysis_root / "receipts" / "reuse",
        "normalized_embedding_attestation_dir": (
            legacy_schema5_analysis_root / "receipts" / "attestations"
        ),
    }
    for field, expected in expected_receipts.items():
        if Path(str(config.get(field))) != expected:
            raise CompactPublishError(f"Amendment-D frozen receipt path changed: {field}")
    _require_fields(
        config.get("legacy_schema4_numerical_operator", {}),
        {
            "operator_id": "schema4_job_4968695_python3117_blas_threads4",
            "canonical_schema4_job": 4968695,
            "pbs_ncpus": 4,
            "pbs_memory_gb": 32,
            "omp_num_threads": 4,
            "mkl_num_threads": 4,
            "openblas_num_threads": 4,
            "pythonhashseed": 20260724,
            "python_module": "Python/3.11.7",
            "python_version": "3.11.7",
            "runtime_preload_modules": ["scipy.linalg", "sklearn.linear_model"],
            "required_threadpool_count": 3,
            "required_threadpool_user_api_counts": {"blas": 2, "openmp": 1},
            "exact_numeric_string_replay_required": True,
            "amendment_b_tolerances_retained_as_upper_bound": True,
        },
        "legacy numerical-operator config",
    )


def preflight(
    config_path: Path,
    *,
    result_dir_override: Path | None = None,
    validation_path_override: Path | None = None,
    figure_dir_override: Path | None = None,
) -> dict[str, Any]:
    """Read and verify all full artifacts without performing writes."""

    config_path = config_path.resolve()
    _require_real_file(config_path)
    project_root = config_path.parent.parent
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CompactPublishError(f"Could not read schema-5 config: {exc}") from exc
    if not isinstance(config, dict):
        raise CompactPublishError("Schema-5 config root is not an object")
    _validate_config(config)

    protocol_path = _resolve_source(project_root, config["protocol"])
    comparison_path = _resolve_source(project_root, config["comparison_summary"])
    _require_real_file(protocol_path)
    _require_real_file(comparison_path)
    identities = {
        "config": _sha256(config_path),
        "protocol": _sha256(protocol_path),
        "comparison_summary": _sha256(comparison_path),
    }

    amendment_c_dir = _lexical_absolute(Path(str(config["amendment_c_result_dir"])))
    amendment_c_files = _verify_bundle(amendment_c_dir)
    if set(amendment_c_files) != set(EXPECTED_FULL_RESULT_FILES):
        raise CompactPublishError("Amendment-C source result inventory changed")
    amendment_c_manifest_path = amendment_c_dir / "CHECKSUMS.sha256"
    amendment_c_manifest_sha256 = _sha256(amendment_c_manifest_path)
    if amendment_c_manifest_sha256 != AMENDMENT_C_RESULT_CHECKSUMS_SHA256:
        raise CompactPublishError("Fixed Amendment-C result manifest identity changed")
    amendment_c_validation_path = _lexical_absolute(
        Path(str(config["amendment_c_validation"]))
    )
    _require_real_file(amendment_c_validation_path)
    amendment_c_validation_sha256 = _sha256(amendment_c_validation_path)
    if amendment_c_validation_sha256 != AMENDMENT_C_VALIDATION_SHA256:
        raise CompactPublishError("Fixed Amendment-C validation identity changed")

    result_dir = _lexical_absolute(
        result_dir_override
        if result_dir_override is not None
        else _resolve_source(project_root, config["result_dir"])
    )
    figure_dir = _lexical_absolute(
        figure_dir_override
        if figure_dir_override is not None
        else _resolve_source(project_root, config["figure_dir"])
    )
    validation_path = _lexical_absolute(
        validation_path_override
        if validation_path_override is not None
        else result_dir.with_name("validation.json")
    )

    result_files = _verify_bundle(result_dir)
    if set(result_files) != set(EXPECTED_FULL_RESULT_FILES):
        raise CompactPublishError(
            "Full result files are not the reviewed compact/excluded partition: "
            f"unexpected={sorted(set(result_files) - set(EXPECTED_FULL_RESULT_FILES))}, "
            f"missing={sorted(set(EXPECTED_FULL_RESULT_FILES) - set(result_files))}"
        )
    summary = _read_json(result_dir / "summary.json")
    _validate_summary(summary, config, identities)
    _validate_amendment_c_equivalence(
        summary,
        amendment_c_dir,
        amendment_c_files,
        amendment_c_manifest_sha256,
        amendment_c_validation_sha256,
    )
    if (
        summary.get("lineage_sha256", {}).get("legacy_numerical_operator_runtime")
        != result_files["legacy_numerical_operator_runtime.json"]
    ):
        raise CompactPublishError("Runtime attestation is not bound into result lineage")
    _validate_audit_summary(
        result_dir / "schema4_recomputation_audit_summary.tsv", summary
    )
    _validate_h3_class_summary(
        result_dir / "h3_class_summary.tsv",
        result_dir / "system_registry.tsv",
    )

    result_manifest_sha256 = _sha256(result_dir / "CHECKSUMS.sha256")
    validation = _read_json(validation_path)
    validation_sha256 = _sha256(validation_path)
    _validate_independent_validation(
        validation,
        config,
        identities,
        result_manifest_sha256,
        len(result_files),
        summary["lineage_sha256"]["schema4_predictions"],
        result_files["legacy_numerical_operator_runtime.json"],
        amendment_c_manifest_sha256,
        amendment_c_validation_sha256,
    )

    figure_files = _verify_bundle(figure_dir)
    if not COMPACT_FIGURE_SOURCE_FILES <= set(figure_files) or FIGURE_EXPORTS[3] not in figure_files:
        raise CompactPublishError("Full figure bundle lacks a required compact/full export")
    _validate_figure_manifest(figure_dir, figure_files)
    qa = _read_json(figure_dir / "QA.json")
    _validate_figure_qa(qa, result_files, validation_sha256, identities)
    _validate_h3_figure_source_data(
        figure_dir / "source_data" / "panel_d_h3_boundary.tsv",
        qa,
    )
    svg = (figure_dir / FIGURE_EXPORTS[0]).read_text(encoding="utf-8")
    if "<text" not in svg:
        raise CompactPublishError("Full SVG no longer contains editable text")
    if not (figure_dir / FIGURE_EXPORTS[1]).read_bytes().startswith(b"%PDF-"):
        raise CompactPublishError("Full PDF export has an invalid signature")
    if not (figure_dir / FIGURE_EXPORTS[2]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
        raise CompactPublishError("Full PNG export has an invalid signature")

    result_output = _active_destination(
        project_root, config["active_compact_result_dir"], "active compact result"
    )
    figure_output = _active_destination(
        project_root, config["active_compact_figure_dir"], "active compact figure"
    )
    for destination in (result_output, figure_output):
        _assert_no_existing_symlink_ancestor(project_root, destination.parent)
        _require_absent(destination)
    if _paths_overlap(result_output, figure_output):
        raise CompactPublishError("Active compact destinations overlap")
    for source in (result_dir, figure_dir):
        for destination in (result_output, figure_output):
            if _paths_overlap(source, destination):
                raise CompactPublishError("An active compact destination overlaps a full source")

    return {
        "config_path": config_path,
        "project_root": project_root,
        "config": config,
        "protocol_path": protocol_path,
        "comparison_path": comparison_path,
        "identities": identities,
        "amendment_c_dir": amendment_c_dir,
        "amendment_c_files": amendment_c_files,
        "amendment_c_manifest_path": amendment_c_manifest_path,
        "amendment_c_manifest_sha256": amendment_c_manifest_sha256,
        "amendment_c_validation_path": amendment_c_validation_path,
        "amendment_c_validation_sha256": amendment_c_validation_sha256,
        "result_dir": result_dir,
        "result_files": result_files,
        "result_manifest_sha256": result_manifest_sha256,
        "summary": summary,
        "validation_path": validation_path,
        "validation": validation,
        "validation_sha256": validation_sha256,
        "figure_dir": figure_dir,
        "figure_files": figure_files,
        "figure_checksums_sha256": _sha256(figure_dir / "CHECKSUMS.sha256"),
        "qa": qa,
        "result_output": result_output,
        "figure_output": figure_output,
    }


def _copy_verified(source: Path, destination: Path, expected_sha256: str) -> None:
    _require_real_file(source)
    if os.path.lexists(destination):
        raise CompactPublishError(f"Refusing to overwrite staged artifact: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.is_symlink():
        raise CompactPublishError(f"Staged parent may not be a symlink: {destination.parent}")
    shutil.copyfile(source, destination)
    if _sha256(destination) != expected_sha256:
        raise CompactPublishError(f"Copied artifact identity changed: {source}")


def _write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _write_checksums(directory: Path) -> dict[str, str]:
    manifest = directory / "CHECKSUMS.sha256"
    files = sorted(
        path for path in directory.rglob("*") if path.is_file() and not path.is_symlink()
    )
    if not files:
        raise CompactPublishError(f"Refusing an empty compact bundle: {directory}")
    with manifest.open("x", encoding="utf-8") as handle:
        for path in files:
            relative = path.relative_to(directory).as_posix()
            handle.write(f"{_sha256(path)}  {relative}\n")
    return _verify_bundle(directory)


def _compact_metadata(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_schema_version": SCHEMA_VERSION,
        "analysis_id": ANALYSIS_ID,
        "artifact_role": "checksum_bound_schema5_compact_source_binding",
        "publication_contract": "valid_only_at_config_active_compact_paths",
        "protocol_amendment": PROTOCOL_AMENDMENT,
        "source_analysis_root": str(state["config"]["analysis_root"]),
        "project_version": "V0",
        "data_curation_version": "V3",
        "test_records": 0,
        "source_sha256": {
            "config": state["identities"]["config"],
            "protocol": state["identities"]["protocol"],
            "comparison_summary": state["identities"]["comparison_summary"],
            "schema3_family_member_manifest": state["config"][
                "schema3_family_member_manifest_sha256"
            ],
            "amendment_c_result_checksums": state[
                "amendment_c_manifest_sha256"
            ],
            "amendment_c_validation": state["amendment_c_validation_sha256"],
            "full_result_checksums": state["result_manifest_sha256"],
            "independent_validation": state["validation_sha256"],
            "full_figure_checksums": state["figure_checksums_sha256"],
            "full_figure_qa": state["figure_files"]["QA.json"],
        },
        "source_artifact_sha256": {
            "full_result": dict(state["result_files"]),
            "full_figure": dict(state["figure_files"]),
        },
        "active_destinations": {
            "result": str(state["result_output"]),
            "figure": str(state["figure_output"]),
        },
        "amendment_c_fixed_lineage": {
            "result_dir": str(state["amendment_c_dir"]),
            "result_checksums_sha256": state["amendment_c_manifest_sha256"],
            "validation_path": str(state["amendment_c_validation_path"]),
            "validation_sha256": state["amendment_c_validation_sha256"],
        },
        "result_core": {
            "included_from_full": sorted(COMPACT_RESULT_SOURCE_FILES),
            "included_validation_as": "validation.json",
            "excluded_high_volume": sorted(EXCLUDED_HIGH_VOLUME_RESULT_FILES),
        },
        "h3_rare_endpoint_contract": state["summary"]["h3_rare_endpoint_contract"],
        "figure_core": {
            "included_from_full": sorted(COMPACT_FIGURE_SOURCE_FILES),
            "excluded_from_active": sorted(
                set(state["figure_files"]) - set(COMPACT_FIGURE_SOURCE_FILES)
            ),
            "figure_manifest_scope": "complete_source_figure_generation",
            "active_inventory_authority": "CHECKSUMS.sha256",
        },
    }


def _stage_bundles(
    state: Mapping[str, Any], result_stage: Path, figure_stage: Path
) -> None:
    result_stage.mkdir()
    figure_stage.mkdir()
    metadata = _compact_metadata(state)
    for name in sorted(COMPACT_RESULT_SOURCE_FILES):
        _copy_verified(
            state["result_dir"] / name,
            result_stage / name,
            state["result_files"][name],
        )
    _copy_verified(
        state["validation_path"],
        result_stage / "validation.json",
        state["validation_sha256"],
    )
    _write_json_exclusive(result_stage / COMPACT_METADATA_NAME, metadata)
    result_verified = _write_checksums(result_stage)
    expected_result = set(COMPACT_RESULT_SOURCE_FILES) | {
        "validation.json",
        COMPACT_METADATA_NAME,
    }
    if set(result_verified) != expected_result:
        raise CompactPublishError("Staged compact result inventory changed")

    for name in sorted(COMPACT_FIGURE_SOURCE_FILES):
        _copy_verified(
            state["figure_dir"] / name,
            figure_stage / name,
            state["figure_files"][name],
        )
    _write_json_exclusive(figure_stage / COMPACT_METADATA_NAME, metadata)
    figure_verified = _write_checksums(figure_stage)
    expected_figure = set(COMPACT_FIGURE_SOURCE_FILES) | {COMPACT_METADATA_NAME}
    if set(figure_verified) != expected_figure:
        raise CompactPublishError("Staged compact figure inventory changed")


def _assert_sources_unchanged(state: Mapping[str, Any]) -> None:
    if _verify_bundle(state["amendment_c_dir"]) != state["amendment_c_files"]:
        raise CompactPublishError("Amendment-C source result changed after preflight")
    if _verify_bundle(state["result_dir"]) != state["result_files"]:
        raise CompactPublishError("Full result changed after preflight")
    if _verify_bundle(state["figure_dir"]) != state["figure_files"]:
        raise CompactPublishError("Full figure changed after preflight")
    for path, expected in (
        (state["config_path"], state["identities"]["config"]),
        (state["protocol_path"], state["identities"]["protocol"]),
        (state["comparison_path"], state["identities"]["comparison_summary"]),
        (
            state["amendment_c_manifest_path"],
            state["amendment_c_manifest_sha256"],
        ),
        (
            state["amendment_c_validation_path"],
            state["amendment_c_validation_sha256"],
        ),
        (state["validation_path"], state["validation_sha256"]),
    ):
        if _sha256(path) != expected:
            raise CompactPublishError(f"Source changed after preflight: {path}")
    for destination in (state["result_output"], state["figure_output"]):
        _require_absent(destination)


def _rollback_commits(
    committed: Sequence[tuple[Path, Path]], original_error: BaseException
) -> None:
    failures: list[str] = []
    for stage, destination in reversed(committed):
        try:
            if os.path.lexists(stage):
                raise CompactPublishError(f"Rollback stage unexpectedly exists: {stage}")
            _atomic_rename_noreplace(destination, stage)
        except BaseException as exc:  # pragma: no cover - emergency preservation path
            failures.append(f"{destination} -> {stage}: {exc}")
    if failures:
        raise CompactPublishError(
            f"Publication failed ({original_error}); rollback also failed: {failures}"
        ) from original_error


def _commit_pair(
    result_stage: Path,
    result_output: Path,
    figure_stage: Path,
    figure_output: Path,
    post_verify: Callable[[], None],
) -> list[str]:
    """Commit two staged directories and roll back the first on any later failure."""

    operations = ((result_stage, result_output), (figure_stage, figure_output))
    committed: list[tuple[Path, Path]] = []
    mechanisms: list[str] = []
    try:
        for stage, destination in operations:
            mechanisms.append(_atomic_rename_noreplace(stage, destination))
            committed.append((stage, destination))
        post_verify()
        return mechanisms
    except BaseException as exc:
        _rollback_commits(committed, exc)
        raise


def _preserve_failed_stages(stages: Iterable[Path]) -> list[str]:
    errors: list[str] = []
    for stage in stages:
        if not os.path.lexists(stage):
            continue
        failed = stage.with_name(f"{stage.name}.failed")
        try:
            _atomic_rename_noreplace(stage, failed)
        except BaseException as exc:  # pragma: no cover - emergency preservation path
            errors.append(f"{stage} -> {failed}: {exc}")
    return errors


def publish(state: Mapping[str, Any]) -> dict[str, Any]:
    """Stage, verify, and no-overwrite publish both compact cores."""

    for destination in (state["result_output"], state["figure_output"]):
        _require_absent(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _assert_no_existing_symlink_ancestor(state["project_root"], destination.parent)
    token = f"{os.getpid()}-{uuid.uuid4().hex}"
    result_stage = state["result_output"].with_name(
        f".{state['result_output'].name}.stage-{token}"
    )
    figure_stage = state["figure_output"].with_name(
        f".{state['figure_output'].name}.stage-{token}"
    )
    for stage in (result_stage, figure_stage):
        _require_absent(stage)

    def post_verify() -> None:
        result_verified = _verify_bundle(state["result_output"])
        figure_verified = _verify_bundle(state["figure_output"])
        if set(result_verified) != set(COMPACT_RESULT_SOURCE_FILES) | {
            "validation.json",
            COMPACT_METADATA_NAME,
        }:
            raise CompactPublishError("Published compact result inventory changed")
        if set(figure_verified) != set(COMPACT_FIGURE_SOURCE_FILES) | {
            COMPACT_METADATA_NAME
        }:
            raise CompactPublishError("Published compact figure inventory changed")

    try:
        _stage_bundles(state, result_stage, figure_stage)
        _assert_sources_unchanged(state)
        mechanisms = _commit_pair(
            result_stage,
            state["result_output"],
            figure_stage,
            state["figure_output"],
            post_verify,
        )
    except BaseException as exc:
        preservation_errors = _preserve_failed_stages((result_stage, figure_stage))
        if preservation_errors:
            raise CompactPublishError(
                f"Compact publication failed ({exc}); failed-stage preservation errors: "
                f"{preservation_errors}"
            ) from exc
        raise
    return {
        "schema_version": 1,
        "analysis_id": ANALYSIS_ID,
        "status": "published",
        "writes_performed": True,
        "test_records": 0,
        "result_output": str(state["result_output"]),
        "figure_output": str(state["figure_output"]),
        "result_file_count": len(COMPACT_RESULT_SOURCE_FILES) + 3,
        "figure_file_count": len(COMPACT_FIGURE_SOURCE_FILES) + 2,
        "atomic_mechanisms": mechanisms,
        "source_full_result_checksums_sha256": state["result_manifest_sha256"],
        "source_validation_sha256": state["validation_sha256"],
        "source_full_figure_checksums_sha256": state["figure_checksums_sha256"],
    }


def _preflight_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "analysis_id": ANALYSIS_ID,
        "status": "ready_no_writes",
        "writes_performed": False,
        "test_records": 0,
        "full_result_file_count": len(state["result_files"]),
        "full_figure_file_count": len(state["figure_files"]),
        "compact_result_source_files": sorted(COMPACT_RESULT_SOURCE_FILES),
        "excluded_high_volume_result_files": sorted(EXCLUDED_HIGH_VOLUME_RESULT_FILES),
        "compact_figure_source_files": sorted(COMPACT_FIGURE_SOURCE_FILES),
        "result_output": str(state["result_output"]),
        "figure_output": str(state["figure_output"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_DIR
        / "configs"
        / "validation_family_robustness_v0_schema5_mixed_heads.yaml",
    )
    parser.add_argument(
        "--result-dir",
        type=Path,
        help="Read-only full result override; active destination remains config-bound.",
    )
    parser.add_argument(
        "--validation",
        type=Path,
        help="Read-only validation.json override; active destination remains config-bound.",
    )
    parser.add_argument(
        "--figure-dir",
        type=Path,
        help="Read-only full figure override; active destination remains config-bound.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Perform no-overwrite publication after preflight; default is read-only.",
    )
    args = parser.parse_args()
    state = preflight(
        args.config,
        result_dir_override=args.result_dir,
        validation_path_override=args.validation,
        figure_dir_override=args.figure_dir,
    )
    payload = publish(state) if args.publish else _preflight_summary(state)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
