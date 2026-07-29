#!/usr/bin/env python3
"""Score the frozen eight-model/schema-5 mixed-head robustness extension.

This is a Validation-family development follow-up.  It never opens Test and it
cannot fit a head, recalibrate probabilities, change a threshold, or modify the
released V0 tool.  Candidate order is computed from the already-frozen
Train-only five-fold scores; the four-source robustness endpoints are
source-specific diagnostics only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import math
import os
import platform
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import yaml

from djrmcp_finder.benchmark_config import expand_benchmark_model
from djrmcp_finder.benchmark_selection import (
    _verify_selected_model_artifacts,
    load_frozen_benchmark_selection,
)
from djrmcp_finder.config import load_config
from djrmcp_finder.validation_family_robustness import (
    HEADS,
    KNOWN_H3_CLASSES,
    ModelSpec,
    _check_representation,
    _decision_scores,
    _load_bundles,
    _load_embedding,
    _probabilities,
)


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
H12_CANDIDATES = ("esm2_650m", "esm2_3b", "esmc_6b")
H3_CANDIDATES = ("esmc_300m", "esmc_600m", "esmc_6b")
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
    ("viral_vma_djr", "head1"): (1, "djr", "positive_sensitivity"),
    ("viral_vma_djr", "head2"): (
        1,
        "viral_morphogenesis_associated",
        "positive_sensitivity",
    ),
    ("cellular_djr_none", "head1"): (1, "djr", "positive_sensitivity"),
    ("cellular_djr_none", "head2"): (0, "none", "negative_specificity"),
    ("background_non_djr", "head1"): (0, "non_djr", "negative_specificity"),
    ("hard_non_djr", "head1"): (0, "non_djr", "negative_specificity"),
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
REFERENCE_SYSTEM = "esmc_6b"
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
        "expected_records": 1,
        "expected_parents": 1,
        "expected_dependence_blocks": 1,
        "bootstrap_seed_offset": 6_110,
        "interpretation": "single_record_descriptive_only_no_generalization",
    },
    "rare_or_unclassified_reject_recall": {
        "endpoint_role": "secondary_pooled_diagnostic",
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
REQUIRED_RESULT_FILES = {
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


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise RuntimeError(f"Missing TSV header: {path}")
        return list(reader)


def _write_tsv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def _verify_flat_bundle(directory: Path, *, exact: set[str] | None = None) -> dict[str, str]:
    manifest = directory / "CHECKSUMS.sha256"
    if not manifest.is_file():
        raise FileNotFoundError(f"Missing checksum manifest: {manifest}")
    verified: dict[str, str] = {}
    for line_number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split(maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError(f"Malformed checksum at {manifest}:{line_number}")
        expected, name = parts[0].lower(), parts[1].strip().lstrip("*")
        target = directory / name
        if (
            len(expected) != 64
            or any(value not in "0123456789abcdef" for value in expected)
            or Path(name).name != name
            or name in verified
            or not target.is_file()
            or _sha256(target) != expected
        ):
            raise RuntimeError(f"Unsafe, missing, or mismatched checksum target: {target}")
        verified[name] = expected
    if not verified or (exact is not None and set(verified) != exact):
        raise RuntimeError(f"Checksum bundle contract mismatch: {directory}")
    return verified


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes"}:
        return 1
    if text in {"0", "false", "no", ""}:
        return 0
    raise RuntimeError(f"Expected Boolean/integer flag, observed {value!r}")


def _candidate_id(h12: str, h3: str) -> str:
    return f"h12_{h12}__h3_{h3}"


def _expected_candidates() -> list[dict[str, str]]:
    return [
        {
            "candidate_id": _candidate_id(h12, h3),
            "head1_model": h12,
            "head2_model": h12,
            "head3_model": h3,
        }
        for h12 in H12_CANDIDATES
        for h3 in H3_CANDIDATES
    ]


def _validate_config(config: dict[str, Any]) -> None:
    if (
        config.get("schema_version") != 5
        or config.get("analysis_id") != ANALYSIS_ID
        or config.get("evaluation_role")
        != "auxiliary_post_freeze_multimodel_stress_test"
        or config.get("selection_feedback_permitted") is not False
        or config.get("released_v0_feedback_permitted") is not False
        or config.get("train_cv_candidate_nomination_permitted") is not True
        or config.get("schema5_robustness_reranking_permitted") is not False
        or config.get("model_state") != "frozen"
        or config.get("test_policy") != "no_test_vector_selection_or_performance_scoring"
        or int(config.get("bootstrap_replicates", 0)) != 10_000
        or int(config.get("bootstrap_seed", 0)) != 20260728
        or tuple(config.get("models", ())) != MODELS
        or tuple(config.get("homogeneous_models", ())) != MODELS
        or tuple(config.get("h12_candidates", ())) != H12_CANDIDATES
        or tuple(config.get("h3_candidates", ())) != H3_CANDIDATES
        or config.get("nomination_primary_evidence") != "train_only_shared_five_fold_cv"
        or config.get("robustness_role_in_nomination")
        != "source_specific_warning_not_reranking"
        or config.get("multiple_comparison_method") != "holm"
        or config.get("multiple_comparison_family")
        != "eight_nontrivial_primary_mixed_candidates_vs_all_esmc_6b"
        or config.get("contextual_reference_model_id") != "esm2_650m"
        or config.get("protocol_amendment") != PROTOCOL_AMENDMENT
        or config.get("schema4_prediction_cache_policy")
        != SCHEMA4_CANONICAL_CACHE_POLICY
        or int(config.get("schema4_expected_prediction_rows", 0)) != 92_844
    ):
        raise RuntimeError("Schema-5 frozen development boundary mismatch")
    observed_tolerances = config.get("schema4_recomputation_tolerances", {})
    expected_tolerances = {
        "probability": {"absolute": 5e-7, "relative": 1e-6},
        "raw_decision_score": {"absolute": 1e-5, "relative": 1e-6},
        "threshold": {"absolute": 0.0, "relative": 0.0},
    }
    if observed_tolerances != expected_tolerances:
        raise RuntimeError("Schema-4 recomputation tolerance contract changed")
    h3_contract = config.get("h3_rare_endpoint_contract", {})
    if h3_contract != {
        "derivation": "frozen_family_manifest_join_to_existing_per_record_predictions",
        "model_inference_repeated_for_subgroups": False,
        "refit_recalibration_or_threshold_change_permitted": False,
        "prediction_threshold_cv_nomination_equivalence_to_amendment_c_required": True,
        "subgroup_fields": ["head3_status", "head3_phylum_label"],
        "raw_reject_counts_required": True,
        "endpoints": H3_RARE_ENDPOINT_CONTRACT,
    }:
        raise RuntimeError("Amendment-D H3 rare-endpoint contract changed")
    operator = config.get("legacy_schema4_numerical_operator")
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
    if operator != expected_operator:
        raise RuntimeError("Legacy schema-4 numerical-operator contract changed")
    for field in (
        "embedding_materialization_protocol_sha256",
        "embedding_materialization_config_sha256",
        "schema4_result_checksums_sha256",
        "schema4_validation_sha256",
        "schema3_family_member_manifest_sha256",
        "amendment_c_result_checksums_sha256",
        "amendment_c_validation_sha256",
    ):
        value = str(config.get(field, ""))
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise RuntimeError(f"Invalid frozen lineage SHA: {field}")
    if config.get("primary_mixed_candidates") != _expected_candidates():
        raise RuntimeError("The predeclared nine-candidate grid changed")
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
        raise RuntimeError("Amendment-C byte-equivalence boundary changed")
    weights = config.get("score_weights", {})
    if weights != {"head1_ap": 0.60, "head2_ap": 0.30, "head3_known_macro_f1": 0.10}:
        raise RuntimeError("Frozen Train-CV score weights changed")
    registries = config.get("embedding_registries", {})
    if set(registries) != {"viral_family", "graph_family", "hardnegative_matched"}:
        raise RuntimeError("Exactly three embedding registries are required")
    for shard, registry in registries.items():
        if not isinstance(registry, dict) or set(registry) != set(MODELS):
            raise RuntimeError(f"Embedding registry is not exact 8-model: {shard}")
    for shard in registries:
        spec = config.get("inputs", {}).get(shard, {})
        if int(spec.get("expected_records", 0)) <= 0:
            raise RuntimeError(f"Missing frozen input count: {shard}")
        for field in ("manifest_sha256", "fasta_sha256"):
            value = str(spec.get(field, ""))
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise RuntimeError(f"Invalid frozen input identity: {shard}/{field}")


def _legacy_operator_runtime_attestation(
    config: Mapping[str, Any],
    config_path: Path,
    *,
    environ: Mapping[str, str] | None = None,
    observed_python_version: str | None = None,
    observed_executable: str | None = None,
    observed_threadpools: Sequence[Mapping[str, Any]] | None = None,
    preload_fn: Any | None = None,
    threadpool_info_fn: Any | None = None,
) -> dict[str, Any]:
    """Fail closed unless the schema-4 numerical operator is reproduced.

    The optional observations exist only to make this gate unit-testable.  The
    formal scorer supplies none of them and therefore attests the live process.
    Exact row replay remains a second, independent gate after inference.
    """

    operator = config["legacy_schema4_numerical_operator"]
    preloader = preload_fn or _preload_legacy_numerical_runtime
    preloaded_modules = preloader(config)
    runtime_env = os.environ if environ is None else environ
    observed_env = {key: str(runtime_env.get(key, "")) for key in LEGACY_OPERATOR_ENV}
    mismatched_env = {
        key: {"expected": expected, "observed": observed_env[key]}
        for key, expected in LEGACY_OPERATOR_ENV.items()
        if observed_env[key] != expected
    }
    venv_root = str(operator["venv_root"])
    observed_virtual_env = str(runtime_env.get("VIRTUAL_ENV", ""))
    if observed_virtual_env != venv_root:
        mismatched_env["VIRTUAL_ENV"] = {
            "expected": venv_root,
            "observed": observed_virtual_env,
        }
    pbs_job_id = str(runtime_env.get("PBS_JOBID", "")).strip()
    if mismatched_env or not pbs_job_id:
        raise RuntimeError(
            "Legacy numerical-operator environment attestation failed: "
            f"mismatches={mismatched_env}; PBS_JOBID={pbs_job_id!r}"
        )

    python_version = observed_python_version or platform.python_version()
    executable = observed_executable or sys.executable
    expected_python = str(operator["python_version"])
    expected_executable = Path(venv_root) / "bin" / "python"
    if (
        python_version != expected_python
        or Path(executable).resolve() != expected_executable.resolve()
    ):
        raise RuntimeError(
            "Legacy numerical-operator Python attestation failed: "
            f"version={python_version!r}/{expected_python!r}; "
            f"executable={Path(executable).resolve()!s}/{expected_executable.resolve()!s}"
        )

    if observed_threadpools is None:
        if threadpool_info_fn is None:
            from threadpoolctl import threadpool_info

            threadpool_info_fn = threadpool_info
        observed_threadpools = threadpool_info_fn()
    numerical_pools = [
        pool
        for pool in observed_threadpools
        if str(pool.get("user_api", "")) in {"blas", "openmp"}
    ]
    expected_pool_count = int(operator["required_threadpool_count"])
    expected_api_counts = {
        str(key): int(value)
        for key, value in operator["required_threadpool_user_api_counts"].items()
    }
    observed_api_counts = dict(
        sorted(Counter(str(pool.get("user_api", "")) for pool in numerical_pools).items())
    )
    expected_threads = int(operator["openblas_num_threads"])
    if (
        len(numerical_pools) != expected_pool_count
        or observed_api_counts != expected_api_counts
        or any(int(pool.get("num_threads", -1)) != expected_threads for pool in numerical_pools)
    ):
        raise RuntimeError(
            "Legacy numerical-operator threadpool attestation failed: "
            f"count={len(numerical_pools)}/{expected_pool_count}; "
            f"apis={observed_api_counts}/{expected_api_counts}; "
            f"threads={[pool.get('num_threads') for pool in numerical_pools]}"
        )
    normalized_pools = sorted(
        [
            {
                "user_api": str(pool.get("user_api", "")),
                "internal_api": str(pool.get("internal_api", "")),
                "prefix": str(pool.get("prefix", "")),
                "version": str(pool.get("version", "")),
                "num_threads": int(pool["num_threads"]),
                "filepath": str(pool.get("filepath", "")),
                "file_basename": Path(str(pool.get("filepath", ""))).name,
            }
            for pool in numerical_pools
        ],
        key=lambda row: (
            row["user_api"],
            row["internal_api"],
            row["prefix"],
            row["file_basename"],
        ),
    )
    scorer_path = Path(__file__).resolve()
    launcher_path = scorer_path.with_name(
        "run_validation_family_robustness_v0_schema5_mixed_heads.pbs"
    )
    protocol_path = Path(config["protocol"])
    if not launcher_path.is_file() or not protocol_path.is_file():
        raise RuntimeError("Legacy numerical-operator source lineage is incomplete")
    return {
        "schema_version": 1,
        "status": "PASS",
        "operator_id": LEGACY_OPERATOR_ID,
        "cache_policy": SCHEMA4_CANONICAL_CACHE_POLICY,
        "canonical_schema4_job": int(operator["canonical_schema4_job"]),
        "canonical_schema4_job_overall_status": (
            "Exit1_after_valid_prediction_generation_and_independent_prediction_validation"
        ),
        "exact_numeric_string_replay_required": True,
        "amendment_b_tolerances_retained_as_upper_bound": True,
        "pbs": {
            "job_id": pbs_job_id,
            "job_name": str(runtime_env.get("PBS_JOBNAME", "")),
            "ncpus": int(observed_env["SCHEMA5_PBS_NCPUS"]),
            "memory_gb": int(observed_env["SCHEMA5_PBS_MEMORY_GB"]),
        },
        "environment": {
            **observed_env,
            "VIRTUAL_ENV": observed_virtual_env,
        },
        "python": {
            "module": observed_env["SCHEMA5_PYTHON_MODULE"],
            "version": python_version,
            "executable": str(Path(executable).resolve()),
            "configured_venv_python": str(expected_executable.resolve()),
        },
        "runtime_preload_modules": preloaded_modules,
        "threadpool_count": len(normalized_pools),
        "threadpool_user_api_counts": observed_api_counts,
        "threadpools": normalized_pools,
        "lineage_sha256": {
            "config": _sha256(config_path),
            "protocol": _sha256(protocol_path),
            "scorer": _sha256(scorer_path),
            "pbs_launcher": _sha256(launcher_path),
        },
    }


def _preload_legacy_numerical_runtime(
    config: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Load the complete frozen numerical backend before pool attestation.

    NumPy alone exposes only its BLAS pool on gds2.  Importing the declared
    SciPy and sklearn modules deterministically loads the second BLAS runtime
    and OpenMP runtime without fitting a model or evaluating a decision score.
    """

    operator = config["legacy_schema4_numerical_operator"]
    names = tuple(str(value) for value in operator["runtime_preload_modules"])
    if names != ("scipy.linalg", "sklearn.linear_model"):
        raise RuntimeError("Legacy numerical-operator preload module list changed")
    records: list[dict[str, str]] = []
    for name in names:
        module = importlib.import_module(name)
        root = importlib.import_module(name.split(".", 1)[0])
        filepath = str(getattr(module, "__file__", ""))
        version = str(getattr(root, "__version__", ""))
        if not filepath or not Path(filepath).is_absolute() or not version:
            raise RuntimeError(f"Legacy numerical-operator preload failed: {name}")
        records.append(
            {
                "module": name,
                "package_version": version,
                "module_file": filepath,
            }
        )
    return records


