#!/usr/bin/env python3
"""Score the v0.1 ESM-2 3B encoder under the frozen v0 cyclic design."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score


SOURCE = Path(__file__).resolve()
LOCAL_PROJECT_ROOT = SOURCE.parents[3]
PARENT_SCRIPTS = LOCAL_PROJECT_ROOT / "benchmarks/plm_vs_classical_v0/scripts"
for value in (LOCAL_PROJECT_ROOT / "src", PARENT_SCRIPTS):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from common import (  # noqa: E402
    atomic_json,
    cyclic_fold_roles,
    read_json,
    read_tsv,
    score_text,
    sha256_file,
    sha256_lines,
    write_tsv,
)
from djrmcp_finder.stages.classifier import _decision_scores, _fit_model  # noqa: E402
from run_plm import (  # noqa: E402
    empirical_tail_evidence,
    historical_scores,
    load_embedding,
    matrix_for,
    max_cosine,
    model_score,
    source_component_weights,
)


TASKS = {
    "h1_djr": "is_djr",
    "h2_vma_conditional": "is_vma",
    "vma_end_to_end": "is_vma",
}


def append_scores(
    destination: list[dict[str, str]],
    rows: list[dict[str, str]],
    evaluation_fold: int,
    role: str,
    method: str,
    h1_scores: np.ndarray,
    h2_scores: np.ndarray,
    cascade_scores: np.ndarray | None = None,
) -> None:
    for index, row in enumerate(rows):
        common = {
            "protein_id": row["protein_id"],
            "global_component_id": row["global_component_id"],
            "evaluation_fold": str(evaluation_fold),
            "source_fold": row["fold"],
            "role": role,
            "source_dataset": row["source_dataset"],
            "method": method,
            "status": "ok",
        }
        destination.append(
            {
                **common,
                "task": "h1_djr",
                "label": row["is_djr"],
                "score": score_text(h1_scores[index]),
            }
        )
        if row["is_djr"] == "1":
            destination.append(
                {
                    **common,
                    "task": "h2_vma_conditional",
                    "label": row["is_vma"],
                    "score": score_text(h2_scores[index]),
                }
            )
        end_score = h2_scores[index] if cascade_scores is None else cascade_scores[index]
        destination.append(
            {
                **common,
                "task": "vma_end_to_end",
                "label": row["is_vma"],
                "score": score_text(end_score),
            }
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    project_root = Path(config["project_root"]).resolve()
    benchmark_root = (project_root / config["benchmark_root"]).resolve()
    parent_root = (project_root / config["parent_benchmark_root"]).resolve()
    parent_config_path = parent_root / "config/benchmark.json"
    parent_reproduction_path = parent_root / "work/plm_reproduction.json"
    parent_config = read_json(parent_config_path)
    parent_reproduction = read_json(parent_reproduction_path)
    output_path = benchmark_root / "work/v01_query_scores.tsv"
    reproduction_path = benchmark_root / "work/v01_reproduction.json"
    cohort_path = parent_root / "inputs/cohort.tsv"
    embedding_dir = Path(config["esm2_3b_embedding_dir"]).resolve()
    historical_path = (project_root / config["esm2_3b_historical_cv_json"]).resolve()
    classifier_path = Path(sys.modules[_fit_model.__module__].__file__).resolve()
    if parent_reproduction.get("status") != "PASS":
        raise RuntimeError("Parent PLM reproduction is not PASS")
    if parent_reproduction.get("design_id") != parent_config.get("design_id"):
        raise RuntimeError("Parent design/reproduction mismatch")
    if parent_reproduction.get("config_sha256") != sha256_file(parent_config_path):
        raise RuntimeError("Parent config has drifted since v0 PLM scoring")
    if parent_reproduction.get("classifier_module_sha256") != sha256_file(classifier_path):
        raise RuntimeError("Current classifier implementation differs from frozen v0")
    comparable_contract = {
        "seed": (config["seed"], parent_config["seed"]),
        "folds": (
            config["parameters"]["folds"],
            parent_config["parameters"]["folds"],
        ),
        "calibration_fold_offset": (
            config["parameters"]["calibration_fold_offset"],
            parent_config["parameters"]["calibration_fold_offset"],
        ),
        "head1_alpha": (
            config["classifier"]["head1_alpha"],
            parent_config["classifier"]["head1_alpha"],
        ),
        "head1_epochs": (
            config["classifier"]["head1_epochs"],
            parent_config["classifier"]["head1_epochs"],
        ),
        "head1_negative_ratio": (
            config["classifier"]["head1_negative_ratio"],
            parent_config["classifier"]["head1_negative_ratio"],
        ),
        "head2_c": (
            config["classifier"]["head2_c"],
            parent_config["classifier"]["head2_c"],
        ),
        "logistic_max_iter": (
            config["classifier"]["logistic_max_iter"],
            parent_config["classifier"]["logistic_max_iter"],
        ),
    }
    mismatched_contract = {
        key: values for key, values in comparable_contract.items() if values[0] != values[1]
    }
    if mismatched_contract:
        raise RuntimeError(f"v0/v0.1 paired-fit contract mismatch: {mismatched_contract}")
    bindings = {
        "config_sha256": sha256_file(args.config.resolve()),
        "parent_cohort_sha256": sha256_file(cohort_path),
        "parent_query_scores_sha256": sha256_file(parent_root / "results/query_scores.tsv"),
        "embedding_metadata_sha256": sha256_file(embedding_dir / "metadata.json"),
        "embedding_index_sha256": sha256_file(embedding_dir / "index.tsv"),
        "score_script_sha256": sha256_file(SOURCE),
        "parent_run_plm_sha256": sha256_file(PARENT_SCRIPTS / "run_plm.py"),
        "classifier_module_sha256": sha256_file(classifier_path),
        "parent_config_sha256": sha256_file(parent_config_path),
        "parent_plm_reproduction_sha256": sha256_file(parent_reproduction_path),
    }
    if output_path.is_file() and reproduction_path.is_file() and not args.force:
        prior = read_json(reproduction_path)
        if (
            prior.get("status") == "PASS"
            and prior.get("design_id") == config["design_id"]
            and prior.get("score_sha256") == sha256_file(output_path)
            and all(prior.get(key) == value for key, value in bindings.items())
        ):
            print(f"REUSE {output_path}")
            return
        raise RuntimeError("Existing v0.1 scores are not bound to current inputs/source")

    started = time.monotonic()
    cohort = read_tsv(cohort_path)
    vectors, metadata, row_by_id = load_embedding(embedding_dir, cohort)
    all_x = matrix_for(vectors, row_by_id, cohort)
    is_djr = np.asarray([int(row["is_djr"]) for row in cohort], dtype=np.int64)
    is_vma = np.asarray([int(row["is_vma"]) for row in cohort], dtype=np.int64)
    fold_array = np.asarray([int(row["fold"]) for row in cohort], dtype=np.int64)
    selected_split_counts = {"train": len(cohort), "validation": 0, "test": 0}
    fold_count = int(config["parameters"]["folds"])
    offset = int(config["parameters"]["calibration_fold_offset"])
    seed = int(config["seed"])
    classifier = config["classifier"]
    settings = {
        "head1_epochs": int(classifier["head1_epochs"]),
        "head1_negative_ratio": int(classifier["head1_negative_ratio"]),
        "logistic_max_iter": int(classifier["logistic_max_iter"]),
    }
    head1_alpha = float(classifier["head1_alpha"])
    head2_c = float(classifier["head2_c"])

    score_rows: list[dict[str, str]] = []
    reference_contract: list[dict[str, str]] = []
    fit_contract: list[dict[str, str]] = []
    diagnostics: list[dict[str, str]] = []

    # Controlled representation-only retrieval: the reference IDs are byte-for-byte
    # identical to the parent benchmark; only the encoder matrix changes.
    for evaluation_fold in range(1, fold_count + 1):
        fold_root = parent_root / f"inputs/fold_{evaluation_fold}"
        role_rows = {
            "calibration": read_tsv(fold_root / "query_calibration.tsv"),
            "evaluation": read_tsv(fold_root / "query_evaluation.tsv"),
        }
        reference_rows = {
            kind: read_tsv(fold_root / f"reference_{kind}.tsv")
            for kind in ("djr", "vma")
        }
        role_scores: dict[str, dict[str, np.ndarray]] = defaultdict(dict)
        for kind, references in reference_rows.items():
            reference_ids = sorted(row["protein_id"] for row in references)
            reference_components = {row["global_component_id"] for row in references}
            reference_x = matrix_for(vectors, row_by_id, references)
            reference_contract.append(
                {
                    "method": "esm2_3b_cosine",
                    "evaluation_fold": str(evaluation_fold),
                    "reference_kind": kind,
                    "reference_records": str(len(references)),
                    "reference_components": str(len(reference_components)),
                    "reference_id_set_sha256": sha256_lines(reference_ids),
                    "parent_reference_manifest_sha256": sha256_file(
                        fold_root / f"reference_{kind}.tsv"
                    ),
                    "exact_equal": "1",
                    "status": "PASS",
                }
            )
            for role, rows in role_rows.items():
                if {row["global_component_id"] for row in rows} & reference_components:
                    raise RuntimeError(
                        f"Component leakage in fold {evaluation_fold}, {role}, {kind}"
                    )
                role_scores[role][kind] = max_cosine(
                    matrix_for(vectors, row_by_id, rows), reference_x
                )
        for role, rows in role_rows.items():
            append_scores(
                score_rows,
                rows,
                evaluation_fold,
                role,
                "esm2_3b_cosine",
                role_scores[role]["djr"],
                role_scores[role]["vma"],
            )

    # Reproduce the historical 4-fit/1-heldout CV before accepting the embedding and
    # classifier implementation for the new cyclic comparison.
    observed_h1_ap: list[float] = []
    observed_h2_ap: list[float] = []
    for heldout_fold in range(1, fold_count + 1):
        train_indices = np.flatnonzero(fold_array != heldout_fold)
        query_indices = np.flatnonzero(fold_array == heldout_fold)
        h1_score = model_score(
            "head1",
            [cohort[int(i)] for i in train_indices],
            all_x[train_indices],
            is_djr[train_indices],
            all_x[query_indices],
            head1_alpha,
            settings,
            seed + 100 + heldout_fold - 1,
        )
        observed_h1_ap.append(
            float(average_precision_score(is_djr[query_indices], h1_score))
        )
        h2_train = np.flatnonzero((fold_array != heldout_fold) & (is_djr == 1))
        h2_score = model_score(
            "head2",
            [cohort[int(i)] for i in h2_train],
            all_x[h2_train],
            is_vma[h2_train],
            all_x[query_indices],
            head2_c,
            settings,
            seed + heldout_fold - 1,
        )
        heldout_djr = is_djr[query_indices] == 1
        observed_h2_ap.append(
            float(
                average_precision_score(
                    is_vma[query_indices][heldout_djr], h2_score[heldout_djr]
                )
            )
        )

    expected_h1 = historical_scores(historical_path, "head1", head1_alpha)
    expected_h2 = historical_scores(historical_path, "head2", head2_c)
    deviations = [
        abs(observed - expected)
        for observed, expected in zip(
            observed_h1_ap + observed_h2_ap,
            expected_h1 + expected_h2,
            strict=True,
        )
    ]
    tolerance = float(classifier["reproduction_tolerance"])
    if max(deviations) > tolerance:
        raise RuntimeError(
            f"ESM-2 3B historical CV reproduction failed: {max(deviations):.4g}"
        )

    # Task-adapted cyclic detector comparison. The exact same fold roles, labels,
    # hyperparameters, and seeds used for v0 are applied to the v0.1 encoder.
    for evaluation_fold in range(1, fold_count + 1):
        calibration_fold, fit_folds = cyclic_fold_roles(
            evaluation_fold, fold_count, offset
        )
        fit_mask = np.isin(fold_array, fit_folds)
        h1_fit = np.flatnonzero(fit_mask)
        h2_fit = np.flatnonzero(fit_mask & (is_djr == 1))
        model_seed = seed + 30_000 + evaluation_fold
        h1_model = _fit_model(
            "head1",
            all_x[h1_fit],
            is_djr[h1_fit],
            [cohort[int(i)] for i in h1_fit],
            head1_alpha,
            settings,
            model_seed,
        )
        h2_model = _fit_model(
            "head2",
            all_x[h2_fit],
            is_vma[h2_fit],
            [cohort[int(i)] for i in h2_fit],
            head2_c,
            settings,
            model_seed + 1,
        )
        role_indices = {
            "calibration": np.flatnonzero(fold_array == calibration_fold),
            "evaluation": np.flatnonzero(fold_array == evaluation_fold),
        }
        fit_components = {
            cohort[int(i)]["global_component_id"] for i in np.flatnonzero(fit_mask)
        }
        calibration_components = {
            cohort[int(i)]["global_component_id"]
            for i in role_indices["calibration"]
        }
        evaluation_components = {
            cohort[int(i)]["global_component_id"]
            for i in role_indices["evaluation"]
        }
        fit_cal_overlap = len(fit_components & calibration_components)
        fit_eval_overlap = len(fit_components & evaluation_components)
        cal_eval_overlap = len(calibration_components & evaluation_components)
        if fit_cal_overlap or fit_eval_overlap or cal_eval_overlap:
            raise RuntimeError(f"Component-role leakage in cycle {evaluation_fold}")
        raw_by_role: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for role, indices in role_indices.items():
            raw_by_role[role] = (
                np.asarray(_decision_scores(h1_model, all_x[indices]), dtype=np.float64),
                np.asarray(_decision_scores(h2_model, all_x[indices]), dtype=np.float64),
            )
        calibration_indices = role_indices["calibration"]
        calibration_rows = [cohort[int(i)] for i in calibration_indices]
        calibration_h1, calibration_h2 = raw_by_role["calibration"]
        h1_negative_mask = is_djr[calibration_indices] == 0
        h2_negative_mask = (is_djr[calibration_indices] == 1) & (
            is_vma[calibration_indices] == 0
        )
        h1_negative_rows = [
            row
            for row, keep in zip(calibration_rows, h1_negative_mask, strict=True)
            if keep
        ]
        h2_negative_rows = [
            row
            for row, keep in zip(calibration_rows, h2_negative_mask, strict=True)
            if keep
        ]
        h1_negative = calibration_h1[h1_negative_mask]
        h2_negative = calibration_h2[h2_negative_mask]
        if not len(h1_negative) or not len(h2_negative):
            raise RuntimeError(f"Empty calibration class in cycle {evaluation_fold}")
        h1_weights = source_component_weights(h1_negative_rows)
        h2_weights = source_component_weights(h2_negative_rows)

        for role, indices in role_indices.items():
            rows = [cohort[int(i)] for i in indices]
            h1_raw, h2_raw = raw_by_role[role]
            h1_evidence = empirical_tail_evidence(h1_raw, h1_negative, h1_weights)
            h2_evidence = empirical_tail_evidence(h2_raw, h2_negative, h2_weights)
            cascade = np.minimum(h1_evidence, h2_evidence)
            append_scores(
                score_rows,
                rows,
                evaluation_fold,
                role,
                "esm2_3b_supervised",
                h1_raw,
                h2_raw,
                cascade,
            )
            for index, row in enumerate(rows):
                diagnostics.append(
                    {
                        "protein_id": row["protein_id"],
                        "evaluation_fold": str(evaluation_fold),
                        "role": role,
                        "head1_raw_score": score_text(h1_raw[index]),
                        "head2_raw_score": score_text(h2_raw[index]),
                        "head1_tail_evidence": score_text(h1_evidence[index]),
                        "head2_tail_evidence": score_text(h2_evidence[index]),
                        "cascade_tail_evidence": score_text(cascade[index]),
                    }
                )
        fit_contract.append(
            {
                "evaluation_fold": str(evaluation_fold),
                "calibration_fold": str(calibration_fold),
                "fit_folds": ",".join(map(str, fit_folds)),
                "h1_fit_records": str(len(h1_fit)),
                "h2_fit_records": str(len(h2_fit)),
                "fit_components": str(
                    len(fit_components)
                ),
                "calibration_components": str(len(calibration_components)),
                "evaluation_components": str(len(evaluation_components)),
                "fit_calibration_component_overlap": str(fit_cal_overlap),
                "fit_evaluation_component_overlap": str(fit_eval_overlap),
                "calibration_evaluation_component_overlap": str(cal_eval_overlap),
                "status": "PASS",
            }
        )

    fields = [
        "protein_id",
        "global_component_id",
        "evaluation_fold",
        "source_fold",
        "role",
        "source_dataset",
        "task",
        "label",
        "method",
        "score",
        "status",
    ]
    score_rows.sort(
        key=lambda row: (
            row["method"],
            row["task"],
            int(row["evaluation_fold"]),
            row["role"],
            row["protein_id"],
        )
    )
    write_tsv(output_path, score_rows, fields)
    write_tsv(
        benchmark_root / "work/v01_reference_contract.tsv",
        reference_contract,
        list(reference_contract[0]),
    )
    write_tsv(
        benchmark_root / "work/v01_fit_contract.tsv",
        fit_contract,
        list(fit_contract[0]),
    )
    write_tsv(
        benchmark_root / "work/v01_supervised_diagnostics.tsv",
        diagnostics,
        list(diagnostics[0]),
    )
    reproduction = {
        "status": "PASS",
        "benchmark_id": config["benchmark_id"],
        "design_id": config["design_id"],
        **bindings,
        "embedding_model_name": metadata.get("model_name"),
        "embedding_model_revision": metadata.get("resolved_model_revision"),
        "embedding_dimension": int(vectors.shape[1]),
        "historical_cv_sha256": sha256_file(historical_path),
        "head1_observed_fold_ap": observed_h1_ap,
        "head1_expected_fold_ap": expected_h1,
        "head2_observed_fold_ap": observed_h2_ap,
        "head2_expected_fold_ap": expected_h2,
        "max_absolute_deviation": max(deviations),
        "tolerance": tolerance,
        "score_rows": len(score_rows),
        "selected_split_counts": selected_split_counts,
        "validation_prediction_rows": selected_split_counts["validation"],
        "test_prediction_rows": selected_split_counts["test"],
        "parent_contract": {
            key: values[0] for key, values in comparable_contract.items()
        },
        "wall_seconds": time.monotonic() - started,
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
    }
    reproduction["score_sha256"] = sha256_file(output_path)
    atomic_json(reproduction_path, reproduction)
    print(
        f"PASS wrote {len(score_rows)} v0.1 rows; "
        f"historical max delta={max(deviations):.3g}"
    )


if __name__ == "__main__":
    main()
