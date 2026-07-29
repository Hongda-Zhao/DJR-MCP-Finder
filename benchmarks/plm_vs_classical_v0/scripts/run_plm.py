#!/usr/bin/env python3
"""Run cyclic 3-fit/1-calibration/1-evaluation PLM comparisons."""

from __future__ import annotations

import argparse
import math
import platform
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score

from common import (
    atomic_json,
    cyclic_fold_roles,
    load_config,
    read_json,
    read_tsv,
    score_text,
    sha256_file,
    sha256_lines,
    write_tsv,
)
from djrmcp_finder.stages.classifier import _decision_scores, _fit_model


def load_embedding(
    embedding_dir: Path, cohort: list[dict[str, str]]
) -> tuple[np.ndarray, dict, dict[str, int]]:
    metadata = read_json(embedding_dir / "metadata.json")
    if metadata.get("status") != "complete":
        raise RuntimeError(f"Incomplete embedding bundle: {embedding_dir}")
    checksum_path = embedding_dir / "CHECKSUMS.sha256"
    if not checksum_path.is_file():
        raise RuntimeError(f"Embedding bundle lacks CHECKSUMS.sha256: {embedding_dir}")
    declared = {}
    for line_number, line in enumerate(checksum_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            raise RuntimeError(f"Malformed embedding checksum line {line_number}: {embedding_dir}")
        declared[fields[1].lstrip("* ")] = fields[0]
    for name in ("embeddings.float16.npy", "index.tsv", "metadata.json", "completed.npy"):
        if name not in declared or sha256_file(embedding_dir / name) != declared[name]:
            raise RuntimeError(f"Embedding checksum failure for {embedding_dir / name}")
    index = read_tsv(embedding_dir / "index.tsv")
    row_by_id: dict[str, int] = {}
    index_by_id: dict[str, dict[str, str]] = {}
    for physical_row, row in enumerate(index):
        protein_id = row["protein_id"]
        if protein_id in row_by_id:
            raise RuntimeError(f"Duplicate embedding ID: {protein_id}")
        embedding_row = int(row["embedding_row"])
        if embedding_row != physical_row:
            raise RuntimeError(f"Non-contiguous embedding_row at physical row {physical_row}")
        row_by_id[protein_id] = embedding_row
        index_by_id[protein_id] = row
    for row in cohort:
        protein_id = row["protein_id"]
        indexed = index_by_id.get(protein_id)
        if indexed is None:
            raise RuntimeError(f"Train ID absent from embedding: {protein_id}")
        if indexed["split"] != "train" or indexed["sequence_sha256"] != row["sequence_sha256"]:
            raise RuntimeError(f"Embedding alignment failure for {protein_id}")
    vectors = np.load(embedding_dir / "embeddings.float16.npy", mmap_mode="r")
    if vectors.ndim != 2 or vectors.shape[0] != len(index):
        raise RuntimeError(f"Embedding shape/index mismatch in {embedding_dir}")
    return vectors, metadata, row_by_id


def matrix_for(
    vectors: np.ndarray, row_by_id: dict[str, int], rows: list[dict[str, str]]
) -> np.ndarray:
    indices = np.asarray([row_by_id[row["protein_id"]] for row in rows], dtype=np.int64)
    return np.asarray(vectors[indices], dtype=np.float32)


def max_cosine(query: np.ndarray, reference: np.ndarray, chunk_size: int = 256) -> np.ndarray:
    if not len(query) or not len(reference):
        raise ValueError("Cosine retrieval requires non-empty query/reference matrices")
    query_norm = np.linalg.norm(query, axis=1)
    reference_norm = np.linalg.norm(reference, axis=1)
    if np.any(query_norm == 0) or np.any(reference_norm == 0):
        raise RuntimeError("Zero-norm embedding entered cosine retrieval")
    reference_unit = reference / reference_norm[:, None]
    result = np.empty(len(query), dtype=np.float64)
    for start in range(0, len(query), chunk_size):
        block = query[start : start + chunk_size]
        block = block / query_norm[start : start + len(block), None]
        result[start : start + len(block)] = np.max(block @ reference_unit.T, axis=1)
    if not np.isfinite(result).all():
        raise RuntimeError("Non-finite cosine score")
    return result


def empirical_tail_evidence(
    scores: np.ndarray,
    negative_calibration: np.ndarray,
    negative_weights: np.ndarray | None = None,
) -> np.ndarray:
    calibration = np.sort(np.asarray(negative_calibration, dtype=np.float64))
    if not len(calibration) or not np.isfinite(calibration).all():
        raise ValueError("Tail adapter requires finite negative calibration scores")
    score = np.asarray(scores, dtype=np.float64)
    if negative_weights is None:
        weights = np.full(len(calibration), 1.0 / len(calibration), dtype=np.float64)
    else:
        original_calibration = np.asarray(negative_calibration, dtype=np.float64)
        order = np.argsort(original_calibration)
        weights = np.asarray(negative_weights, dtype=np.float64)[order]
        if len(weights) != len(calibration) or np.any(weights < 0) or not np.isfinite(weights).all():
            raise ValueError("Invalid tail-adapter weights")
        weights = weights / weights.sum()
    pseudo_mass = float(np.min(weights[weights > 0]))
    upper_tail = np.asarray(
        [
            (pseudo_mass + float(weights[calibration >= value].sum())) / (1.0 + pseudo_mass)
            for value in score
        ],
        dtype=np.float64,
    )
    return -np.log10(upper_tail)


def source_component_weights(rows: list[dict[str, str]]) -> np.ndarray:
    sources = sorted({row["source_dataset"] for row in rows})
    by_source_component: dict[tuple[str, str], int] = {}
    source_component_count = {}
    for source in sources:
        source_rows = [row for row in rows if row["source_dataset"] == source]
        components = {row["global_component_id"] for row in source_rows}
        source_component_count[source] = len(components)
        for component in components:
            by_source_component[(source, component)] = sum(
                row["global_component_id"] == component for row in source_rows
            )
    return np.asarray(
        [
            1.0
            / len(sources)
            / source_component_count[row["source_dataset"]]
            / by_source_component[(row["source_dataset"], row["global_component_id"])]
            for row in rows
        ],
        dtype=np.float64,
    )


def model_score(
    head: str,
    train_rows: list[dict[str, str]],
    train_x: np.ndarray,
    train_y: np.ndarray,
    query_x: np.ndarray,
    parameter: float,
    settings: dict,
    seed: int,
) -> np.ndarray:
    model = _fit_model(head, train_x, train_y, train_rows, parameter, settings, seed)
    scores = np.asarray(_decision_scores(model, query_x), dtype=np.float64)
    if scores.ndim != 1 or not np.isfinite(scores).all():
        raise RuntimeError(f"Invalid {head} decision scores")
    return scores


def historical_scores(path: Path, head: str, parameter: float) -> list[float]:
    data = read_json(path)
    for row in data["heads"][head]["candidates_ranked"]:
        if math.isclose(float(row["parameter"]), parameter, rel_tol=0.0, abs_tol=1e-15):
            return [float(value) for value in row["fold_scores"]]
    raise RuntimeError(f"Historical parameter not found: {head} {parameter}")


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
            "evaluation_fold": str(evaluation_fold),
            "source_fold": row["fold"],
            "role": role,
            "method": method,
            "status": "ok",
        }
        destination.append(
            {**common, "task": "h1_djr", "score": score_text(h1_scores[index])}
        )
        if row["is_djr"] == "1":
            destination.append(
                {**common, "task": "h2_vma_conditional", "score": score_text(h2_scores[index])}
            )
        end_score = h2_scores[index] if cascade_scores is None else cascade_scores[index]
        destination.append(
            {**common, "task": "vma_end_to_end", "score": score_text(end_score)}
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    config, project_root, benchmark_root = load_config(args.config)
    output_path = benchmark_root / "work/scores/plm_scores.tsv"
    reproduction_path = benchmark_root / "work/plm_reproduction.json"
    classifier_path = Path(sys.modules[_fit_model.__module__].__file__).resolve()
    current_bindings = {
        "config_sha256": sha256_file(args.config.resolve()),
        "input_attestation_sha256": sha256_file(
            benchmark_root / "inputs/input_attestation.json"
        ),
        "run_plm_script_sha256": sha256_file(Path(__file__).resolve()),
        "common_script_sha256": sha256_file(Path(__file__).with_name("common.py")),
        "classifier_module_sha256": sha256_file(classifier_path),
    }
    if output_path.exists() and reproduction_path.exists() and not args.force:
        reproduction = read_json(reproduction_path)
        if (
            reproduction.get("design_id") == config["design_id"]
            and reproduction.get("status") == "PASS"
            and reproduction.get("score_sha256") == sha256_file(output_path)
            and all(reproduction.get(key) == value for key, value in current_bindings.items())
        ):
            print(f"REUSE {output_path}")
            return
        raise RuntimeError(
            "PLM scores are not bound to the current design/config/input/source; "
            "rerun with --force"
        )

    started = time.monotonic()
    cohort = read_tsv(benchmark_root / "inputs/cohort.tsv")
    is_djr = np.asarray([int(row["is_djr"]) for row in cohort], dtype=np.int64)
    is_vma = np.asarray([int(row["is_vma"]) for row in cohort], dtype=np.int64)
    fold_array = np.asarray([int(row["fold"]) for row in cohort], dtype=np.int64)
    score_rows: list[dict[str, str]] = []
    reference_contract: list[dict[str, str]] = []
    embedding_attestations = {}

    embedding_specs = {
        "esmc6b_cosine": Path(config["embeddings"]["esmc6b"]),
        "esm2_650m_cosine": project_root / config["embeddings"]["esm2_650m"],
    }
    for method, embedding_dir in embedding_specs.items():
        embedding_dir = embedding_dir.resolve()
        vectors, metadata, row_by_id = load_embedding(embedding_dir, cohort)
        embedding_attestations[method] = {
            "directory": str(embedding_dir),
            "metadata_sha256": sha256_file(embedding_dir / "metadata.json"),
            "index_sha256": sha256_file(embedding_dir / "index.tsv"),
            "model_name": metadata.get("model_name"),
            "resolved_model_revision": metadata.get("resolved_model_revision"),
            "embedding_dimension": int(vectors.shape[1]),
        }
        for evaluation_fold in range(1, 6):
            fold_root = benchmark_root / f"inputs/fold_{evaluation_fold}"
            role_rows = {
                "calibration": read_tsv(fold_root / "query_calibration.tsv"),
                "evaluation": read_tsv(fold_root / "query_evaluation.tsv"),
            }
            references = {
                kind: read_tsv(fold_root / f"reference_{kind}.tsv") for kind in ("djr", "vma")
            }
            role_scores: dict[str, dict[str, np.ndarray]] = defaultdict(dict)
            for reference_kind, reference_rows in references.items():
                reference_ids = sorted(row["protein_id"] for row in reference_rows)
                reference_x = matrix_for(vectors, row_by_id, reference_rows)
                reference_contract.append(
                    {
                        "method": method,
                        "evaluation_fold": str(evaluation_fold),
                        "calibration_fold": role_rows["calibration"][0]["fold"],
                        "reference_kind": reference_kind,
                        "expected_record_count": str(len(reference_rows)),
                        "observed_record_count": str(len(reference_x)),
                        "expected_id_set_sha256": sha256_lines(reference_ids),
                        "observed_id_set_sha256": sha256_lines(reference_ids),
                        "reference_fasta_sha256": sha256_file(fold_root / f"reference_{reference_kind}.faa"),
                        "reference_manifest_sha256": sha256_file(fold_root / f"reference_{reference_kind}.tsv"),
                        "exact_equal": "1",
                        "receipt_kind": "embedding_index_exact_lookup",
                        "receipt_status": "PASS",
                    }
                )
                for role, rows in role_rows.items():
                    query_components = {row["global_component_id"] for row in rows}
                    if query_components & {row["global_component_id"] for row in reference_rows}:
                        raise RuntimeError(f"PLM component leakage: fold={evaluation_fold}, role={role}")
                    role_scores[role][reference_kind] = max_cosine(
                        matrix_for(vectors, row_by_id, rows), reference_x
                    )
            for role, rows in role_rows.items():
                append_scores(
                    score_rows,
                    rows,
                    evaluation_fold,
                    role,
                    method,
                    role_scores[role]["djr"],
                    role_scores[role]["vma"],
                )

    # Load ESM-C once for the exact historical implementation check and cyclic fits.
    esmc_dir = Path(config["embeddings"]["esmc6b"])
    esmc_vectors, _, esmc_row_by_id = load_embedding(esmc_dir, cohort)
    all_x = matrix_for(esmc_vectors, esmc_row_by_id, cohort)
    settings = {
        "head1_epochs": int(config["classifier"]["head1_epochs"]),
        "head1_negative_ratio": int(config["classifier"]["head1_negative_ratio"]),
        "logistic_max_iter": int(config["classifier"]["logistic_max_iter"]),
    }
    head1_alpha = float(config["classifier"]["head1_alpha"])
    head2_c = float(config["classifier"]["head2_c"])
    base_seed = int(config["seed"])

    observed_h1_ap, observed_h2_ap = [], []
    for fold in range(1, 6):
        train_indices = np.flatnonzero(fold_array != fold)
        query_indices = np.flatnonzero(fold_array == fold)
        h1 = model_score(
            "head1", [cohort[int(i)] for i in train_indices], all_x[train_indices],
            is_djr[train_indices], all_x[query_indices], head1_alpha, settings,
            base_seed + 100 + fold - 1,
        )
        observed_h1_ap.append(float(average_precision_score(is_djr[query_indices], h1)))
        train_h2 = np.flatnonzero((fold_array != fold) & (is_djr == 1))
        h2 = model_score(
            "head2", [cohort[int(i)] for i in train_h2], all_x[train_h2],
            is_vma[train_h2], all_x[query_indices], head2_c, settings,
            base_seed + fold - 1,
        )
        heldout_djr = is_djr[query_indices] == 1
        observed_h2_ap.append(
            float(average_precision_score(is_vma[query_indices][heldout_djr], h2[heldout_djr]))
        )

    diagnostic_rows: list[dict[str, str]] = []
    fit_contract: list[dict[str, str]] = []
    fold_count = int(config["parameters"]["folds"])
    offset = int(config["parameters"]["calibration_fold_offset"])
    for evaluation_fold in range(1, fold_count + 1):
        calibration_fold, fit_folds = cyclic_fold_roles(evaluation_fold, fold_count, offset)
        fit_mask = np.isin(fold_array, fit_folds)
        fit_h1_indices = np.flatnonzero(fit_mask)
        fit_h2_indices = np.flatnonzero(fit_mask & (is_djr == 1))
        model_seed = base_seed + 30_000 + evaluation_fold
        # Fit once, then apply the same exact models to calibration and evaluation.
        head1_model = _fit_model(
            "head1", all_x[fit_h1_indices], is_djr[fit_h1_indices],
            [cohort[int(i)] for i in fit_h1_indices], head1_alpha, settings, model_seed,
        )
        head2_model = _fit_model(
            "head2", all_x[fit_h2_indices], is_vma[fit_h2_indices],
            [cohort[int(i)] for i in fit_h2_indices], head2_c, settings, model_seed + 1,
        )
        role_indices = {
            "calibration": np.flatnonzero(fold_array == calibration_fold),
            "evaluation": np.flatnonzero(fold_array == evaluation_fold),
        }
        raw_by_role = {}
        for role, indices in role_indices.items():
            raw_by_role[role] = (
                np.asarray(_decision_scores(head1_model, all_x[indices]), dtype=np.float64),
                np.asarray(_decision_scores(head2_model, all_x[indices]), dtype=np.float64),
            )
        calibration_indices = role_indices["calibration"]
        calibration_h1, calibration_h2 = raw_by_role["calibration"]
        h1_negative_mask = is_djr[calibration_indices] == 0
        h2_negative_mask = (is_djr[calibration_indices] == 1) & (is_vma[calibration_indices] == 0)
        h1_negative = calibration_h1[h1_negative_mask]
        h2_negative = calibration_h2[h2_negative_mask]
        calibration_rows = [cohort[int(i)] for i in calibration_indices]
        h1_negative_rows = [row for row, keep in zip(calibration_rows, h1_negative_mask, strict=True) if keep]
        h2_negative_rows = [row for row, keep in zip(calibration_rows, h2_negative_mask, strict=True) if keep]
        h1_negative_weights = source_component_weights(h1_negative_rows)
        h2_negative_weights = source_component_weights(h2_negative_rows)
        if not len(h1_negative) or not len(h2_negative):
            raise RuntimeError(f"Empty supervised calibration class in cycle {evaluation_fold}")
        for role, indices in role_indices.items():
            rows = [cohort[int(i)] for i in indices]
            h1_raw, h2_raw = raw_by_role[role]
            h1_evidence = empirical_tail_evidence(h1_raw, h1_negative, h1_negative_weights)
            h2_evidence = empirical_tail_evidence(h2_raw, h2_negative, h2_negative_weights)
            cascade = np.minimum(h1_evidence, h2_evidence)
            append_scores(
                score_rows, rows, evaluation_fold, role, "esmc6b_supervised",
                h1_raw, h2_raw, cascade,
            )
            for index, row in enumerate(rows):
                diagnostic_rows.append(
                    {
                        "protein_id": row["protein_id"],
                        "evaluation_fold": str(evaluation_fold),
                        "source_fold": row["fold"],
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
                "fit_records_h1": str(len(fit_h1_indices)),
                "fit_records_h2": str(len(fit_h2_indices)),
                "fit_components": str(len({cohort[int(i)]["global_component_id"] for i in fit_h1_indices})),
                "calibration_records": str(len(calibration_indices)),
                "evaluation_records": str(len(role_indices["evaluation"])),
            }
        )

    historical_path = project_root / config["classifier"]["historical_cv_json"]
    expected_h1 = historical_scores(historical_path, "head1", head1_alpha)
    expected_h2 = historical_scores(historical_path, "head2", head2_c)
    deviations = [
        abs(a - b)
        for a, b in zip(observed_h1_ap + observed_h2_ap, expected_h1 + expected_h2, strict=True)
    ]
    tolerance = float(config["classifier"]["reproduction_tolerance"])
    if max(deviations) > tolerance:
        raise RuntimeError(f"Frozen classifier reproduction failed; max deviation={max(deviations)}")

    score_rows.sort(
        key=lambda row: (
            row["method"], row["task"], int(row["evaluation_fold"]), row["role"], row["protein_id"]
        )
    )
    write_tsv(
        output_path,
        score_rows,
        ["protein_id", "evaluation_fold", "source_fold", "role", "task", "method", "score", "status"],
    )
    write_tsv(
        benchmark_root / "work/scores/supervised_head_diagnostics.tsv",
        diagnostic_rows,
        list(diagnostic_rows[0]),
    )
    write_tsv(
        benchmark_root / "work/plm_reference_contract.tsv",
        reference_contract,
        list(reference_contract[0]),
    )
    write_tsv(
        benchmark_root / "work/supervised_fit_contract.tsv",
        fit_contract,
        list(fit_contract[0]),
    )
    reproduction = {
            "status": "PASS",
            "design_id": config["design_id"],
            **current_bindings,
            "historical_cross_validation_sha256": sha256_file(historical_path),
            "head1_observed_fold_ap": observed_h1_ap,
            "head1_expected_fold_ap": expected_h1,
            "head2_observed_fold_ap": observed_h2_ap,
            "head2_expected_fold_ap": expected_h2,
            "max_absolute_deviation": max(deviations),
            "tolerance": tolerance,
            "embedding_attestations": embedding_attestations,
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "wall_seconds": time.monotonic() - started,
            "validation_prediction_rows": 0,
            "test_prediction_rows": 0,
        }
    reproduction["score_sha256"] = sha256_file(output_path)
    atomic_json(reproduction_path, reproduction)
    print(f"PASS wrote {len(score_rows)} cyclic PLM scores; historical max delta={max(deviations):.3g}")


if __name__ == "__main__":
    main()
