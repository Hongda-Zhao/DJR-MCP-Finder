#!/usr/bin/env python3
"""Freeze Train-only outer-fold queries and positive reference manifests."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from common import (
    atomic_json,
    cyclic_fold_roles,
    load_config,
    profile_group,
    read_fasta,
    read_json,
    read_tsv,
    resolved_input,
    sha256_file,
    sha256_lines,
    write_fasta,
    write_tsv,
)


def validate_derived_outputs(input_root: Path, declared: object) -> bool:
    if not isinstance(declared, dict) or not declared:
        return False
    root = input_root.resolve()
    for relative, expected in declared.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            return False
        path = (input_root / relative).resolve()
        if (
            not path.is_relative_to(root)
            or not path.is_file()
            or len(expected) != 64
            or sha256_file(path) != expected
        ):
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    config, project_root, benchmark_root = load_config(args.config)
    input_root = benchmark_root / "inputs"
    attestation_path = input_root / "input_attestation.json"
    current_bindings = {
        "config_sha256": sha256_file(args.config.resolve()),
        "prepare_inputs_script_sha256": sha256_file(Path(__file__).resolve()),
        "common_script_sha256": sha256_file(Path(__file__).with_name("common.py")),
    }
    paths = {key: resolved_input(config, project_root, key) for key in config["inputs"]}
    for key, expected in config["expected_sha256"].items():
        observed = sha256_file(paths[key])
        if observed != expected:
            raise RuntimeError(f"Frozen input checksum mismatch for {key}: {observed} != {expected}")
    current_input_sha = {
        key: sha256_file(path) for key, path in paths.items() if path.is_file()
    }
    if attestation_path.exists() and not args.force:
        existing = read_json(attestation_path)
        if (
            existing.get("design_id") == config["design_id"]
            and existing.get("status") == "PASS"
            and all(existing.get(key) == value for key, value in current_bindings.items())
            and existing.get("input_sha256") == current_input_sha
            and validate_derived_outputs(
                input_root, existing.get("derived_output_sha256")
            )
        ):
            print(f"REUSE {attestation_path}")
            return
        raise RuntimeError(
            "Prepared inputs are not bound to the current design/config/source; rerun with --force"
        )

    audit = read_json(paths["postsplit_audit"])
    status = str(audit.get("status", audit.get("overall_status", ""))).upper()
    if status != "PASS":
        raise RuntimeError(f"Post-split leakage audit is not PASS: {status!r}")

    rows = read_tsv(paths["train_manifest"])
    sequences = read_fasta(paths["train_fasta"])
    if len(rows) != 6634 or len(sequences) != 6634:
        raise RuntimeError(f"Unexpected Train size: manifest={len(rows)}, fasta={len(sequences)}")
    ids = [row["protein_id"] for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != set(sequences):
        raise RuntimeError("Train manifest/FASTA ID contract failed")
    if {row["split"] for row in rows} != {"train"}:
        raise RuntimeError("Non-Train record entered the benchmark manifest")

    fold_rows = read_tsv(paths["fold_map"])
    folds = {row["global_component_id"]: int(row["fold"]) for row in fold_rows}
    if len(folds) != len(fold_rows) or set(folds.values()) != set(range(1, 6)):
        raise RuntimeError("Frozen fold map is malformed")

    cohort: list[dict[str, str]] = []
    for row in rows:
        component = row["global_component_id"]
        if component not in folds:
            raise RuntimeError(f"Train component absent from fold map: {component}")
        is_djr = row["head1_mask"] == "1" and row["head1_label"] == "djr"
        is_vma = row["head2_mask"] == "1" and row["head2_label"] == "viral_morphogenesis_associated"
        if is_vma and not is_djr:
            raise RuntimeError(f"VMA without DJR label: {row['protein_id']}")
        cohort.append(
            {
                "protein_id": row["protein_id"],
                "sequence_sha256": row["sequence_sha256"],
                "global_component_id": component,
                "fold": str(folds[component]),
                "source_dataset": row["source_dataset"],
                "source_cluster_id": row.get("source_cluster_id", ""),
                "family_metadata": row.get("family_metadata", ""),
                "length_aa": row["length_aa"],
                "is_djr": "1" if is_djr else "0",
                "is_vma": "1" if is_vma else "0",
                "profile_group": profile_group(row) if is_djr else "",
            }
        )

    cohort_fields = list(cohort[0])
    cohort_path = input_root / "cohort.tsv"
    write_tsv(cohort_path, cohort, cohort_fields)
    derived_paths = [cohort_path]
    reference_attestations = []
    fold_count = int(config["parameters"]["folds"])
    offset = int(config["parameters"]["calibration_fold_offset"])
    for fold in range(1, fold_count + 1):
        fold_root = input_root / f"fold_{fold}"
        calibration_fold, fit_folds = cyclic_fold_roles(fold, fold_count, offset)
        if len(fit_folds) != int(config["parameters"]["fit_fold_count"]):
            raise RuntimeError("Cyclic fit/calibration/evaluation fold contract failed")
        query_evaluation = [row for row in cohort if int(row["fold"]) == fold]
        query_calibration = [row for row in cohort if int(row["fold"]) == calibration_fold]
        query_combined = [
            {**row, "benchmark_role": "calibration"} for row in query_calibration
        ] + [
            {**row, "benchmark_role": "evaluation"} for row in query_evaluation
        ]
        query_evaluation_tsv = fold_root / "query_evaluation.tsv"
        query_evaluation_faa = fold_root / "query_evaluation.faa"
        query_calibration_tsv = fold_root / "query_calibration.tsv"
        query_calibration_faa = fold_root / "query_calibration.faa"
        query_combined_tsv = fold_root / "query_combined.tsv"
        query_combined_faa = fold_root / "query_combined.faa"
        write_tsv(query_evaluation_tsv, query_evaluation, cohort_fields)
        write_fasta(query_evaluation_faa, query_evaluation, sequences)
        write_tsv(query_calibration_tsv, query_calibration, cohort_fields)
        write_fasta(query_calibration_faa, query_calibration, sequences)
        write_tsv(
            query_combined_tsv,
            query_combined,
            [*cohort_fields, "benchmark_role"],
        )
        write_fasta(query_combined_faa, query_combined, sequences)
        derived_paths.extend(
            [
                query_evaluation_tsv,
                query_evaluation_faa,
                query_calibration_tsv,
                query_calibration_faa,
                query_combined_tsv,
                query_combined_faa,
            ]
        )
        query_components = {
            row["global_component_id"]
            for row in [*query_evaluation, *query_calibration]
        }
        for reference_kind, flag in (("djr", "is_djr"), ("vma", "is_vma")):
            reference = [
                row for row in cohort if int(row["fold"]) in fit_folds and row[flag] == "1"
            ]
            reference_components = {row["global_component_id"] for row in reference}
            if query_components & reference_components:
                raise RuntimeError(f"Component leakage in fold {fold} {reference_kind}")
            reference_path = fold_root / f"reference_{reference_kind}.tsv"
            fasta_path = fold_root / f"reference_{reference_kind}.faa"
            write_tsv(reference_path, reference, cohort_fields)
            write_fasta(fasta_path, reference, sequences)
            derived_paths.extend([reference_path, fasta_path])
            reference_attestations.append(
                {
                    "fold": fold,
                    "evaluation_fold": fold,
                    "calibration_fold": calibration_fold,
                    "fit_folds": fit_folds,
                    "reference_kind": reference_kind,
                    "record_count": len(reference),
                    "component_count": len(reference_components),
                    "id_sha256": sha256_lines(sorted(row["protein_id"] for row in reference)),
                    "manifest_sha256": sha256_file(reference_path),
                    "fasta_sha256": sha256_file(fasta_path),
                }
            )

    counts = Counter(row["source_dataset"] for row in cohort)
    if counts != Counter(
        {"viral_vma_djr": 336, "cellular_djr_none": 298, "hard_non_djr": 3000, "background_non_djr": 3000}
    ):
        raise RuntimeError(f"Unexpected source counts: {dict(counts)}")
    fold_metadata = read_json(paths["fold_metadata"])
    reference_attestation_path = input_root / "reference_attestation.tsv"
    write_tsv(
        reference_attestation_path,
        [
            {
                **row,
                "fit_folds": ",".join(map(str, row["fit_folds"])),
            }
            for row in reference_attestations
        ],
        [
            "fold",
            "evaluation_fold",
            "calibration_fold",
            "fit_folds",
            "reference_kind",
            "record_count",
            "component_count",
            "id_sha256",
            "manifest_sha256",
            "fasta_sha256",
        ],
    )
    derived_paths.append(reference_attestation_path)
    derived_output_sha = {
        str(path.resolve().relative_to(input_root.resolve())): sha256_file(path)
        for path in sorted(derived_paths, key=lambda value: str(value.resolve()))
    }
    attestation = {
        "status": "PASS",
        "design_id": config["design_id"],
        **current_bindings,
        "claim_boundary": config["title"],
        "allowed_split": "train",
        "record_count": len(cohort),
        "component_count": len({row["global_component_id"] for row in cohort}),
        "source_counts": dict(sorted(counts.items())),
        "fold_counts": dict(sorted(Counter(row["fold"] for row in cohort).items())),
        "fold_metadata": fold_metadata,
        "input_sha256": current_input_sha,
        "derived_output_sha256": derived_output_sha,
        "references": reference_attestations,
        "validation_prediction_rows": 0,
        "test_prediction_rows": 0,
    }
    atomic_json(attestation_path, attestation)
    print(f"PASS prepared {len(cohort)} Train rows in {input_root}")


if __name__ == "__main__":
    main()