def _source_cluster_key(row: Mapping[str, Any]) -> str:
    return str(
        row.get("source_cluster_key")
        or f"{row['source_dataset']}::{row['source_cluster_id']}"
    )


def _binary_label(head: str, prediction: int) -> str:
    if head == "head1":
        return "djr" if prediction else "non_djr"
    if head == "head2":
        return "viral_morphogenesis_associated" if prediction else "none"
    raise RuntimeError(f"Not a binary head: {head}")


def _h3_prediction(run: Mapping[str, Any], protein_id: str) -> tuple[str, float]:
    probabilities = np.asarray(run["h3_probability"][protein_id], dtype=np.float64)
    index = int(np.argmax(probabilities))
    confidence = float(probabilities[index])
    if confidence < float(run["h3_threshold"]):
        return "unknown/other", confidence
    return KNOWN_H3_CLASSES[index], confidence


def _schema3_runtime_config(
    config: dict[str, Any], schema4_config: dict[str, Any]
) -> tuple[dict[str, Any], Path]:
    schema3_path = Path(config["schema3_config"])
    runtime = yaml.safe_load(schema3_path.read_text(encoding="utf-8"))
    for key in (
        "benchmark_config",
        "comparison_summary",
        "master_manifest",
    ):
        runtime[key] = config[key]
    # The shared loader has an inference-only schema-3 boundary.  Schema-5
    # candidate nomination happens later and cannot affect any loaded artifact.
    runtime.update(
        {
            "evaluation_role": "auxiliary_post_freeze_support",
            "selection_feedback_permitted": False,
            "model_state": "frozen",
            "frozen_primary_model_id": "esmc_6b",
            "fixed_reference_model_id": "esm2_650m",
            "cohort_dir": schema4_config["schema3"]["full_cohort_dir"],
            "member_embeddings": config["embedding_registries"]["viral_family"],
            "graph_member_embeddings": config["embedding_registries"]["graph_family"],
        }
    )
    return runtime, schema3_path


def _write_subset_embedding_bundle(
    config: dict[str, Any],
    model_id: str,
    representative_ids: list[str],
    output: Path,
) -> Path:
    benchmark = load_config(Path(config["benchmark_config"]))
    model_config = expand_benchmark_model(benchmark, model_id)
    source = Path(model_config["paths"]["embedding_output"])
    _verify_flat_bundle(source)
    master_path = Path(config["master_manifest"])
    master_rows = _read_tsv(master_path)
    master_by_id = {row["protein_id"]: row for row in master_rows}
    if len(master_by_id) != len(master_rows) or not set(representative_ids) <= set(master_by_id):
        raise RuntimeError("HardNeg representatives are not unique Validation master records")
    selected_manifest = [master_by_id[value] for value in representative_ids]
    if any(row["split"] != "validation" for row in selected_manifest):
        raise RuntimeError("HardNeg representative subset is not Validation-only")
    source_index_rows = _read_tsv(source / "index.tsv")
    source_index = {row["protein_id"]: row for row in source_index_rows}
    if not set(representative_ids) <= set(source_index):
        raise RuntimeError("HardNeg representative embeddings are incomplete")
    source_vectors = np.load(source / "embeddings.float16.npy", mmap_mode="r")
    selected_indices = [int(source_index[value]["embedding_row"]) for value in representative_ids]
    output.mkdir(parents=True)
    manifest_path = output / "representative_manifest.tsv"
    _write_tsv(manifest_path, list(master_rows[0]), selected_manifest)
    index_rows: list[dict[str, object]] = []
    for embedding_row, protein_id in enumerate(representative_ids):
        copied: dict[str, object] = dict(source_index[protein_id])
        copied["embedding_row"] = embedding_row
        index_rows.append(copied)
    _write_tsv(output / "index.tsv", list(source_index_rows[0]), index_rows)
    np.save(output / "embeddings.float16.npy", np.asarray(source_vectors[selected_indices]))
    np.save(output / "completed.npy", np.ones(len(representative_ids), dtype=bool))
    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    source_fasta_sha = metadata.pop("fasta_sha256", None)
    source_fasta_path = metadata.pop("fasta_path", None)
    source_manifest_path = metadata.pop("manifest_path", None)
    metadata["manifest_sha256"] = _sha256(manifest_path)
    for key in (
        "records",
        "record_count",
        "n_records",
        "num_sequences",
        "completed_records",
    ):
        if key in metadata:
            metadata[key] = len(representative_ids)
    metadata.update(
        {
            "status": "complete",
            "derived_validation_representative_subset": True,
            "derived_subset_records": len(representative_ids),
            "source_embedding_dir": str(source),
            "source_embedding_checksums_sha256": _sha256(source / "CHECKSUMS.sha256"),
            "source_embedding_metadata_sha256": _sha256(source / "metadata.json"),
        }
    )
    if source_fasta_sha is not None:
        metadata["source_fasta_sha256"] = source_fasta_sha
    if source_fasta_path is not None:
        metadata["source_fasta_path"] = source_fasta_path
    if source_manifest_path is not None:
        metadata["source_manifest_path"] = source_manifest_path
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    names = ("completed.npy", "embeddings.float16.npy", "index.tsv", "metadata.json")
    (output / "CHECKSUMS.sha256").write_text(
        "".join(f"{_sha256(output / name)}  {name}\n" for name in names), encoding="utf-8"
    )
    return manifest_path


