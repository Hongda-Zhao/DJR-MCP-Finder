#!/usr/bin/env python3
"""Render the checksum-bound schema-5 eight-model/mixed-head figure.

The renderer is downstream-only.  It verifies the completed schema-5 result
bundle before reading any table, verifies the checksum-bound schema-4 coverage
continuity table, and never opens embeddings or raw predictions.  No demo or
synthetic-data path exists: rendering requires the real completed result.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence


# Plotting imports are deliberately lazy so static contract tests and --help
# remain available on transfer hosts without matplotlib.
mpl: Any = None
plt: Any = None
np: Any = None


def _load_matplotlib() -> None:
    global mpl, plt, np
    if mpl is not None:
        return
    import matplotlib as matplotlib_module

    matplotlib_module.use("Agg")
    import matplotlib.pyplot as pyplot_module
    import numpy as numpy_module

    mpl, plt, np = matplotlib_module, pyplot_module, numpy_module
    # Nature-figure delivery contract: editable SVG/PDF text.
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
    plt.rcParams["svg.fonttype"] = "none"
    plt.rcParams["pdf.fonttype"] = 42


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ID = "project_v0_validation_family_robustness_schema5_mixed_heads"
FIGURE_BASENAME = "validation_family_robustness_v0_schema5_mixed_heads"
FIGURE_WIDTH_MM = 183.0
FIGURE_HEIGHT_MM = 225.0
SUPPORTED_EXPORT_SUFFIXES = (".svg", ".pdf", ".png", ".tiff")
PANEL_LABELS = ("a", "b", "c", "d", "e")

SOURCE_ORDER = (
    "viral_vma_djr",
    "cellular_djr_none",
    "background_non_djr",
    "hard_non_djr",
)
SOURCE_LABEL = {
    "viral_vma_djr": "Viral VMA-DJR",
    "cellular_djr_none": "Cellular DJR, non-MCP",
    "background_non_djr": "Background non-DJR",
    "hard_non_djr": "Matched HardNeg",
}
SOURCE_SHORT = {
    "viral_vma_djr": "V",
    "cellular_djr_none": "C",
    "background_non_djr": "B",
    "hard_non_djr": "H",
}
HEAD_ORDER = ("head1", "head2", "head3_phylum")
HEAD_LABEL = {"head1": "H1", "head2": "H2", "head3_phylum": "H3"}
APPLICABLE_HEADS = {
    "viral_vma_djr": frozenset(HEAD_ORDER),
    "cellular_djr_none": frozenset(("head1", "head2")),
    "background_non_djr": frozenset(("head1",)),
    "hard_non_djr": frozenset(("head1",)),
}
PATH_ID = "full_expected_path"

MODEL_ORDER = (
    "esmc_6b",
    "esm2_3b",
    "esmc_300m",
    "prostt5",
    "prott5_xl",
    "esm3_open_1_4b",
    "esmc_600m",
    "esm2_650m",
)
MODEL_LABEL = {
    "esmc_6b": "ESM-C 6B",
    "esm2_3b": "ESM-2 3B",
    "esmc_300m": "ESM-C 300M",
    "prostt5": "ProstT5",
    "prott5_xl": "ProtT5-XL-U50",
    "esm3_open_1_4b": "ESM3-open 1.4B",
    "esmc_600m": "ESM-C 600M",
    "esm2_650m": "ESM-2 650M",
}
H12_ORDER = ("esm2_650m", "esm2_3b", "esmc_6b")
H3_ORDER = ("esmc_300m", "esmc_600m", "esmc_6b")
CANDIDATE_ORDER = tuple(
    f"h12_{h12}__h3_{h3}" for h12 in H12_ORDER for h3 in H3_ORDER
)
REFERENCE_SYSTEM = "esmc_6b"
CONTEXTUAL_REFERENCE_SYSTEM = "esm2_650m"

REPRESENTATIVE_RARE_N = 5
MATCHED_RARE_RELATIONS_N = 8
MATCHED_RARE_PARENTS_N = 3
MATCHED_RARE_BLOCKS_N = 3
PRODUGELAVIRICOTA_RELATIONS_N = 7
PRODUGELAVIRICOTA_PARENTS_N = 2
PRODUGELAVIRICOTA_BLOCKS_N = 2
LITERATURE_UNCLASSIFIED_RELATIONS_N = 1
LITERATURE_UNCLASSIFIED_PARENTS_N = 1
LITERATURE_UNCLASSIFIED_BLOCKS_N = 1
PROTOCOL_AMENDMENT = "D_h3_rare_subgroup_transparency_no_model_change"
H3_PRIMARY_DISPLAY_ENDPOINTS = (
    "Nucleocytoviricota_f1",
    "Preplasmiviricota_f1",
    "Produgelaviricota_reject_recall",
    "literature_unclassified_reject_recall",
)
H3_ALL_ENDPOINTS = H3_PRIMARY_DISPLAY_ENDPOINTS[:2] + (
    "known_two_phylum_macro_f1",
) + H3_PRIMARY_DISPLAY_ENDPOINTS[2:] + (
    "rare_or_unclassified_reject_recall",
)
NOMINATION_PRIMARY_EVIDENCE = "train_only_shared_five_fold_cv"

CELL_ESTIMATED = "estimated"
CELL_NOT_APPLICABLE = "not_applicable"
CELL_NOT_ESTIMABLE = "not_estimable"

PALETTE = {
    "blue": "#245B8A",
    "blue_light": "#D9E7F2",
    "orange": "#D9842B",
    "orange_light": "#F7E4CB",
    "teal": "#2A8C82",
    "teal_light": "#D8EEE9",
    "grey": "#777777",
    "grey_mid": "#BDBDBD",
    "grey_light": "#E5E5E5",
    "grey_pale": "#F4F4F4",
    "ink": "#222222",
    "warning": "#B34A3C",
    "ne": "#F4DFA7",
}

# Require the complete scientific result bundle, not just the tables drawn.
REQUIRED_RESULT_FILES = (
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
)

REQUIRED_VALIDATION_GATES = frozenset(
    (
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
        "schema4_two_model_per_record_continuity",
        "schema4_canonical_cache_full_recomputation_audit",
        "schema4_legacy_operator_runtime_and_exact_numeric_replay",
        "h3_rare_subgroups_independently_recomputed",
        "amendment_c_predictions_threshold_cv_order_byte_equivalent",
        "test_record_count_zero",
        "released_v0_unchanged_external_confirmation_required",
    )
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve(project_root: Path, value: Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else project_root / path


def _read_tsv(path: Path, *, allow_empty: bool = False) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise RuntimeError(f"TSV has no header: {path}")
        rows = list(reader)
    if not rows and not allow_empty:
        raise RuntimeError(f"TSV has no rows: {path}")
    return rows


def _write_tsv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def _verify_checksums(directory: Path, required: Sequence[str]) -> dict[str, str]:
    manifest = directory / "CHECKSUMS.sha256"
    if not manifest.is_file():
        raise RuntimeError(f"Missing checksum manifest: {manifest}")
    verified: dict[str, str] = {}
    for line_number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split(maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError(f"Malformed checksum row {manifest}:{line_number}")
        expected, relative = parts[0].lower(), parts[1].strip().lstrip("*")
        rel = Path(relative)
        if (
            len(expected) != 64
            or any(char not in "0123456789abcdef" for char in expected)
            or rel.is_absolute()
            or ".." in rel.parts
            or relative in verified
        ):
            raise RuntimeError(f"Unsafe checksum target: {relative}")
        target = directory / rel
        if not target.is_file() or _sha256(target) != expected:
            raise RuntimeError(f"Missing or mismatched checksum target: {target}")
        verified[relative] = expected
    missing = sorted(set(required) - set(verified))
    if missing:
        raise RuntimeError(f"Required result files are not checksum-bound: {missing}")
    return verified


def _require_fields(rows: list[dict[str, str]], fields: set[str], label: str) -> None:
    if not rows:
        raise RuntimeError(f"{label} is empty")
    missing = fields - set(rows[0])
    if missing:
        raise RuntimeError(f"{label} is missing fields: {sorted(missing)}")


def _unique_index(
    rows: Iterable[dict[str, str]], fields: tuple[str, ...], label: str
) -> dict[tuple[str, ...], dict[str, str]]:
    output: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        key = tuple(row[field] for field in fields)
        if key in output:
            raise RuntimeError(f"Duplicate {label} key: {key}")
        output[key] = row
    return output


def _as_int(value: Any, label: str) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid integer {label}: {value!r}") from exc
    if not math.isfinite(number) or not number.is_integer() or number < 0:
        raise RuntimeError(f"Invalid nonnegative integer {label}: {value!r}")
    return int(number)


def _optional_int(value: Any, label: str) -> Optional[int]:
    if value is None or str(value).strip().lower() in {"", "na", "n/a", "ne", "nan"}:
        return None
    return _as_int(value, label)


def _optional_float(value: Any, label: str = "value") -> Optional[float]:
    if value is None or str(value).strip().lower() in {"", "na", "n/a", "ne", "nan"}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid numeric {label}: {value!r}") from exc
    if not math.isfinite(number):
        raise RuntimeError(f"Non-finite numeric {label}: {value!r}")
    return number


def _as_flag(value: Any, label: str) -> int:
    text = str(value).strip().lower()
    if text in {"1", "true", "yes"}:
        return 1
    if text in {"0", "false", "no", ""}:
        return 0
    raise RuntimeError(f"Invalid Boolean flag {label}: {value!r}")


def _classify_cell(applicable: bool, value: Optional[float]) -> str:
    if not applicable:
        return CELL_NOT_APPLICABLE
    if value is None:
        return CELL_NOT_ESTIMABLE
    return CELL_ESTIMATED


def _format_rate(value: Optional[float]) -> str:
    return "NE" if value is None else f"{value:.3f}"


def _validate_rate(value: Optional[float], low: Optional[float], high: Optional[float], label: str) -> None:
    if value is None:
        if low is not None or high is not None:
            raise RuntimeError(f"Half-populated not-estimable interval: {label}")
        return
    if not 0.0 <= value <= 1.0:
        raise RuntimeError(f"Out-of-range rate: {label}")
    if (low is None) != (high is None):
        raise RuntimeError(f"Half-empty interval: {label}")
    if low is not None and not (0.0 <= low <= value <= high <= 1.0):
        raise RuntimeError(f"Invalid confidence interval: {label}")


def _candidate_label(candidate_id: str) -> str:
    if candidate_id not in CANDIDATE_ORDER:
        raise RuntimeError(f"Unexpected mixed candidate: {candidate_id}")
    h12, h3 = candidate_id.removeprefix("h12_").split("__h3_", 1)
    short = {
        "esm2_650m": "650M",
        "esm2_3b": "3B",
        "esmc_300m": "C-300M",
        "esmc_600m": "C-600M",
        "esmc_6b": "C-6B",
    }
    return f"{short[h12]} → {short[h3]}"


def _validate_zero_test(summary: Mapping[str, Any], materialization: list[dict[str, str]]) -> None:
    for field in (
        "test_vectors_selected_for_inference",
        "test_predictions_or_metrics_computed",
        "test_records_scored",
        "test_records",
    ):
        if field in summary and _as_int(summary[field], field) != 0:
            raise RuntimeError(f"Refusing result with nonzero {field}")
    for index, row in enumerate(materialization):
        if _as_int(row.get("test_records_embedded", "0"), f"materialization[{index}] Test") != 0:
            raise RuntimeError("Materialization includes a Test record")
        if _as_int(
            row.get("prediction_or_metric_records_created", "0"),
            f"materialization[{index}] predictions",
        ) != 0:
            raise RuntimeError("Embedding materialization created predictions or metrics")


def _load_and_validate(
    config_path: Path,
    result_dir_override: Optional[Path] = None,
    schema4_result_dir_override: Optional[Path] = None,
    validation_path_override: Optional[Path] = None,
) -> dict[str, Any]:
    import yaml

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if (
        config.get("analysis_id") != ANALYSIS_ID
        or config.get("schema_version") != 5
        or config.get("model_state") != "frozen"
        or config.get("selection_feedback_permitted") is not False
        or config.get("schema5_robustness_reranking_permitted") is not False
        or config.get("nomination_primary_evidence") != NOMINATION_PRIMARY_EVIDENCE
        or config.get("test_policy") != "no_test_vector_selection_or_performance_scoring"
        or config.get("protocol_amendment") != PROTOCOL_AMENDMENT
        or config.get("schema4_prediction_cache_policy")
        != "checksum_bound_schema4_serialized_rows_after_legacy_operator_exact_numeric_replay"
        or config.get("legacy_schema4_numerical_operator", {}).get("operator_id")
        != "schema4_job_4968695_python3117_blas_threads4"
        or config.get("legacy_schema4_numerical_operator", {}).get(
            "exact_numeric_string_replay_required"
        )
        is not True
        or tuple(config.get("models", ())) != (
            "esm2_650m",
            "esm2_3b",
            "esmc_300m",
            "esmc_600m",
            "esmc_6b",
            "prott5_xl",
            "prostt5",
            "esm3_open_1_4b",
        )
    ):
        raise RuntimeError("Schema-5 plotting config contract mismatch")
    config_candidates = tuple(row["candidate_id"] for row in config["primary_mixed_candidates"])
    if config_candidates != CANDIDATE_ORDER:
        raise RuntimeError("Schema-5 candidate order changed")

    config_path = config_path.resolve()
    project_root = config_path.parents[1]
    config_sha256 = _sha256(config_path)
    protocol_path = _resolve(project_root, config["protocol"])
    protocol_sha256 = _sha256(protocol_path)
    result_dir = (
        result_dir_override.resolve()
        if result_dir_override is not None
        else _resolve(project_root, config["result_dir"])
    )
    verified = _verify_checksums(result_dir, REQUIRED_RESULT_FILES)
    summary = json.loads((result_dir / "summary.json").read_text(encoding="utf-8"))
    if (
        summary.get("analysis_id") != ANALYSIS_ID
        or int(summary.get("schema_version", -1)) != 5
        or summary.get("status") != "complete_eight_model_nine_candidate_four_source"
        or summary.get("nomination_primary_evidence") != NOMINATION_PRIMARY_EVIDENCE
        or summary.get("robustness_role_in_nomination")
        != "source_specific_warning_not_reranking"
    ):
        raise RuntimeError("Result summary is not a completed schema-5 result")
    lineage = summary.get("lineage_sha256", {})
    if (
        lineage.get("config") != config_sha256
        or lineage.get("protocol") != protocol_sha256
        or lineage.get("legacy_numerical_operator_runtime")
        != verified["legacy_numerical_operator_runtime.json"]
    ):
        raise RuntimeError("Schema-5 result is not bound to the current config/protocol")

    schema4_result_dir = (
        schema4_result_dir_override.resolve()
        if schema4_result_dir_override is not None
        else _resolve(project_root, config["schema4_result_dir"])
    )
    schema4_verified = _verify_checksums(schema4_result_dir, ("coverage_summary.tsv",))
    checksum_manifest = schema4_result_dir / "CHECKSUMS.sha256"
    if _sha256(checksum_manifest) != config["schema4_result_checksums_sha256"]:
        raise RuntimeError("Schema-4 result continuity manifest changed")
    if (
        schema4_result_dir_override is None
        and checksum_manifest != _resolve(project_root, config["schema4_result_checksums"])
    ):
        raise RuntimeError("Schema-4 result continuity path changed")

    validation_path = (
        validation_path_override.resolve()
        if validation_path_override is not None
        else result_dir.with_name("validation.json")
    )
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation_inputs = validation.get("input_sha256", {})
    validation_gates = validation.get("gates", {})
    if (
        validation.get("schema_version") != 5
        or validation.get("analysis_id") != ANALYSIS_ID
        or validation.get("status") != "PASS"
        or validation.get("validated_result_status") != summary["status"]
        or validation.get("counts", {}).get("test_records") != 0
        or set(validation_gates) != set(REQUIRED_VALIDATION_GATES)
        or any(validation_gates[gate] != "PASS" for gate in REQUIRED_VALIDATION_GATES)
        or validation_inputs.get("config") != config_sha256
        or validation_inputs.get("result_checksums")
        != _sha256(result_dir / "CHECKSUMS.sha256")
        or validation_inputs.get("schema4_result_checksums") != _sha256(checksum_manifest)
        or validation_inputs.get("schema4_validation")
        != config["schema4_validation_sha256"]
        or validation_inputs.get("legacy_numerical_operator_runtime")
        != verified["legacy_numerical_operator_runtime.json"]
    ):
        raise RuntimeError(
            "Independent schema-5 validation is not exact PASS/Test=0 for these inputs"
        )

    coverage = _read_tsv(schema4_result_dir / "coverage_summary.tsv")
    _require_fields(
        coverage,
        {
            "source_dataset",
            "n_candidate_members",
            "n_legal_members",
            "n_legal_clusters",
            "n_excluded_members",
        },
        "schema4 coverage_summary.tsv",
    )
    coverage_index = _unique_index(coverage, ("source_dataset",), "coverage")
    if {key[0] for key in coverage_index} != set(SOURCE_ORDER):
        raise RuntimeError("Coverage does not contain exactly four sources")

    materialization = _read_tsv(result_dir / "materialization_summary.tsv")
    _require_fields(
        materialization,
        {
            "model_id",
            "shard_id",
            "status",
            "records",
            "embedded_records",
            "test_records_embedded",
            "prediction_or_metric_records_created",
        },
        "materialization_summary.tsv",
    )
    materialization_index = _unique_index(
        materialization, ("model_id", "shard_id"), "materialization"
    )
    expected_materialization = {
        (model, shard)
        for model in MODEL_ORDER
        for shard in ("viral_family", "graph_family", "hardnegative_matched")
    }
    if set(materialization_index) != expected_materialization:
        raise RuntimeError("Materialization table is not an exact 8-model x 3-shard grid")
    expected_records = {"viral_family": 13074, "graph_family": 3391, "hardnegative_matched": 3478}
    for (model, shard), row in materialization_index.items():
        records = _as_int(row["records"], f"{model}/{shard} records")
        embedded = _as_int(row["embedded_records"], f"{model}/{shard} embedded")
        if records != expected_records[shard] or embedded != records or row["status"] != "complete":
            raise RuntimeError(f"Incomplete materialization evidence: {model}/{shard}")
    _validate_zero_test(summary, materialization)

    path_rows = _read_tsv(result_dir / "source_path_summary.tsv")
    _require_fields(
        path_rows,
        {
            "system_id",
            "system_type",
            "source_dataset",
            "path_id",
            "member_value",
            "member_ci_low",
            "member_ci_high",
            "n_member_records",
            "n_source_clusters",
            "n_dependence_blocks",
        },
        "source_path_summary.tsv",
    )
    path_index = _unique_index(path_rows, ("system_id", "source_dataset"), "source path")
    expected_systems = set(MODEL_ORDER) | set(CANDIDATE_ORDER)
    expected_path_keys = {(system, source) for system in expected_systems for source in SOURCE_ORDER}
    if set(path_index) != expected_path_keys:
        raise RuntimeError("Source-path table is not the exact 17-system x four-source grid")
    for key, row in path_index.items():
        if row["path_id"] != PATH_ID:
            raise RuntimeError(f"Unexpected path endpoint: {key}")
        value = _optional_float(row["member_value"], f"{key} value")
        low = _optional_float(row["member_ci_low"], f"{key} low")
        high = _optional_float(row["member_ci_high"], f"{key} high")
        _validate_rate(value, low, high, "/".join(key))

    strict_rows_all = _read_tsv(result_dir / "strict_cluster_summary.tsv")
    _require_fields(
        strict_rows_all,
        {
            "system_id",
            "source_dataset",
            "endpoint_id",
            "head_or_path",
            "n_clusters",
            "clusters_all_members_correct",
            "proportion_clusters_all_members_correct",
        },
        "strict_cluster_summary.tsv",
    )
    strict_rows = [
        row
        for row in strict_rows_all
        if row["endpoint_id"] == PATH_ID and row["head_or_path"] == "path"
    ]
    strict_index = _unique_index(strict_rows, ("system_id", "source_dataset"), "strict path")
    if set(strict_index) != expected_path_keys:
        raise RuntimeError("Strict-cluster table is not the exact path grid")
    for key, row in strict_index.items():
        total = _as_int(row["n_clusters"], f"{key} clusters")
        correct = _as_int(row["clusters_all_members_correct"], f"{key} correct clusters")
        proportion = _optional_float(row["proportion_clusters_all_members_correct"], f"{key} strict")
        if total <= 0 or correct > total or proportion is None or abs(proportion - correct / total) > 1e-6:
            raise RuntimeError(f"Invalid strict-cluster result: {key}")
        if total != _as_int(path_index[key]["n_source_clusters"], f"{key} path clusters"):
            raise RuntimeError(f"Strict/path cluster count mismatch: {key}")

    cv_rows = _read_tsv(result_dir / "train_cv_candidate_summary.tsv")
    _require_fields(
        cv_rows,
        {
            "candidate_id",
            "head1_model",
            "head2_model",
            "head3_model",
            "mean_train_cv_score",
            "train_cv_score_se",
            "within_one_paired_se",
            "primary_evidence",
        },
        "train_cv_candidate_summary.tsv",
    )
    cv_index = _unique_index(cv_rows, ("candidate_id",), "Train-CV candidate")
    if tuple(row["candidate_id"] for row in cv_rows) != CANDIDATE_ORDER:
        raise RuntimeError("Train-CV candidate table order changed")
    for candidate, row in cv_index.items():
        score = _optional_float(row["mean_train_cv_score"], f"{candidate} S")
        se = _optional_float(row["train_cv_score_se"], f"{candidate} SE")
        if score is None or se is None or not 0 <= score <= 1 or se < 0:
            raise RuntimeError(f"Invalid Train-CV score: {candidate}")
        if row["head1_model"] != row["head2_model"] or row["primary_evidence"] != NOMINATION_PRIMARY_EVIDENCE:
            raise RuntimeError(f"Candidate architecture/evidence changed: {candidate}")
        _as_flag(row["within_one_paired_se"], f"{candidate} one-SE")

    pareto_rows = _read_tsv(result_dir / "accuracy_cost_pareto.tsv")
    _require_fields(
        pareto_rows,
        {
            "candidate_id",
            "mean_train_cv_score",
            "always_on_gpu_seconds_per_sequence",
            "conditional_h3_gpu_seconds_per_sequence",
            "worst_case_gpu_seconds_per_sequence",
            "peak_gpu_memory_bytes",
            "within_one_paired_se",
            "one_se_cost_accuracy_pareto",
            "robustness_used_for_pareto_or_ordering",
        },
        "accuracy_cost_pareto.tsv",
    )
    pareto_index = _unique_index(pareto_rows, ("candidate_id",), "Pareto candidate")
    if set(key[0] for key in pareto_index) != set(CANDIDATE_ORDER):
        raise RuntimeError("Pareto table candidate set changed")
    for candidate, row in pareto_index.items():
        always = _optional_float(row["always_on_gpu_seconds_per_sequence"], f"{candidate} always")
        conditional = _optional_float(row["conditional_h3_gpu_seconds_per_sequence"], f"{candidate} conditional")
        worst = _optional_float(row["worst_case_gpu_seconds_per_sequence"], f"{candidate} worst")
        if (
            always is None
            or conditional is None
            or worst is None
            or always <= 0
            or conditional < 0
            or abs((always + conditional) - worst) > 1e-9
            or _as_flag(row["robustness_used_for_pareto_or_ordering"], candidate) != 0
        ):
            raise RuntimeError(f"Invalid cost/Pareto contract: {candidate}")

    nomination_rows = _read_tsv(result_dir / "candidate_nomination.tsv")
    _require_fields(
        nomination_rows,
        {
            "candidate_id",
            "nomination_status",
            "robustness_used_for_candidate_ordering",
            "released_v0_change_permitted",
            "prospective_external_confirmation_required",
        },
        "candidate_nomination.tsv",
    )
    if len(nomination_rows) != 1:
        raise RuntimeError("Exactly one Train-CV nomination row is required")
    nomination = nomination_rows[0]
    nominee_id = nomination["candidate_id"]
    if (
        nominee_id not in CANDIDATE_ORDER
        or not nomination["nomination_status"].startswith("recommended_for_external_confirmation")
        or _as_flag(nomination["robustness_used_for_candidate_ordering"], "nominee robustness") != 0
        or _as_flag(nomination["released_v0_change_permitted"], "released V0") != 0
        or _as_flag(nomination["prospective_external_confirmation_required"], "confirmation") != 1
        or _as_flag(cv_index[(nominee_id,)]["within_one_paired_se"], "nominee one-SE") != 1
    ):
        raise RuntimeError("Nomination is not Train-CV-only/external-confirmation bounded")

    pairwise_rows = _read_tsv(result_dir / "pairwise_source_path_delta.tsv")
    _require_fields(
        pairwise_rows,
        {
            "candidate_id",
            "reference_system_id",
            "source_dataset",
            "delta_candidate_minus_reference",
            "delta_ci_low",
            "delta_ci_high",
            "holm_adjusted_p",
            "positive_control",
            "diagnostic_status",
        },
        "pairwise_source_path_delta.tsv",
    )
    pairwise_index = _unique_index(pairwise_rows, ("candidate_id", "source_dataset"), "pairwise")
    expected_pairwise = {(candidate, source) for candidate in CANDIDATE_ORDER for source in SOURCE_ORDER}
    if set(pairwise_index) != expected_pairwise:
        raise RuntimeError("Pairwise table is not nine candidates x four sources")
    positive_control_id = "h12_esmc_6b__h3_esmc_6b"
    for key, row in pairwise_index.items():
        candidate, source = key
        if row["reference_system_id"] != REFERENCE_SYSTEM:
            raise RuntimeError(f"Pairwise reference changed: {key}")
        is_control = _as_flag(row["positive_control"], f"{key} positive control")
        if is_control != int(candidate == positive_control_id):
            raise RuntimeError(f"Positive-control identity mismatch: {key}")
        adjusted = _optional_float(row["holm_adjusted_p"], f"{key} Holm p")
        if adjusted is None or not 0 <= adjusted <= 1:
            raise RuntimeError(f"Invalid Holm-adjusted p: {key}")

    contextual_rows = _read_tsv(result_dir / "contextual_source_path_delta.tsv")
    _require_fields(
        contextual_rows,
        {
            "candidate_id",
            "contextual_reference_system_id",
            "source_dataset",
            "delta_candidate_minus_reference",
            "delta_ci_low",
            "delta_ci_high",
            "comparison_role",
        },
        "contextual_source_path_delta.tsv",
    )
    contextual_index = _unique_index(
        contextual_rows, ("candidate_id", "source_dataset"), "contextual 650M delta"
    )
    contextual_sources = SOURCE_ORDER[1:]
    expected_contextual = {
        (candidate, source) for candidate in CANDIDATE_ORDER for source in contextual_sources
    }
    if set(contextual_index) != expected_contextual:
        raise RuntimeError("Contextual table is not nine candidates x three sources")
    for key, row in contextual_index.items():
        if (
            row["contextual_reference_system_id"] != CONTEXTUAL_REFERENCE_SYSTEM
            or row["comparison_role"]
            != "descriptive_context_only_not_reranking_not_holm_family"
        ):
            raise RuntimeError(f"Contextual comparison escaped its descriptive boundary: {key}")
        for field in ("delta_candidate_minus_reference", "delta_ci_low", "delta_ci_high"):
            value = _optional_float(row[field], f"{key} {field}")
            if value is None or not -1 <= value <= 1:
                raise RuntimeError(f"Invalid contextual delta: {key}/{field}")

    h3_rows = _read_tsv(result_dir / "h3_class_summary.tsv")
    _require_fields(
        h3_rows,
        {
            "system_id",
            "head3_model",
            "endpoint_id",
            "diagnostic_group",
            "truth_label",
            "metric",
            "endpoint_role",
            "member_value",
            "member_ci_low",
            "member_ci_high",
            "n_truth_records",
            "n_evaluation_records",
            "n_member_records",
            "n_source_clusters",
            "n_dependence_blocks",
            "raw_member_reject_k",
            "raw_member_reject_n",
            "raw_representative_reject_k",
            "raw_representative_reject_n",
            "interpretation",
        },
        "h3_class_summary.tsv",
    )
    h3_index = _unique_index(h3_rows, ("system_id", "endpoint_id"), "H3 endpoint")
    expected_h3_keys = {
        (system_id, endpoint_id)
        for system_id in expected_systems
        for endpoint_id in H3_ALL_ENDPOINTS
    }
    if set(h3_index) != expected_h3_keys:
        raise RuntimeError("H3 table is not the exact 17-system x six-endpoint grid")

    h3_contract = {
        "Nucleocytoviricota_f1": (
            "known_phylum",
            "Nucleocytoviricota",
            "f1",
            "primary_known_class",
        ),
        "Preplasmiviricota_f1": (
            "known_phylum",
            "Preplasmiviricota",
            "f1",
            "primary_known_class",
        ),
        "known_two_phylum_macro_f1": (
            "known_phylum",
            "Nucleocytoviricota|Preplasmiviricota",
            "macro_f1",
            "primary_known_macro",
        ),
        "Produgelaviricota_reject_recall": (
            "rare_formal_phylum_rejection",
            "Produgelaviricota",
            "reject_recall",
            "descriptive_subgroup",
        ),
        "literature_unclassified_reject_recall": (
            "literature_unclassified_rejection",
            "literature-unclassified",
            "reject_recall",
            "descriptive_single_record_subgroup",
        ),
        "rare_or_unclassified_reject_recall": (
            "small_prespecified_rejection",
            "unknown/other",
            "reject_recall",
            "secondary_pooled_diagnostic",
        ),
    }
    reject_support = {
        "Produgelaviricota_reject_recall": (
            PRODUGELAVIRICOTA_RELATIONS_N,
            PRODUGELAVIRICOTA_PARENTS_N,
            PRODUGELAVIRICOTA_BLOCKS_N,
        ),
        "literature_unclassified_reject_recall": (
            LITERATURE_UNCLASSIFIED_RELATIONS_N,
            LITERATURE_UNCLASSIFIED_PARENTS_N,
            LITERATURE_UNCLASSIFIED_BLOCKS_N,
        ),
        "rare_or_unclassified_reject_recall": (
            MATCHED_RARE_RELATIONS_N,
            MATCHED_RARE_PARENTS_N,
            MATCHED_RARE_BLOCKS_N,
        ),
    }
    for key, row in h3_index.items():
        system_id, endpoint_id = key
        expected_contract = h3_contract[endpoint_id]
        observed_contract = tuple(
            row[field]
            for field in ("diagnostic_group", "truth_label", "metric", "endpoint_role")
        )
        if observed_contract != expected_contract:
            raise RuntimeError(f"H3 endpoint contract changed: {key}")
        value = _optional_float(row["member_value"], f"{key} member value")
        low = _optional_float(row["member_ci_low"], f"{key} member CI low")
        high = _optional_float(row["member_ci_high"], f"{key} member CI high")
        _validate_rate(value, low, high, f"{system_id}/{endpoint_id}")
        raw_values = tuple(
            _optional_int(row[field], f"{key} {field}")
            for field in (
                "raw_member_reject_k",
                "raw_member_reject_n",
                "raw_representative_reject_k",
                "raw_representative_reject_n",
            )
        )
        if endpoint_id not in reject_support:
            if any(raw is not None for raw in raw_values):
                raise RuntimeError(f"Known-phylum H3 row contains reject k/n: {key}")
            continue
        relations, parents, blocks = reject_support[endpoint_id]
        member_k, member_n, representative_k, representative_n = raw_values
        interpretation_guard = (
            "no_generalization"
            if endpoint_id == "literature_unclassified_reject_recall"
            else "not_general_unknown_detection"
        )
        if (
            _as_int(row["n_truth_records"], f"{key} truth records") != relations
            or _as_int(row["n_evaluation_records"], f"{key} evaluation records")
            != relations
            or _as_int(row["n_member_records"], f"{key} member records") != relations
            or _as_int(row["n_source_clusters"], f"{key} parents") != parents
            or _as_int(row["n_dependence_blocks"], f"{key} blocks") != blocks
            or member_n != relations
            or representative_n != parents
            or member_k is None
            or representative_k is None
            or member_k > member_n
            or representative_k > representative_n
            or interpretation_guard not in row["interpretation"]
        ):
            raise RuntimeError(f"H3 rare subgroup support/raw k/n changed: {key}")
        if endpoint_id == "literature_unclassified_reject_recall" and (
            low is not None or high is not None
        ):
            raise RuntimeError("Single-record literature subgroup must be point-only")

    comparison_path = _resolve(project_root, config["comparison_summary"])
    if (
        lineage.get("comparison_summary") != _sha256(comparison_path)
        or lineage.get("schema4_result_checksums") != _sha256(checksum_manifest)
        or lineage.get("schema4_validation") != config["schema4_validation_sha256"]
    ):
        raise RuntimeError("Figure inputs differ from scorer-recorded lineage")
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    comparison_by_model = {row["model_id"]: row for row in comparison.get("models", [])}
    nominee_h3_model = cv_index[(nominee_id,)]["head3_model"]
    if nominee_h3_model not in comparison_by_model:
        raise RuntimeError("Nominee H3 model is absent from frozen benchmark comparison")
    benchmark_h3 = comparison_by_model[nominee_h3_model]
    if _as_int(benchmark_h3["val_head3_unknown_diagnostic_n"], "benchmark H3 rare n") != REPRESENTATIVE_RARE_N:
        raise RuntimeError("Representative benchmark H3 rare denominator changed")
    benchmark_unknown = _optional_float(
        benchmark_h3["val_head3_unknown_recall"], "benchmark rare recall"
    )
    if benchmark_unknown is None or not 0 <= benchmark_unknown <= 1:
        raise RuntimeError("Invalid representative benchmark rare recall")

    model_cost_rows = _read_tsv(result_dir / "model_cost_registry.tsv")
    _require_fields(
        model_cost_rows,
        {"model_id", "gpu_seconds_per_sequence", "peak_gpu_memory_bytes", "timing_source"},
        "model_cost_registry.tsv",
    )
    if {row["model_id"] for row in model_cost_rows} != set(MODEL_ORDER):
        raise RuntimeError("Model cost registry is not the exact eight-model set")

    # Head applicability is audited from the compact summary.  The high-volume
    # predictions remain checksum-verified but are not loaded by the renderer.
    head_rows = _read_tsv(result_dir / "source_head_summary.tsv")
    _require_fields(
        head_rows,
        {"system_id", "source_dataset", "head"},
        "source_head_summary.tsv",
    )
    head_keys = {(row["system_id"], row["source_dataset"], row["head"]) for row in head_rows}
    expected_head_keys = {
        (system, source, head)
        for system in expected_systems
        for source in SOURCE_ORDER
        for head in APPLICABLE_HEADS[source]
    }
    if head_keys != expected_head_keys or len(head_rows) != len(head_keys):
        raise RuntimeError("Head summary contains missing, duplicate, or N/A cascade rows")
    prediction_row_count = _as_int(
        summary.get("record_counts", {}).get("system_predictions", -1),
        "system prediction row count",
    )
    summary_heads = summary.get("applicable_heads", {})
    if (
        prediction_row_count <= 0
        or set(summary_heads) != set(SOURCE_ORDER)
        or any(
            set(summary_heads[source]) != set(APPLICABLE_HEADS[source])
            for source in SOURCE_ORDER
        )
    ):
        raise RuntimeError("Summary head-applicability provenance changed")

    return {
        "config": config,
        "config_path": config_path,
        "project_root": project_root,
        "result_dir": result_dir,
        "verified": verified,
        "summary": summary,
        "protocol_path": protocol_path,
        "validation_path": validation_path,
        "validation": validation,
        "schema4_result_dir": schema4_result_dir,
        "schema4_verified": schema4_verified,
        "coverage": coverage,
        "coverage_index": coverage_index,
        "materialization": materialization,
        "path_rows": path_rows,
        "path_index": path_index,
        "strict_rows": strict_rows,
        "strict_index": strict_index,
        "cv_rows": cv_rows,
        "cv_index": cv_index,
        "pareto_rows": pareto_rows,
        "pareto_index": pareto_index,
        "nomination": nomination,
        "nominee_id": nominee_id,
        "pairwise_rows": pairwise_rows,
        "pairwise_index": pairwise_index,
        "contextual_rows": contextual_rows,
        "contextual_index": contextual_index,
        "h3_rows": h3_rows,
        "h3_index": h3_index,
        "comparison_path": comparison_path,
        "benchmark_h3": benchmark_h3,
        "benchmark_unknown": benchmark_unknown,
        "model_cost_rows": model_cost_rows,
        "prediction_row_count": prediction_row_count,
    }


def _apply_style() -> None:
    _load_matplotlib()
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "DejaVu Sans", "Liberation Sans"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 6.5,
            "axes.titlesize": 7.2,
            "axes.titleweight": "bold",
            "axes.labelsize": 6.5,
            "axes.linewidth": 0.65,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "legend.fontsize": 6.5,
            "legend.frameon": False,
            "lines.linewidth": 0.9,
        }
    )


def _add_panel_label(ax: Any, label: str, *, x: float = -0.055, y: float = 1.03) -> None:
    ax.text(
        x,
        y,
        label,
        transform=ax.transAxes,
        fontsize=8.5,
        fontweight="bold",
        ha="left",
        va="bottom",
        color=PALETTE["ink"],
    )


def _rate_cell_rows(
    bundle: Mapping[str, Any], systems: Sequence[str]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for system in systems:
        for source in SOURCE_ORDER:
            path = bundle["path_index"][(system, source)]
            strict = bundle["strict_index"][(system, source)]
            value = _optional_float(path["member_value"])
            low = _optional_float(path["member_ci_low"])
            high = _optional_float(path["member_ci_high"])
            strict_value = _optional_float(strict["proportion_clusters_all_members_correct"])
            output.append(
                {
                    "system_id": system,
                    "source_dataset": source,
                    "endpoint_id": PATH_ID,
                    "value": "" if value is None else value,
                    "ci_low": "" if low is None else low,
                    "ci_high": "" if high is None else high,
                    "cell_state": _classify_cell(True, value),
                    "strict_cluster_value": "" if strict_value is None else strict_value,
                    "strict_clusters_correct": strict["clusters_all_members_correct"],
                    "strict_clusters_total": strict["n_clusters"],
                    "n_member_relations": path["n_member_records"],
                    "n_source_clusters": path["n_source_clusters"],
                    "n_dependence_blocks": path["n_dependence_blocks"],
                    "weighting": path.get("weighting", ""),
                }
            )
    return output


def _panel_a_rows(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for source in SOURCE_ORDER:
        coverage = bundle["coverage_index"][(source,)]
        reference_path = bundle["path_index"][(REFERENCE_SYSTEM, source)]
        row: dict[str, Any] = {
            "source_dataset": source,
            "source_label": SOURCE_LABEL[source],
            "n_legal_members": coverage["n_legal_members"],
            "n_legal_clusters": coverage["n_legal_clusters"],
            "n_dependence_blocks": reference_path["n_dependence_blocks"],
            "test_records": 0,
        }
        for head in HEAD_ORDER:
            row[f"{head}_state"] = _classify_cell(
                head in APPLICABLE_HEADS[source],
                1.0 if head in APPLICABLE_HEADS[source] else None,
            )
        output.append(row)
    return output


def _draw_state_box(
    ax: Any,
    x: float,
    y: float,
    state: str,
    *,
    width: float = 0.78,
    height: float = 0.70,
) -> None:
    if state == CELL_NOT_APPLICABLE:
        face, hatch, label, color = PALETTE["grey_light"], "///", "N/A", PALETTE["grey"]
    elif state == CELL_NOT_ESTIMABLE:
        face, hatch, label, color = PALETTE["ne"], "...", "NE", "#765900"
    else:
        face, hatch, label, color = PALETTE["blue_light"], "", "applies", PALETTE["blue"]
    ax.add_patch(
        mpl.patches.Rectangle(
            (x - width / 2, y - height / 2),
            width,
            height,
            facecolor=face,
            edgecolor="white",
            hatch=hatch,
            linewidth=0.6,
        )
    )
    ax.text(x, y, label, ha="center", va="center", color=color, fontsize=6.5)


def _draw_panel_a(ax: Any, bundle: Mapping[str, Any], rows: list[dict[str, Any]]) -> None:
    ax.set_xlim(-0.45, 6.65)
    ax.set_ylim(-0.55, 4.15)
    ax.axis("off")
    headers = ((0.0, "Source"), (2.55, "clusters / members / blocks"))
    for x, label in headers:
        ax.text(x, 3.78, label, fontweight="bold", ha="left", va="center")
    for col, head in enumerate(HEAD_ORDER):
        ax.text(4.60 + col * 0.85, 3.78, HEAD_LABEL[head], fontweight="bold", ha="center")
    for index, row in enumerate(rows):
        y = 2.95 - index * 0.82
        ax.add_patch(
            mpl.patches.Rectangle(
                (-0.08, y - 0.36),
                6.62,
                0.72,
                facecolor=PALETTE["grey_pale"] if index % 2 else "white",
                edgecolor="none",
            )
        )
        ax.text(0.0, y, row["source_label"], ha="left", va="center")
        counts = (
            f"{int(row['n_legal_clusters']):,} / "
            f"{int(row['n_legal_members']):,} / {int(row['n_dependence_blocks']):,}"
        )
        ax.text(2.55, y, counts, ha="left", va="center", family="monospace")
        for col, head in enumerate(HEAD_ORDER):
            _draw_state_box(ax, 4.60 + col * 0.85, y, str(row[f"{head}_state"]))
    # The leakage boundary remains explicit without repeating a Test column.
    ax.text(
        6.52,
        -0.34,
        "Test accessed = 0",
        ha="right",
        va="center",
        color=PALETTE["teal"],
        fontweight="bold",
        bbox={
            "boxstyle": "round,pad=0.22",
            "facecolor": PALETTE["teal_light"],
            "edgecolor": "none",
        },
    )
    ax.set_title("Same four-source evidence and applicable cascade heads", loc="left", pad=4)
    _add_panel_label(ax, "a", x=-0.035, y=1.0)


def _matrix_cmap() -> Any:
    return mpl.colors.LinearSegmentedColormap.from_list(
        "schema5_blue", ("#F7FAFC", "#BBD4E7", PALETTE["blue"])
    )


def _draw_rate_matrix(
    ax: Any,
    rows: list[dict[str, Any]],
    systems: Sequence[str],
    labels: Sequence[str],
    *,
    title: str,
    show_ylabels: bool = True,
    nominee_id: Optional[str] = None,
) -> None:
    lookup = {(row["system_id"], row["source_dataset"]): row for row in rows}
    matrix = np.full((len(systems), len(SOURCE_ORDER)), np.nan)
    for i, system in enumerate(systems):
        for j, source in enumerate(SOURCE_ORDER):
            row = lookup[(system, source)]
            if row["cell_state"] == CELL_ESTIMATED:
                matrix[i, j] = float(row["value"])
    ax.imshow(matrix, cmap=_matrix_cmap(), norm=mpl.colors.Normalize(0, 1), aspect="auto")
    for i, system in enumerate(systems):
        for j, source in enumerate(SOURCE_ORDER):
            row = lookup[(system, source)]
            state = row["cell_state"]
            if state != CELL_ESTIMATED:
                _draw_state_box(ax, j, i, str(state), width=0.94, height=0.94)
                continue
            value = float(row["value"])
            low = _optional_float(row["ci_low"])
            high = _optional_float(row["ci_high"])
            color = "white" if value >= 0.66 else PALETTE["ink"]
            interval = "" if low is None else f"\n[{low:.2f}, {high:.2f}]"
            ax.text(j, i - 0.06, f"{value:.3f}{interval}", ha="center", va="center", color=color)
            strict = _optional_float(row["strict_cluster_value"])
            if strict is not None:
                left = j - 0.40
                ax.plot(
                    [left, left + 0.80 * strict],
                    [i + 0.37, i + 0.37],
                    color=PALETTE["orange"],
                    linewidth=2.0,
                    solid_capstyle="butt",
                )
                ax.plot(
                    [left + 0.80 * strict, j + 0.40],
                    [i + 0.37, i + 0.37],
                    color=(1, 1, 1, 0.65),
                    linewidth=2.0,
                    solid_capstyle="butt",
                )
    if nominee_id is not None:
        nominee_row = list(systems).index(nominee_id)
        ax.add_patch(
            mpl.patches.Rectangle(
                (-0.49, nominee_row - 0.48),
                len(SOURCE_ORDER) - 0.02,
                0.96,
                fill=False,
                edgecolor=PALETTE["orange"],
                linewidth=1.6,
            )
        )
    ax.set_xticks(range(len(SOURCE_ORDER)))
    ax.set_xticklabels([SOURCE_LABEL[source] for source in SOURCE_ORDER])
    ax.set_yticks(range(len(systems)))
    ax.set_yticklabels(labels if show_ylabels else [""] * len(systems))
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(title, loc="left", pad=4)


def _draw_panel_b(ax: Any, rows: list[dict[str, Any]]) -> None:
    _draw_rate_matrix(
        ax,
        rows,
        MODEL_ORDER,
        [MODEL_LABEL[model] for model in MODEL_ORDER],
        title="Eight frozen homogeneous models: source-specific expected-path accuracy",
    )
    ax.text(
        1.0,
        -0.18,
        "cell: equal-block→cluster→member estimate [95% CI]  ·  orange bar: all-members-correct clusters",
        transform=ax.transAxes,
        ha="right",
        va="top",
        color=PALETTE["grey"],
    )
    _add_panel_label(ax, "b")


def _draw_panel_c_cv(ax: Any, bundle: Mapping[str, Any]) -> None:
    y = np.arange(len(CANDIDATE_ORDER))
    scores = [float(bundle["cv_index"][(candidate,)]["mean_train_cv_score"]) for candidate in CANDIDATE_ORDER]
    errors = [float(bundle["cv_index"][(candidate,)]["train_cv_score_se"]) for candidate in CANDIDATE_ORDER]
    within = [
        _as_flag(bundle["cv_index"][(candidate,)]["within_one_paired_se"], candidate)
        for candidate in CANDIDATE_ORDER
    ]
    for yi, candidate, score, error, in_one_se in zip(
        y, CANDIDATE_ORDER, scores, errors, within, strict=True
    ):
        nominee = candidate == bundle["nominee_id"]
        ax.errorbar(
            score,
            yi,
            xerr=error,
            fmt="o",
            markersize=5.0 if nominee else 4.2,
            markerfacecolor=PALETTE["orange"] if nominee else (
                PALETTE["teal"] if in_one_se else PALETTE["grey_mid"]
            ),
            markeredgecolor=PALETTE["ink"] if nominee else "white",
            markeredgewidth=0.7,
            ecolor=PALETTE["grey"],
            capsize=1.8,
        )
    span = max(scores) - min(scores)
    pad = max(0.0005, span * 0.24)
    ax.set_xlim(min(score - error for score, error in zip(scores, errors)) - pad,
                max(score + error for score, error in zip(scores, errors)) + pad)
    nominee_row = CANDIDATE_ORDER.index(bundle["nominee_id"])
    xmin, xmax = ax.get_xlim()
    ax.add_patch(
        mpl.patches.Rectangle(
            (xmin, nominee_row - 0.46),
            xmax - xmin,
            0.92,
            fill=False,
            edgecolor=PALETTE["orange"],
            linewidth=1.5,
        )
    )
    ax.set_ylim(len(CANDIDATE_ORDER) - 0.5, -0.5)
    ax.set_yticks(y)
    ax.set_yticklabels([_candidate_label(candidate) for candidate in CANDIDATE_ORDER])
    ax.set_xlabel("S ± fold SE")
    ax.grid(axis="x", color=PALETTE["grey_light"], linewidth=0.5)
    ax.set_title("Nine frozen mixed heads: Train-CV nomination", loc="left", pad=4)
    _add_panel_label(ax, "c", x=-0.16)


def _candidate_panel_rows(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    base_rows = _rate_cell_rows(bundle, CANDIDATE_ORDER)
    output: list[dict[str, Any]] = []
    for row in base_rows:
        candidate = str(row["system_id"])
        source = str(row["source_dataset"])
        pairwise = bundle["pairwise_index"][(candidate, source)]
        contextual = bundle["contextual_index"].get((candidate, source))
        cv = bundle["cv_index"][(candidate,)]
        pareto = bundle["pareto_index"][(candidate,)]
        output.append(
            {
                **row,
                "candidate_label": _candidate_label(candidate),
                "mean_train_cv_score": cv["mean_train_cv_score"],
                "train_cv_score_se": cv["train_cv_score_se"],
                "within_one_paired_se": cv["within_one_paired_se"],
                "one_se_cost_accuracy_pareto": pareto["one_se_cost_accuracy_pareto"],
                "train_cv_nominee": int(candidate == bundle["nominee_id"]),
                "holm_diagnostic_status_vs_all_6b": pairwise["diagnostic_status"],
                "holm_adjusted_p_vs_all_6b": pairwise["holm_adjusted_p"],
                "delta_vs_all_6b": pairwise["delta_candidate_minus_reference"],
                "delta_vs_all_650m": "" if contextual is None else contextual["delta_candidate_minus_reference"],
                "delta_vs_all_650m_ci_low": "" if contextual is None else contextual["delta_ci_low"],
                "delta_vs_all_650m_ci_high": "" if contextual is None else contextual["delta_ci_high"],
                "contextual_only_not_reranking": "" if contextual is None else 1,
            }
        )
    return output


def _draw_panel_c_nominee_source(ax: Any, bundle: Mapping[str, Any]) -> None:
    """Show only the Train-CV nominee's four source diagnostics.

    The complete nine-candidate by four-source grid and contextual deltas stay
    in the checksum-bound panel-c Source Data.  Keeping the main panel to the
    preselected nominee prevents auxiliary Validation-family diagnostics from
    visually resembling a second candidate-ranking step.
    """

    nominee = bundle["nominee_id"]
    y_positions = np.arange(len(SOURCE_ORDER))[::-1]
    warnings = sum(
        bundle["pairwise_index"][(nominee, source)]["diagnostic_status"]
        == "source_specific_inferiority_warning"
        for source in SOURCE_ORDER
    )
    for y, source in zip(y_positions, SOURCE_ORDER, strict=True):
        row = bundle["path_index"][(nominee, source)]
        value = float(row["member_value"])
        low = _optional_float(row["member_ci_low"])
        high = _optional_float(row["member_ci_high"])
        xerr = None if low is None else [[value - low], [high - value]]
        ax.errorbar(
            value,
            y,
            xerr=xerr,
            fmt="o",
            color=PALETTE["orange"],
            ecolor=PALETTE["blue"],
            markersize=5.2,
            capsize=2.0,
            zorder=3,
        )
        ax.text(
            1.004,
            y,
            f"{value:.3f}",
            ha="left",
            va="center",
            family="monospace",
            color=PALETTE["ink"],
        )
    ax.axvline(1.0, color=PALETTE["grey_mid"], linewidth=0.6, zorder=0)
    ax.set_xlim(0.895, 1.025)
    ax.set_ylim(-0.6, len(SOURCE_ORDER) - 0.05)
    ax.set_xticks((0.90, 0.95, 1.00))
    ax.set_yticks(y_positions)
    ax.set_yticklabels([SOURCE_LABEL[source] for source in SOURCE_ORDER])
    ax.set_xlabel("Expected-path accuracy [95% CI]")
    ax.grid(axis="x", color=PALETTE["grey_light"], linewidth=0.5)
    ax.set_title("Train-CV nominee 3B → C-6B", loc="left", pad=4)
    ax.text(
        0.99,
        0.04,
        f"{warnings}/4 inferiority warnings vs all-6B",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        color=PALETTE["warning"] if warnings else PALETTE["teal"],
        fontweight="bold",
        bbox={
            "boxstyle": "round,pad=0.20",
            "facecolor": "white",
            "edgecolor": PALETTE["grey_light"],
            "linewidth": 0.5,
        },
    )


def _draw_panel_d_pareto(ax: Any, bundle: Mapping[str, Any]) -> None:
    for index, candidate in enumerate(CANDIDATE_ORDER):
        row = bundle["pareto_index"][(candidate,)]
        x0 = float(row["always_on_gpu_seconds_per_sequence"])
        x1 = float(row["worst_case_gpu_seconds_per_sequence"])
        y = float(row["mean_train_cv_score"])
        frontier = _as_flag(row["one_se_cost_accuracy_pareto"], f"{candidate} Pareto")
        nominee = candidate == bundle["nominee_id"]
        color = PALETTE["orange"] if nominee else (PALETTE["teal"] if frontier else PALETTE["grey_mid"])
        ax.plot([x0, x1], [y, y], color=color, alpha=0.78, linewidth=1.4)
        ax.scatter(
            [x0],
            [y],
            s=32 if nominee else 22,
            color=color,
            edgecolor=PALETTE["ink"] if nominee else "white",
            linewidth=0.7,
            zorder=3,
        )
        ax.scatter([x1], [y], marker=">", s=22, color=color, edgecolor="white", linewidth=0.4)
        if nominee or frontier:
            ax.annotate(
                _candidate_label(candidate),
                (x0, y),
                xytext=(3, 4 if index % 2 == 0 else -8),
                textcoords="offset points",
                color=PALETTE["ink"],
                ha="left",
            )
    ax.set_xscale("log")
    scores = [float(row["mean_train_cv_score"]) for row in bundle["pareto_rows"]]
    span = max(scores) - min(scores)
    pad = max(0.0005, span * 0.18)
    ax.set_ylim(min(scores) - pad, max(scores) + pad)
    ax.set_xlabel("GPU s sequence⁻¹ (log): ● always-on → ▶ worst case")
    ax.set_ylabel("Frozen Train-CV S")
    ax.grid(color=PALETTE["grey_light"], linewidth=0.5)
    ax.set_title("Accuracy–cost Pareto (workstation-specific)", loc="left", pad=4)
    _add_panel_label(ax, "d")


def _panel_h3_rows(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    nominee = bundle["nominee_id"]
    rows: list[dict[str, Any]] = []
    for endpoint, label in (
        ("Nucleocytoviricota_f1", "Nucleocytoviricota F1"),
        ("Preplasmiviricota_f1", "Preplasmiviricota F1"),
        ("Produgelaviricota_reject_recall", "Produgelaviricota reject"),
        (
            "literature_unclassified_reject_recall",
            "Literature-unclassified reject",
        ),
    ):
        source = bundle["h3_index"][(nominee, endpoint)]
        raw_member_k = _optional_int(
            source["raw_member_reject_k"], f"{endpoint} raw member k"
        )
        raw_member_n = _optional_int(
            source["raw_member_reject_n"], f"{endpoint} raw member n"
        )
        raw_representative_k = _optional_int(
            source["raw_representative_reject_k"],
            f"{endpoint} raw representative k",
        )
        raw_representative_n = _optional_int(
            source["raw_representative_reject_n"],
            f"{endpoint} raw representative n",
        )
        rows.append(
            {
                "candidate_id": nominee,
                "head3_model": source["head3_model"],
                "endpoint_id": endpoint,
                "display_label": label,
                "scope": "matched_family_member",
                "value": source["member_value"],
                "ci_low": source["member_ci_low"],
                "ci_high": source["member_ci_high"],
                "n_relations": source["n_truth_records"],
                "n_evaluation_records": source["n_evaluation_records"],
                "n_parents": source.get("n_source_clusters", ""),
                "n_dependence_blocks": source.get("n_dependence_blocks", ""),
                "raw_member_k": "" if raw_member_k is None else raw_member_k,
                "raw_member_n": "" if raw_member_n is None else raw_member_n,
                "raw_representative_k": (
                    "" if raw_representative_k is None else raw_representative_k
                ),
                "raw_representative_n": (
                    "" if raw_representative_n is None else raw_representative_n
                ),
                "endpoint_role": source["endpoint_role"],
                "interpretation": source["interpretation"],
            }
        )
    pooled = bundle["h3_index"][(nominee, "rare_or_unclassified_reject_recall")]
    rows.append(
        {
            "candidate_id": nominee,
            "head3_model": pooled["head3_model"],
            "endpoint_id": "rare_or_unclassified_reject_recall",
            "display_label": "Pooled rare reject (secondary only)",
            "scope": "matched_family_member_secondary",
            "value": pooled["member_value"],
            "ci_low": pooled["member_ci_low"],
            "ci_high": pooled["member_ci_high"],
            "n_relations": pooled["n_truth_records"],
            "n_evaluation_records": pooled["n_evaluation_records"],
            "n_parents": pooled["n_source_clusters"],
            "n_dependence_blocks": pooled["n_dependence_blocks"],
            "raw_member_k": pooled["raw_member_reject_k"],
            "raw_member_n": pooled["raw_member_reject_n"],
            "raw_representative_k": pooled["raw_representative_reject_k"],
            "raw_representative_n": pooled["raw_representative_reject_n"],
            "endpoint_role": pooled["endpoint_role"],
            "interpretation": pooled["interpretation"],
        }
    )
    benchmark_k = int(round(float(bundle["benchmark_unknown"]) * REPRESENTATIVE_RARE_N))
    if abs(benchmark_k / REPRESENTATIVE_RARE_N - float(bundle["benchmark_unknown"])) > 1e-12:
        raise RuntimeError("Representative benchmark unknown recall is not an exact raw k/n")
    rows.append(
        {
            "candidate_id": nominee,
            "head3_model": bundle["cv_index"][(nominee,)]["head3_model"],
            "endpoint_id": "representative_benchmark_rare_unknown_recall",
            "display_label": "Separate representative benchmark (secondary only)",
            "scope": "representative_benchmark_secondary",
            "value": bundle["benchmark_unknown"],
            "ci_low": "",
            "ci_high": "",
            "n_relations": REPRESENTATIVE_RARE_N,
            "n_evaluation_records": REPRESENTATIVE_RARE_N,
            "n_parents": "",
            "n_dependence_blocks": "",
            "raw_member_k": "",
            "raw_member_n": "",
            "raw_representative_k": benchmark_k,
            "raw_representative_n": REPRESENTATIVE_RARE_N,
            "endpoint_role": "secondary_external_benchmark_different_cohort",
            "interpretation": "five_representative_validation_records_separate_from_family_relations",
        }
    )
    return rows


def _draw_panel_e_h3(ax: Any, rows: list[dict[str, Any]]) -> None:
    lookup = {row["endpoint_id"]: row for row in rows}
    y_positions = np.arange(len(H3_PRIMARY_DISPLAY_ENDPOINTS))[::-1]
    labels = {
        "Nucleocytoviricota_f1": "Nuc. F1",
        "Preplasmiviricota_f1": "Prep. F1",
        "Produgelaviricota_reject_recall": "Produ. reject",
        "literature_unclassified_reject_recall": "Lit.-uncl. reject",
    }
    ax.axvspan(1.02, 1.68, color=PALETTE["grey_pale"], zorder=0)
    ax.axvline(1.0, color=PALETTE["grey_mid"], linewidth=0.6, zorder=0)
    for y, endpoint in zip(y_positions, H3_PRIMARY_DISPLAY_ENDPOINTS, strict=True):
        row = lookup[endpoint]
        value = float(row["value"])
        low = _optional_float(row["ci_low"])
        high = _optional_float(row["ci_high"])
        xerr = None if low is None else [[value - low], [high - value]]
        is_reject = endpoint.endswith("_reject_recall")
        ax.errorbar(
            value,
            y,
            xerr=xerr,
            fmt="o",
            color=PALETTE["orange"] if is_reject else PALETTE["blue"],
            markersize=5,
            capsize=2,
            zorder=3,
        )
        ax.text(
            max(0.01, min(value - 0.018, 0.965)),
            y + 0.23,
            f"{value:.3f}",
            ha="right",
            va="center",
            color=PALETTE["ink"],
        )
        raw_k = _optional_int(row["raw_member_k"], f"{endpoint} panel raw k")
        raw_n = _optional_int(row["raw_member_n"], f"{endpoint} panel raw n")
        if raw_k is None:
            support = (
                f"truth/eval {int(row['n_relations']):,}/"
                f"{int(row['n_evaluation_records']):,}"
            )
        else:
            support = (
                f"raw {raw_k}/{raw_n} · P/B "
                f"{int(row['n_parents'])}/{int(row['n_dependence_blocks'])}"
            )
        ax.text(1.055, y, support, ha="left", va="center", color=PALETTE["grey"])
    ax.set_yticks(y_positions)
    ax.set_yticklabels([labels[endpoint] for endpoint in H3_PRIMARY_DISPLAY_ENDPOINTS])
    ax.set_xlim(-0.03, 1.68)
    ax.set_ylim(-0.55, len(H3_PRIMARY_DISPLAY_ENDPOINTS) - 0.25)
    ax.set_xticks((0.0, 0.5, 1.0))
    ax.set_xlabel("Equal-block score")
    ax.grid(axis="x", color=PALETTE["grey_light"], linewidth=0.5)
    ax.set_title("H3 boundary (Train-CV nominee)", loc="left", pad=4)
    _add_panel_label(ax, "e", x=-0.20)


def _render(bundle: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite figure directory: {output_dir}")
    temporary = output_dir.with_name(f"{output_dir.name}.tmp-{os.getpid()}")
    if temporary.exists():
        raise FileExistsError(f"Temporary figure directory exists: {temporary}")
    temporary.mkdir(parents=True)
    source_dir = temporary / "source_data"
    source_dir.mkdir()
    try:
        _apply_style()
        figure = plt.figure(
            figsize=(FIGURE_WIDTH_MM / 25.4, FIGURE_HEIGHT_MM / 25.4),
            constrained_layout=True,
        )
        outer = figure.add_gridspec(
            4,
            1,
            height_ratios=(0.88, 1.64, 1.54, 1.18),
            hspace=0.10,
        )
        ax_a = figure.add_subplot(outer[0, 0])
        ax_b = figure.add_subplot(outer[1, 0])
        c_grid = outer[2, 0].subgridspec(
            1, 2, width_ratios=(1.02, 1.42), wspace=0.25
        )
        ax_c_cv = figure.add_subplot(c_grid[0, 0])
        ax_c_nominee = figure.add_subplot(c_grid[0, 1])
        d_grid = outer[3, 0].subgridspec(
            1, 2, width_ratios=(1.28, 1.0), wspace=0.28
        )
        ax_d_pareto = figure.add_subplot(d_grid[0, 0])
        ax_e_h3 = figure.add_subplot(d_grid[0, 1])

        panel_a = _panel_a_rows(bundle)
        panel_b = _rate_cell_rows(bundle, MODEL_ORDER)
        panel_c = _candidate_panel_rows(bundle)
        panel_d_pareto = [dict(bundle["pareto_index"][(candidate,)]) for candidate in CANDIDATE_ORDER]
        panel_d_h3 = _panel_h3_rows(bundle)

        _draw_panel_a(ax_a, bundle, panel_a)
        _draw_panel_b(ax_b, panel_b)
        _draw_panel_c_cv(ax_c_cv, bundle)
        _draw_panel_c_nominee_source(ax_c_nominee, bundle)
        _draw_panel_d_pareto(ax_d_pareto, bundle)
        _draw_panel_e_h3(ax_e_h3, panel_d_h3)

        base = temporary / FIGURE_BASENAME
        figure.savefig(base.with_suffix(".svg"))
        figure.savefig(base.with_suffix(".pdf"))
        figure.savefig(base.with_suffix(".png"), dpi=300)
        figure.savefig(
            base.with_suffix(".tiff"),
            dpi=600,
            pil_kwargs={"compression": "tiff_lzw"},
        )
        plt.close(figure)

        _write_tsv(source_dir / "panel_a_evidence.tsv", list(panel_a[0]), panel_a)
        _write_tsv(source_dir / "panel_b_homogeneous.tsv", list(panel_b[0]), panel_b)
        _write_tsv(source_dir / "panel_c_mixed_candidates.tsv", list(panel_c[0]), panel_c)
        _write_tsv(
            source_dir / "panel_d_accuracy_cost_pareto.tsv",
            list(panel_d_pareto[0]),
            panel_d_pareto,
        )
        _write_tsv(source_dir / "panel_d_h3_boundary.tsv", list(panel_d_h3[0]), panel_d_h3)

        exported = [base.with_suffix(suffix) for suffix in SUPPORTED_EXPORT_SUFFIXES]
        if not all(path.is_file() and path.stat().st_size > 0 for path in exported):
            raise RuntimeError("One or more figure exports are empty")
        svg_text = exported[0].read_text(encoding="utf-8")
        if "<text" not in svg_text:
            raise RuntimeError("SVG export does not retain editable text")

        panel_a_states = Counter(
            str(row[f"{head}_state"]) for row in panel_a for head in HEAD_ORDER
        )
        panel_rate_states = Counter(
            str(row["cell_state"]) for row in (*panel_b, *panel_c)
        )
        numeric_zero_count = sum(
            row["cell_state"] == CELL_ESTIMATED and float(row["value"]) == 0.0
            for row in (*panel_b, *panel_c)
        )
        nominee_h3_model = bundle["cv_index"][(bundle["nominee_id"],)]["head3_model"]
        qa = {
            "schema_version": 1,
            "analysis_id": ANALYSIS_ID,
            "status": "pass",
            "figure_contract": "eight_model_mixed_head_quantitative_grid",
            "panel_labels": list(PANEL_LABELS),
            "protocol_amendment": PROTOCOL_AMENDMENT,
            "backend": "python_matplotlib_only",
            "figure_size_mm": {"width": FIGURE_WIDTH_MM, "height": FIGURE_HEIGHT_MM},
            "minimum_text_pt": 6.5,
            "exports": [path.name for path in exported],
            "svg_text_editable": True,
            "result_checksum_manifest_verified": True,
            "independent_schema5_validation_verified": True,
            "schema4_coverage_checksum_manifest_verified": True,
            "result_input_sha256": {
                name: bundle["verified"][name] for name in REQUIRED_RESULT_FILES
            },
            "schema4_coverage_sha256": bundle["schema4_verified"]["coverage_summary.tsv"],
            "schema5_validation_sha256": _sha256(bundle["validation_path"]),
            "config_sha256": _sha256(bundle["config_path"]),
            "protocol_sha256": _sha256(bundle["protocol_path"]),
            "comparison_summary_sha256": _sha256(bundle["comparison_path"]),
            "four_sources_separate": list(SOURCE_ORDER),
            "cross_source_average_plotted": False,
            "panel_a_repeated_test_column_plotted": False,
            "panel_a_test_accessed_zero_badge_plotted": True,
            "homogeneous_models": len(MODEL_ORDER),
            "primary_mixed_candidates": len(CANDIDATE_ORDER),
            "panel_c_candidates_in_train_cv_forest": len(CANDIDATE_ORDER),
            "panel_c_candidates_in_source_diagnostic": 1,
            "panel_c_full_nine_by_four_retained_in_source_data": True,
            "train_cv_nominee": bundle["nominee_id"],
            "nomination_primary_evidence": NOMINATION_PRIMARY_EVIDENCE,
            "robustness_used_for_candidate_ordering": False,
            "validation_family_warning_or_context_only": True,
            "released_v0_change_permitted": False,
            "prospective_external_confirmation_required": True,
            "test_vectors_selected_for_inference": 0,
            "test_predictions_or_metrics_computed": 0,
            "prediction_rows_audited_for_NA_and_Test": bundle["prediction_row_count"],
            "cell_states": {
                "not_applicable": int(panel_a_states[CELL_NOT_APPLICABLE]),
                "not_estimable": int(
                    panel_a_states[CELL_NOT_ESTIMABLE]
                    + panel_rate_states[CELL_NOT_ESTIMABLE]
                ),
                "estimated": int(
                    panel_a_states[CELL_ESTIMATED] + panel_rate_states[CELL_ESTIMATED]
                ),
                "numeric_zero": int(numeric_zero_count),
            },
            "na_ne_numeric_zero_have_distinct_encodings": True,
            "h3_nominee_model": nominee_h3_model,
            "h3_primary_endpoint_ids": list(H3_PRIMARY_DISPLAY_ENDPOINTS),
            "h3_primary_display_rows": len(H3_PRIMARY_DISPLAY_ENDPOINTS),
            "h3_representative_benchmark_rare_n": REPRESENTATIVE_RARE_N,
            "h3_matched_family_rare_relations_n": MATCHED_RARE_RELATIONS_N,
            "h3_matched_family_rare_parents_n": MATCHED_RARE_PARENTS_N,
            "h3_matched_family_rare_blocks_n": MATCHED_RARE_BLOCKS_N,
            "h3_produgelaviricota_relations_n": PRODUGELAVIRICOTA_RELATIONS_N,
            "h3_produgelaviricota_parents_n": PRODUGELAVIRICOTA_PARENTS_N,
            "h3_produgelaviricota_blocks_n": PRODUGELAVIRICOTA_BLOCKS_N,
            "h3_literature_unclassified_relations_n": (
                LITERATURE_UNCLASSIFIED_RELATIONS_N
            ),
            "h3_literature_unclassified_parents_n": (
                LITERATURE_UNCLASSIFIED_PARENTS_N
            ),
            "h3_literature_unclassified_blocks_n": (
                LITERATURE_UNCLASSIFIED_BLOCKS_N
            ),
            "h3_raw_k_n_displayed": True,
            "h3_pooled_used_as_primary": False,
            "h3_pooled_secondary_only": True,
            "h3_secondary_pooled_and_representative_rows_plotted": False,
            "h3_secondary_rows_retained_in_source_data": True,
            "h3_single_block_ci_drawn": False,
            "h3_unknown_generalization_claim_permitted": False,
            "cost_interpretation": "workstation_specific_always_on_and_conditional_terms_no_prevalence_assumption",
            "source_data_tables": sorted(path.name for path in source_dir.iterdir()),
        }
        (temporary / "QA.json").write_text(
            json.dumps(qa, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        manifest_rows: list[dict[str, Any]] = []
        for path in sorted(item for item in temporary.rglob("*") if item.is_file()):
            relative = path.relative_to(temporary).as_posix()
            manifest_rows.append(
                {
                    "path": relative,
                    "role": (
                        "figure"
                        if path.suffix in SUPPORTED_EXPORT_SUFFIXES
                        else "panel_source_data" if path.parent == source_dir else "qa"
                    ),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        _write_tsv(
            temporary / "figure_manifest.tsv",
            ("path", "role", "bytes", "sha256"),
            manifest_rows,
        )
        checksummed = sorted(
            item
            for item in temporary.rglob("*")
            if item.is_file() and item.name != "CHECKSUMS.sha256"
        )
        with (temporary / "CHECKSUMS.sha256").open("x", encoding="utf-8") as handle:
            for path in checksummed:
                relative = path.relative_to(temporary).as_posix()
                handle.write(f"{_sha256(path)}  {relative}\n")
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output_dir)
        return qa
    except Exception:
        # Failed renders remain forensic generations and are never promoted.
        failed = temporary.with_name(f"{temporary.name}.failed")
        if temporary.exists() and not failed.exists():
            os.replace(temporary, failed)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "validation_family_robustness_v0_schema5_mixed_heads.yaml",
    )
    parser.add_argument(
        "--result-dir",
        type=Path,
        help="Read-only completed result directory override for transfer rendering.",
    )
    parser.add_argument(
        "--schema4-result-dir",
        type=Path,
        help="Read-only schema-4 result override for local continuity rendering.",
    )
    parser.add_argument(
        "--validation",
        type=Path,
        help=(
            "Read-only independent schema-5 validation.json override; defaults to "
            "the sibling of the completed result directory."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="New figure directory; existing directories are never overwritten.",
    )
    args = parser.parse_args()
    bundle = _load_and_validate(
        args.config,
        args.result_dir,
        args.schema4_result_dir,
        args.validation,
    )
    project_root = args.config.resolve().parents[1]
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else _resolve(project_root, bundle["config"]["figure_dir"])
    )
    qa = _render(bundle, output_dir)
    print(json.dumps({"output_dir": str(output_dir), "qa": qa}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
