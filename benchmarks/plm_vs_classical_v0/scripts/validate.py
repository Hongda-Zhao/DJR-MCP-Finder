#!/usr/bin/env python3
"""Fail-closed release validation for the cyclic PLM/classical benchmark.

Metric recomputation lives in ``validation_metrics.py`` and does not import the
summarizer; this entry point owns provenance, profile/search receipts,
protected-split gates, scheduler receipts, and release checksums.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from common import atomic_json, cyclic_fold_roles, load_config, read_fasta, read_tsv, sha256_file
from summarize import (
    ALL_METHODS,
    PSI_METHOD,
    normalize_registry_rows,
    validate_profile_registries,
    validate_raw_receipt_ledger,
    validate_reference_contracts,
)


CLASSICAL_METHODS = {
    "blastp",
    "diamond_ultra",
    "mmseqs_s7.5",
    "hmmer_component",
    "hmmer_family",
    PSI_METHOD,
}
REFERENCE_METHODS = set(ALL_METHODS) - {"esmc6b_supervised"}
HMM_METHODS = {"hmmer_component", "hmmer_family"}
SHA_RE = re.compile(r"[0-9a-f]{64}")


def fail(message: str) -> None:
    raise RuntimeError(f"BENCHMARK VALIDATION FAILED: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def read_json(path: Path) -> object:
    require(path.is_file(), f"missing JSON: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"malformed JSON {path}: {error}")


def json_object(path: Path) -> dict:
    value = read_json(path)
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def required_tsv(path: Path) -> list[dict[str, str]]:
    require(path.is_file(), f"missing TSV: {path}")
    try:
        rows = read_tsv(path)
    except (OSError, csv.Error, ValueError) as error:
        fail(f"malformed TSV {path}: {error}")
    require(bool(rows), f"empty required TSV: {path}")
    return rows


def is_sha(value: object) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def sha_lines(values: Iterable[str]) -> str:
    data = "".join(f"{value}\n" for value in values).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def stable_sha(value: object) -> str:
    data = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def safe_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), f"path escapes benchmark root: {relative}")
    require(path.is_file(), f"missing bound file: {relative}")
    return path


def path_sha(path: Path) -> str:
    if path.is_file():
        return sha256_file(path)
    require(path.is_dir(), f"missing receipt input: {path}")
    entries = [
        (str(item.relative_to(path)), sha256_file(item))
        for item in sorted(path.rglob("*"))
        if item.is_file()
    ]
    return stable_sha(entries)


def expected_derived_paths() -> set[str]:
    paths = {"cohort.tsv", "reference_attestation.tsv"}
    for fold in range(1, 6):
        paths.update(
            {
                f"fold_{fold}/query_evaluation.tsv",
                f"fold_{fold}/query_evaluation.faa",
                f"fold_{fold}/query_calibration.tsv",
                f"fold_{fold}/query_calibration.faa",
                f"fold_{fold}/query_combined.tsv",
                f"fold_{fold}/query_combined.faa",
                f"fold_{fold}/reference_djr.tsv",
                f"fold_{fold}/reference_djr.faa",
                f"fold_{fold}/reference_vma.tsv",
                f"fold_{fold}/reference_vma.faa",
            }
        )
    return paths


def validate_inputs(
    config: Mapping[str, object], project_root: Path, benchmark_root: Path
) -> tuple[list[dict[str, str]], dict[tuple[int, str], list[dict[str, str]]], dict]:
    input_root = benchmark_root / "inputs"
    attestation_path = input_root / "input_attestation.json"
    attestation = json_object(attestation_path)
    require(attestation.get("status") == "PASS", "input attestation is not PASS")
    require(attestation.get("design_id") == config["design_id"], "input design mismatch")
    require(attestation.get("allowed_split") == "train", "inputs are not Train-only")
    require(attestation.get("validation_prediction_rows") == 0, "input Validation rows nonzero")
    require(attestation.get("test_prediction_rows") == 0, "input Test rows nonzero")

    config_path = benchmark_root / "config/benchmark.json"
    bindings = {
        "config_sha256": sha256_file(config_path),
        "prepare_inputs_script_sha256": sha256_file(benchmark_root / "scripts/prepare_inputs.py"),
        "common_script_sha256": sha256_file(benchmark_root / "scripts/common.py"),
    }
    require(all(attestation.get(k) == v for k, v in bindings.items()), "input source binding drift")

    inputs = config["inputs"]
    expected_frozen = config["expected_sha256"]
    require(isinstance(inputs, dict) and isinstance(expected_frozen, dict), "invalid config input maps")
    require(
        set(expected_frozen)
        == {"train_manifest", "train_fasta", "master_manifest", "fold_map", "fold_metadata"},
        "frozen checksum key set drift",
    )
    source_sha = {}
    for key, relative in inputs.items():
        path = (project_root / str(relative)).resolve()
        require(path.is_relative_to(project_root) and path.is_file(), f"missing source input {key}")
        source_sha[key] = sha256_file(path)
    require(attestation.get("input_sha256") == source_sha, "source input map is stale/incomplete")
    for key, expected in expected_frozen.items():
        require(source_sha.get(key) == expected, f"frozen checksum drift: {key}")
    postsplit = json_object((project_root / str(inputs["postsplit_audit"])).resolve())
    require(
        str(postsplit.get("status", postsplit.get("overall_status", ""))).upper() == "PASS",
        "post-split integrity audit is not PASS",
    )

    derived = attestation.get("derived_output_sha256")
    require(isinstance(derived, dict), "derived-output map absent")
    require(set(derived) == expected_derived_paths(), "derived-output map has omissions/extras")
    for relative, expected in derived.items():
        path = safe_file(input_root, relative)
        require(is_sha(expected) and sha256_file(path) == expected, f"derived checksum drift: {relative}")

    cohort = required_tsv(input_root / "cohort.tsv")
    by_id = {row["protein_id"]: row for row in cohort}
    require(len(cohort) == 6634 and len(by_id) == len(cohort), "cohort size/ID uniqueness")
    require(all(row["is_vma"] != "1" or row["is_djr"] == "1" for row in cohort), "VMA not subset of DJR")
    require({int(row["fold"]) for row in cohort} == set(range(1, 6)), "cohort fold coverage")
    component_folds: dict[str, set[str]] = defaultdict(set)
    for row in cohort:
        component_folds[row["global_component_id"]].add(row["fold"])
    require(all(len(v) == 1 for v in component_folds.values()), "component spans frozen folds")
    require(
        Counter(row["source_dataset"] for row in cohort)
        == Counter(
            {
                "viral_vma_djr": 336,
                "cellular_djr_none": 298,
                "hard_non_djr": 3000,
                "background_non_djr": 3000,
            }
        ),
        "cohort source counts drift",
    )
    policy = config["protected_split_policy"]
    require(
        policy.get("allowed_splits") == ["train"]
        and policy.get("validation_prediction_rows") == 0
        and policy.get("test_prediction_rows") == 0,
        "protected split policy drift",
    )

    references: dict[tuple[int, str], list[dict[str, str]]] = {}
    reference_attestation = required_tsv(input_root / "reference_attestation.tsv")
    require(len(reference_attestation) == 10, "reference attestation row count")
    reference_attestation_by_key = {
        (int(row["evaluation_fold"]), row["reference_kind"]): row
        for row in reference_attestation
    }
    require(len(reference_attestation_by_key) == 10, "duplicate reference attestation key")
    for fold in range(1, 6):
        calibration, fit_folds = cyclic_fold_roles(fold, 5, 1)
        fold_root = input_root / f"fold_{fold}"
        expected_roles = {
            "evaluation": [row for row in cohort if int(row["fold"]) == fold],
            "calibration": [row for row in cohort if int(row["fold"]) == calibration],
        }
        for role, expected_rows in expected_roles.items():
            rows = required_tsv(fold_root / f"query_{role}.tsv")
            require(rows == expected_rows, f"cycle {fold} {role} query is not exact cohort slice")
            fasta = read_fasta(fold_root / f"query_{role}.faa")
            require(set(fasta) == {row["protein_id"] for row in rows}, f"cycle {fold} {role} FASTA IDs")
        combined = required_tsv(fold_root / "query_combined.tsv")
        expected_combined = [
            {**row, "benchmark_role": "calibration"} for row in expected_roles["calibration"]
        ] + [{**row, "benchmark_role": "evaluation"} for row in expected_roles["evaluation"]]
        require(combined == expected_combined, f"cycle {fold} combined role contract")
        combined_fasta = read_fasta(fold_root / "query_combined.faa")
        require(set(combined_fasta) == {row["protein_id"] for row in combined}, f"cycle {fold} combined FASTA")
        query_components = {row["global_component_id"] for row in combined}
        for reference, label in (("djr", "is_djr"), ("vma", "is_vma")):
            rows = required_tsv(fold_root / f"reference_{reference}.tsv")
            expected_rows = [
                row for row in cohort if int(row["fold"]) in fit_folds and row[label] == "1"
            ]
            require(rows == expected_rows, f"cycle {fold} {reference} reference differs from fit positives")
            require(not (query_components & {row["global_component_id"] for row in rows}), f"cycle {fold} component leakage")
            fasta_path = fold_root / f"reference_{reference}.faa"
            fasta = read_fasta(fasta_path)
            require(set(fasta) == {row["protein_id"] for row in rows}, f"cycle {fold} {reference} FASTA IDs")
            for row in rows:
                seq = fasta[row["protein_id"]]
                require(len(seq) == int(row["length_aa"]), f"reference length drift: {row['protein_id']}")
                require(hashlib.sha256(seq.encode("ascii")).hexdigest() == row["sequence_sha256"], f"reference sequence drift: {row['protein_id']}")
            references[(fold, reference)] = rows
            receipt = reference_attestation_by_key[(fold, reference)]
            require(int(receipt["calibration_fold"]) == calibration, f"reference calibration fold mismatch: {fold}")
            require(receipt["fit_folds"] == ",".join(map(str, fit_folds)), f"reference fit-fold mismatch: {fold}")
            require(int(receipt["record_count"]) == len(rows), f"reference record count: {fold} {reference}")
            require(receipt["id_sha256"] == sha_lines(sorted(fasta)), f"reference ID digest: {fold} {reference}")
            require(receipt["manifest_sha256"] == sha256_file(fold_root / f"reference_{reference}.tsv"), f"reference manifest digest: {fold} {reference}")
            require(receipt["fasta_sha256"] == sha256_file(fasta_path), f"reference FASTA digest: {fold} {reference}")
    return cohort, references, attestation


def validate_attestations(config: Mapping[str, object], project_root: Path, benchmark_root: Path, input_attestation: dict) -> dict[str, dict]:
    config_sha = sha256_file(benchmark_root / "config/benchmark.json")
    input_sha = sha256_file(benchmark_root / "inputs/input_attestation.json")
    docs = {
        "plm": json_object(benchmark_root / "work/plm_reproduction.json"),
        "classical": json_object(benchmark_root / "work/classical_attestation.json"),
    }
    for name, doc in docs.items():
        require(doc.get("status") == "PASS" and doc.get("design_id") == config["design_id"], f"{name} attestation status/design")
        require(doc.get("config_sha256") == config_sha, f"{name} config binding")
        require(doc.get("input_attestation_sha256") == input_sha, f"{name} input binding")
        require(doc.get("validation_prediction_rows") == 0 and doc.get("test_prediction_rows") == 0, f"{name} protected split count")
        require(doc.get("common_script_sha256") == sha256_file(benchmark_root / "scripts/common.py"), f"{name} common.py binding")
    require(docs["plm"].get("run_plm_script_sha256") == sha256_file(benchmark_root / "scripts/run_plm.py"), "PLM runner binding")
    classifier = project_root / "src/djrmcp_finder/stages/classifier.py"
    require(docs["plm"].get("classifier_module_sha256") == sha256_file(classifier), "classifier binding")
    historical = (project_root / str(config["classifier"]["historical_cv_json"])).resolve()
    require(
        docs["plm"].get("historical_cross_validation_sha256") == sha256_file(historical),
        "historical classifier reproduction input drift",
    )
    embedding_docs = docs["plm"].get("embedding_attestations")
    require(
        isinstance(embedding_docs, dict)
        and set(embedding_docs) == {"esmc6b_cosine", "esm2_650m_cosine"},
        "PLM embedding attestation coverage",
    )
    for method, description in embedding_docs.items():
        directory = Path(description.get("directory", "")).resolve()
        require(directory.is_dir(), f"embedding directory missing: {method}")
        require(
            description.get("metadata_sha256") == sha256_file(directory / "metadata.json")
            and description.get("index_sha256") == sha256_file(directory / "index.tsv"),
            f"embedding bundle binding drift: {method}",
        )
    plm_scores = benchmark_root / "work/scores/plm_scores.tsv"
    require(docs["plm"].get("score_sha256") == sha256_file(plm_scores), "PLM score binding")
    require(docs["classical"].get("run_classical_script_sha256") == sha256_file(benchmark_root / "scripts/run_classical.py"), "classical runner binding")
    classical_scores = benchmark_root / "work/scores/classical_scores.tsv"
    require(docs["classical"].get("classical_scores_sha256") == sha256_file(classical_scores), "classical score binding")
    require(docs["classical"].get("raw_receipt_ledger_sha256") == sha256_file(benchmark_root / "work/raw_receipt_ledger.tsv"), "raw ledger binding")
    merged = docs["classical"].get("merged_output_sha256")
    expected_merged = {
        "work/scores/classical_scores.tsv",
        "work/classical_reference_contract.tsv",
        "work/profile_members.tsv",
        "work/profile_inclusion_ledger.tsv",
        "work/psiblast_seed_ledger.tsv",
        "work/profile_artifact_registry.tsv",
        "work/raw_receipt_ledger.tsv",
        "work/runtime_resources.tsv",
    }
    require(isinstance(merged, dict) and set(merged) == expected_merged, "merged-output attestation coverage")
    for relative, expected in merged.items():
        require(is_sha(expected) and sha256_file(safe_file(benchmark_root, relative)) == expected, f"merged output drift: {relative}")
    fold_map = docs["classical"].get("fold_attestation_sha256")
    require(isinstance(fold_map, dict) and len(fold_map) == 5, "fold attestation map")
    for relative, expected in fold_map.items():
        require(is_sha(expected) and sha256_file(safe_file(benchmark_root, relative)) == expected, f"fold attestation drift: {relative}")
    executables = docs["classical"].get("executables")
    require(isinstance(executables, dict) and set(executables) == set(config["tools"]), "tool attestation coverage")
    for name, configured in config["tools"].items():
        description = executables[name]
        path = Path(configured)
        require(description.get("path") == configured and description.get("sha256") == sha256_file(path), f"tool binding drift: {name}")
    for name in ("plm_reproduction.json", "classical_attestation.json"):
        require(
            sha256_file(benchmark_root / "work" / name)
            == sha256_file(benchmark_root / "results" / name),
            f"result/work attestation copy differs: {name}",
        )
    return docs


def validate_contracts_and_profiles(
    config: Mapping[str, object], benchmark_root: Path, cohort: list[dict[str, str]], references: dict[tuple[int, str], list[dict[str, str]]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    results = benchmark_root / "results"
    work = benchmark_root / "work"
    registry_names = [
        "plm_reference_contract.tsv", "classical_reference_contract.tsv", "profile_members.tsv",
        "profile_inclusion_ledger.tsv", "psiblast_seed_ledger.tsv", "profile_artifact_registry.tsv",
        "runtime_resources.tsv", "raw_receipt_ledger.tsv",
    ]
    for name in registry_names:
        require(sha256_file(work / name) == sha256_file(results / name), f"result/work registry copy differs: {name}")
    contracts = normalize_registry_rows(required_tsv(results / "plm_reference_contract.tsv") + required_tsv(results / "classical_reference_contract.tsv"))
    validate_reference_contracts(contracts)
    require(len(contracts) == 80, "reference contract must be 8 x 5 x 2")
    for row in contracts:
        method = row["method"]
        fold = int(row["evaluation_fold"])
        reference = row["reference_kind"]
        calibration, _ = cyclic_fold_roles(fold, 5, 1)
        expected = references[(fold, reference)]
        require(method in REFERENCE_METHODS and int(row["calibration_fold"]) == calibration, f"reference role contract: {row}")
        require(int(row["expected_record_count"]) == len(expected), f"reference count contract: {row}")
        require(row["expected_id_set_sha256"] == sha_lines(sorted(r["protein_id"] for r in expected)), f"reference IDs: {row}")

    members = normalize_registry_rows(required_tsv(results / "profile_members.tsv"))
    inclusion = normalize_registry_rows(required_tsv(results / "profile_inclusion_ledger.tsv"))
    seeds = normalize_registry_rows(required_tsv(results / "psiblast_seed_ledger.tsv"))
    artifacts = normalize_registry_rows(required_tsv(results / "profile_artifact_registry.tsv"))
    cohort_by_id = {row["protein_id"]: row for row in cohort}
    validate_profile_registries(
        benchmark_root, cohort_by_id, members, seeds, inclusion, artifacts,
        float(config["parameters"]["psiblast_inclusion_evalue"]),
    )
    # Reject registry extras: exact HMM profile + library artifacts, and one PSSM per seed.
    expected_artifacts = {
        (row["evaluation_fold"], row["reference_kind"], row["method"], row["profile_id"], "hmm_profile")
        for row in members
    }
    expected_artifacts.update(
        (str(fold), reference, method, "__library__", "hmm_library")
        for fold in range(1, 6) for reference in ("djr", "vma") for method in HMM_METHODS
    )
    expected_artifacts.update(
        (row["evaluation_fold"], row["reference_kind"], PSI_METHOD, row["profile_id"], "pssm")
        for row in seeds
    )
    observed_artifacts = [
        (row["evaluation_fold"], row["reference_kind"], row["method"], row["profile_id"], row["artifact_kind"])
        for row in artifacts
    ]
    require(len(observed_artifacts) == len(set(observed_artifacts)) and set(observed_artifacts) == expected_artifacts, "profile artifact registry set mismatch")
    for row in artifacts:
        artifact = safe_file(benchmark_root, row["artifact_path"])
        receipt = safe_file(benchmark_root, row["receipt_path"])
        require(row["receipt_status"] == "PASS", f"profile artifact receipt status: {row}")
        require(sha256_file(artifact) == row["artifact_sha256"] and sha256_file(receipt) == row["receipt_sha256"], f"profile artifact checksum: {row}")
    return seeds, members


def expected_raw_stages(fold: int, members: Sequence[dict[str, str]], seeds: Sequence[dict[str, str]]) -> set[tuple[str, str, str]]:
    result: set[tuple[str, str, str]] = set()
    for reference in ("djr", "vma"):
        result.update({
            ("blastp", reference, "blast_db"), ("blastp", reference, "search_hits"),
            ("diamond_ultra", reference, "diamond_db"), ("diamond_ultra", reference, "search_hits"),
            ("mmseqs_s7.5", reference, "search_hits"), (PSI_METHOD, reference, "reference_db"),
            (PSI_METHOD, reference, "query_db"),
        })
        for method in HMM_METHODS:
            grouped = Counter(
                row["profile_id"] for row in members
                if int(row["evaluation_fold"]) == fold and row["reference_kind"] == reference and row["method"] == method
            )
            result.update({(method, reference, "library_hmmpress"), (method, reference, "hmmscan_hits")})
            for profile, count in grouped.items():
                result.add((method, reference, f"profile_hmmbuild:{profile}"))
                if count > 1:
                    result.add((method, reference, f"profile_alignment:{profile}"))
        for row in seeds:
            if int(row["evaluation_fold"]) == fold and row["reference_kind"] == reference:
                result.add((PSI_METHOD, reference, f"profile_enrichment:{row['profile_id']}"))
                result.add((PSI_METHOD, reference, f"scan_hits:{row['profile_id']}"))
    return result


def validate_raw_receipts(config: Mapping[str, object], benchmark_root: Path, seeds: Sequence[dict[str, str]], members: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    rows = normalize_registry_rows(required_tsv(benchmark_root / "results/raw_receipt_ledger.tsv"))
    validate_raw_receipt_ledger(rows, benchmark_root)
    by_fold: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_fold[int(row["evaluation_fold"])].append(row)
    for fold in range(1, 6):
        observed = [(row["method"], row["reference_kind"], row["stage"]) for row in by_fold[fold]]
        expected = expected_raw_stages(fold, members, seeds)
        require(len(observed) == len(set(observed)) and set(observed) == expected, f"raw stage set mismatch in cycle {fold}")
    for row in rows:
        receipt_path = safe_file(benchmark_root, row["receipt_path"])
        receipt = json_object(receipt_path)
        require(receipt.get("design_id") == config["design_id"], f"raw receipt design: {receipt_path}")
        inputs = receipt.get("inputs")
        tools = receipt.get("tools")
        require(isinstance(inputs, dict) and stable_sha(inputs) == row["input_sha256"], f"raw input map digest: {receipt_path}")
        for relative, expected in inputs.items():
            path = (benchmark_root / relative).resolve()
            require(path.is_relative_to(benchmark_root) and path.exists() and path_sha(path) == expected, f"raw input changed: {relative}")
        require(isinstance(tools, dict) and stable_sha(tools) == row["tool_sha256"], f"raw tool map digest: {receipt_path}")
        for name, description in tools.items():
            require(name in config["tools"] and description.get("path") == config["tools"][name], f"raw tool path: {receipt_path}")
            require(description.get("sha256") == sha256_file(Path(config["tools"][name])), f"raw tool checksum: {receipt_path}")
    return rows


def validate_resolution_and_inference(config: Mapping[str, object], benchmark_root: Path, cohort: Sequence[dict[str, str]], metric_audit: Mapping[str, object]) -> dict:
    results = benchmark_root / "results"
    summary = json_object(results / "summary.json")
    require(
        summary.get("status") in {"PROVISIONAL_PENDING_VALIDATION", "PASS"},
        "summary has an invalid validation state",
    )
    require(summary.get("benchmark_id") == config["benchmark_id"] and summary.get("design_id") == config["design_id"], "summary identity")
    require(summary.get("validation_prediction_rows") == 0 and summary.get("test_prediction_rows") == 0, "protected split predictions present")
    require(summary.get("fpm_status") == "NOT_ESTIMABLE", "FPM incorrectly estimable")
    require(summary.get("specificity_0.999_status") == "RESOLUTION_LIMITED_SECONDARY", "99.9% endpoint label")
    require(summary.get("bootstrap_replicates") == int(config["parameters"]["bootstrap_replicates"]), "bootstrap replicate count")
    audit = summary.get("resolution_audit")
    require(isinstance(audit, dict) and set(audit) == {"h1_djr", "h2_vma_conditional", "vma_end_to_end"}, "resolution audit task coverage")
    h2 = audit["h2_vma_conditional"]
    require(h2.get("primary_sensitivity_inference_status") == "CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED", "H2 singleton resolution status")
    require(bool(h2.get("calibration_singleton_negative_sources")) and bool(h2.get("evaluation_singleton_negative_sources")), "H2 singleton strata not disclosed")
    expected_calibration: set[tuple[int, int, str, int, int]] = set()
    expected_evaluation: set[tuple[int, str, int, int]] = set()
    for evaluation_fold in range(1, 6):
        calibration_fold, _ = cyclic_fold_roles(evaluation_fold, 5, 1)
        for role, source_fold in (("calibration", calibration_fold), ("evaluation", evaluation_fold)):
            negatives = [
                row
                for row in cohort
                if int(row["fold"]) == source_fold
                and row["is_djr"] == "1"
                and row["is_vma"] == "0"
            ]
            for source in {row["source_dataset"] for row in negatives}:
                local = [row for row in negatives if row["source_dataset"] == source]
                components = len({row["global_component_id"] for row in local})
                if components == 1 and role == "calibration":
                    expected_calibration.add(
                        (evaluation_fold, calibration_fold, source, len(local), components)
                    )
                elif components == 1:
                    expected_evaluation.add((evaluation_fold, source, len(local), components))
    observed_calibration = {
        (
            int(row["evaluation_fold"]), int(row["calibration_fold"]), str(row["source"]),
            int(row["records"]), int(row["components"]),
        )
        for row in h2["calibration_singleton_negative_sources"]
    }
    observed_evaluation = {
        (
            int(row["evaluation_fold"]), str(row["source"]), int(row["records"]),
            int(row["components"]),
        )
        for row in h2["evaluation_singleton_negative_sources"]
    }
    require(
        observed_calibration == expected_calibration
        and observed_evaluation == expected_evaluation,
        "H2 singleton resolution ledger differs from frozen cohort",
    )

    paired = required_tsv(results / "paired_deltas.tsv")
    expected_pairs = {(task, method) for task in audit for method in ("blastp", "diamond_ultra", "mmseqs_s7.5", "hmmer_component")}
    observed_pairs = {(row["task"], row["comparator_method"]) for row in paired}
    require(len(paired) == 12 and observed_pairs == expected_pairs, "paired comparison registry")
    forbidden = re.compile(r"(^|_)(p_?value|holm)($|_)", re.IGNORECASE)
    for path in sorted(results.glob("*.tsv")):
        with path.open(encoding="utf-8", newline="") as handle:
            fields = csv.DictReader(handle, delimiter="\t").fieldnames or []
        require(not any(forbidden.search(field) for field in fields), f"forbidden p/Holm field in {path.name}")
    def walk_keys(value: object) -> Iterable[str]:
        if isinstance(value, dict):
            for key, child in value.items():
                yield str(key)
                yield from walk_keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk_keys(child)
    require(not any(forbidden.search(key) for key in walk_keys(summary)), "forbidden p/Holm JSON key")
    return summary


def validate_pbs(benchmark_root: Path) -> int:
    runtime = required_tsv(benchmark_root / "results/runtime_resources.tsv")
    for row in runtime:
        require(
            row["method"] in CLASSICAL_METHODS
            and int(row["evaluation_fold"]) in range(1, 6)
            and row["reference_kind"] in {"djr", "vma"},
            f"runtime row scope: {row}",
        )
        seconds = float(row["wall_seconds"])
        require(
            math.isfinite(seconds)
            and seconds >= 0
            and row["status"] in {"ok", "reused"},
            f"runtime row status/value: {row}",
        )
        require(safe_file(benchmark_root, row["receipt_path"]).is_file(), f"runtime receipt missing: {row}")
    result_path = benchmark_root / "results/pbs_job_resources.tsv"
    work_path = benchmark_root / "work/pbs_job_resources.tsv"
    require(result_path.is_file() and work_path.is_file(), "PBS resource receipt missing")
    require(sha256_file(result_path) == sha256_file(work_path), "PBS result/work copy differs")
    rows = required_tsv(result_path)
    fields = {
        "job_id", "job_name", "job_state", "exit_status", "queue",
        "resources_used_walltime", "resources_used_cput", "resources_used_mem",
        "resources_used_ncpus", "resources_used_cpupercent", "exec_host",
    }
    require(fields <= set(rows[0]), "PBS schema incomplete")
    require(len({row["job_id"] for row in rows}) == len(rows), "duplicate PBS job receipt")
    hms = re.compile(r"\d+:[0-5]\d:[0-5]\d")
    for row in rows:
        require(row["job_state"] == "F" and row["exit_status"] == "0", f"PBS job failed: {row}")
        require(hms.fullmatch(row["resources_used_walltime"]) is not None, f"PBS walltime malformed: {row}")
        require(hms.fullmatch(row["resources_used_cput"]) is not None, f"PBS cput malformed: {row}")
        require(bool(row["resources_used_mem"]) and int(row["resources_used_ncpus"]) > 0, f"PBS resources incomplete: {row}")
    return len(rows)


def release_paths(benchmark_root: Path, raw_rows: Sequence[dict[str, str]]) -> list[Path]:
    selected: set[Path] = set()
    for subdir in ("results", "config", "scripts", "pbs", "tests", "inputs"):
        root = benchmark_root / subdir
        if root.is_dir():
            selected.update(path.resolve() for path in root.rglob("*") if path.is_file())
    selected.update(path.resolve() for path in benchmark_root.iterdir() if path.is_file())
    for relative in (
        "work/plm_reproduction.json", "work/classical_attestation.json",
        "work/plm_reference_contract.tsv", "work/classical_reference_contract.tsv",
        "work/profile_members.tsv", "work/profile_inclusion_ledger.tsv",
        "work/psiblast_seed_ledger.tsv", "work/profile_artifact_registry.tsv",
        "work/raw_receipt_ledger.tsv", "work/runtime_resources.tsv",
        "work/pbs_job_resources.tsv", "work/scores/plm_scores.tsv", "work/scores/classical_scores.tsv",
        "work/supervised_fit_contract.tsv", "work/scores/supervised_head_diagnostics.tsv",
    ):
        selected.add(safe_file(benchmark_root, relative).resolve())
    classical_root = benchmark_root / "work/classical"
    selected.update(
        path.resolve()
        for pattern in ("fold_attestation.fold_*.json", "*.tsv")
        for path in classical_root.glob(pattern)
        if path.is_file()
    )
    for row in raw_rows:
        selected.add(safe_file(benchmark_root, row["artifact_path"]).resolve())
        receipt_path = safe_file(benchmark_root, row["receipt_path"]).resolve()
        selected.add(receipt_path)
        receipt = json_object(receipt_path)
        for relative in receipt.get("outputs", {}):
            selected.add(safe_file(benchmark_root, relative).resolve())
    checksum = (benchmark_root / "CHECKSUMS.sha256").resolve()
    checksum_temporary = (benchmark_root / "CHECKSUMS.sha256.tmp").resolve()
    return sorted(
        path for path in selected
        if path not in {checksum, checksum_temporary}
        and path.suffix != ".pyc"
        and "__pycache__" not in path.parts
    )


def publish_checksums(benchmark_root: Path, paths: Sequence[Path]) -> int:
    lines = [f"{sha256_file(path)}  {path.relative_to(benchmark_root.resolve())}" for path in paths]
    temporary = benchmark_root / "CHECKSUMS.sha256.tmp"
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temporary, benchmark_root / "CHECKSUMS.sha256")
    return len(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    config, project_root, benchmark_root = load_config(args.config)
    require(args.config.resolve() == (benchmark_root / "config/benchmark.json").resolve(), "validator requires canonical config path")
    require(int(config["parameters"]["folds"]) == 5, "validator requires frozen five-fold design")
    require(math.isclose(float(config["parameters"]["primary_specificity"]), 0.995), "primary specificity drift")

    cohort, references, input_attestation = validate_inputs(config, project_root, benchmark_root)
    validate_attestations(config, project_root, benchmark_root, input_attestation)
    seeds, members = validate_contracts_and_profiles(config, benchmark_root, cohort, references)
    raw_rows = validate_raw_receipts(config, benchmark_root, seeds, members)
    try:
        from validation_metrics import validate_final_metrics
        metric_audit = validate_final_metrics(benchmark_root, config)
    except ImportError as error:
        fail(f"independent metric validator unavailable: {error}")
    summary = validate_resolution_and_inference(config, benchmark_root, cohort, metric_audit)
    pbs_rows = validate_pbs(benchmark_root)

    validation = {
        "status": "PASS",
        "benchmark_id": config["benchmark_id"],
        "design_id": config["design_id"],
        "claim_boundary": config["title"],
        "validator_sha256": sha256_file(Path(__file__).resolve()),
        "cohort_records": len(cohort),
        "methods": list(ALL_METHODS),
        "tasks": ["h1_djr", "h2_vma_conditional", "vma_end_to_end"],
        "raw_receipt_rows": len(raw_rows),
        "pbs_job_receipt_rows": pbs_rows,
        "metric_recomputation": metric_audit,
        "validation_prediction_rows": 0,
        "test_prediction_rows": 0,
        "specificity_0.999_status": "RESOLUTION_LIMITED_SECONDARY",
        "fpm_status": "NOT_ESTIMABLE",
        "stop_gates_passed": [
            "frozen_source_and_derived_checksums", "cyclic_component_role_isolation",
            "attestation_source_and_output_bindings", "exact_reference_contracts",
            "exact_hmm_profile_partition", "deterministic_psiblast_seed_and_inclusion",
            "raw_receipt_stage_and_checksum_contract", "exact_cyclic_score_matrix",
            "independent_cycle_and_primary_metric_recomputation", "paired_ci_schema_no_p_holm",
            "h2_singleton_resolution_disclosure", "protected_split_zero_predictions",
            "pbs_resource_receipts", "release_checksum_coverage",
        ],
    }
    atomic_json(benchmark_root / "results/validation.json", validation)
    summary["status"] = "PASS"
    summary["validation_artifact"] = "validation.json"
    atomic_json(benchmark_root / "results/summary.json", summary)
    checksum_count = publish_checksums(benchmark_root, release_paths(benchmark_root, raw_rows))
    print(
        f"PASS validation; {metric_audit.get('query_score_rows', 'unknown')} query scores; "
        f"{len(raw_rows)} raw receipts; {checksum_count} release checksums"
    )


if __name__ == "__main__":
    main()
