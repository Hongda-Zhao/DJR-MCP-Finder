#!/usr/bin/env python3
"""Fail-closed validation for the v0/v0.1 ultra-remote development audit."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


METHODS = {
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
}
TASKS = {"h1_djr", "h2_vma_conditional", "vma_end_to_end"}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--project-root", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    project_root = (
        args.project_root.resolve()
        if args.project_root is not None
        else Path(config["project_root"]).resolve()
    )
    benchmark_root = (project_root / config["benchmark_root"]).resolve()
    results = benchmark_root / "results"
    figures = benchmark_root / "figures"
    work = benchmark_root / "work"

    reproduction = json.loads((work / "v01_reproduction.json").read_text(encoding="utf-8"))
    check(reproduction["status"] == "PASS", "v0.1 reproduction is not PASS")
    check(
        reproduction["max_absolute_deviation"] <= reproduction["tolerance"],
        "Historical ESM-2 3B reproduction exceeded tolerance",
    )
    check(
        reproduction["selected_split_counts"]
        == {"train": 6634, "validation": 0, "test": 0},
        "Protected split accounting is not Train-only",
    )
    check(reproduction["validation_prediction_rows"] == 0, "Validation was scored")
    check(reproduction["test_prediction_rows"] == 0, "Test was scored")
    check(
        reproduction["score_sha256"] == sha256(work / "v01_query_scores.tsv"),
        "v0.1 score checksum mismatch",
    )
    fit_contract = read_tsv(work / "v01_fit_contract.tsv")
    check(len(fit_contract) == 5, "Unexpected cyclic fit-contract row count")
    for row in fit_contract:
        check(row["status"] == "PASS", "A fit contract is not PASS")
        for key in (
            "fit_calibration_component_overlap",
            "fit_evaluation_component_overlap",
            "calibration_evaluation_component_overlap",
        ):
            check(row[key] == "0", f"Nonzero component overlap: {key}")

    fold_metrics = read_tsv(results / "fold_metrics.tsv")
    check(
        len(fold_metrics) == len(METHODS) * len(TASKS) * 5,
        "Unexpected fold-metric row count",
    )
    check({row["method"] for row in fold_metrics} == METHODS, "Method set mismatch")
    check({row["task"] for row in fold_metrics} == TASKS, "Task set mismatch")
    check(
        all(
            0.0 <= float(row["component_sensitivity_99.5"]) <= 1.0
            for row in fold_metrics
        ),
        "Sensitivity outside [0,1]",
    )
    check(
        all(0.0 <= float(row["evaluation_specificity"]) <= 1.0 for row in fold_metrics),
        "Specificity outside [0,1]",
    )
    for row in fold_metrics:
        pauc = row["normalized_pauc_fpr_0.005"]
        if row["low_fpr_pauc_status"] == "RESOLVABLE":
            check(pauc != "NA" and 0.0 <= float(pauc) <= 1.0, "Invalid resolvable pAUC")
        else:
            check(
                row["low_fpr_pauc_status"] == "RESOLUTION_LIMITED_NO_ESTIMATE"
                and pauc == "NA",
                "Resolution-limited pAUC was not suppressed",
            )

    summary = read_tsv(results / "method_summary.tsv")
    check(len(summary) == len(METHODS) * len(TASKS), "Unexpected summary row count")
    check(
        all(
            row["low_fpr_pauc_status"] == "NOT_HEADLINE_RESOLUTION_LIMITED_FOLD"
            for row in summary
            if row["task"] == "h2_vma_conditional"
        ),
        "H2 low-FPR resolution limitation was not propagated",
    )
    paired = read_tsv(results / "paired_v0_v01.tsv")
    check(len(paired) == len(TASKS) * 2 * 5, "Unexpected paired row count")
    check(
        all(
            row["matched_specificity_status"]
            in {"PASS_BOTH_ALL_FOLDS", "NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY"}
            for row in paired
        ),
        "Invalid paired specificity status",
    )
    complementarity = read_tsv(results / "plm_classical_complementarity.tsv")
    check(
        len(complementarity) == len(TASKS) * 5 * 6,
        "Unexpected PLM/classical complementarity row count",
    )
    for row in complementarity:
        total = sum(
            int(row[key])
            for key in (
                "both_have_any_detected_record",
                "plm_only_has_any_detected_record",
                "comparator_only_has_any_detected_record",
                "neither_has_any_detected_record",
            )
        )
        check(
            total == int(row["positive_components"]),
            "Complementarity detection partition does not sum to n",
        )
    strata = read_tsv(results / "stratum_sensitivity.tsv")
    check(
        len(strata) == len(METHODS) * len(TASKS) * 5,
        "Unexpected stratum row count",
    )
    strict = [
        row
        for row in strata
        if row["stratum"] == "blast_defined_qcov_ge80_pident_lt20"
    ]
    check(bool(strict), "Strict ultra-remote stratum is absent")
    check(
        all(row["inference_status"] == "CASE_SERIES_NO_CI" for row in strict),
        "Strict ultra-remote rows were promoted beyond case-series status",
    )
    check(
        all(row["ci95_low_fixed_threshold"] == "NA" for row in strict),
        "Strict case series unexpectedly has a lower CI",
    )
    check(
        all(row["ci95_high_fixed_threshold"] == "NA" for row in strict),
        "Strict case series unexpectedly has an upper CI",
    )
    strict_cases = read_tsv(results / "strict_qcov_ge80_lt20_cases.tsv")
    check(bool(strict_cases), "Strict case table is empty")
    check(
        all(
            float(row["best_blast_qcov"]) >= 80.0
            and float(row["best_blast_pident"]) < 20.0
            for row in strict_cases
        ),
        "Strict case table contains a non-strict case",
    )

    validation = json.loads((results / "validation.json").read_text(encoding="utf-8"))
    check(
        validation["status"] == "PASS_WITH_FORMAL_ULTRA_REMOTE_BLOCKED_BY_SAMPLE_SIZE",
        "Unexpected validation status",
    )
    check(
        validation["formal_ultra_remote_claim_allowed"] is False,
        "Formal ultra-remote claim was incorrectly enabled",
    )
    check(validation["validation_prediction_rows"] == 0, "Validation count is nonzero")
    check(validation["test_prediction_rows"] == 0, "Test count is nonzero")
    formal_minimum = validation["formal_ultra_remote_minimum_components"]
    check(
        all(
            count < formal_minimum
            for count in validation["strict_ultra_remote_positive_components"].values()
        ),
        "Formal sample-size gate should not pass",
    )

    required_figure_outputs = [
        figures / "ultra_remote_v0_v01.svg",
        figures / "ultra_remote_v0_v01.pdf",
        figures / "ultra_remote_v0_v01.png",
        figures / "ultra_remote_v0_v01.tiff",
        figures / "visualization_manifest.json",
        figures / "FIGURE_CONTRACT.md",
        figures / "FIGURE_LEGEND.md",
        figures / "QA_REPORT.md",
    ]
    check(
        all(path.is_file() and path.stat().st_size > 0 for path in required_figure_outputs),
        "A required figure output is missing/empty",
    )
    manifest = json.loads((figures / "visualization_manifest.json").read_text(encoding="utf-8"))
    check(manifest["backend"] == "python_matplotlib", "Unexpected figure backend")
    check(manifest["excluded_rows"] == 0, "Figure manifest reports excluded rows")
    for name, digest in manifest["outputs"].items():
        check(sha256(figures / name) == digest, f"Figure checksum mismatch: {name}")
    for name, digest in manifest["source_data"].items():
        check(
            sha256(figures / "source_data" / name) == digest,
            f"Figure source-data checksum mismatch: {name}",
        )

    checksum_targets = sorted(
        [
            *results.glob("*.tsv"),
            *results.glob("*.json"),
            *results.glob("*.md"),
            *figures.glob("ultra_remote_v0_v01.*"),
            *figures.glob("*.md"),
            figures / "visualization_manifest.json",
            *list((figures / "source_data").glob("*.tsv")),
        ],
        key=lambda path: str(path.relative_to(benchmark_root)),
    )
    lines = [
        f"{sha256(path)}  {path.relative_to(benchmark_root)}"
        for path in checksum_targets
    ]
    (benchmark_root / "CHECKSUMS.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        "PASS validated audit; formal ultra-remote claim remains blocked by "
        + json.dumps(validation["strict_ultra_remote_positive_components"], sort_keys=True)
    )


if __name__ == "__main__":
    main()