def _build_model_contexts(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    benchmark_config, selection = load_frozen_benchmark_selection(
        Path(config["benchmark_config"]),
        Path(config["comparison_summary"]),
        verify_artifacts=False,
    )
    summary = json.loads(Path(config["comparison_summary"]).read_text(encoding="utf-8"))
    row_by_model = {row["model_id"]: row for row in summary["models"]}
    if set(MODELS) - set(row_by_model):
        raise RuntimeError("Frozen 14-model comparison lacks a schema-5 model")
    manifest_sha = _sha256(Path(config["master_manifest"]))
    contexts: dict[str, dict[str, Any]] = {}
    for model_id in MODELS:
        lineage = _verify_selected_model_artifacts(
            benchmark_config, model_id, row_by_model[model_id], manifest_sha
        )
        expanded = expand_benchmark_model(benchmark_config, model_id)
        contexts[model_id] = {
            "benchmark_config": benchmark_config,
            "selection": selection,
            "row": row_by_model[model_id],
            "lineage": lineage,
            "spec": ModelSpec(
                model_id=model_id,
                label=row_by_model[model_id]["label"],
                original_embedding=Path(expanded["paths"]["embedding_output"]),
                member_embedding=Path(config["embedding_registries"]["viral_family"][model_id]),
                result_dir=Path(expanded["paths"]["result_output"]),
            ),
        }
    return contexts


def _load_schema5_family_predictions(
    runtime: Mapping[str, Any],
    model_id: str,
    family_rows: list[dict[str, str]],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    spec: ModelSpec = context["spec"]
    master_path = Path(runtime["master_manifest"])
    viral_manifest_path = Path(runtime["source_family_dir"]) / "validation_source_entities.tsv"
    graph_manifest_path = Path(runtime["graph_family_trace"])
    original_manifest, original_vectors, original_metadata, original_artifacts = _load_embedding(
        master_path, spec.original_embedding
    )
    shard_specs = (
        (
            "viral_source_family",
            viral_manifest_path,
            Path(runtime["member_embeddings"][model_id]),
            {"viral_vma_djr"},
        ),
        (
            "validation_graph_family",
            graph_manifest_path,
            Path(runtime["graph_member_embeddings"][model_id]),
            {"cellular_djr_none", "background_non_djr"},
        ),
    )
    member_location: dict[str, tuple[np.ndarray, int, str]] = {}
    shard_payloads: dict[str, dict[str, Any]] = {}
    for shard_id, manifest_path, embedding_dir, expected_sources in shard_specs:
        manifest, vectors, metadata, artifacts = _load_embedding(manifest_path, embedding_dir)
        _check_representation(original_metadata, metadata, model_id)
        if {row["source_dataset"] for row in manifest} != expected_sources:
            raise RuntimeError(f"Unexpected source set in {model_id}/{shard_id}")
        for index, row in enumerate(manifest):
            if row["protein_id"] in member_location:
                raise RuntimeError("Member occurs in multiple schema-5 embedding shards")
            member_location[row["protein_id"]] = (vectors, index, shard_id)
        shard_payloads[shard_id] = {
            "manifest": manifest,
            "manifest_path": manifest_path,
            "embedding_dir": embedding_dir,
            "artifacts": artifacts,
        }
    original_index = {row["protein_id"]: index for index, row in enumerate(original_manifest)}
    family_ids = [row["protein_id"] for row in family_rows]
    representative_ids = sorted({row["paired_representative_id"] for row in family_rows})
    if len(set(family_ids)) != len(family_ids) or not set(family_ids) <= set(member_location):
        raise RuntimeError(f"Family member embedding coverage mismatch: {model_id}")
    if not set(representative_ids) <= set(original_index):
        raise RuntimeError(f"Representative embedding coverage mismatch: {model_id}")
    for row in family_rows:
        expected_shard = (
            "viral_source_family"
            if row["source_dataset"] == "viral_vma_djr"
            else "validation_graph_family"
        )
        if member_location[row["protein_id"]][2] != expected_shard:
            raise RuntimeError(f"Source/shard mismatch: {model_id}/{row['protein_id']}")
    representative_x = np.asarray(
        original_vectors[[original_index[value] for value in representative_ids]], dtype=np.float32
    )
    member_x = np.stack(
        [
            np.asarray(member_location[value][0][member_location[value][1]], dtype=np.float32)
            for value in family_ids
        ]
    )
    manifest_sha = _sha256(master_path)
    metadata_sha = _sha256(spec.original_embedding / "metadata.json")
    loaded = _load_bundles(spec, manifest_sha, metadata_sha)
    probability: dict[str, dict[str, float]] = defaultdict(dict)
    raw_score: dict[str, dict[str, float]] = defaultdict(dict)
    thresholds: dict[str, float] = {}
    temperatures: dict[str, float] = {}
    for head in HEADS:
        bundle = loaded["bundles"][head]
        temperature = float(bundle["temperature"])
        threshold = float(bundle["decision_threshold"])
        rep_probability = _probabilities(bundle["estimator"], representative_x, temperature)[:, 1]
        mem_probability = _probabilities(bundle["estimator"], member_x, temperature)[:, 1]
        rep_raw = _decision_scores(bundle["estimator"], representative_x)
        mem_raw = _decision_scores(bundle["estimator"], member_x)
        probability[head].update(zip(representative_ids, rep_probability, strict=True))
        probability[head].update(zip(family_ids, mem_probability, strict=True))
        raw_score[head].update(zip(representative_ids, rep_raw, strict=True))
        raw_score[head].update(zip(family_ids, mem_raw, strict=True))
        thresholds[head] = threshold
        temperatures[head] = temperature
    calibration_path = spec.result_dir / "calibration.json"
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    h3_calibration = calibration["heads"]["head3_phylum"]
    h3_path = spec.result_dir / "models/head3_phylum.joblib"
    if _sha256(h3_path) != h3_calibration["model_sha256"]:
        raise RuntimeError(f"Frozen H3 checksum mismatch: {model_id}")
    import joblib

    h3_bundle = joblib.load(h3_path)
    if h3_bundle.get("head") != "head3_phylum" or h3_bundle.get("classes") != list(KNOWN_H3_CLASSES):
        raise RuntimeError(f"Frozen H3 schema mismatch: {model_id}")
    if (
        h3_bundle.get("manifest_sha256") != manifest_sha
        or h3_bundle.get("embedding_metadata_sha256") != metadata_sha
        or float(h3_bundle["temperature"]) != float(h3_calibration["temperature"])
        or float(h3_bundle["decision_threshold"])
        != float(h3_calibration["decision_threshold"])
    ):
        raise RuntimeError(f"Frozen H3 lineage mismatch: {model_id}")
    h3_temperature = float(h3_bundle["temperature"])
    h3_threshold = float(h3_bundle["decision_threshold"])
    rep_h3 = _probabilities(h3_bundle["estimator"], representative_x, h3_temperature)
    mem_h3 = _probabilities(h3_bundle["estimator"], member_x, h3_temperature)
    h3_probability = {
        **dict(zip(representative_ids, rep_h3, strict=True)),
        **dict(zip(family_ids, mem_h3, strict=True)),
    }
    return {
        "label": spec.label,
        "probability": probability,
        "raw_score": raw_score,
        "thresholds": thresholds,
        "temperatures": temperatures,
        "h3_probability": h3_probability,
        "h3_threshold": h3_threshold,
        "h3_temperature": h3_temperature,
        "provenance": {
            "model_id": model_id,
            "model_label": spec.label,
            "inference_only": True,
            "full_14_model_registry_fallback": True,
            "frozen_model_lineage": context["lineage"],
            "original_embedding_artifacts": original_artifacts,
            "member_embedding_shards": {
                key: {
                    "manifest": str(value["manifest_path"]),
                    "manifest_sha256": _sha256(value["manifest_path"]),
                    "records": len(value["manifest"]),
                    "embedding_dir": str(value["embedding_dir"]),
                    "embedding_checksums_sha256": _sha256(
                        value["embedding_dir"] / "CHECKSUMS.sha256"
                    ),
                    "artifacts": value["artifacts"],
                }
                for key, value in shard_payloads.items()
            },
            "thresholds": {**thresholds, "head3_phylum": h3_threshold},
            "temperatures": {**temperatures, "head3_phylum": h3_temperature},
            "test_vectors_selected_for_inference": 0,
            "test_predictions_or_metrics_computed": 0,
        },
    }


def _load_schema5_h1_predictions(
    config: Mapping[str, Any],
    model_id: str,
    manifest_path: Path,
    embedding_dir: Path,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    spec: ModelSpec = context["spec"]
    master_path = Path(config["master_manifest"])
    _master, _vectors, original_metadata, original_artifacts = _load_embedding(
        master_path, spec.original_embedding
    )
    manifest, vectors, metadata, artifacts = _load_embedding(manifest_path, embedding_dir)
    _check_representation(original_metadata, metadata, model_id)
    ids = [row["protein_id"] for row in manifest]
    if len(set(ids)) != len(ids):
        raise RuntimeError("Duplicate challenge protein IDs")
    manifest_sha = _sha256(master_path)
    metadata_sha = _sha256(spec.original_embedding / "metadata.json")
    loaded = _load_bundles(spec, manifest_sha, metadata_sha)
    bundle = loaded["bundles"]["head1"]
    temperature = float(bundle["temperature"])
    threshold = float(bundle["decision_threshold"])
    x = np.asarray(vectors, dtype=np.float32)
    probability = _probabilities(bundle["estimator"], x, temperature)[:, 1]
    raw_score = _decision_scores(bundle["estimator"], x)
    return {
        "label": spec.label,
        "probability": dict(zip(ids, probability, strict=True)),
        "raw_score": dict(zip(ids, raw_score, strict=True)),
        "threshold": threshold,
        "temperature": temperature,
        "provenance": {
            "model_id": model_id,
            "inference_only": True,
            "full_14_model_registry_fallback": True,
            "frozen_model_lineage": context["lineage"],
            "manifest": str(manifest_path),
            "manifest_sha256": _sha256(manifest_path),
            "records": len(manifest),
            "embedding_dir": str(embedding_dir),
            "embedding_checksums_sha256": _sha256(embedding_dir / "CHECKSUMS.sha256"),
            "embedding_artifacts": artifacts,
            "original_embedding_artifacts": original_artifacts,
            "test_vectors_selected_for_inference": 0,
            "test_predictions_or_metrics_computed": 0,
        },
    }


def _family_prediction_rows(
    family_rows: list[dict[str, str]],
    runs: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for model_id in MODELS:
        run = runs[model_id]
        for row in family_rows:
            source = row["source_dataset"]
            if source not in SOURCES[:-1]:
                raise RuntimeError(f"Unexpected schema-3 source: {source}")
            protein_id = row["protein_id"]
            representative_id = row["paired_representative_id"]
            common = {
                "model_id": model_id,
                "protein_id": protein_id,
                "source_dataset": source,
                "paired_representative_id": representative_id,
                "paired_representative_protein_id": representative_id,
                "source_cluster_id": row["source_cluster_id"],
                "source_cluster_key": _source_cluster_key(row),
                "dependence_block_id": row["dependence_block_id"],
                "train_relationship_stratum": row.get("train_relationship_stratum", ""),
            }
            for head in APPLICABLE_HEADS[source]:
                if head == "head3_phylum":
                    member_prediction, member_probability = _h3_prediction(run, protein_id)
                    rep_prediction, rep_probability = _h3_prediction(run, representative_id)
                    truth = row.get("head3_operational_label", "")
                    eligible = _as_int(row.get("h3_analysis_included", 0)) == 1 and bool(truth)
                    output.append(
                        {
                            **common,
                            "head": head,
                            "truth_label": truth if eligible else "",
                            "expected_prediction": truth if eligible else "",
                            "member_probability": member_probability,
                            "member_raw_decision_score": "",
                            "member_prediction": member_prediction,
                            "member_predicted_label": member_prediction,
                            "member_correct": int(member_prediction == truth) if eligible else "",
                            "representative_probability": rep_probability,
                            "representative_raw_decision_score": "",
                            "representative_prediction": rep_prediction,
                            "representative_predicted_label": rep_prediction,
                            "representative_correct": int(rep_prediction == truth) if eligible else "",
                            "threshold": run["h3_threshold"],
                            "applicable_to_source": 1,
                            "metric_eligible": int(eligible),
                            "test_record": 0,
                        }
                    )
                    continue
                expected, truth_label, _metric = EXPECTED_BINARY[(source, head)]
                threshold = float(run["thresholds"][head])
                member_probability = float(run["probability"][head][protein_id])
                rep_probability = float(run["probability"][head][representative_id])
                member_prediction = int(member_probability >= threshold)
                rep_prediction = int(rep_probability >= threshold)
                output.append(
                    {
                        **common,
                        "head": head,
                        "truth_label": truth_label,
                        "expected_prediction": expected,
                        "member_probability": member_probability,
                        "member_raw_decision_score": run["raw_score"][head][protein_id],
                        "member_prediction": member_prediction,
                        "member_predicted_label": _binary_label(head, member_prediction),
                        "member_correct": int(member_prediction == expected),
                        "representative_probability": rep_probability,
                        "representative_raw_decision_score": run["raw_score"][head][representative_id],
                        "representative_prediction": rep_prediction,
                        "representative_predicted_label": _binary_label(head, rep_prediction),
                        "representative_correct": int(rep_prediction == expected),
                        "threshold": threshold,
                        "applicable_to_source": 1,
                        "metric_eligible": 1,
                        "test_record": 0,
                    }
                )
    return output


def _hardnegative_runs(
    config: dict[str, Any],
    rows: list[dict[str, str]],
    contexts: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    manifest_path = Path(config["inputs"]["hardnegative_matched"]["manifest"])
    representative_ids = sorted({row["paired_representative_protein_id"] for row in rows})
    runs: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="djrmcp-schema5-hardneg-reps-") as raw_tmp:
        base = Path(raw_tmp)
        for model_id in MODELS:
            member = _load_schema5_h1_predictions(
                config,
                model_id,
                manifest_path,
                Path(config["embedding_registries"]["hardnegative_matched"][model_id]),
                contexts[model_id],
            )
            representative_dir = base / model_id
            representative_manifest = _write_subset_embedding_bundle(
                config, model_id, representative_ids, representative_dir
            )
            representative = _load_schema5_h1_predictions(
                config,
                model_id,
                representative_manifest,
                representative_dir,
                contexts[model_id],
            )
            if float(member["threshold"]) != float(representative["threshold"]):
                raise RuntimeError("HardNeg member/representative H1 threshold mismatch")
            runs[model_id] = {
                "member": member,
                "representative": representative,
                "provenance": {
                    "member": member["provenance"],
                    "representative_validation_subset": representative["provenance"],
                    "representative_subset_records": len(representative_ids),
                    "test_vectors_selected_for_inference": 0,
                    "test_predictions_or_metrics_computed": 0,
                },
            }
    return runs


def _hardnegative_prediction_rows(
    rows: list[dict[str, str]], runs: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for model_id in MODELS:
        member = runs[model_id]["member"]
        representative = runs[model_id]["representative"]
        threshold = float(member["threshold"])
        for row in rows:
            if (
                row["source_dataset"] != "hard_non_djr"
                or _as_int(row.get("score_head1", 0)) != 1
                or _as_int(row.get("score_head2", 0)) != 0
                or _as_int(row.get("h3_analysis_included", 0)) != 0
                or _as_int(row.get("test_record", 0)) != 0
            ):
                raise RuntimeError("Illegal HardNeg source/head/Test contract")
            protein_id = row["protein_id"]
            representative_id = row["paired_representative_protein_id"]
            member_probability = float(member["probability"][protein_id])
            rep_probability = float(representative["probability"][representative_id])
            member_prediction = int(member_probability >= threshold)
            rep_prediction = int(rep_probability >= threshold)
            output.append(
                {
                    "model_id": model_id,
                    "protein_id": protein_id,
                    "source_dataset": "hard_non_djr",
                    "paired_representative_id": row["paired_representative_id"],
                    "paired_representative_protein_id": representative_id,
                    "source_cluster_id": row["source_cluster_id"],
                    "source_cluster_key": _source_cluster_key(row),
                    "dependence_block_id": row["dependence_block_id"],
                    "train_relationship_stratum": row.get("train_relationship_stratum", ""),
                    "head": "head1",
                    "truth_label": "non_djr",
                    "expected_prediction": 0,
                    "member_probability": member_probability,
                    "member_raw_decision_score": member["raw_score"][protein_id],
                    "member_prediction": member_prediction,
                    "member_predicted_label": _binary_label("head1", member_prediction),
                    "member_correct": int(member_prediction == 0),
                    "representative_probability": rep_probability,
                    "representative_raw_decision_score": representative["raw_score"][representative_id],
                    "representative_prediction": rep_prediction,
                    "representative_predicted_label": _binary_label("head1", rep_prediction),
                    "representative_correct": int(rep_prediction == 0),
                    "threshold": threshold,
                    "applicable_to_source": 1,
                    "metric_eligible": 1,
                    "test_record": 0,
                }
            )
    return output


def _validate_input_identity(config: dict[str, Any]) -> None:
    for shard, spec in config["inputs"].items():
        manifest = Path(spec["manifest"])
        fasta = Path(spec["fasta"])
        if _sha256(manifest) != spec["manifest_sha256"] or _sha256(fasta) != spec["fasta_sha256"]:
            raise RuntimeError(f"Frozen schema-5 input identity changed: {shard}")
        if len(_read_tsv(manifest)) != int(spec["expected_records"]):
            raise RuntimeError(f"Frozen schema-5 input record count changed: {shard}")


def _load_single_model_predictions(
    config: dict[str, Any]
) -> tuple[list[dict[str, object]], dict[str, Any]]:
    schema4_config = yaml.safe_load(Path(config["schema4_config"]).read_text(encoding="utf-8"))
    runtime, _schema3_path = _schema3_runtime_config(config, schema4_config)
    family_manifest = Path(schema4_config["schema3"]["family_member_manifest"])
    family_rows = _read_tsv(family_manifest)
    if (
        not family_rows
        or {row["source_dataset"] for row in family_rows} != set(SOURCES[:-1])
        or any(_as_int(row.get("test_record", 0)) for row in family_rows)
    ):
        raise RuntimeError("Schema-4 three-source legal cohort changed")
    contexts = _build_model_contexts(config)
    family_runs = {
        model_id: _load_schema5_family_predictions(
            runtime, model_id, family_rows, contexts[model_id]
        )
        for model_id in MODELS
    }
    hard_manifest = Path(config["inputs"]["hardnegative_matched"]["manifest"])
    hard_rows = _read_tsv(hard_manifest)
    if not hard_rows or any(_as_int(row.get("test_record", 0)) for row in hard_rows):
        raise RuntimeError("HardNeg legal cohort is empty or contains Test")
    hard_runs = _hardnegative_runs(config, hard_rows, contexts)
    rows = _family_prediction_rows(family_rows, family_runs)
    rows.extend(_hardnegative_prediction_rows(hard_rows, hard_runs))
    if {str(row["model_id"]) for row in rows} != set(MODELS):
        raise RuntimeError("Eight-model prediction materialization is incomplete")
    return rows, {
        "family_manifest": str(family_manifest),
        "family_manifest_sha256": _sha256(family_manifest),
        "family_records": len(family_rows),
        "hardnegative_manifest": str(hard_manifest),
        "hardnegative_manifest_sha256": _sha256(hard_manifest),
        "hardnegative_records": len(hard_rows),
        "models": {
            model_id: {
                "schema3": family_runs[model_id]["provenance"],
                "hardnegative": hard_runs[model_id]["provenance"],
            }
            for model_id in MODELS
        },
    }


def _load_h3_rare_subgroups(
    config: Mapping[str, Any], inference_provenance: Mapping[str, Any]
) -> dict[str, str]:
    """Derive the Amendment-D 7+1 display split from the frozen manifest.

    This join occurs after per-record inference and changes no prediction,
    threshold, calibration, CV score, or candidate order.  The high-volume
    prediction tables intentionally retain their Amendment-C byte schema.
    """

    schema4_config = yaml.safe_load(
        Path(str(config["schema4_config"])).read_text(encoding="utf-8")
    )
    manifest = Path(schema4_config["schema3"]["family_member_manifest"])
    manifest_sha256 = _sha256(manifest)
    if (
        str(manifest) != str(inference_provenance["family_manifest"])
        or manifest_sha256 != str(inference_provenance["family_manifest_sha256"])
        or manifest_sha256 != SCHEMA3_FAMILY_MEMBER_MANIFEST_SHA256
        or manifest_sha256 != str(config["schema3_family_member_manifest_sha256"])
    ):
        raise RuntimeError("Frozen family manifest lineage changed before H3 subgroup join")
    subgroup_by_id: dict[str, str] = {}
    support: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _read_tsv(manifest):
        if (
            row["source_dataset"] != "viral_vma_djr"
            or _as_int(row.get("h3_analysis_included", 0)) != 1
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
        protein_id = row["protein_id"]
        if protein_id in subgroup_by_id:
            raise RuntimeError(f"Duplicate H3 subgroup protein ID: {protein_id}")
        subgroup_by_id[protein_id] = subgroup
        support[subgroup].append(row)
    expected = {
        "Produgelaviricota": (7, 2, 2),
        "literature-unclassified": (1, 1, 1),
    }
    observed = {
        subgroup: (
            len(rows),
            len({_source_cluster_key(row) for row in rows}),
            len({row["dependence_block_id"] for row in rows}),
        )
        for subgroup, rows in support.items()
    }
    if observed != expected or len(subgroup_by_id) != 8:
        raise RuntimeError(
            f"Frozen H3 subgroup support changed: observed={observed}, expected={expected}"
        )
    return subgroup_by_id


def build_system_registry(config: Mapping[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {
            "system_id": model_id,
            "system_type": "homogeneous_model",
            "head1_model": model_id,
            "head2_model": model_id,
            "head3_model": model_id,
            "primary_mixed_candidate": 0,
            "prediction_alias_of": "",
            "unique_prediction_system": 1,
            "selection_role": "descriptive_comparator",
        }
        for model_id in MODELS
    ]
    for candidate in config["primary_mixed_candidates"]:
        candidate_id = candidate["candidate_id"]
        alias = REFERENCE_SYSTEM if candidate_id == _candidate_id("esmc_6b", "esmc_6b") else ""
        rows.append(
            {
                "system_id": candidate_id,
                "system_type": "mixed_head_candidate",
                "head1_model": candidate["head1_model"],
                "head2_model": candidate["head2_model"],
                "head3_model": candidate["head3_model"],
                "primary_mixed_candidate": 1,
                "prediction_alias_of": alias,
                "unique_prediction_system": int(not alias),
                "selection_role": "train_cv_candidate_external_confirmation_only",
            }
        )
    if len(rows) != 17 or sum(int(row["unique_prediction_system"]) for row in rows) != 16:
        raise RuntimeError("Expected 17 labels representing 16 unique systems")
    return rows


def compose_system_predictions(
    single_rows: list[dict[str, object]], registry: list[dict[str, object]]
) -> list[dict[str, object]]:
    index: dict[tuple[str, str, str], dict[str, object]] = {}
    per_model_keys: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in single_rows:
        key = (str(row["model_id"]), str(row["protein_id"]), str(row["head"]))
        if key in index:
            raise RuntimeError(f"Duplicate single-model prediction key: {key}")
        index[key] = row
        per_model_keys[key[0]].add((key[1], key[2]))
    if set(per_model_keys) != set(MODELS):
        raise RuntimeError("Single-model prediction registry is incomplete")
    reference_keys = per_model_keys[MODELS[0]]
    if any(per_model_keys[model] != reference_keys for model in MODELS[1:]):
        raise RuntimeError("Eight models were not scored on identical legal source/head rows")
    output: list[dict[str, object]] = []
    for system in registry:
        for protein_id, head in sorted(reference_keys):
            source_model = str(
                system[
                    {
                        "head1": "head1_model",
                        "head2": "head2_model",
                        "head3_phylum": "head3_model",
                    }[head]
                ]
            )
            source = index[(source_model, protein_id, head)]
            copied = {key: value for key, value in source.items() if key != "model_id"}
            output.append(
                {
                    "system_id": system["system_id"],
                    "system_type": system["system_type"],
                    "head_model_id": source_model,
                    "head1_model": system["head1_model"],
                    "head2_model": system["head2_model"],
                    "head3_model": system["head3_model"],
                    **copied,
                }
            )
    # Positive control: the all-6B mixed label must be a byte-equivalent value
    # projection of the homogeneous all-6B predictions for every legal row.
    fields = [
        key
        for key in output[0]
        if key not in {"system_id", "system_type", "head1_model", "head2_model", "head3_model"}
    ]
    by_system: dict[str, dict[tuple[str, str], dict[str, object]]] = defaultdict(dict)
    for row in output:
        by_system[str(row["system_id"])][(str(row["protein_id"]), str(row["head"]))] = row
    positive = _candidate_id("esmc_6b", "esmc_6b")
    if set(by_system[positive]) != set(by_system[REFERENCE_SYSTEM]):
        raise RuntimeError("All-6B positive-control keys differ")
    for key in by_system[positive]:
        if any(by_system[positive][key][field] != by_system[REFERENCE_SYSTEM][key][field] for field in fields):
            raise RuntimeError(f"All-6B positive-control mismatch: {key}")
    return output


def build_path_rows(predictions: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in predictions:
        grouped[(str(row["system_id"]), str(row["protein_id"]))].append(row)
    output: list[dict[str, object]] = []
    for (_system, _protein), records in sorted(grouped.items()):
        first = records[0]
        source = str(first["source_dataset"])
        if any(str(row["source_dataset"]) != source for row in records):
            raise RuntimeError("One system/protein maps to multiple sources")
        eligible = [row for row in records if _as_int(row["metric_eligible"]) == 1]
        ordered = sorted(eligible, key=lambda row: APPLICABLE_HEADS[source].index(str(row["head"])))
        if not ordered:
            raise RuntimeError("Path record has no metric-eligible head")
        output.append(
            {
                "system_id": first["system_id"],
                "system_type": first["system_type"],
                "head1_model": first["head1_model"],
                "head2_model": first["head2_model"],
                "head3_model": first["head3_model"],
                "protein_id": first["protein_id"],
                "source_dataset": source,
                "paired_representative_id": first["paired_representative_id"],
                "source_cluster_id": first["source_cluster_id"],
                "source_cluster_key": first["source_cluster_key"],
                "dependence_block_id": first["dependence_block_id"],
                "path_id": PATH_ID,
                "expected_path": ">".join(str(row["truth_label"]) for row in ordered),
                "member_observed_path": ">".join(
                    str(row["member_predicted_label"]) for row in ordered
                ),
                "representative_observed_path": ">".join(
                    str(row["representative_predicted_label"]) for row in ordered
                ),
                "member_correct": int(all(_as_int(row["member_correct"]) for row in ordered)),
                "representative_correct": int(
                    all(_as_int(row["representative_correct"]) for row in ordered)
                ),
                "n_applicable_heads": len(ordered),
                "test_record": 0,
            }
        )
    return output


def nested_values(
    rows: list[Mapping[str, Any]],
) -> tuple[list[str], np.ndarray, np.ndarray, list[int]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["dependence_block_id"]), str(row["source_cluster_key"]))].append(row)
    if not grouped:
        raise RuntimeError("Cannot summarize an empty endpoint")
    rep_by_block: dict[str, list[float]] = defaultdict(list)
    member_by_block: dict[str, list[float]] = defaultdict(list)
    cluster_all: list[int] = []
    for (block, _cluster), members in sorted(grouped.items()):
        representative = {_as_int(row["representative_correct"]) for row in members}
        if len(representative) != 1:
            raise RuntimeError("Representative correctness changed within a source cluster")
        member_values = [float(_as_int(row["member_correct"])) for row in members]
        rep_by_block[block].append(float(next(iter(representative))))
        member_by_block[block].append(float(np.mean(member_values)))
        cluster_all.append(int(all(member_values)))
    blocks = sorted(member_by_block)
    representative = np.asarray([np.mean(rep_by_block[block]) for block in blocks], dtype=float)
    member = np.asarray([np.mean(member_by_block[block]) for block in blocks], dtype=float)
    return blocks, representative, member, cluster_all


def paired_bootstrap(
    representative: np.ndarray,
    member: np.ndarray,
    *,
    replicates: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if representative.ndim != 1 or member.ndim != 1 or len(representative) != len(member) or not len(member):
        raise RuntimeError("Invalid paired dependence-block arrays")
    rng = np.random.default_rng(seed)
    rep_draws = np.empty(replicates, dtype=float)
    member_draws = np.empty(replicates, dtype=float)
    for start in range(0, replicates, 256):
        stop = min(start + 256, replicates)
        selected = rng.integers(0, len(member), size=(stop - start, len(member)))
        rep_draws[start:stop] = representative[selected].mean(axis=1)
        member_draws[start:stop] = member[selected].mean(axis=1)
    return rep_draws, member_draws, member_draws - rep_draws


def nested_summary(
    rows: list[Mapping[str, Any]], *, replicates: int, seed: int
) -> tuple[dict[str, object], tuple[np.ndarray, np.ndarray, np.ndarray], list[str]]:
    blocks, representative, member, cluster_all = nested_values(rows)
    boot = paired_bootstrap(representative, member, replicates=replicates, seed=seed)
    payload: dict[str, object] = {
        "representative_value": float(representative.mean()),
        "representative_ci_low": float(np.quantile(boot[0], 0.025)),
        "representative_ci_high": float(np.quantile(boot[0], 0.975)),
        "member_value": float(member.mean()),
        "member_ci_low": float(np.quantile(boot[1], 0.025)),
        "member_ci_high": float(np.quantile(boot[1], 0.975)),
        "delta_members_minus_representative": float(member.mean() - representative.mean()),
        "delta_ci_low": float(np.quantile(boot[2], 0.025)),
        "delta_ci_high": float(np.quantile(boot[2], 0.975)),
        "n_member_records": len(rows),
        "n_source_clusters": len({(str(r["dependence_block_id"]), str(r["source_cluster_key"])) for r in rows}),
        "n_dependence_blocks": len(blocks),
        "clusters_all_members_correct": int(sum(cluster_all)),
        "proportion_clusters_all_members_correct": float(np.mean(cluster_all)),
        "bootstrap_replicates": replicates,
        "bootstrap_seed": seed,
        "bootstrap_unit": "dependence_block",
        "weighting": WEIGHTING,
    }
    return payload, boot, blocks


def _f1_summary(
    rows: list[Mapping[str, Any]], target: str, *, replicates: int, seed: int
) -> dict[str, object]:
    blocks = sorted({str(row["dependence_block_id"]) for row in rows})
    block_index = {block: index for index, block in enumerate(blocks)}
    clusters_by_block: dict[str, set[str]] = defaultdict(set)
    records_by_cluster: Counter[tuple[str, str]] = Counter()
    for row in rows:
        block = str(row["dependence_block_id"])
        cluster = str(row["source_cluster_key"])
        clusters_by_block[block].add(cluster)
        records_by_cluster[(block, cluster)] += 1
    representative = np.zeros((len(blocks), 3), dtype=float)
    member = np.zeros_like(representative)
    for row in rows:
        block = str(row["dependence_block_id"])
        cluster = str(row["source_cluster_key"])
        weight = 1.0 / len(clusters_by_block[block]) / records_by_cluster[(block, cluster)]
        truth_positive = str(row["truth_label"]) == target
        for role, matrix in (("representative", representative), ("member", member)):
            predicted_positive = str(row[f"{role}_predicted_label"]) == target
            if truth_positive and predicted_positive:
                column = 0
            elif not truth_positive and predicted_positive:
                column = 1
            elif truth_positive:
                column = 2
            else:
                continue
            matrix[block_index[block], column] += weight

    def f1(contribution: np.ndarray) -> np.ndarray:
        denominator = 2 * contribution[..., 0] + contribution[..., 1] + contribution[..., 2]
        return np.divide(
            2 * contribution[..., 0],
            denominator,
            out=np.zeros_like(denominator),
            where=denominator != 0,
        )

    rep_value = float(f1(representative.sum(axis=0)))
    member_value = float(f1(member.sum(axis=0)))
    rng = np.random.default_rng(seed)
    rep_boot = np.empty(replicates, dtype=float)
    member_boot = np.empty(replicates, dtype=float)
    for start in range(0, replicates, 256):
        stop = min(start + 256, replicates)
        selected = rng.integers(0, len(blocks), size=(stop - start, len(blocks)))
        rep_boot[start:stop] = f1(representative[selected].sum(axis=1))
        member_boot[start:stop] = f1(member[selected].sum(axis=1))
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
        "bootstrap_replicates": replicates,
        "bootstrap_seed": seed,
        "bootstrap_unit": "dependence_block",
        "weighting": WEIGHTING,
    }


def _macro_f1_summary(
    rows: list[Mapping[str, Any]],
    targets: Sequence[str],
    *,
    replicates: int,
    seed: int,
) -> dict[str, object]:
    blocks = sorted({str(row["dependence_block_id"]) for row in rows})
    block_index = {block: index for index, block in enumerate(blocks)}
    clusters_by_block: dict[str, set[str]] = defaultdict(set)
    records_by_cluster: Counter[tuple[str, str]] = Counter()
    for row in rows:
        block, cluster = str(row["dependence_block_id"]), str(row["source_cluster_key"])
        clusters_by_block[block].add(cluster)
        records_by_cluster[(block, cluster)] += 1
    rep = np.zeros((len(targets), len(blocks), 3), dtype=float)
    member = np.zeros_like(rep)
    for row in rows:
        block, cluster = str(row["dependence_block_id"]), str(row["source_cluster_key"])
        weight = 1.0 / len(clusters_by_block[block]) / records_by_cluster[(block, cluster)]
        for target_index, target in enumerate(targets):
            truth_positive = str(row["truth_label"]) == target
            for role, matrix in (("representative", rep), ("member", member)):
                predicted_positive = str(row[f"{role}_predicted_label"]) == target
                if truth_positive and predicted_positive:
                    column = 0
                elif not truth_positive and predicted_positive:
                    column = 1
                elif truth_positive:
                    column = 2
                else:
                    continue
                matrix[target_index, block_index[block], column] += weight

    def macro(contribution: np.ndarray) -> np.ndarray:
        # contribution shape: target x (...bootstrap...) x confusion-column
        denominator = 2 * contribution[..., 0] + contribution[..., 1] + contribution[..., 2]
        values = np.divide(
            2 * contribution[..., 0],
            denominator,
            out=np.zeros_like(denominator),
            where=denominator != 0,
        )
        return values.mean(axis=0)

    rep_value = float(macro(rep.sum(axis=1)))
    member_value = float(macro(member.sum(axis=1)))
    rng = np.random.default_rng(seed)
    rep_boot = np.empty(replicates, dtype=float)
    member_boot = np.empty(replicates, dtype=float)
    for start in range(0, replicates, 256):
        stop = min(start + 256, replicates)
        selected = rng.integers(0, len(blocks), size=(stop - start, len(blocks)))
        rep_contribution = np.stack([rep[:, index, :].sum(axis=1) for index in selected])
        member_contribution = np.stack(
            [member[:, index, :].sum(axis=1) for index in selected]
        )
        # stacked shape is batch x targets x 3; transpose target first.
        rep_boot[start:stop] = macro(np.moveaxis(rep_contribution, 1, 0))
        member_boot[start:stop] = macro(np.moveaxis(member_contribution, 1, 0))
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
        "bootstrap_replicates": replicates,
        "bootstrap_seed": seed,
        "bootstrap_unit": "dependence_block",
        "weighting": WEIGHTING,
    }


def _raw_reject_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    representative_by_parent: dict[tuple[str, str], int] = {}
    member_k = 0
    for row in rows:
        member_k += int(str(row["member_predicted_label"]) == "unknown/other")
        parent = (str(row["dependence_block_id"]), str(row["source_cluster_key"]))
        value = int(str(row["representative_predicted_label"]) == "unknown/other")
        if parent in representative_by_parent and representative_by_parent[parent] != value:
            raise RuntimeError("H3 representative reject call changed inside a parent")
        representative_by_parent[parent] = value
    return {
        "raw_member_reject_k": member_k,
        "raw_member_reject_n": len(rows),
        "raw_representative_reject_k": sum(representative_by_parent.values()),
        "raw_representative_reject_n": len(representative_by_parent),
    }


def _finalize_h3_reject_uncertainty(
    values: Mapping[str, object], *, dependence_blocks: int
) -> tuple[dict[str, object], str]:
    finalized = dict(values)
    if dependence_blocks == 1:
        for field in (
            "representative_ci_low",
            "representative_ci_high",
            "member_ci_low",
            "member_ci_high",
            "delta_ci_low",
            "delta_ci_high",
        ):
            finalized[field] = ""
        finalized["bootstrap_replicates"] = 0
        return finalized, "point_only_ci_not_estimable_single_block"
    return finalized, "complete_fixed_seed_nested_block_bootstrap"


def summarize_systems(
    predictions: list[dict[str, object]],
    paths: list[dict[str, object]],
    registry: list[dict[str, object]],
    h3_rare_subgroups: Mapping[str, str],
    *,
    replicates: int,
    base_seed: int,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    dict[tuple[str, str], np.ndarray],
]:
    head_summary: list[dict[str, object]] = []
    path_summary: list[dict[str, object]] = []
    strict: list[dict[str, object]] = []
    h3_summary: list[dict[str, object]] = []
    bootstrap_rows: list[dict[str, object]] = []
    path_boot: dict[tuple[str, str], np.ndarray] = {}
    for system in registry:
        system_id = str(system["system_id"])
        for source in SOURCES:
            for head in APPLICABLE_HEADS[source]:
                selected = [
                    row
                    for row in predictions
                    if row["system_id"] == system_id
                    and row["source_dataset"] == source
                    and row["head"] == head
                    and _as_int(row["metric_eligible"]) == 1
                ]
                if not selected:
                    raise RuntimeError(f"Missing source/head endpoint: {system_id}/{source}/{head}")
                seed = base_seed + HEAD_SEED_OFFSET[(source, head)]
                values, _boot, _blocks = nested_summary(selected, replicates=replicates, seed=seed)
                metric = (
                    "expected_label_accuracy"
                    if head == "head3_phylum"
                    else EXPECTED_BINARY[(source, head)][2]
                )
                head_summary.append(
                    {
                        "system_id": system_id,
                        "system_type": system["system_type"],
                        "head_model_id": selected[0]["head_model_id"],
                        "source_dataset": source,
                        "head": head,
                        "metric": metric,
                        **values,
                    }
                )
                strict.append(
                    {
                        "system_id": system_id,
                        "source_dataset": source,
                        "endpoint_id": head,
                        "head_or_path": "head",
                        "n_clusters": values["n_source_clusters"],
                        "clusters_all_members_correct": values["clusters_all_members_correct"],
                        "proportion_clusters_all_members_correct": values[
                            "proportion_clusters_all_members_correct"
                        ],
                    }
                )
            selected_paths = [
                row
                for row in paths
                if row["system_id"] == system_id and row["source_dataset"] == source
            ]
            seed = base_seed + PATH_SEED_OFFSET[source]
            values, boot, blocks = nested_summary(selected_paths, replicates=replicates, seed=seed)
            path_boot[(system_id, source)] = boot[1]
            path_summary.append(
                {
                    "system_id": system_id,
                    "system_type": system["system_type"],
                    "head1_model": system["head1_model"],
                    "head2_model": system["head2_model"],
                    "head3_model": system["head3_model"],
                    "source_dataset": source,
                    "path_id": PATH_ID,
                    "metric": "expected_path_accuracy",
                    **values,
                }
            )
            strict.append(
                {
                    "system_id": system_id,
                    "source_dataset": source,
                    "endpoint_id": PATH_ID,
                    "head_or_path": "path",
                    "n_clusters": values["n_source_clusters"],
                    "clusters_all_members_correct": values["clusters_all_members_correct"],
                    "proportion_clusters_all_members_correct": values[
                        "proportion_clusters_all_members_correct"
                    ],
                }
            )
            for index, (rep, member, delta) in enumerate(zip(*boot, strict=True), 1):
                bootstrap_rows.append(
                    {
                        "bootstrap_index": index,
                        "system_id": system_id,
                        "source_dataset": source,
                        "endpoint_id": PATH_ID,
                        "representative_value": rep,
                        "member_value": member,
                        "delta_member_minus_representative": delta,
                        "bootstrap_seed": seed,
                        "n_dependence_blocks": len(blocks),
                    }
                )
        h3_rows = [
            row
            for row in predictions
            if row["system_id"] == system_id
            and row["source_dataset"] == "viral_vma_djr"
            and row["head"] == "head3_phylum"
            and _as_int(row["metric_eligible"]) == 1
        ]
        known = [row for row in h3_rows if row["truth_label"] in KNOWN_H3_CLASSES]
        class_f1_values: list[dict[str, object]] = []
        for class_index, label in enumerate(KNOWN_H3_CLASSES):
            values = _f1_summary(
                known,
                label,
                replicates=replicates,
                seed=base_seed + 6_000 + class_index,
            )
            row = {
                "system_id": system_id,
                "head3_model": system["head3_model"],
                "endpoint_id": f"{label}_f1",
                "diagnostic_group": "known_phylum",
                "truth_label": label,
                "metric": "f1",
                "endpoint_role": "primary_known_class",
                **values,
                "n_truth_records": sum(item["truth_label"] == label for item in known),
                "n_evaluation_records": len(known),
                "raw_member_reject_k": "",
                "raw_member_reject_n": "",
                "raw_representative_reject_k": "",
                "raw_representative_reject_n": "",
                "bootstrap_status": "complete_fixed_seed_nested_block_bootstrap",
                "interpretation": "two_known_inherited_phyla_only",
            }
            h3_summary.append(row)
            class_f1_values.append(row)
        macro_values = _macro_f1_summary(
            known,
            KNOWN_H3_CLASSES,
            replicates=replicates,
            seed=base_seed + 6_020,
        )
        h3_summary.append(
            {
                "system_id": system_id,
                "head3_model": system["head3_model"],
                "endpoint_id": "known_two_phylum_macro_f1",
                "diagnostic_group": "known_phylum",
                "truth_label": "Nucleocytoviricota|Preplasmiviricota",
                "metric": "macro_f1",
                "endpoint_role": "primary_known_macro",
                **macro_values,
                "n_truth_records": len(known),
                "n_evaluation_records": len(known),
                "raw_member_reject_k": "",
                "raw_member_reject_n": "",
                "raw_representative_reject_k": "",
                "raw_representative_reject_n": "",
                "bootstrap_status": "complete_fixed_seed_nested_block_bootstrap",
                "interpretation": "two_known_inherited_phyla_only",
            }
        )
        unknown = [row for row in h3_rows if row["truth_label"] not in KNOWN_H3_CLASSES]
        if len(unknown) != 8 or len({row["source_cluster_key"] for row in unknown}) != 3:
            raise RuntimeError("Frozen H3 rare family must be exactly 8 relations / 3 parents")
        if set(h3_rare_subgroups) != {str(row["protein_id"]) for row in unknown}:
            raise RuntimeError("Frozen H3 subgroup join does not exactly cover the 8 unknown rows")
        subgroup_specs = (
            (
                "Produgelaviricota_reject_recall",
                "rare_formal_phylum_rejection",
                "Produgelaviricota",
                [
                    row
                    for row in unknown
                    if h3_rare_subgroups[str(row["protein_id"])] == "Produgelaviricota"
                ],
            ),
            (
                "literature_unclassified_reject_recall",
                "literature_unclassified_rejection",
                "literature-unclassified",
                [
                    row
                    for row in unknown
                    if h3_rare_subgroups[str(row["protein_id"])]
                    == "literature-unclassified"
                ],
            ),
            (
                "rare_or_unclassified_reject_recall",
                "small_prespecified_rejection",
                "unknown/other",
                unknown,
            ),
        )
        for endpoint_id, group, truth_label, selected in subgroup_specs:
            contract = H3_RARE_ENDPOINT_CONTRACT[endpoint_id]
            if (
                len(selected) != contract["expected_records"]
                or len({str(row["source_cluster_key"]) for row in selected})
                != contract["expected_parents"]
                or len({str(row["dependence_block_id"]) for row in selected})
                != contract["expected_dependence_blocks"]
            ):
                raise RuntimeError(f"Frozen H3 subgroup support changed: {endpoint_id}")
            values, _boot, _blocks = nested_summary(
                selected,
                replicates=replicates,
                seed=base_seed + int(contract["bootstrap_seed_offset"]),
            )
            values, bootstrap_status = _finalize_h3_reject_uncertainty(
                values,
                dependence_blocks=int(contract["expected_dependence_blocks"]),
            )
            h3_summary.append(
                {
                    "system_id": system_id,
                    "head3_model": system["head3_model"],
                    "endpoint_id": endpoint_id,
                    "diagnostic_group": group,
                    "truth_label": truth_label,
                    "metric": "reject_recall",
                    "endpoint_role": contract["endpoint_role"],
                    **values,
                    "n_truth_records": len(selected),
                    "n_evaluation_records": len(selected),
                    **_raw_reject_counts(selected),
                    "bootstrap_status": bootstrap_status,
                    "interpretation": contract["interpretation"],
                }
            )
    return head_summary, path_summary, strict, h3_summary, bootstrap_rows, path_boot


def _holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    ordered = sorted(p_values, key=lambda key: (p_values[key], key))
    adjusted: dict[str, float] = {}
    running = 0.0
    count = len(ordered)
    for rank, key in enumerate(ordered):
        value = min(1.0, (count - rank) * float(p_values[key]))
        running = max(running, value)
        adjusted[key] = running
    return adjusted


def pairwise_source_deltas(
    config: Mapping[str, Any],
    path_summary: list[dict[str, object]],
    path_boot: Mapping[tuple[str, str], np.ndarray],
) -> list[dict[str, object]]:
    point = {
        (str(row["system_id"]), str(row["source_dataset"])): float(row["member_value"])
        for row in path_summary
    }
    rows: list[dict[str, object]] = []
    for source in SOURCES:
        provisional: list[dict[str, object]] = []
        p_values: dict[str, float] = {}
        for candidate in config["primary_mixed_candidates"]:
            candidate_id = candidate["candidate_id"]
            candidate_draws = path_boot[(candidate_id, source)]
            reference_draws = path_boot[(REFERENCE_SYSTEM, source)]
            if candidate_draws.shape != reference_draws.shape:
                raise RuntimeError("Paired source-path bootstrap arrays differ in shape")
            delta = candidate_draws - reference_draws
            positive_control = candidate_id == _candidate_id("esmc_6b", "esmc_6b")
            if positive_control and (not np.array_equal(delta, np.zeros_like(delta))):
                raise RuntimeError("All-6B positive-control bootstrap is not exactly zero")
            raw_p = 1.0 if positive_control else min(
                1.0,
                (1.0 + float(np.count_nonzero(delta >= 0.0))) / (len(delta) + 1.0),
            )
            if not positive_control:
                p_values[candidate_id] = raw_p
            provisional.append(
                {
                    "candidate_id": candidate_id,
                    "reference_system_id": REFERENCE_SYSTEM,
                    "source_dataset": source,
                    "endpoint_id": PATH_ID,
                    "candidate_member_value": point[(candidate_id, source)],
                    "reference_member_value": point[(REFERENCE_SYSTEM, source)],
                    "delta_candidate_minus_reference": point[(candidate_id, source)]
                    - point[(REFERENCE_SYSTEM, source)],
                    "delta_ci_low": float(np.quantile(delta, 0.025)),
                    "delta_ci_high": float(np.quantile(delta, 0.975)),
                    "one_sided_inferiority_p": raw_p,
                    "positive_control": int(positive_control),
                    "holm_family": f"eight_nontrivial_candidates__{source}",
                    "bootstrap_replicates": len(delta),
                    "bootstrap_seed": int(config["bootstrap_seed"])
                    + PATH_SEED_OFFSET[source],
                }
            )
        adjusted = _holm_adjust(p_values)
        for row in provisional:
            candidate_id = str(row["candidate_id"])
            p_adjusted = 1.0 if _as_int(row["positive_control"]) else adjusted[candidate_id]
            row["holm_adjusted_p"] = p_adjusted
            row["diagnostic_status"] = (
                "positive_control_exact_equivalence"
                if _as_int(row["positive_control"])
                else (
                    "source_specific_inferiority_warning"
                    if p_adjusted < 0.05 and float(row["delta_ci_high"]) < 0.0
                    else "no_established_source_specific_inferiority"
                )
            )
            rows.append(row)
    if len(rows) != 36:
        raise RuntimeError("Expected nine candidates by four source-specific comparisons")
    return rows


def contextual_source_deltas(
    config: Mapping[str, Any],
    path_summary: list[dict[str, object]],
    path_boot: Mapping[tuple[str, str], np.ndarray],
) -> list[dict[str, object]]:
    """Descriptive non-selection deltas versus the contextual 650M reference."""

    reference = str(config["contextual_reference_model_id"])
    point = {
        (str(row["system_id"]), str(row["source_dataset"])): float(row["member_value"])
        for row in path_summary
    }
    rows: list[dict[str, object]] = []
    for source in ("cellular_djr_none", "background_non_djr", "hard_non_djr"):
        for candidate in config["primary_mixed_candidates"]:
            candidate_id = candidate["candidate_id"]
            delta = path_boot[(candidate_id, source)] - path_boot[(reference, source)]
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "contextual_reference_system_id": reference,
                    "source_dataset": source,
                    "endpoint_id": PATH_ID,
                    "candidate_member_value": point[(candidate_id, source)],
                    "reference_member_value": point[(reference, source)],
                    "delta_candidate_minus_reference": point[(candidate_id, source)]
                    - point[(reference, source)],
                    "delta_ci_low": float(np.quantile(delta, 0.025)),
                    "delta_ci_high": float(np.quantile(delta, 0.975)),
                    "bootstrap_replicates": len(delta),
                    "bootstrap_seed": int(config["bootstrap_seed"])
                    + PATH_SEED_OFFSET[source],
                    "comparison_role": "descriptive_context_only_not_reranking_not_holm_family",
                }
            )
    if len(rows) != 27:
        raise RuntimeError("Expected nine by three contextual 650M comparisons")
    return rows


def _comparison_table_path(config: Mapping[str, Any]) -> Path:
    configured = config.get("model_comparison_table")
    if configured:
        return Path(str(configured))
    return Path(str(config["comparison_summary"])).with_name("model_comparison.tsv")


def load_model_costs(config: Mapping[str, Any]) -> list[dict[str, object]]:
    table = _read_tsv(_comparison_table_path(config))
    by_model = {row["model_id"]: row for row in table}
    if not set(MODELS) <= set(by_model):
        raise RuntimeError("Frozen comparison table lacks a schema-5 model")
    rows: list[dict[str, object]] = []
    for model_id in MODELS:
        source = by_model[model_id]
        gpu_seconds = float(source["gpu_seconds_per_sequence"])
        peak_memory = int(source["peak_gpu_memory_bytes"])
        representative_unknown_n = int(source["val_head3_unknown_diagnostic_n"])
        if (
            not math.isfinite(gpu_seconds)
            or gpu_seconds <= 0
            or peak_memory <= 0
            or representative_unknown_n != 5
        ):
            raise RuntimeError(f"Invalid deployment-cost evidence: {model_id}")
        rows.append(
            {
                "model_id": model_id,
                "label": source["label"],
                "gpu_seconds_per_sequence": gpu_seconds,
                "peak_gpu_memory_bytes": peak_memory,
                "parameter_count": int(source["parameter_count"]),
                "resolved_model_revision": source["resolved_model_revision"],
                "representative_benchmark_h3_unknown_diagnostic_n": representative_unknown_n,
                "timing_source": source["embedding_timing_source"],
                "timing_comparability_key": source["timing_comparability_key"],
                "cost_role": "frozen_deployment_proxy_not_schema5_materialization_time",
            }
        )
    return rows


def train_cv_candidate_rows(
    config: Mapping[str, Any], model_costs: list[dict[str, object]]
) -> tuple[list[dict[str, object]], list[dict[str, object]], str]:
    fold_path = Path(str(config["comparison_summary"])).with_name("fold_scores.tsv")
    fold_rows = _read_tsv(fold_path)
    score_by_key = {
        (row["model_id"], row["head"], int(row["fold"])): float(row["score"])
        for row in fold_rows
    }
    weights = config["score_weights"]
    cost_by_model = {str(row["model_id"]): row for row in model_costs}
    rows: list[dict[str, object]] = []
    fold_values_by_candidate: dict[str, np.ndarray] = {}
    for candidate in config["primary_mixed_candidates"]:
        h12 = candidate["head1_model"]
        h3 = candidate["head3_model"]
        values = np.asarray(
            [
                float(weights["head1_ap"]) * score_by_key[(h12, "head1", fold)]
                + float(weights["head2_ap"]) * score_by_key[(h12, "head2", fold)]
                + float(weights["head3_known_macro_f1"])
                * score_by_key[(h3, "head3_phylum", fold)]
                for fold in range(1, 6)
            ],
            dtype=float,
        )
        fold_values_by_candidate[candidate["candidate_id"]] = values
        base_cost = float(cost_by_model[h12]["gpu_seconds_per_sequence"])
        conditional_cost = (
            0.0 if h12 == h3 else float(cost_by_model[h3]["gpu_seconds_per_sequence"])
        )
        rows.append(
            {
                "candidate_id": candidate["candidate_id"],
                "head1_model": h12,
                "head2_model": h12,
                "head3_model": h3,
                "fold1_score": values[0],
                "fold2_score": values[1],
                "fold3_score": values[2],
                "fold4_score": values[3],
                "fold5_score": values[4],
                "mean_train_cv_score": float(values.mean()),
                "train_cv_score_se": float(values.std(ddof=1) / math.sqrt(len(values))),
                "always_on_gpu_seconds_per_sequence": base_cost,
                "conditional_h3_gpu_seconds_per_sequence": conditional_cost,
                "worst_case_gpu_seconds_per_sequence": base_cost + conditional_cost,
                "peak_gpu_memory_bytes": max(
                    int(cost_by_model[h12]["peak_gpu_memory_bytes"]),
                    int(cost_by_model[h3]["peak_gpu_memory_bytes"]),
                ),
                "encoder_count": 1 if h12 == h3 else 2,
                "primary_evidence": "train_only_shared_five_fold_cv",
            }
        )
    best = min(
        rows,
        key=lambda row: (-float(row["mean_train_cv_score"]), str(row["candidate_id"])),
    )
    best_id = str(best["candidate_id"])
    best_values = fold_values_by_candidate[best_id]
    for row in rows:
        candidate_id = str(row["candidate_id"])
        delta = best_values - fold_values_by_candidate[candidate_id]
        paired_se = float(delta.std(ddof=1) / math.sqrt(len(delta)))
        row["best_mean_candidate_id"] = best_id
        row["difference_from_best_mean"] = float(best["mean_train_cv_score"]) - float(
            row["mean_train_cv_score"]
        )
        row["paired_delta_se_vs_best"] = paired_se
        row["within_one_paired_se"] = int(
            float(row["difference_from_best_mean"]) <= paired_se + 1e-15
        )
    one_se_rows = [row for row in rows if _as_int(row["within_one_paired_se"]) == 1]
    pareto: list[dict[str, object]] = []
    for row in rows:
        dominated_by: list[str] = []
        if _as_int(row["within_one_paired_se"]) == 1:
            for other in one_se_rows:
                if other is row:
                    continue
                no_worse = (
                    float(other["mean_train_cv_score"]) >= float(row["mean_train_cv_score"])
                    and float(other["always_on_gpu_seconds_per_sequence"])
                    <= float(row["always_on_gpu_seconds_per_sequence"])
                    and float(other["worst_case_gpu_seconds_per_sequence"])
                    <= float(row["worst_case_gpu_seconds_per_sequence"])
                    and int(other["peak_gpu_memory_bytes"]) <= int(row["peak_gpu_memory_bytes"])
                )
                strict = (
                    float(other["mean_train_cv_score"]) > float(row["mean_train_cv_score"])
                    or float(other["always_on_gpu_seconds_per_sequence"])
                    < float(row["always_on_gpu_seconds_per_sequence"])
                    or float(other["worst_case_gpu_seconds_per_sequence"])
                    < float(row["worst_case_gpu_seconds_per_sequence"])
                    or int(other["peak_gpu_memory_bytes"]) < int(row["peak_gpu_memory_bytes"])
                )
                if no_worse and strict:
                    dominated_by.append(str(other["candidate_id"]))
        pareto.append(
            {
                **row,
                "one_se_cost_accuracy_pareto": int(
                    _as_int(row["within_one_paired_se"]) == 1 and not dominated_by
                ),
                "dominated_by": ";".join(sorted(dominated_by)),
                "robustness_used_for_pareto_or_ordering": 0,
            }
        )
    frontier = [row for row in pareto if _as_int(row["one_se_cost_accuracy_pareto"]) == 1]
    if not frontier:
        raise RuntimeError("Train-CV one-SE Pareto frontier is empty")
    nominee = min(
        frontier,
        key=lambda row: (
            float(row["always_on_gpu_seconds_per_sequence"]),
            float(row["worst_case_gpu_seconds_per_sequence"]),
            int(row["peak_gpu_memory_bytes"]),
            str(row["candidate_id"]),
        ),
    )
    return rows, pareto, str(nominee["candidate_id"])


def _first(payload: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return default


def _read_attestation_jsons(directory: Path) -> list[tuple[Path, dict[str, Any]]]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Missing schema-5 receipt directory: {directory}")
    rows: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError(f"Receipt is not a JSON object: {path}")
        rows.append((path, payload))
    return rows


def validate_embedding_attestations(config: Mapping[str, Any]) -> list[dict[str, object]]:
    materialized_models = set(MODELS) - {"esm2_650m", "esmc_6b"}
    expected_new = {(model, shard) for model in materialized_models for shard in config["inputs"]}
    expected_reuse = {
        (model, shard) for model in ("esm2_650m", "esmc_6b") for shard in config["inputs"]
    }
    observed: dict[tuple[str, str], dict[str, object]] = {}
    comparison_rows = {
        row["model_id"]: row for row in _read_tsv(_comparison_table_path(config))
    }

    def consume(path: Path, payload: dict[str, Any], expected_kind: str) -> None:
        model_id = str(payload.get("model_id", ""))
        shard_id = str(payload.get("shard_id", ""))
        key = (model_id, shard_id)
        expected = expected_new if expected_kind == "materialization" else expected_reuse
        if key not in expected or key in observed:
            raise RuntimeError(f"Unexpected or duplicate {expected_kind} receipt: {path}")
        spec = config["inputs"][shard_id]
        output = Path(config["embedding_registries"][shard_id][model_id])
        checksums = output / "CHECKSUMS.sha256"
        _verify_flat_bundle(output)
        metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
        embedding = payload.get("embedding", {})
        required_fields = (
            "embedded_records",
            "test_records_embedded",
            "prediction_or_metric_records_created",
            "embedding_output",
            "embedding_checksums_sha256",
            "manifest_sha256",
            "fasta_sha256",
            "resolved_model_revision",
        )
        if any(field not in payload for field in required_fields):
            raise RuntimeError(f"Receipt/attestation lacks an explicit critical field: {path}")
        embedded_records = int(payload["embedded_records"])
        test_records = int(payload["test_records_embedded"])
        output_value = str(payload["embedding_output"])
        checksums_sha = str(payload["embedding_checksums_sha256"])
        expected_revision = str(comparison_rows[model_id]["resolved_model_revision"])
        if (
            payload.get("status") not in {"complete", "PASS", "reused_checksum_attested"}
            or embedded_records != int(spec["expected_records"])
            or int(payload.get("records", embedded_records)) != int(spec["expected_records"])
            or test_records != 0
            or output_value != str(output)
            or checksums_sha != _sha256(checksums)
            or str(payload["manifest_sha256"]) != spec["manifest_sha256"]
            or str(payload["fasta_sha256"]) != spec["fasta_sha256"]
            or int(payload["prediction_or_metric_records_created"]) != 0
            or str(payload["resolved_model_revision"]) != expected_revision
            or metadata.get("status") != "complete"
            or int(metadata.get("completed_records", -1)) != int(spec["expected_records"])
            or metadata.get("manifest_sha256") != spec["manifest_sha256"]
            or metadata.get("resolved_model_revision") != expected_revision
        ):
            raise RuntimeError(f"Embedding receipt/attestation contract mismatch: {path}")
        if expected_kind == "materialization" and (
            str(
                _first(
                    payload,
                    "config_sha256",
                    "materialization_config_sha256",
                    "source_config_sha256",
                )
            )
            != config["embedding_materialization_config_sha256"]
            or str(
                _first(
                    payload,
                    "protocol_sha256",
                    "materialization_protocol_sha256",
                    "source_protocol_sha256",
                )
            )
            != config["embedding_materialization_protocol_sha256"]
        ):
            raise RuntimeError(f"Materialization snapshot lineage mismatch: {path}")
        if expected_kind == "materialization":
            for field in ("gpu_seconds", "wall_seconds", "peak_gpu_memory_bytes"):
                if field not in payload or float(payload[field]) <= 0:
                    raise RuntimeError(f"Materialization resource field is absent: {path}/{field}")
        if payload.get("normalization_role") == "path_rebinding_only_no_numeric_recomputation":
            source_evidence = Path(str(payload.get("source_receipt_or_attestation", "")))
            if (
                not source_evidence.is_file()
                or payload.get("source_receipt_or_attestation_sha256")
                != _sha256(source_evidence)
                or payload.get("source_embedding_checksums_sha256") != checksums_sha
            ):
                raise RuntimeError(f"Normalized attestation lost its source receipt lineage: {path}")
        observed[key] = {
            "model_id": model_id,
            "shard_id": shard_id,
            "attestation_kind": expected_kind,
            "status": "complete",
            "records": int(spec["expected_records"]),
            "embedded_records": embedded_records,
            "gpu_seconds": _first(payload, "gpu_seconds", default=""),
            "wall_seconds": _first(payload, "wall_seconds", default=""),
            "peak_gpu_memory_bytes": _first(payload, "peak_gpu_memory_bytes", default=""),
            "test_records_embedded": 0,
            "prediction_or_metric_records_created": 0,
            "manifest_sha256": spec["manifest_sha256"],
            "fasta_sha256": spec["fasta_sha256"],
            "embedding_output": str(output),
            "embedding_checksums_sha256": _sha256(checksums),
            "receipt_or_attestation": str(path),
            "receipt_or_attestation_sha256": _sha256(path),
        }

    normalized_dir = Path(config["normalized_embedding_attestation_dir"])
    normalized = (
        _read_attestation_jsons(normalized_dir) if normalized_dir.is_dir() else []
    )
    if normalized:
        if len(normalized) != 24:
            raise RuntimeError("Normalized embedding-attestation directory must contain 24 JSON rows")
        for path, payload in normalized:
            kind = (
                "reuse"
                if str(payload.get("model_id", "")) in {"esm2_650m", "esmc_6b"}
                else "materialization"
            )
            consume(path, payload, kind)
    else:
        for path, payload in _read_attestation_jsons(Path(config["materialization_receipt_dir"])):
            consume(path, payload, "materialization")
        for path, payload in _read_attestation_jsons(Path(config["reuse_attestation_dir"])):
            consume(path, payload, "reuse")
    if set(observed) != expected_new | expected_reuse:
        missing = sorted((expected_new | expected_reuse) - set(observed))
        extra = sorted(set(observed) - (expected_new | expected_reuse))
        raise RuntimeError(f"Embedding attestations are not exact 24 rows: missing={missing}, extra={extra}")
    return [observed[key] for key in sorted(observed)]


def _verify_schema4_lineage(config: Mapping[str, Any]) -> dict[str, str]:
    checksums = Path(config["schema4_result_checksums"])
    validation = Path(config["schema4_validation"])
    if (
        checksums.parent != Path(config["schema4_result_dir"])
        or _sha256(checksums) != config["schema4_result_checksums_sha256"]
        or _sha256(validation) != config["schema4_validation_sha256"]
    ):
        raise RuntimeError("Checksum-bound schema-4 continuity evidence changed")
    verified = _verify_flat_bundle(checksums.parent)
    if "predictions.tsv" not in verified:
        raise RuntimeError("Schema-4 prediction cache is not checksum-bound")
    payload = json.loads(validation.read_text(encoding="utf-8"))
    if payload.get("status") != "PASS" or payload.get("counts", {}).get("test_records") != 0:
        raise RuntimeError("Schema-4 independent validation is not PASS/Test=0")
    return {
        "schema4_result_checksums": _sha256(checksums),
        "schema4_validation": _sha256(validation),
        "schema4_predictions": _sha256(checksums.parent / "predictions.tsv"),
    }


def build_nomination(
    nominee_id: str,
    cv_rows: list[dict[str, object]],
    pareto_rows: list[dict[str, object]],
    pairwise_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    cv = {str(row["candidate_id"]): row for row in cv_rows}[nominee_id]
    pareto = {str(row["candidate_id"]): row for row in pareto_rows}[nominee_id]
    warning_sources = sorted(
        str(row["source_dataset"])
        for row in pairwise_rows
        if row["candidate_id"] == nominee_id
        and row["diagnostic_status"] == "source_specific_inferiority_warning"
    )
    return [
        {
            "candidate_id": nominee_id,
            "nomination_status": (
                "recommended_for_external_confirmation_with_source_warning"
                if warning_sources
                else "recommended_for_external_confirmation"
            ),
            "mean_train_cv_score": cv["mean_train_cv_score"],
            "within_one_paired_se": cv["within_one_paired_se"],
            "one_se_cost_accuracy_pareto": pareto["one_se_cost_accuracy_pareto"],
            "source_specific_warning_count": len(warning_sources),
            "source_specific_warnings": ";".join(warning_sources),
            "robustness_used_for_candidate_ordering": 0,
            "released_v0_change_permitted": 0,
            "prospective_external_confirmation_required": 1,
            "interpretation": "train_cv_nominated_schema5_diagnostic_only_not_independent_validation",
        }
    ]


def _prediction_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return tuple(str(row[field]) for field in SCHEMA4_KEY_FIELDS)  # type: ignore[return-value]


def _prediction_rows_sha256(rows: Iterable[Mapping[str, Any]]) -> str:
    """Digest the exact string value of every prediction field in key order."""

    ordered = sorted(rows, key=_prediction_key)
    fields = sorted(set().union(*(set(row) for row in ordered)))
    digest = hashlib.sha256()
    for row in ordered:
        payload = [str(row.get(field, "")) for field in fields]
        digest.update(
            (json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
        )
    return digest.hexdigest()


def _validate_recomputed_decisions(row: Mapping[str, Any]) -> None:
    """Independently derive calls/correctness from recomputed probabilities."""

    source, head = str(row["source_dataset"]), str(row["head"])
    if (
        source not in APPLICABLE_HEADS
        or head not in APPLICABLE_HEADS[source]
        or _as_int(row["applicable_to_source"]) != 1
        or _as_int(row["test_record"]) != 0
    ):
        raise RuntimeError(f"Illegal source/head/Test semantics: {_prediction_key(row)}")
    threshold = float(row["threshold"])
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise RuntimeError(f"Invalid frozen threshold: {_prediction_key(row)}")
    for role in ("member", "representative"):
        probability = float(row[f"{role}_probability"])
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise RuntimeError(f"Invalid recomputed probability: {_prediction_key(row)}/{role}")
        raw = str(row[f"{role}_raw_decision_score"])
        if head == "head3_phylum":
            if raw != "":
                raise RuntimeError(f"H3 raw-score blank contract changed: {_prediction_key(row)}")
            prediction = str(row[f"{role}_prediction"])
            expected_reject = probability < threshold
            if (
                (expected_reject and prediction != "unknown/other")
                or (not expected_reject and prediction not in KNOWN_H3_CLASSES)
                or str(row[f"{role}_predicted_label"]) != prediction
            ):
                raise RuntimeError(f"H3 reject/call derivation mismatch: {_prediction_key(row)}/{role}")
        else:
            if raw == "" or not math.isfinite(float(raw)):
                raise RuntimeError(f"Binary raw score is blank/non-finite: {_prediction_key(row)}")
            prediction = int(probability >= threshold)
            if (
                _as_int(row[f"{role}_prediction"]) != prediction
                or str(row[f"{role}_predicted_label"]) != _binary_label(head, prediction)
            ):
                raise RuntimeError(f"Binary call derivation mismatch: {_prediction_key(row)}/{role}")
    eligible = _as_int(row["metric_eligible"])
    if head == "head3_phylum":
        truth = str(row["truth_label"])
        if eligible:
            if not truth or str(row["expected_prediction"]) != truth:
                raise RuntimeError(f"Eligible H3 truth contract changed: {_prediction_key(row)}")
            for role in ("member", "representative"):
                expected_correct = int(str(row[f"{role}_prediction"]) == truth)
                if _as_int(row[f"{role}_correct"]) != expected_correct:
                    raise RuntimeError(f"H3 correctness derivation mismatch: {_prediction_key(row)}/{role}")
        elif any(
            str(row[field]) != ""
            for field in ("truth_label", "expected_prediction", "member_correct", "representative_correct")
        ):
            raise RuntimeError(f"Ineligible H3 scoring fields are nonblank: {_prediction_key(row)}")
    else:
        expected, truth, _metric = EXPECTED_BINARY[(source, head)]
        if (
            eligible != 1
            or _as_int(row["expected_prediction"]) != expected
            or str(row["truth_label"]) != truth
        ):
            raise RuntimeError(f"Binary truth/eligibility contract changed: {_prediction_key(row)}")
        for role in ("member", "representative"):
            expected_correct = int(_as_int(row[f"{role}_prediction"]) == expected)
            if _as_int(row[f"{role}_correct"]) != expected_correct:
                raise RuntimeError(f"Binary correctness derivation mismatch: {_prediction_key(row)}/{role}")


def _canonicalize_schema4_predictions(
    config: Mapping[str, Any], recomputed_rows: list[dict[str, object]]
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, Any]]:
    """Require legacy-operator exact replay, then atomically substitute rows.

    Amendment C reproduces schema-4's four-thread numerical operator.  Every
    serialized numeric field must therefore replay exactly across all 92,844
    rows.  Amendment-B tolerances remain fixed diagnostic upper bounds, but
    they cannot authorize a nonexact row.
    """

    canonical_path = Path(config["schema4_result_dir"]) / "predictions.tsv"
    canonical_rows = _read_tsv(canonical_path)
    selected_recomputed = [
        row for row in recomputed_rows if str(row["model_id"]) in SCHEMA4_CANONICAL_MODELS
    ]
    canonical_keys = [_prediction_key(row) for row in canonical_rows]
    recomputed_keys = [_prediction_key(row) for row in selected_recomputed]
    if (
        not canonical_rows
        or len(set(canonical_keys)) != len(canonical_keys)
        or len(set(recomputed_keys)) != len(recomputed_keys)
        or set(canonical_keys) != set(recomputed_keys)
        or {key[0] for key in canonical_keys} != set(SCHEMA4_CANONICAL_MODELS)
        or len(canonical_rows) != int(config["schema4_expected_prediction_rows"])
    ):
        raise RuntimeError("Schema-4/schema-5 canonical prediction key contract changed")
    expected_fields = set(SCHEMA4_KEY_FIELDS) | set(SCHEMA4_SEMANTIC_FIELDS) | set(
        SCHEMA4_NUMERIC_TOLERANCES
    )
    if any(set(row) != expected_fields for row in canonical_rows + selected_recomputed):
        raise RuntimeError("Schema-4/schema-5 prediction field schema changed")
    canonical = dict(zip(canonical_keys, canonical_rows))
    recomputed = dict(zip(recomputed_keys, selected_recomputed))
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
    audit_rows: list[dict[str, object]] = []
    semantic_comparisons = 0
    for key in sorted(canonical):
        old, fresh = canonical[key], recomputed[key]
        for field in SCHEMA4_SEMANTIC_FIELDS:
            semantic_comparisons += 1
            if str(old[field]) != str(fresh[field]):
                raise RuntimeError(f"Schema-4 recomputation semantic mismatch: {key}/{field}")
        _validate_recomputed_decisions(fresh)
        audit: dict[str, object] = {
            "model_id": key[0],
            "protein_id": key[1],
            "head": key[2],
            **{
                f"recomputed_{field}": str(fresh[field])
                for field in SCHEMA4_SEMANTIC_FIELDS
            },
            "semantic_fields_exact": 1,
            "derived_decisions_exact": 1,
            "audit_status": "PASS",
        }
        for field, (absolute_tolerance, relative_tolerance) in SCHEMA4_NUMERIC_TOLERANCES.items():
            left_text, right_text = str(old[field]), str(fresh[field])
            audit[f"canonical_{field}"] = left_text
            audit[f"recomputed_{field}"] = right_text
            exact_replay = left_text == right_text
            audit[f"{field}_exact_replay"] = int(exact_replay)
            blank_parity = (left_text == "") == (right_text == "")
            audit[f"{field}_blank_parity"] = int(blank_parity)
            if not blank_parity:
                raise RuntimeError(f"Schema-4 recomputation blank mismatch: {key}/{field}")
            stats = numeric_stats[field]
            if left_text == "":
                stats["blank_pairs"] += 1
                for suffix in (
                    "absolute_delta",
                    "relative_delta",
                    "tolerance_limit",
                    "tolerance_ratio",
                ):
                    audit[f"{field}_{suffix}"] = ""
                audit[f"{field}_within_tolerance"] = 1
                if not exact_replay:
                    raise RuntimeError(
                        f"Schema-4 legacy-operator exact numeric replay failed: {key}/{field}"
                    )
                continue
            left, right = float(left_text), float(right_text)
            if not math.isfinite(left) or not math.isfinite(right):
                raise RuntimeError(f"Schema-4 recomputation non-finite value: {key}/{field}")
            if "probability" in field and (not 0.0 <= left <= 1.0 or not 0.0 <= right <= 1.0):
                raise RuntimeError(f"Schema-4 recomputation probability outside [0,1]: {key}/{field}")
            delta = abs(right - left)
            denominator = max(abs(left), abs(right), np.finfo(np.float64).tiny)
            relative_delta = delta / denominator
            tolerance_limit = absolute_tolerance + relative_tolerance * abs(left)
            tolerance_ratio = (
                0.0
                if delta == 0.0
                else math.inf if tolerance_limit == 0.0 else delta / tolerance_limit
            )
            within = delta <= tolerance_limit
            audit.update(
                {
                    f"{field}_absolute_delta": delta,
                    f"{field}_relative_delta": relative_delta,
                    f"{field}_tolerance_limit": tolerance_limit,
                    f"{field}_tolerance_ratio": tolerance_ratio,
                    f"{field}_within_tolerance": int(within),
                }
            )
            stats["comparisons"] += 1
            stats["nonexact_comparisons"] += int(delta != 0.0)
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
            if not within:
                raise RuntimeError(
                    "Schema-4 recomputation exceeded retained Amendment-B upper bound: "
                    f"{key}/{field}; canonical={left_text}; recomputed={right_text}; "
                    f"abs_delta={delta}; limit={tolerance_limit}"
                )
            if not exact_replay:
                raise RuntimeError(
                    "Schema-4 legacy-operator exact numeric replay failed: "
                    f"{key}/{field}; canonical={left_text}; recomputed={right_text}; "
                    f"Amendment-B upper-bound ratio={tolerance_ratio}"
                )
        audit_rows.append(audit)

    # Substitution occurs only after every row has passed.  Values are copied
    # as strings from the checksum-bound schema-4 TSV, preserving its exact
    # serialization for homogeneous and downstream mixed-head composition.
    canonicalized: list[dict[str, object]] = []
    for row in recomputed_rows:
        key = _prediction_key(row)
        canonicalized.append(dict(canonical[key]) if key in canonical else row)
    canonical_selected = [
        row for row in canonicalized if str(row["model_id"]) in SCHEMA4_CANONICAL_MODELS
    ]
    report = {
        "status": "PASS",
        "policy": SCHEMA4_CANONICAL_CACHE_POLICY,
        "canonical_models": list(SCHEMA4_CANONICAL_MODELS),
        "canonical_source": str(canonical_path),
        "canonical_source_sha256": _sha256(canonical_path),
        "prediction_keys": len(canonical_rows),
        "canonicalized_rows": len(canonical_selected),
        "row_level_audit_rows": len(audit_rows),
        "prediction_fields": len(expected_fields),
        "semantic_fields": list(SCHEMA4_SEMANTIC_FIELDS),
        "semantic_comparisons": semantic_comparisons,
        "semantic_mismatches": 0,
        "derived_decision_mismatches": 0,
        "exact_numeric_string_replay_required": True,
        "exact_numeric_string_comparisons": len(canonical_rows)
        * len(SCHEMA4_NUMERIC_TOLERANCES),
        "numeric_string_mismatches": 0,
        "legacy_numerical_operator_id": LEGACY_OPERATOR_ID,
        "amendment_b_tolerances_retained_as_upper_bound": True,
        "test_records": 0,
        "recomputed_prediction_rows_sha256": _prediction_rows_sha256(selected_recomputed),
        "canonical_prediction_rows_sha256": _prediction_rows_sha256(canonical_selected),
        "numeric_fields": numeric_stats,
        "canonicalization": "all_rows_substituted_only_after_complete_audit_pass",
        "interpretation": (
            "legacy_four_thread_operator_exact_numeric_replay_no_endpoint_or_model_change"
        ),
    }
    return canonicalized, audit_rows, report


def _schema4_audit_summary_rows(report: Mapping[str, Any]) -> list[dict[str, object]]:
    common = {
        "status": report["status"],
        "policy": report["policy"],
        "canonical_source_sha256": report["canonical_source_sha256"],
    }
    rows: list[dict[str, object]] = [
        {
            "audit_item": "prediction_keys",
            "comparison_kind": "exact_key_and_all_or_none_canonicalization",
            "comparisons": report["prediction_keys"],
            "mismatches": 0,
            **common,
        },
        {
            "audit_item": "semantic_fields",
            "comparison_kind": "exact_string_equality",
            "comparisons": report["semantic_comparisons"],
            "mismatches": report["semantic_mismatches"],
            **common,
        },
        {
            "audit_item": "derived_decisions",
            "comparison_kind": "independently_derived_call_reject_and_correctness",
            "comparisons": report["prediction_keys"],
            "mismatches": report["derived_decision_mismatches"],
            **common,
        },
        {
            "audit_item": "exact_numeric_string_replay",
            "comparison_kind": "exact_serialized_string_equality_all_numeric_fields",
            "comparisons": report["exact_numeric_string_comparisons"],
            "mismatches": report["numeric_string_mismatches"],
            **common,
        },
        {
            "audit_item": "test_records",
            "comparison_kind": "exact_zero",
            "comparisons": report["prediction_keys"],
            "mismatches": report["test_records"],
            **common,
        },
    ]
    for field, values in report["numeric_fields"].items():
        rows.append(
            {
                "audit_item": field,
                "comparison_kind": (
                    "exact_serialized_equality_with_fixed_amendment_b_upper_bound"
                ),
                "absolute_tolerance": values["absolute_tolerance"],
                "relative_tolerance": values["relative_tolerance"],
                "comparisons": values["comparisons"],
                "blank_pairs": values["blank_pairs"],
                "nonexact_comparisons": values["nonexact_comparisons"],
                "max_absolute_delta": values["max_absolute_delta"],
                "max_absolute_delta_key": values["max_absolute_delta_key"],
                "max_relative_delta": values["max_relative_delta"],
                "max_relative_delta_key": values["max_relative_delta_key"],
                "max_tolerance_ratio": values["max_tolerance_ratio"],
                "max_tolerance_ratio_key": values["max_tolerance_ratio_key"],
                "mismatches": 0,
                **common,
            }
        )
    return rows


def score(config_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    _validate_config(config)
    protocol = Path(config["protocol"])
    if not protocol.is_file():
        raise FileNotFoundError(protocol)
    output = Path(config["result_dir"])
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite schema-5 result: {output}")
    temporary = output.with_name(f"{output.name}.tmp-{os.getpid()}")
    if temporary.exists():
        raise FileExistsError(f"Temporary result already exists: {temporary}")
    temporary.mkdir(parents=True)

    legacy_operator_runtime = _legacy_operator_runtime_attestation(config, config_path)
    runtime_path = temporary / "legacy_numerical_operator_runtime.json"
    runtime_path.write_text(
        json.dumps(legacy_operator_runtime, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    legacy_operator_runtime_sha256 = _sha256(runtime_path)

    _validate_input_identity(config)
    schema4_lineage = _verify_schema4_lineage(config)
    materialization = validate_embedding_attestations(config)
    recomputed_single_rows, inference_provenance = _load_single_model_predictions(config)
    h3_rare_subgroups = _load_h3_rare_subgroups(config, inference_provenance)
    single_rows, schema4_audit_rows, schema4_cache_audit = (
        _canonicalize_schema4_predictions(config, recomputed_single_rows)
    )
    schema4_audit_summary_rows = _schema4_audit_summary_rows(schema4_cache_audit)
    continuity_rows = int(schema4_cache_audit["prediction_keys"])
    if any(_as_int(row["test_record"]) for row in single_rows):
        raise RuntimeError("Test row reached schema-5 single-model predictions")
    registry = build_system_registry(config)
    system_rows = compose_system_predictions(single_rows, registry)
    path_rows = build_path_rows(system_rows)
    replicates = int(config["bootstrap_replicates"])
    seed = int(config["bootstrap_seed"])
    (
        head_summary,
        path_summary,
        strict_summary,
        h3_summary,
        bootstrap_rows,
        path_boot,
    ) = summarize_systems(
        system_rows,
        path_rows,
        registry,
        h3_rare_subgroups,
        replicates=replicates,
        base_seed=seed,
    )
    pairwise_rows = pairwise_source_deltas(config, path_summary, path_boot)
    contextual_rows = contextual_source_deltas(config, path_summary, path_boot)
    model_costs = load_model_costs(config)
    cv_rows, pareto_rows, nominee_id = train_cv_candidate_rows(config, model_costs)
    nomination = build_nomination(nominee_id, cv_rows, pareto_rows, pairwise_rows)

    tables: list[tuple[str, list[dict[str, object]]]] = [
        ("single_model_predictions.tsv", single_rows),
        ("system_predictions.tsv", system_rows),
        ("system_expected_path_predictions.tsv", path_rows),
        ("system_registry.tsv", registry),
        ("source_head_summary.tsv", head_summary),
        ("source_path_summary.tsv", path_summary),
        ("strict_cluster_summary.tsv", strict_summary),
        ("h3_class_summary.tsv", h3_summary),
        ("path_bootstrap_replicates.tsv", bootstrap_rows),
        ("pairwise_source_path_delta.tsv", pairwise_rows),
        ("contextual_source_path_delta.tsv", contextual_rows),
        ("train_cv_candidate_summary.tsv", cv_rows),
        ("accuracy_cost_pareto.tsv", pareto_rows),
        ("candidate_nomination.tsv", nomination),
        ("model_cost_registry.tsv", model_costs),
        ("materialization_summary.tsv", materialization),
        ("schema4_recomputation_audit.tsv", schema4_audit_rows),
        ("schema4_recomputation_audit_summary.tsv", schema4_audit_summary_rows),
    ]
    for name, rows in tables:
        if not rows:
            raise RuntimeError(f"Refusing to write empty required table: {name}")
        fields: list[str] = []
        for row in rows:
            for field in row:
                if field not in fields:
                    fields.append(field)
        _write_tsv(temporary / name, fields, rows)

    amendment_c_result_dir = Path(config["amendment_c_result_dir"])
    amendment_c_validation = Path(config["amendment_c_validation"])
    if (
        _sha256(amendment_c_result_dir / "CHECKSUMS.sha256")
        != config["amendment_c_result_checksums_sha256"]
        or _sha256(amendment_c_validation) != config["amendment_c_validation_sha256"]
    ):
        raise RuntimeError("Retained Amendment-C generation identity changed")
    amendment_c_files = _verify_flat_bundle(amendment_c_result_dir)
    amendment_c_equivalence: dict[str, str] = {}
    for name in AMENDMENT_D_BYTE_EQUIVALENT_ARTIFACTS:
        if name not in amendment_c_files or _sha256(temporary / name) != amendment_c_files[name]:
            raise RuntimeError(
                f"Amendment-D changed a prediction/threshold/CV/order artifact: {name}"
            )
        amendment_c_equivalence[name] = amendment_c_files[name]

    summary: dict[str, Any] = {
        "schema_version": 5,
        "analysis_id": ANALYSIS_ID,
        "status": "complete_eight_model_nine_candidate_four_source",
        "project_version": config["project_version"],
        "data_curation_version": config["data_curation_version"],
        "evaluation_role": config["evaluation_role"],
        "interpretation": config["interpretation"],
        "selection_feedback_permitted": False,
        "released_v0_feedback_permitted": False,
        "schema5_robustness_reranking_permitted": False,
        "train_cv_candidate_nomination_permitted": True,
        "model_state": "frozen",
        "training_operations": 0,
        "calibration_fit_operations": 0,
        "threshold_optimization_operations": 0,
        "test_vectors_selected_for_inference": 0,
        "test_predictions_or_metrics_computed": 0,
        "released_v0_artifacts_modified": 0,
        "models": list(MODELS),
        "sources": list(SOURCES),
        "applicable_heads": {key: list(value) for key, value in APPLICABLE_HEADS.items()},
        "homogeneous_systems": 8,
        "primary_mixed_candidate_labels": 9,
        "unique_prediction_systems": 16,
        "all_6b_positive_control": "exact_row_and_bootstrap_equivalence",
        "legacy_numerical_operator_runtime": {
            "status": legacy_operator_runtime["status"],
            "operator_id": legacy_operator_runtime["operator_id"],
            "artifact": runtime_path.name,
            "artifact_sha256": legacy_operator_runtime_sha256,
            "pbs_job_id": legacy_operator_runtime["pbs"]["job_id"],
            "python_version": legacy_operator_runtime["python"]["version"],
            "runtime_preload_modules": [
                row["module"]
                for row in legacy_operator_runtime["runtime_preload_modules"]
            ],
            "threadpool_count": legacy_operator_runtime["threadpool_count"],
            "exact_numeric_string_replay_required": True,
        },
        "schema4_canonical_prediction_cache": schema4_cache_audit,
        "amendment_c_byte_equivalence": {
            "status": "PASS",
            "source_result_dir": str(amendment_c_result_dir),
            "source_checksums_sha256": _sha256(
                amendment_c_result_dir / "CHECKSUMS.sha256"
            ),
            "source_validation_sha256": _sha256(amendment_c_validation),
            "artifacts": amendment_c_equivalence,
            "interpretation": (
                "predictions_thresholds_cv_scores_and_candidate_order_byte_equivalent"
            ),
        },
        "h3_rare_endpoint_contract": {
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
        },
        "nominee": nomination[0],
        "nomination_primary_evidence": "train_only_shared_five_fold_cv",
        "robustness_role_in_nomination": "source_specific_warning_not_reranking",
        "bootstrap": {
            "replicates": replicates,
            "seed": seed,
            "unit": "dependence_block",
            "weighting": WEIGHTING,
            "interval": "paired_percentile_95pct_descriptive",
        },
        "multiple_comparisons": {
            "method": "Holm",
            "families": "eight_nontrivial_candidates_vs_all_esmc_6b_within_each_source",
            "positive_control_excluded_from_hypothesis_count": True,
        },
        "record_counts": {
            "single_model_predictions": len(single_rows),
            "system_predictions": len(system_rows),
            "system_expected_paths": len(path_rows),
            "schema4_continuity_predictions": continuity_rows,
            "schema4_recomputation_audit_rows": len(schema4_audit_rows),
            "schema4_recomputation_audit_summary_rows": len(
                schema4_audit_summary_rows
            ),
            "path_bootstrap_rows": len(bootstrap_rows),
            "h3_endpoint_rows": len(h3_summary),
            "h3_subgroup_endpoint_rows": sum(
                row["endpoint_id"]
                in {
                    "Produgelaviricota_reject_recall",
                    "literature_unclassified_reject_recall",
                }
                for row in h3_summary
            ),
            "materialization_or_reuse_attestations": len(materialization),
            "new_materialization_receipts": sum(
                row["attestation_kind"] == "materialization" for row in materialization
            ),
            "reuse_attestations": sum(row["attestation_kind"] == "reuse" for row in materialization),
            "hardnegative_h2_h3_predictions": sum(
                row["source_dataset"] == "hard_non_djr" and row["head"] != "head1"
                for row in system_rows
            ),
            "test_records": 0,
        },
        "lineage_sha256": {
            "config": _sha256(config_path),
            "protocol": _sha256(protocol),
            "benchmark_config": _sha256(Path(config["benchmark_config"])),
            "comparison_summary": _sha256(Path(config["comparison_summary"])),
            **schema4_lineage,
            "schema3_family_manifest": inference_provenance["family_manifest_sha256"],
            "hardnegative_manifest": inference_provenance["hardnegative_manifest_sha256"],
            "legacy_numerical_operator_runtime": legacy_operator_runtime_sha256,
        },
        "limits": [
            "Schema-5 was planned after schema-4 and is not an independent Test.",
            "ESM-2 650M and ESM-C 6B preserve checksum-bound schema-4 serialized rows only after the attested legacy four-thread operator exactly replays every numeric string across all 92,844 rows; Amendment-B tolerances remain diagnostic upper bounds only.",
            "The four robustness sources are never pooled to reorder candidates.",
            "N/A heads have no prediction rows and are not zeros.",
            "Produgelaviricota rejection is a 7-record/2-parent descriptive subgroup; literature-unclassified rejection is a single-record descriptive result with no generalization claim.",
            "The pooled 8-record/3-parent rare-or-unclassified H3 rejection endpoint is secondary and is not general unknown detection.",
            "The nominee is only a candidate for prospective external confirmation and cannot replace V0.",
        ],
    }
    (temporary / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    written = {path.name for path in temporary.iterdir()}
    if written != REQUIRED_RESULT_FILES:
        raise RuntimeError(f"Schema-5 result contract mismatch before manifest: {sorted(written ^ REQUIRED_RESULT_FILES)}")
    (temporary / "CHECKSUMS.sha256").write_text(
        "".join(
            f"{_sha256(temporary / name)}  {name}\n" for name in sorted(REQUIRED_RESULT_FILES)
        ),
        encoding="utf-8",
    )
    os.replace(temporary, output)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/validation_family_robustness_v0_schema5_mixed_heads.yaml"),
    )
    args = parser.parse_args()
    print(json.dumps(score(args.config), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
