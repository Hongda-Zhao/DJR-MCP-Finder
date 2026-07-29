#!/usr/bin/env python3
"""Audit immutable V0 model results and write a checksum manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import joblib
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_recall_fscore_support,
    roc_auc_score,
    roc_curve,
)

from djrmcp_finder.config import load_config
from djrmcp_finder.test_ledger import (
    PRODUCTION_LEDGER_MODE,
    PRODUCTION_MANIFEST_SHA256,
    canonical_sha256 as _ledger_canonical_sha256,
    content_identity_payload,
    matching_identity_artifacts,
    resolve_test_state_locations,
    selection_decision_sha256,
)


EXPECTED_WEIGHTS = {"head1": 0.60, "head2": 0.30, "head3_phylum": 0.10}
EXPECTED_EMBEDDING_FILES = {
    "completed.npy",
    "embeddings.float16.npy",
    "index.tsv",
    "metadata.json",
}
EXPECTED_EVIDENCE_INPUTS = {
    "embedding_metadata",
    "embedding_checksums",
    "calibration",
    "cross_validation",
    "validation",
}
H3_KNOWN_CLASSES = ["Nucleocytoviricota", "Preplasmiviricota"]
H3_UNKNOWN = "unknown/other"
H3_NOT_REACHED = "not_reached"
H3_NOT_APPLICABLE = "not_applicable"
H3_OUTPUTS = [*H3_KNOWN_CLASSES, H3_UNKNOWN]
FULL_PATH_LABELS = [
    "non_djr",
    "djr_non_vma",
    *[f"vma::{label}" for label in H3_OUTPUTS],
]
TEST_COMPONENT_BOOTSTRAP_REPLICATES = 10_000
EXPECTED_PREDICTION_FIELDS = (
    "protein_id",
    "global_component_id",
    "source_dataset",
    "head1_true",
    "head1_djr_probability",
    "head1_predicted",
    "head2_true",
    "head2_vma_probability",
    "head2_raw_predicted",
    "head2_operational_predicted",
    "head3_true",
    "head3_formal_phylum",
    "head3_status",
    "head3_unknown_reason",
    "head3_oracle_nucleocytoviricota_probability",
    "head3_oracle_preplasmiviricota_probability",
    "head3_oracle_predicted",
    "head3_reached",
    "head3_operational_nucleocytoviricota_probability",
    "head3_operational_preplasmiviricota_probability",
    "head3_predicted",
    "operational_path_true",
    "operational_path_predicted",
    "operational_path_correct",
)
REQUIRED_MASTER_FIELDS = {
    "protein_id",
    "sequence_sha256",
    "split",
    "global_component_id",
    "source_dataset",
    "head1_label",
    "head2_label",
    "head2_mask",
    "head3_phylum_label",
    "head3_operational_label",
    "head3_scope_mask",
    "head3_mask",
    "head3_unknown_diagnostic_mask",
    "head3_status",
    "head3_unknown_reason",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return value


def _resolved(path_value: str | Path) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _canonical_sha256(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_manifest_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None or not REQUIRED_MASTER_FIELDS.issubset(reader.fieldnames):
            raise RuntimeError("Master manifest lacks fields required for independent Test audit")
        return list(reader)


def read_manifest_test_rows(path: Path) -> list[dict[str, str]]:
    return [row for row in read_manifest_rows(path) if row["split"] == "test"]


def read_prediction_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != EXPECTED_PREDICTION_FIELDS:
            raise RuntimeError("Prediction table schema differs from frozen cascade contract")
        return list(reader)


def _independent_probabilities(
    estimator: Any, x: np.ndarray, temperature: float
) -> np.ndarray:
    if not math.isfinite(temperature) or temperature <= 0:
        raise RuntimeError("frozen_model_reinference: invalid temperature")
    logits = np.asarray(estimator.decision_function(x), dtype=np.float64)
    if logits.ndim == 1:
        scaled = np.clip(logits / temperature, -60.0, 60.0)
        positive = 1.0 / (1.0 + np.exp(-scaled))
        return np.column_stack([1.0 - positive, positive])
    if logits.ndim != 2:
        raise RuntimeError("frozen_model_reinference: invalid decision-function shape")
    scaled = logits / temperature
    scaled -= scaled.max(axis=1, keepdims=True)
    exponent = np.exp(scaled)
    return exponent / exponent.sum(axis=1, keepdims=True)


def _load_independent_bundle(
    head_name: str,
    calibration: dict[str, Any],
    *,
    manifest_sha256: str,
    embedding_metadata_sha256: str,
) -> dict[str, Any]:
    head = calibration["heads"][head_name]
    model_path = _resolved(head["model_path"])
    if not model_path.is_file() or sha256_file(model_path) != head.get("model_sha256"):
        raise RuntimeError(f"frozen_model_reinference: model hash mismatch for {head_name}")
    bundle = joblib.load(model_path)
    expected_classes = (
        H3_KNOWN_CLASSES
        if head_name == "head3_phylum"
        else (["non_djr", "djr"] if head_name == "head1" else ["none", "viral_morphogenesis_associated"])
    )
    checks = (
        isinstance(bundle, dict),
        bundle.get("head") == head_name if isinstance(bundle, dict) else False,
        bundle.get("classes") == expected_classes if isinstance(bundle, dict) else False,
        bundle.get("classes") == head.get("classes") if isinstance(bundle, dict) else False,
        bundle.get("manifest_sha256") == manifest_sha256 if isinstance(bundle, dict) else False,
        bundle.get("embedding_metadata_sha256") == embedding_metadata_sha256
        if isinstance(bundle, dict)
        else False,
        bundle.get("temperature") == head.get("temperature") if isinstance(bundle, dict) else False,
        bundle.get("decision_threshold") == head.get("decision_threshold")
        if isinstance(bundle, dict)
        else False,
        hasattr(bundle.get("estimator"), "decision_function")
        if isinstance(bundle, dict)
        else False,
    )
    if not all(checks):
        raise RuntimeError(f"frozen_model_reinference: invalid bundle contract for {head_name}")
    return bundle


def _load_aligned_test_embeddings(
    manifest_path: Path, embedding_dir: Path
) -> tuple[list[dict[str, str]], np.ndarray, dict[str, Any]]:
    manifest_rows = read_manifest_rows(manifest_path)
    metadata_path = embedding_dir / "metadata.json"
    index_path = embedding_dir / "index.tsv"
    vector_path = embedding_dir / "embeddings.float16.npy"
    metadata = read_json(metadata_path)
    if (
        metadata.get("status") != "complete"
        or metadata.get("manifest_sha256") != sha256_file(manifest_path)
    ):
        raise RuntimeError("frozen_embedding_reinference: metadata lineage mismatch")
    with index_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"embedding_row", "protein_id", "sequence_sha256", "split"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise RuntimeError("frozen_embedding_reinference: index schema mismatch")
        index_rows = list(reader)
    vectors = np.load(vector_path, mmap_mode="r")
    if (
        vectors.ndim != 2
        or len(manifest_rows) != len(index_rows)
        or vectors.shape[0] != len(manifest_rows)
    ):
        raise RuntimeError("frozen_embedding_reinference: manifest/index/vector count mismatch")
    test_indices: list[int] = []
    for row_number, (master, index) in enumerate(
        zip(manifest_rows, index_rows, strict=True)
    ):
        try:
            embedding_row = int(index["embedding_row"])
        except ValueError as exc:
            raise RuntimeError("frozen_embedding_reinference: invalid embedding row") from exc
        if embedding_row != row_number or any(
            master[field] != index[field]
            for field in ("protein_id", "sequence_sha256", "split")
        ):
            raise RuntimeError(
                f"frozen_embedding_reinference: row alignment mismatch at {row_number}"
            )
        if master["split"] == "test":
            test_indices.append(row_number)
    test_rows = [manifest_rows[index] for index in test_indices]
    test_vectors = np.asarray(vectors[np.asarray(test_indices, dtype=np.int64)], dtype=np.float32)
    if not np.isfinite(test_vectors).all():
        raise RuntimeError("frozen_embedding_reinference: non-finite Test embedding")
    return test_rows, test_vectors, metadata


def _reinfer_frozen_test_predictions(
    manifest_path: Path,
    embedding_dir: Path,
    calibration: dict[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Load frozen vectors and joblib bundles and reconstruct every Test row."""

    test_rows, test_x, embedding_metadata = _load_aligned_test_embeddings(
        manifest_path, embedding_dir
    )
    manifest_sha256 = sha256_file(manifest_path)
    embedding_metadata_sha256 = sha256_file(embedding_dir / "metadata.json")
    if (
        calibration.get("manifest_sha256") != manifest_sha256
        or calibration.get("embedding_metadata_sha256") != embedding_metadata_sha256
    ):
        raise RuntimeError("frozen_model_reinference: calibration input lineage mismatch")
    bundles = {
        head: _load_independent_bundle(
            head,
            calibration,
            manifest_sha256=manifest_sha256,
            embedding_metadata_sha256=embedding_metadata_sha256,
        )
        for head in ("head1", "head2", "head3_phylum")
    }
    probabilities = {
        head: _independent_probabilities(
            bundle["estimator"], test_x, float(bundle["temperature"])
        )
        for head, bundle in bundles.items()
        if head != "head3_phylum"
    }
    h1_probability = probabilities["head1"][:, 1]
    h2_probability = probabilities["head2"][:, 1]
    h1_positive = h1_probability >= float(bundles["head1"]["decision_threshold"])
    h2_positive = h2_probability >= float(bundles["head2"]["decision_threshold"])
    h3_threshold = float(bundles["head3_phylum"]["decision_threshold"])
    scope = np.asarray([row["head3_scope_mask"] == "1" for row in test_rows], dtype=bool)
    reached = h1_positive & h2_positive
    oracle_probability = _independent_probabilities(
        bundles["head3_phylum"]["estimator"],
        test_x[scope],
        float(bundles["head3_phylum"]["temperature"]),
    )
    operational_probability = _independent_probabilities(
        bundles["head3_phylum"]["estimator"],
        test_x[reached],
        float(bundles["head3_phylum"]["temperature"]),
    )
    oracle_by_row = {
        int(index): probability
        for index, probability in zip(np.flatnonzero(scope), oracle_probability, strict=True)
    }
    operational_by_row = {
        int(index): probability
        for index, probability in zip(
            np.flatnonzero(reached), operational_probability, strict=True
        )
    }
    rows: list[dict[str, str]] = []
    for index, master in enumerate(test_rows):
        oracle = oracle_by_row.get(index)
        operational = operational_by_row.get(index)
        oracle_label = _h3_label(oracle, h3_threshold) if oracle is not None else H3_NOT_APPLICABLE
        h3_label = (
            _h3_label(operational, h3_threshold)
            if operational is not None
            else H3_NOT_REACHED
        )
        truth_path = _truth_path(master)
        if not h1_positive[index]:
            predicted_path = "non_djr"
        elif not h2_positive[index]:
            predicted_path = "djr_non_vma"
        else:
            predicted_path = f"vma::{h3_label}"
        rows.append(
            {
                "protein_id": master["protein_id"],
                "global_component_id": master["global_component_id"],
                "source_dataset": master["source_dataset"],
                "head1_true": master["head1_label"],
                "head1_djr_probability": f"{h1_probability[index]:.17g}",
                "head1_predicted": "djr" if h1_positive[index] else "non_djr",
                "head2_true": master["head2_label"],
                "head2_vma_probability": f"{h2_probability[index]:.17g}",
                "head2_raw_predicted": (
                    "viral_morphogenesis_associated" if h2_positive[index] else "none"
                ),
                "head2_operational_predicted": (
                    H3_NOT_REACHED
                    if not h1_positive[index]
                    else (
                        "viral_morphogenesis_associated"
                        if h2_positive[index]
                        else "none"
                    )
                ),
                "head3_true": master["head3_operational_label"],
                "head3_formal_phylum": master["head3_phylum_label"],
                "head3_status": master["head3_status"],
                "head3_unknown_reason": master["head3_unknown_reason"],
                "head3_oracle_nucleocytoviricota_probability": (
                    f"{oracle[0]:.17g}" if oracle is not None else "NA"
                ),
                "head3_oracle_preplasmiviricota_probability": (
                    f"{oracle[1]:.17g}" if oracle is not None else "NA"
                ),
                "head3_oracle_predicted": oracle_label,
                "head3_reached": "1" if reached[index] else "0",
                "head3_operational_nucleocytoviricota_probability": (
                    f"{operational[0]:.17g}" if operational is not None else "NA"
                ),
                "head3_operational_preplasmiviricota_probability": (
                    f"{operational[1]:.17g}" if operational is not None else "NA"
                ),
                "head3_predicted": h3_label,
                "operational_path_true": truth_path,
                "operational_path_predicted": predicted_path,
                "operational_path_correct": "1" if truth_path == predicted_path else "0",
            }
        )
    return rows, {
        "manifest_sha256": manifest_sha256,
        "embedding_metadata_sha256": embedding_metadata_sha256,
        "embedding_row_count": int(len(test_rows)),
        "model_sha256": {
            head: calibration["heads"][head]["model_sha256"] for head in bundles
        },
        "probability_method": "joblib_estimator_decision_function_plus_frozen_temperature",
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float | None]:
    if total == 0:
        return [None, None]
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = proportion + z * z / (2.0 * total)
    spread = z * math.sqrt(
        proportion * (1.0 - proportion) / total + z * z / (4 * total * total)
    )
    return [(centre - spread) / denominator, (centre + spread) / denominator]


def _component_bootstrap_fraction(
    success: np.ndarray,
    eligible: np.ndarray,
    groups: np.ndarray,
    *,
    seed: int,
    replicates: int = TEST_COMPONENT_BOOTSTRAP_REPLICATES,
) -> dict[str, Any]:
    """Independently cluster-bootstrap a fraction over global components."""

    success = np.asarray(success, dtype=bool)
    eligible = np.asarray(eligible, dtype=bool)
    groups = np.asarray(groups, dtype=str)
    if not (len(success) == len(eligible) == len(groups)) or not len(groups):
        raise RuntimeError("independent_component_bootstrap: arrays are not aligned")
    unique_groups, inverse = np.unique(groups, return_inverse=True)
    if not len(unique_groups):
        raise RuntimeError("independent_component_bootstrap: no components")
    numerator_by_component = np.bincount(
        inverse,
        weights=(success & eligible).astype(np.int64),
        minlength=len(unique_groups),
    )
    denominator_by_component = np.bincount(
        inverse, weights=eligible.astype(np.int64), minlength=len(unique_groups)
    )
    rng = np.random.default_rng(seed)
    component_probability = np.repeat(1.0 / len(unique_groups), len(unique_groups))
    sampled_values: list[float] = []
    for offset in range(0, replicates, 512):
        size = min(512, replicates - offset)
        multiplicity = rng.multinomial(
            len(unique_groups), component_probability, size=size
        )
        numerator = multiplicity @ numerator_by_component
        denominator = multiplicity @ denominator_by_component
        usable = denominator > 0
        sampled_values.extend((numerator[usable] / denominator[usable]).tolist())
    values = np.asarray(sampled_values, dtype=np.float64)
    return {
        "method": "unstratified_global_component_multinomial_percentile_bootstrap",
        "unit": "global_component_id",
        "confidence_level": 0.95,
        "replicates": replicates,
        "seed": seed,
        "component_count": int(len(unique_groups)),
        "effective_replicates": int(len(values)),
        "ci_95pct": (
            [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]
            if len(values)
            else [None, None]
        ),
    }


def _component_bootstrap_multiclass(
    y: np.ndarray,
    prediction: np.ndarray,
    closed_prediction: np.ndarray,
    groups: np.ndarray,
    *,
    seed: int,
    replicates: int = TEST_COMPONENT_BOOTSTRAP_REPLICATES,
) -> dict[str, Any]:
    """Independently recompute component-aware H3 intervals."""

    y = np.asarray(y, dtype=np.int64)
    prediction = np.asarray(prediction, dtype=np.int64)
    closed_prediction = np.asarray(closed_prediction, dtype=np.int64)
    groups = np.asarray(groups, dtype=str)
    if not (len(y) == len(prediction) == len(closed_prediction) == len(groups)):
        raise RuntimeError("independent_h3_bootstrap: arrays are not aligned")
    unique_groups, inverse = np.unique(groups, return_inverse=True)
    if not len(unique_groups):
        raise RuntimeError("independent_h3_bootstrap: no components")
    class_count = len(H3_KNOWN_CLASSES)
    support = np.zeros((len(unique_groups), class_count), dtype=np.int64)
    predicted = np.zeros_like(support)
    true_positive = np.zeros_like(support)
    closed_predicted = np.zeros_like(support)
    closed_true_positive = np.zeros_like(support)
    for class_index in range(class_count):
        for row_index, component_index in enumerate(inverse):
            if y[row_index] == class_index:
                support[component_index, class_index] += 1
            if prediction[row_index] == class_index:
                predicted[component_index, class_index] += 1
            if y[row_index] == class_index and prediction[row_index] == class_index:
                true_positive[component_index, class_index] += 1
            if closed_prediction[row_index] == class_index:
                closed_predicted[component_index, class_index] += 1
            if y[row_index] == class_index and closed_prediction[row_index] == class_index:
                closed_true_positive[component_index, class_index] += 1
    rng = np.random.default_rng(seed)
    component_probability = np.repeat(1.0 / len(unique_groups), len(unique_groups))
    samples: dict[str, list[float]] = defaultdict(list)
    per_class_samples = {
        label: {"recall": [], "precision": []} for label in H3_KNOWN_CLASSES
    }
    for offset in range(0, replicates, 512):
        size = min(512, replicates - offset)
        multiplicity = rng.multinomial(
            len(unique_groups), component_probability, size=size
        )
        batch_support = multiplicity @ support
        usable = np.all(batch_support > 0, axis=1)
        if not np.any(usable):
            continue
        batch_support = batch_support[usable].astype(np.float64)
        batch_predicted = (multiplicity @ predicted)[usable].astype(np.float64)
        batch_tp = (multiplicity @ true_positive)[usable].astype(np.float64)
        batch_closed_predicted = (multiplicity @ closed_predicted)[usable].astype(
            np.float64
        )
        batch_closed_tp = (multiplicity @ closed_true_positive)[usable].astype(
            np.float64
        )
        recall = batch_tp / batch_support
        precision = np.divide(
            batch_tp,
            batch_predicted,
            out=np.zeros_like(batch_tp),
            where=batch_predicted > 0,
        )
        f1 = np.divide(
            2.0 * recall * precision,
            recall + precision,
            out=np.zeros_like(recall),
            where=(recall + precision) > 0,
        )
        closed_recall = batch_closed_tp / batch_support
        closed_precision = np.divide(
            batch_closed_tp,
            batch_closed_predicted,
            out=np.zeros_like(batch_closed_tp),
            where=batch_closed_predicted > 0,
        )
        closed_f1 = np.divide(
            2.0 * closed_recall * closed_precision,
            closed_recall + closed_precision,
            out=np.zeros_like(closed_recall),
            where=(closed_recall + closed_precision) > 0,
        )
        samples["macro_f1_unknown_as_error"].extend(np.mean(f1, axis=1).tolist())
        samples["balanced_accuracy_unknown_as_error"].extend(
            np.mean(recall, axis=1).tolist()
        )
        samples["closed_set_macro_f1"].extend(np.mean(closed_f1, axis=1).tolist())
        samples["closed_set_balanced_accuracy"].extend(
            np.mean(closed_recall, axis=1).tolist()
        )
        for class_index, label in enumerate(H3_KNOWN_CLASSES):
            per_class_samples[label]["recall"].extend(recall[:, class_index].tolist())
            per_class_samples[label]["precision"].extend(
                precision[:, class_index].tolist()
            )

    def interval(sample: Sequence[float]) -> dict[str, Any]:
        values = np.asarray(sample, dtype=np.float64)
        return {
            "effective_replicates": int(len(values)),
            "ci_95pct": (
                [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]
                if len(values)
                else [None, None]
            ),
        }

    return {
        "method": "unstratified_global_component_multinomial_percentile_bootstrap",
        "unit": "global_component_id",
        "confidence_level": 0.95,
        "replicates": replicates,
        "seed": seed,
        "component_count": int(len(unique_groups)),
        "metrics": {name: interval(sample) for name, sample in samples.items()},
        "per_class": {
            label: {
                name: interval(sample) for name, sample in class_samples.items()
            }
            for label, class_samples in per_class_samples.items()
        },
    }


def _fpr_at_recall(y: np.ndarray, score: np.ndarray, target: float) -> float | None:
    fpr, tpr, _ = roc_curve(y, score)
    eligible = fpr[tpr >= target]
    return float(eligible.min()) if len(eligible) else None


def _binary_metrics(y: np.ndarray, probability: np.ndarray, threshold: float) -> dict[str, Any]:
    prediction = (probability >= threshold).astype(np.int64)
    precision, recall, f1, support = precision_recall_fscore_support(
        y, prediction, labels=[0, 1], zero_division=0
    )
    return {
        "n": len(y),
        "positive": int(y.sum()),
        "negative": int((y == 0).sum()),
        "threshold": threshold,
        "average_precision": float(average_precision_score(y, probability)),
        "roc_auc": float(roc_auc_score(y, probability)),
        "mcc": float(matthews_corrcoef(y, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
        "precision_by_class": precision,
        "recall_by_class": recall,
        "f1_by_class": f1,
        "support_by_class": support,
        "confusion_matrix": confusion_matrix(y, prediction, labels=[0, 1]),
        "fpr_at_90pct_recall": _fpr_at_recall(y, probability, 0.90),
        "fpr_at_95pct_recall": _fpr_at_recall(y, probability, 0.95),
    }


def _binary_metric_values(
    y: np.ndarray, probability: np.ndarray, prediction: np.ndarray
) -> dict[str, float] | None:
    if len(y) == 0 or set(np.unique(y)) != {0, 1}:
        return None
    precision, recall, f1, _ = precision_recall_fscore_support(
        y, prediction, labels=[0, 1], zero_division=0
    )
    return {
        "average_precision": float(average_precision_score(y, probability)),
        "roc_auc": float(roc_auc_score(y, probability)),
        "mcc": float(matthews_corrcoef(y, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
        "positive_precision": float(precision[1]),
        "positive_recall": float(recall[1]),
        "positive_f1": float(f1[1]),
    }


def _component_bootstrap_binary(
    y: np.ndarray,
    probability: np.ndarray,
    groups: np.ndarray,
    *,
    threshold: float,
    seed: int,
    prediction_override: np.ndarray | None = None,
    replicates: int = TEST_COMPONENT_BOOTSTRAP_REPLICATES,
) -> dict[str, Any]:
    y = np.asarray(y, dtype=np.int64)
    probability = np.asarray(probability, dtype=np.float64)
    groups = np.asarray(groups, dtype=str)
    prediction = (
        (probability >= threshold).astype(np.int64)
        if prediction_override is None
        else np.asarray(prediction_override, dtype=np.int64)
    )
    unique_groups, row_group_index = np.unique(groups, return_inverse=True)
    if not len(unique_groups):
        raise RuntimeError("Independent bootstrap found no global components")
    rng = np.random.default_rng(seed)
    samples: dict[str, list[float]] = defaultdict(list)
    ascending = np.argsort(probability, kind="mergesort")
    score_starts = np.flatnonzero(
        np.concatenate(
            [[True], probability[ascending][1:] != probability[ascending][:-1]]
        )
    )
    y_positive = y == 1
    prediction_positive = prediction == 1
    masks = {
        "tp": (y_positive & prediction_positive).astype(np.int64),
        "fp": (~y_positive & prediction_positive).astype(np.int64),
        "tn": (~y_positive & ~prediction_positive).astype(np.int64),
        "fn": (y_positive & ~prediction_positive).astype(np.int64),
    }
    batch_size = 256
    component_probability = np.full(
        len(unique_groups), 1.0 / len(unique_groups), dtype=np.float64
    )
    for start in range(0, replicates, batch_size):
        batch = min(batch_size, replicates - start)
        component_counts = rng.multinomial(
            len(unique_groups), component_probability, size=batch
        )
        weights = component_counts[:, row_group_index]
        positives = weights @ y_positive.astype(np.int64)
        negatives = weights @ (~y_positive).astype(np.int64)
        valid = (positives > 0) & (negatives > 0)
        if not np.any(valid):
            continue
        weights = weights[valid]
        positives = positives[valid].astype(np.float64)
        negatives = negatives[valid].astype(np.float64)
        tp = (weights @ masks["tp"]).astype(np.float64)
        fp = (weights @ masks["fp"]).astype(np.float64)
        tn = (weights @ masks["tn"]).astype(np.float64)
        fn = (weights @ masks["fn"]).astype(np.float64)
        ordered_weights = weights[:, ascending]
        positive_by_score = np.add.reduceat(
            ordered_weights * y_positive[ascending], score_starts, axis=1
        ).astype(np.float64)
        negative_by_score = np.add.reduceat(
            ordered_weights * (~y_positive[ascending]), score_starts, axis=1
        ).astype(np.float64)
        cumulative_negative_below = (
            np.cumsum(negative_by_score, axis=1) - negative_by_score
        )
        roc_auc = np.sum(
            positive_by_score
            * (cumulative_negative_below + 0.5 * negative_by_score),
            axis=1,
        ) / (positives * negatives)
        positive_descending = positive_by_score[:, ::-1]
        negative_descending = negative_by_score[:, ::-1]
        cumulative_positive = np.cumsum(positive_descending, axis=1)
        cumulative_total = cumulative_positive + np.cumsum(
            negative_descending, axis=1
        )
        average_precision = np.sum(
            (positive_descending / positives[:, None])
            * np.divide(
                cumulative_positive,
                cumulative_total,
                out=np.zeros_like(cumulative_positive),
                where=cumulative_total > 0,
            ),
            axis=1,
        )
        mcc_denominator = np.sqrt(
            (tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)
        )
        mcc = np.divide(
            tp * tn - fp * fn,
            mcc_denominator,
            out=np.zeros_like(tp),
            where=mcc_denominator > 0,
        )
        positive_precision = np.divide(
            tp, tp + fp, out=np.zeros_like(tp), where=(tp + fp) > 0
        )
        positive_recall = tp / positives
        positive_f1 = np.divide(
            2.0 * positive_precision * positive_recall,
            positive_precision + positive_recall,
            out=np.zeros_like(tp),
            where=(positive_precision + positive_recall) > 0,
        )
        values = {
            "average_precision": average_precision,
            "roc_auc": roc_auc,
            "mcc": mcc,
            "balanced_accuracy": 0.5 * (tp / positives + tn / negatives),
            "positive_precision": positive_precision,
            "positive_recall": positive_recall,
            "positive_f1": positive_f1,
        }
        for name, value in values.items():
            samples[name].extend(value.tolist())
    intervals: dict[str, dict[str, Any]] = {}
    for name in (
        "average_precision",
        "roc_auc",
        "mcc",
        "balanced_accuracy",
        "positive_precision",
        "positive_recall",
        "positive_f1",
    ):
        values = np.asarray(samples[name], dtype=np.float64)
        intervals[name] = {
            "effective_replicates": int(len(values)),
            "ci_95pct": (
                [
                    float(np.quantile(values, 0.025)),
                    float(np.quantile(values, 0.975)),
                ]
                if len(values)
                else [None, None]
            ),
        }
    return {
        "method": "unstratified_global_component_multinomial_percentile_bootstrap",
        "unit": "global_component_id",
        "confidence_level": 0.95,
        "replicates": replicates,
        "seed": seed,
        "component_count": int(len(unique_groups)),
        "metrics": intervals,
    }


def _head1_negative_strata(
    metadata: Sequence[dict[str, str]], probability: np.ndarray, threshold: float
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for source in ("hard_non_djr", "background_non_djr"):
        selected = np.asarray(
            [index for index, row in enumerate(metadata) if row["source_dataset"] == source],
            dtype=np.int64,
        )
        scores = probability[selected]
        output[source] = {
            "n": len(selected),
            "false_positives": int(np.sum(scores >= threshold)),
            "false_positive_rate": float(np.mean(scores >= threshold)),
            "score_quantiles": {
                "q50": float(np.quantile(scores, 0.50)),
                "q90": float(np.quantile(scores, 0.90)),
                "q95": float(np.quantile(scores, 0.95)),
                "q99": float(np.quantile(scores, 0.99)),
            },
        }
    return output


def _ece(confidence: np.ndarray, correctness: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    value = 0.0
    for index in range(bins):
        if index == bins - 1:
            mask = (confidence >= edges[index]) & (confidence <= edges[index + 1])
        else:
            mask = (confidence >= edges[index]) & (confidence < edges[index + 1])
        if mask.any():
            value += float(mask.mean()) * abs(
                float(correctness[mask].mean()) - float(confidence[mask].mean())
            )
    return value if len(confidence) else float("nan")


def _multiclass_metrics(
    y: np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
    *,
    groups: np.ndarray | None = None,
    seed: int | None = None,
) -> tuple[dict[str, Any], np.ndarray]:
    best = probabilities.argmax(axis=1)
    confidence = probabilities.max(axis=1)
    prediction = best.copy()
    prediction[confidence < threshold] = -1
    recalls = []
    per_class: dict[str, Any] = {}
    for class_index, label in enumerate(H3_KNOWN_CLASSES):
        true_mask = y == class_index
        predicted_mask = prediction == class_index
        true_positive = int(np.sum(true_mask & predicted_mask))
        recall_total = int(true_mask.sum())
        precision_total = int(predicted_mask.sum())
        recall = true_positive / recall_total if recall_total else 0.0
        precision = true_positive / precision_total if precision_total else 0.0
        recalls.append(recall)
        per_class[label] = {
            "support": recall_total,
            "predicted": precision_total,
            "true_positive": true_positive,
            "recall": recall,
            "recall_naive_row_level_descriptive_wilson_95pct_ci": _wilson(
                true_positive, recall_total
            ),
            "precision": precision,
            "precision_naive_row_level_descriptive_wilson_95pct_ci": _wilson(
                true_positive, precision_total
            ),
        }
    one_hot = np.eye(len(H3_KNOWN_CLASSES), dtype=np.float64)[y]
    correctness = (best == y).astype(np.float64)
    metrics = {
        "n": len(y),
        "unknown_threshold": threshold,
        "unknown_rejections": int(np.sum(prediction == -1)),
        "unknown_rejection_fraction": float(np.mean(prediction == -1)),
        "macro_f1_unknown_as_error": float(
            f1_score(
                y,
                prediction,
                labels=list(range(len(H3_KNOWN_CLASSES))),
                average="macro",
                zero_division=0,
            )
        ),
        "balanced_accuracy_unknown_as_error": float(np.mean(recalls)),
        "closed_set_macro_f1": float(f1_score(y, best, average="macro")),
        "closed_set_balanced_accuracy": float(balanced_accuracy_score(y, best)),
        "ece": _ece(confidence, correctness),
        "multiclass_brier": float(
            np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))
        ),
        "per_class": per_class,
    }
    if groups is not None:
        if seed is None:
            raise RuntimeError("independent_h3_bootstrap: missing frozen seed")
        bootstrap = _component_bootstrap_multiclass(
            y, prediction, best, np.asarray(groups, dtype=str), seed=seed
        )
        metrics["component_bootstrap_95pct_ci"] = bootstrap
        for label in H3_KNOWN_CLASSES:
            metrics["per_class"][label]["component_bootstrap_95pct_ci"] = (
                bootstrap["per_class"][label]
            )
    return metrics, prediction


def _unknown_rejection_strata(
    confidence: np.ndarray,
    metadata: Sequence[dict[str, str]],
    threshold: float,
    *,
    groups: np.ndarray | None = None,
    seed: int | None = None,
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for field in ("head3_status", "head3_unknown_reason"):
        by_value: dict[str, Any] = {}
        for value in sorted({row[field] for row in metadata}):
            selected = np.asarray([row[field] == value for row in metadata], dtype=bool)
            scores = confidence[selected]
            rejected = int(np.sum(scores < threshold))
            by_value[value] = {
                "numerator": rejected,
                "denominator": int(len(scores)),
                "unknown_recall": rejected / len(scores) if len(scores) else None,
                "unknown_recall_naive_row_level_descriptive_wilson_95pct_ci": _wilson(
                    rejected, int(len(scores))
                ),
                "confidence_median": float(np.median(scores)) if len(scores) else None,
                "confidence_p95": (
                    float(np.quantile(scores, 0.95)) if len(scores) else None
                ),
            }
            if groups is not None and seed is not None:
                aligned_groups = np.asarray(groups, dtype=str)
                if len(aligned_groups) != len(confidence):
                    raise RuntimeError("independent_unknown_bootstrap: group mismatch")
                by_value[value]["unknown_recall_component_bootstrap_95pct_ci"] = (
                    _component_bootstrap_fraction(
                        confidence < threshold,
                        selected,
                        aligned_groups,
                        seed=seed,
                    )
                )
        output[field] = by_value
    return output


def _categorical_confusion(
    truth: Sequence[str], prediction: Sequence[str], rows: Sequence[str], columns: Sequence[str]
) -> list[list[int]]:
    row_index = {label: index for index, label in enumerate(rows)}
    column_index = {label: index for index, label in enumerate(columns)}
    matrix = [[0 for _ in columns] for _ in rows]
    for true_label, predicted_label in zip(truth, prediction, strict=True):
        if true_label not in row_index or predicted_label not in column_index:
            raise RuntimeError("Independent confusion matrix found an out-of-contract label")
        matrix[row_index[true_label]][column_index[predicted_label]] += 1
    return matrix


def _rate(successes: int, total: int) -> dict[str, Any]:
    return {
        "numerator": successes,
        "denominator": total,
        "fraction": successes / total if total else None,
        "naive_row_level_descriptive_wilson_95pct_ci": _wilson(successes, total),
    }


def _truth_path(row: dict[str, str]) -> str:
    if row["head1_label"] == "non_djr":
        return "non_djr"
    if row["head1_label"] != "djr":
        raise RuntimeError("Master has an invalid Head-1 truth")
    if row["head2_label"] == "none":
        return "djr_non_vma"
    if row["head2_label"] != "viral_morphogenesis_associated":
        raise RuntimeError("Master has an invalid Head-2 truth for a DJR row")
    if row["head3_operational_label"] not in H3_OUTPUTS:
        raise RuntimeError("Master has an invalid Head-3 operational truth")
    return f"vma::{row['head3_operational_label']}"


def _operational_cascade_metrics(
    metadata: Sequence[dict[str, str]],
    h1_positive: np.ndarray,
    h2_raw_positive: np.ndarray,
    h3_prediction: Sequence[str],
    *,
    groups: np.ndarray | None = None,
    seed: int | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    h3_reached = h1_positive & h2_raw_positive
    truth_paths = [_truth_path(row) for row in metadata]
    predicted_paths = []
    for h1, h2, h3 in zip(h1_positive, h2_raw_positive, h3_prediction, strict=True):
        if not h1:
            if h3 != H3_NOT_REACHED:
                raise RuntimeError("prediction_cascade_contract: H3 bypassed Head 1")
            predicted_paths.append("non_djr")
        elif not h2:
            if h3 != H3_NOT_REACHED:
                raise RuntimeError("prediction_cascade_contract: H3 bypassed Head 2")
            predicted_paths.append("djr_non_vma")
        else:
            if h3 not in H3_OUTPUTS:
                raise RuntimeError("prediction_cascade_contract: reached H3 lacks 3-output label")
            predicted_paths.append(f"vma::{h3}")
    path_correct = sum(
        true == predicted
        for true, predicted in zip(truth_paths, predicted_paths, strict=True)
    )
    scope = np.asarray([row["head3_scope_mask"] == "1" for row in metadata], dtype=bool)
    reached_scope = scope & h3_reached
    scope_truth = [
        row["head3_operational_label"]
        for row, selected in zip(metadata, scope, strict=True)
        if selected
    ]
    scope_prediction = [
        prediction for prediction, selected in zip(h3_prediction, scope, strict=True) if selected
    ]
    reached_scope_truth = [
        row["head3_operational_label"]
        for row, selected in zip(metadata, reached_scope, strict=True)
        if selected
    ]
    reached_scope_prediction = [
        prediction
        for prediction, selected in zip(h3_prediction, reached_scope, strict=True)
        if selected
    ]
    reached_scope_correct = sum(
        true == predicted
        for true, predicted in zip(
            reached_scope_truth, reached_scope_prediction, strict=True
        )
    )
    unknown_mask = np.asarray(
        [row["head3_unknown_diagnostic_mask"] == "1" for row in metadata], dtype=bool
    )
    unknown_by_reason: dict[str, Any] = {}
    reasons = {
        row["head3_unknown_reason"]
        for row, selected in zip(metadata, unknown_mask, strict=True)
        if selected
    }
    for reason in sorted(reasons):
        selected = np.asarray(
            [
                is_unknown and row["head3_unknown_reason"] == reason
                for row, is_unknown in zip(metadata, unknown_mask, strict=True)
            ],
            dtype=bool,
        )
        total = int(selected.sum())
        reached = int(np.sum(selected & h3_reached))
        correct_unknown = int(
            sum(
                is_selected and prediction == H3_UNKNOWN
                for is_selected, prediction in zip(selected, h3_prediction, strict=True)
            )
        )
        unknown_by_reason[reason] = {
            "numerator": correct_unknown,
            "denominator": total,
            "full_cascade_unknown_recall": correct_unknown / total if total else None,
            "full_cascade_unknown_recall_naive_row_level_descriptive_wilson_95pct_ci": _wilson(
                correct_unknown, total
            ),
            "reached_head3": reached,
            "attrited_before_head3": total - reached,
        }
    aligned_groups = None if groups is None else np.asarray(groups, dtype=str)
    if aligned_groups is not None:
        if seed is None or len(aligned_groups) != len(metadata):
            raise RuntimeError("independent_cascade_bootstrap: groups/seed mismatch")
        for reason, summary in unknown_by_reason.items():
            selected = np.asarray(
                [
                    row["head3_unknown_diagnostic_mask"] == "1"
                    and row["head3_unknown_reason"] == reason
                    for row in metadata
                ],
                dtype=bool,
            )
            summary["full_cascade_unknown_recall_component_bootstrap_95pct_ci"] = (
                _component_bootstrap_fraction(
                    np.asarray(h3_prediction) == H3_UNKNOWN,
                    selected,
                    aligned_groups,
                    seed=seed,
                )
            )
    h1_pass = int(h1_positive.sum())
    reached_n = int(h3_reached.sum())
    scope_n = int(scope.sum())
    scope_reached_n = int(reached_scope.sum())
    output = {
        "policy": {
            "order": ["head1", "head2", "head3_phylum"],
            "head3_gate": "head1_predicted_djr AND head2_predicted_vma",
            "not_reached_label": H3_NOT_REACHED,
            "head3_outputs": H3_OUTPUTS,
        },
        "stage_reach_attrition": {
            "input_n": len(metadata),
            "head1_pass_djr": h1_pass,
            "head1_attrited_non_djr": len(metadata) - h1_pass,
            "head1_pass_rate": _rate(h1_pass, len(metadata)),
            "head2_reached": h1_pass,
            "head2_pass_vma": reached_n,
            "head2_attrited_none": h1_pass - reached_n,
            "head2_pass_rate_given_reached": _rate(reached_n, h1_pass),
            "head3_reached": reached_n,
            "head3_output_counts": {
                label: sum(
                    reached and prediction == label
                    for reached, prediction in zip(h3_reached, h3_prediction, strict=True)
                )
                for label in H3_OUTPUTS
            },
            "truth_head3_scope_n": scope_n,
            "truth_head3_scope_reached": scope_reached_n,
            "truth_head3_scope_attrited_at_head1": int(np.sum(scope & ~h1_positive)),
            "truth_head3_scope_attrited_at_head2": int(
                np.sum(scope & h1_positive & ~h2_raw_positive)
            ),
            "truth_head3_scope_reach_rate": _rate(scope_reached_n, scope_n),
            "false_scope_head3_reached": int(np.sum(~scope & h3_reached)),
        },
        "head3_operational": {
            "truth_labels": H3_OUTPUTS,
            "three_output_labels": H3_OUTPUTS,
            "reached_scope_n": len(reached_scope_truth),
            "reached_scope_confusion_3x3": _categorical_confusion(
                reached_scope_truth, reached_scope_prediction, H3_OUTPUTS, H3_OUTPUTS
            ),
            "reached_scope_accuracy": _rate(
                reached_scope_correct, len(reached_scope_truth)
            ),
            "all_scope_n": len(scope_truth),
            "all_scope_output_labels": [H3_NOT_REACHED, *H3_OUTPUTS],
            "all_scope_confusion_3x4": _categorical_confusion(
                scope_truth,
                scope_prediction,
                H3_OUTPUTS,
                [H3_NOT_REACHED, *H3_OUTPUTS],
            ),
            "unknown_reason_strata": unknown_by_reason,
        },
        "full_path": {
            "labels": FULL_PATH_LABELS,
            "n": len(metadata),
            "correct": path_correct,
            "accuracy": path_correct / len(metadata) if metadata else None,
            "accuracy_naive_row_level_descriptive_wilson_95pct_ci": _wilson(
                path_correct, len(metadata)
            ),
            "confusion_matrix": _categorical_confusion(
                truth_paths, predicted_paths, FULL_PATH_LABELS, FULL_PATH_LABELS
            ),
        },
    }
    if aligned_groups is not None and seed is not None:
        output["stage_reach_attrition"]["head1_pass_rate"][
            "component_bootstrap_95pct_ci"
        ] = _component_bootstrap_fraction(
            h1_positive,
            np.ones(len(metadata), dtype=bool),
            aligned_groups,
            seed=seed,
        )
        output["stage_reach_attrition"]["head2_pass_rate_given_reached"][
            "component_bootstrap_95pct_ci"
        ] = _component_bootstrap_fraction(
            h3_reached, h1_positive, aligned_groups, seed=seed
        )
        output["stage_reach_attrition"]["truth_head3_scope_reach_rate"][
            "component_bootstrap_95pct_ci"
        ] = _component_bootstrap_fraction(
            reached_scope, scope, aligned_groups, seed=seed
        )
        reached_correct = np.asarray(
            [
                selected and row["head3_operational_label"] == prediction
                for row, prediction, selected in zip(
                    metadata, h3_prediction, reached_scope, strict=True
                )
            ],
            dtype=bool,
        )
        output["head3_operational"]["reached_scope_accuracy"][
            "component_bootstrap_95pct_ci"
        ] = _component_bootstrap_fraction(
            reached_correct, reached_scope, aligned_groups, seed=seed
        )
        output["full_path"]["accuracy_component_bootstrap_95pct_ci"] = (
            _component_bootstrap_fraction(
                np.asarray(truth_paths) == np.asarray(predicted_paths),
                np.ones(len(metadata), dtype=bool),
                aligned_groups,
                seed=seed,
            )
        )
    return output, truth_paths, predicted_paths


def _parse_probability(value: str, field: str) -> float:
    try:
        probability = float(value)
    except ValueError as exc:
        raise RuntimeError(f"prediction_probability_contract: invalid {field}") from exc
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise RuntimeError(f"prediction_probability_contract: out-of-range {field}")
    return probability


def _parse_probability_pair(
    row: dict[str, str], first: str, second: str, *, required: bool
) -> np.ndarray | None:
    values = (row[first], row[second])
    if not required:
        if values != ("NA", "NA"):
            raise RuntimeError("prediction_probability_contract: gated probabilities must be NA")
        return None
    if "NA" in values:
        raise RuntimeError("prediction_probability_contract: required probabilities are NA")
    probability = np.asarray(
        [_parse_probability(values[0], first), _parse_probability(values[1], second)],
        dtype=np.float64,
    )
    if not math.isclose(float(probability.sum()), 1.0, rel_tol=0.0, abs_tol=1e-10):
        raise RuntimeError("prediction_probability_contract: H3 probabilities do not sum to one")
    return probability


def _h3_label(probability: np.ndarray, threshold: float) -> str:
    if float(probability.max()) < threshold:
        return H3_UNKNOWN
    return H3_KNOWN_CLASSES[int(probability.argmax())]


def _independently_recompute_test_sections(
    master_rows: list[dict[str, str]],
    prediction_rows: list[dict[str, str]],
    calibration: dict[str, Any],
    *,
    seed: int,
) -> tuple[dict[str, Any], dict[str, bool]]:
    """Recompute Test metrics from row evidence and master truth, not metrics JSON."""

    if len(master_rows) != len(prediction_rows):
        raise RuntimeError("prediction_id_set_exact: row counts differ")
    h1_threshold = float(calibration["heads"]["head1"]["decision_threshold"])
    h2_threshold = float(calibration["heads"]["head2"]["decision_threshold"])
    h3_threshold = float(calibration["heads"]["head3_phylum"]["decision_threshold"])

    h1_probability = np.asarray(
        [
            _parse_probability(row["head1_djr_probability"], "head1_djr_probability")
            for row in prediction_rows
        ],
        dtype=np.float64,
    )
    h2_probability = np.asarray(
        [
            _parse_probability(row["head2_vma_probability"], "head2_vma_probability")
            for row in prediction_rows
        ],
        dtype=np.float64,
    )
    h1_positive = h1_probability >= h1_threshold
    h2_raw_positive = h2_probability >= h2_threshold
    h3_reached = h1_positive & h2_raw_positive
    groups = np.asarray([row["global_component_id"] for row in master_rows], dtype=str)

    copied_fields = {
        "global_component_id": "global_component_id",
        "source_dataset": "source_dataset",
        "head1_true": "head1_label",
        "head2_true": "head2_label",
        "head3_true": "head3_operational_label",
        "head3_formal_phylum": "head3_phylum_label",
        "head3_status": "head3_status",
        "head3_unknown_reason": "head3_unknown_reason",
    }
    for master, prediction in zip(master_rows, prediction_rows, strict=True):
        for prediction_field, master_field in copied_fields.items():
            if prediction[prediction_field] != master[master_field]:
                raise RuntimeError(
                    "prediction_master_truth_lineage: "
                    f"{prediction['protein_id']}/{prediction_field}"
                )

    oracle_probabilities: list[np.ndarray | None] = []
    operational_probabilities: list[np.ndarray | None] = []
    operational_h3_labels: list[str] = []
    for index, (master, prediction) in enumerate(
        zip(master_rows, prediction_rows, strict=True)
    ):
        expected_h1 = "djr" if h1_positive[index] else "non_djr"
        expected_h2_raw = (
            "viral_morphogenesis_associated" if h2_raw_positive[index] else "none"
        )
        expected_h2_operational = (
            H3_NOT_REACHED if not h1_positive[index] else expected_h2_raw
        )
        if prediction["head1_predicted"] != expected_h1:
            raise RuntimeError("prediction_cascade_contract: Head-1 label/threshold mismatch")
        if prediction["head2_raw_predicted"] != expected_h2_raw:
            raise RuntimeError("prediction_cascade_contract: raw Head-2 label/threshold mismatch")
        if prediction["head2_operational_predicted"] != expected_h2_operational:
            raise RuntimeError("prediction_cascade_contract: Head-2 gate mismatch")

        in_scope = master["head3_scope_mask"] == "1"
        oracle_probability = _parse_probability_pair(
            prediction,
            "head3_oracle_nucleocytoviricota_probability",
            "head3_oracle_preplasmiviricota_probability",
            required=in_scope,
        )
        oracle_probabilities.append(oracle_probability)
        expected_oracle = (
            _h3_label(oracle_probability, h3_threshold)
            if oracle_probability is not None
            else H3_NOT_APPLICABLE
        )
        if prediction["head3_oracle_predicted"] != expected_oracle:
            raise RuntimeError("prediction_cascade_contract: H3 oracle label mismatch")

        reached = bool(h3_reached[index])
        operational_probability = _parse_probability_pair(
            prediction,
            "head3_operational_nucleocytoviricota_probability",
            "head3_operational_preplasmiviricota_probability",
            required=reached,
        )
        operational_probabilities.append(operational_probability)
        expected_h3 = (
            _h3_label(operational_probability, h3_threshold)
            if operational_probability is not None
            else H3_NOT_REACHED
        )
        if prediction["head3_predicted"] != expected_h3:
            raise RuntimeError("prediction_cascade_contract: operational H3 label mismatch")
        if prediction["head3_reached"] != ("1" if reached else "0"):
            raise RuntimeError("prediction_cascade_contract: Head-3 reach marker mismatch")
        if in_scope and reached and not np.allclose(
            oracle_probability, operational_probability, rtol=0.0, atol=1e-7
        ):
            raise RuntimeError("prediction_probability_contract: oracle/operational H3 drift")
        operational_h3_labels.append(expected_h3)

    h1_y = np.asarray(
        [int(row["head1_label"] == "djr") for row in master_rows], dtype=np.int64
    )
    h1_metrics = _binary_metrics(h1_y, h1_probability, h1_threshold)
    h1_metrics["negative_source_strata"] = _head1_negative_strata(
        master_rows, h1_probability, h1_threshold
    )
    h1_metrics["component_bootstrap_95pct_ci"] = _component_bootstrap_binary(
        h1_y,
        h1_probability,
        groups,
        threshold=h1_threshold,
        seed=seed,
    )

    h2_mask = np.asarray([row["head2_mask"] == "1" for row in master_rows], dtype=bool)
    h2_y = np.asarray(
        [
            int(row["head2_label"] == "viral_morphogenesis_associated")
            for row, selected in zip(master_rows, h2_mask, strict=True)
            if selected
        ],
        dtype=np.int64,
    )
    h2_oracle_probability = h2_probability[h2_mask]
    h2_oracle = _binary_metrics(h2_y, h2_oracle_probability, h2_threshold)
    h2_oracle["component_bootstrap_95pct_ci"] = _component_bootstrap_binary(
        h2_y,
        h2_oracle_probability,
        groups[h2_mask],
        threshold=h2_threshold,
        seed=seed,
    )

    end_truth = np.asarray(
        [
            int(row["head2_label"] == "viral_morphogenesis_associated")
            for row in master_rows
        ],
        dtype=np.int64,
    )
    end_prediction = (h1_positive & h2_raw_positive).astype(np.int64)
    end_score = h1_probability * h2_probability
    h2_end = _binary_metrics(end_truth, end_score, h1_threshold * h2_threshold)
    h2_end["cascade_mcc"] = float(matthews_corrcoef(end_truth, end_prediction))
    h2_end["cascade_balanced_accuracy"] = float(
        balanced_accuracy_score(end_truth, end_prediction)
    )
    precision, recall, f1, _ = precision_recall_fscore_support(
        end_truth, end_prediction, labels=[0, 1], zero_division=0
    )
    h2_end["cascade_precision_by_class"] = precision
    h2_end["cascade_recall_by_class"] = recall
    h2_end["cascade_f1_by_class"] = f1
    h2_end_ci = _component_bootstrap_binary(
        end_truth,
        end_score,
        groups,
        threshold=h1_threshold * h2_threshold,
        seed=seed,
        prediction_override=end_prediction,
    )
    h2_end_ci["score"] = "head1_djr_probability * head2_vma_probability"
    h2_end_ci["classification"] = (
        "fixed gate: head1_probability >= head1_threshold AND "
        "head2_probability >= head2_threshold"
    )
    for source, target in (
        ("mcc", "cascade_mcc"),
        ("balanced_accuracy", "cascade_balanced_accuracy"),
        ("positive_precision", "cascade_positive_precision"),
        ("positive_recall", "cascade_positive_recall"),
        ("positive_f1", "cascade_positive_f1"),
    ):
        h2_end_ci["metrics"][target] = h2_end_ci["metrics"].pop(source)
    h2_end["component_bootstrap_95pct_ci"] = h2_end_ci

    known_mask = np.asarray([row["head3_mask"] == "1" for row in master_rows], dtype=bool)
    known_probability = np.asarray(
        [
            probability
            for probability, selected in zip(oracle_probabilities, known_mask)
            if selected
        ],
        dtype=np.float64,
    )
    class_to_index = {label: index for index, label in enumerate(H3_KNOWN_CLASSES)}
    known_y = np.asarray(
        [
            class_to_index[row["head3_operational_label"]]
            for row, selected in zip(master_rows, known_mask, strict=True)
            if selected
        ],
        dtype=np.int64,
    )
    known_groups = groups[known_mask]
    h3_metrics, _ = _multiclass_metrics(
        known_y,
        known_probability,
        h3_threshold,
        groups=known_groups,
        seed=seed,
    )
    unknown_mask = np.asarray(
        [row["head3_unknown_diagnostic_mask"] == "1" for row in master_rows], dtype=bool
    )
    unknown_probability = np.asarray(
        [
            probability
            for probability, selected in zip(oracle_probabilities, unknown_mask, strict=True)
            if selected
        ],
        dtype=np.float64,
    )
    unknown_metadata = [
        row for row, selected in zip(master_rows, unknown_mask, strict=True) if selected
    ]
    unknown_groups = groups[unknown_mask]
    known_confidence = known_probability.max(axis=1)
    unknown_confidence = unknown_probability.max(axis=1)
    known_rejected = int(np.sum(known_confidence < h3_threshold))
    unknown_rejected = int(np.sum(unknown_confidence < h3_threshold))
    predicted_unknown = known_rejected + unknown_rejected
    ood_truth = np.concatenate(
        [
            np.zeros(len(known_confidence), dtype=np.int64),
            np.ones(len(unknown_confidence), dtype=np.int64),
        ]
    )
    ood_score = np.concatenate([1.0 - known_confidence, 1.0 - unknown_confidence])
    strata = _unknown_rejection_strata(
        unknown_confidence,
        unknown_metadata,
        h3_threshold,
        groups=unknown_groups,
        seed=seed,
    )
    h3_metrics["scope_n"] = int(np.sum([row["head3_scope_mask"] == "1" for row in master_rows]))
    h3_metrics["known_class_n"] = int(known_mask.sum())
    h3_metrics["unknown_diagnostic"] = {
        "n": int(len(unknown_confidence)),
        "rejected": unknown_rejected,
        "numerator": unknown_rejected,
        "denominator": int(len(unknown_confidence)),
        "unknown_recall": (
            float(np.mean(unknown_confidence < h3_threshold))
            if len(unknown_confidence)
            else None
        ),
        "unknown_recall_naive_row_level_descriptive_wilson_95pct_ci": _wilson(
            unknown_rejected, int(len(unknown_confidence))
        ),
        "unknown_precision": (
            unknown_rejected / predicted_unknown if predicted_unknown else None
        ),
        "ood_auroc": (
            float(roc_auc_score(ood_truth, ood_score))
            if len(np.unique(ood_truth)) == 2
            else None
        ),
        "statuses": sorted({row["head3_status"] for row in unknown_metadata}),
        "by_status": strata["head3_status"],
        "by_reason": strata["head3_unknown_reason"],
    }
    h3_metrics["unknown_diagnostic"][
        "unknown_recall_component_bootstrap_95pct_ci"
    ] = _component_bootstrap_fraction(
        unknown_confidence < h3_threshold,
        np.ones(len(unknown_confidence), dtype=bool),
        unknown_groups,
        seed=seed,
    )
    all_rejection_groups = np.concatenate([known_groups, unknown_groups])
    all_rejected = np.concatenate(
        [known_confidence < h3_threshold, unknown_confidence < h3_threshold]
    )
    true_unknown_rejected = np.concatenate(
        [
            np.zeros(len(known_confidence), dtype=bool),
            unknown_confidence < h3_threshold,
        ]
    )
    h3_metrics["unknown_diagnostic"][
        "unknown_precision_component_bootstrap_95pct_ci"
    ] = _component_bootstrap_fraction(
        true_unknown_rejected,
        all_rejected,
        all_rejection_groups,
        seed=seed,
    )

    cascade, truth_paths, predicted_paths = _operational_cascade_metrics(
        master_rows,
        h1_positive,
        h2_raw_positive,
        operational_h3_labels,
        groups=groups,
        seed=seed,
    )
    for index, prediction in enumerate(prediction_rows):
        expected_correct = truth_paths[index] == predicted_paths[index]
        if (
            prediction["operational_path_true"] != truth_paths[index]
            or prediction["operational_path_predicted"] != predicted_paths[index]
            or prediction["operational_path_correct"] != ("1" if expected_correct else "0")
        ):
            raise RuntimeError("prediction_cascade_contract: stored full path mismatch")

    return _jsonable(
        {
            "heads": {
                "head1": h1_metrics,
                "head2": {
                    "oracle_conditional": h2_oracle,
                    "end_to_end": h2_end,
                },
                "head3_phylum": h3_metrics,
            },
            "operational_cascade": cascade,
        }
    ), {
        "prediction_master_truth_lineage": True,
        "prediction_probability_contract": True,
        "prediction_cascade_contract": True,
    }


def _assert_nested_close(expected: Any, observed: Any, path: str = "metrics") -> None:
    if isinstance(expected, dict):
        if not isinstance(observed, dict) or set(expected) != set(observed):
            raise RuntimeError(f"independent_metrics_recomputation: key mismatch at {path}")
        for key in expected:
            _assert_nested_close(expected[key], observed[key], f"{path}.{key}")
        return
    if isinstance(expected, list):
        if not isinstance(observed, list) or len(expected) != len(observed):
            raise RuntimeError(f"independent_metrics_recomputation: list mismatch at {path}")
        for index, (left, right) in enumerate(zip(expected, observed, strict=True)):
            _assert_nested_close(left, right, f"{path}[{index}]")
        return
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not isinstance(observed, (int, float)) or not math.isclose(
            float(expected), float(observed), rel_tol=1e-10, abs_tol=1e-12
        ):
            raise RuntimeError(f"independent_metrics_recomputation: value mismatch at {path}")
        return
    if expected != observed:
        raise RuntimeError(f"independent_metrics_recomputation: value mismatch at {path}")


def _verify_checksum_manifest(path: Path, root: Path) -> dict[str, str]:
    observed: dict[str, str] = {}
    root = root.resolve()
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        parts = raw_line.split(maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError(f"Malformed checksum line {line_number}: {path}")
        digest, name = parts[0], parts[1].strip().lstrip("*")
        artifact = (root / name).resolve()
        if (
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or artifact.parent != root
            or name in observed
            or not artifact.is_file()
            or sha256_file(artifact) != digest
        ):
            raise RuntimeError(f"Unsafe or invalid checksum entry: {name!r}")
        observed[name] = digest
    return observed


def _selection_lineage_checks(
    manifest_path: Path,
    result_dir: Path,
    calibration: dict[str, Any],
    marker_path: Path,
    marker: dict[str, Any],
    metrics_path: Path,
    predictions_path: Path,
    test_metrics: dict[str, Any],
) -> dict[str, bool]:
    state_dir = _resolved(marker.get("project_test_state_dir", ""))
    authorization_path = state_dir / "TEST_SELECTION_AUTHORIZATION.json"
    reservation_path = state_dir / "TEST_EVALUATION_RESERVED.json"
    receipt_path = state_dir / "TEST_EVALUATION_RECEIPT.json"
    authorization = read_json(authorization_path)
    reservation = read_json(reservation_path)
    receipt = read_json(receipt_path)
    authorization_core = {
        key: value for key, value in authorization.items() if key != "authorization_id"
    }
    authorization_id = authorization.get("authorization_id")
    authorization_sha256 = sha256_file(authorization_path)
    manifest_sha256 = sha256_file(manifest_path)
    production = manifest_sha256 == PRODUCTION_MANIFEST_SHA256
    lifecycle_schema = 3 if production else authorization.get("schema_version")
    selected_model_id = authorization.get("selected_model_id")

    checks = {
        "project_test_state_external": (
            state_dir != result_dir.resolve()
            and not state_dir.is_relative_to(result_dir.resolve())
            and authorization.get("project_test_state_dir") == str(state_dir)
            and marker.get("project_test_state_dir") == str(state_dir)
        ),
        "authorization_schema": authorization.get("schema_version") == lifecycle_schema,
        "authorization_status": (
            authorization.get("status") == "authorized_for_single_test_evaluation"
            and authorization.get("single_test_only") is True
        ),
        "authorization_selection_scope": (
            authorization.get("selection_evidence_scope")
            == "train_cv_and_validation_only"
            and authorization.get("test_labels_or_metrics_read_for_selection") is False
        ),
        "authorization_content_id": (
            isinstance(authorization_id, str)
            and authorization_id == _canonical_sha256(authorization_core)
        ),
        "authorization_weight_policy": authorization.get("weights") == EXPECTED_WEIGHTS,
        "authorization_manifest": authorization.get("manifest_sha256") == manifest_sha256,
        "authorization_result_dir": (
            _resolved(authorization.get("selected_result_dir", ""))
            == result_dir.resolve()
        ),
        "marker_authorization_lineage": (
            marker.get("selection_authorization_id") == authorization_id
            and _resolved(marker.get("selection_authorization_path", ""))
            == authorization_path.resolve()
            and marker.get("selection_authorization_sha256") == authorization_sha256
            and marker.get("project_test_identity")
            == authorization.get("project_test_identity")
        ),
        "reservation_authorization_lineage": (
            reservation.get("schema_version") == lifecycle_schema
            and reservation.get("status") == "reserved_fail_closed"
            and reservation.get("authorization_id") == authorization_id
            and _resolved(reservation.get("authorization_path", ""))
            == authorization_path.resolve()
            and reservation.get("authorization_sha256") == authorization_sha256
            and reservation.get("selected_model_id") == selected_model_id
            and _resolved(reservation.get("selected_result_dir", ""))
            == result_dir.resolve()
            and reservation.get("project_test_state_dir") == str(state_dir)
            and reservation.get("project_test_identity")
            == authorization.get("project_test_identity")
        ),
        "marker_reservation_lineage": (
            _resolved(marker.get("test_reservation_path", ""))
            == reservation_path.resolve()
            and marker.get("test_reservation_sha256") == sha256_file(reservation_path)
            and marker.get("reservation_status") == reservation.get("status")
        ),
        "metrics_selection_lineage": (
            test_metrics.get("selection_authorization_id") == authorization_id
            and _resolved(test_metrics.get("test_reservation_path", ""))
            == reservation_path.resolve()
            and test_metrics.get("manifest_sha256") == manifest_sha256
            and test_metrics.get("project_test_state_dir") == str(state_dir)
            and test_metrics.get("project_test_identity")
            == authorization.get("project_test_identity")
        ),
        "receipt_authorization_lineage": (
            receipt.get("schema_version") == lifecycle_schema
            and receipt.get("status") == "complete"
            and receipt.get("authorization_id") == authorization_id
            and _resolved(receipt.get("authorization_path", ""))
            == authorization_path.resolve()
            and receipt.get("authorization_sha256") == authorization_sha256
            and receipt.get("selected_model_id") == selected_model_id
            and _resolved(receipt.get("selected_result_dir", ""))
            == result_dir.resolve()
            and receipt.get("project_test_state_dir") == str(state_dir)
            and receipt.get("project_test_identity")
            == authorization.get("project_test_identity")
        ),
        "unique_project_test_lifecycle_artifacts": (
            sorted(state_dir.rglob("TEST_SELECTION_AUTHORIZATION*.json"))
            == [authorization_path]
            and sorted(state_dir.rglob("TEST_EVALUATION_RESERVED*.json"))
            == [reservation_path]
            and sorted(state_dir.rglob("TEST_EVALUATION_RECEIPT*.json"))
            == [receipt_path]
        ),
        "receipt_test_lineage": (
            _resolved(receipt.get("test_marker_path", "")) == marker_path.resolve()
            and receipt.get("test_marker_sha256") == sha256_file(marker_path)
            and receipt.get("metrics_sha256") == sha256_file(metrics_path)
            and receipt.get("predictions_sha256") == sha256_file(predictions_path)
        ),
    }

    config_path = _resolved(authorization.get("config_path", ""))
    comparison_path = _resolved(authorization.get("comparison_path", ""))
    comparison_hashes = authorization.get("comparison_sha256")
    checks["authorization_config_lineage"] = (
        config_path.is_file()
        and authorization.get("config_sha256") == sha256_file(config_path)
    )
    frozen_config = load_config(config_path)
    registry = frozen_config.get("benchmark", {}).get("models")
    if not isinstance(registry, dict) or not registry:
        raise RuntimeError("Frozen benchmark config lacks an ordered model registry")
    expected_candidate_ids = list(registry)
    checks["authorization_candidate_registry"] = (
        authorization.get("candidate_count") == len(expected_candidate_ids)
        and authorization.get("candidate_model_ids") == expected_candidate_ids
        and selected_model_id in expected_candidate_ids
    )
    expected_comparison_files = {
        "model_comparison.json",
        "model_comparison.tsv",
        "fold_scores.tsv",
    }
    checks["authorization_comparison_lineage"] = (
        comparison_path.name == "model_comparison.json"
        and isinstance(comparison_hashes, dict)
        and set(comparison_hashes) == expected_comparison_files
        and all(
            (comparison_path.parent / name).is_file()
            and sha256_file(comparison_path.parent / name) == digest
            for name, digest in comparison_hashes.items()
        )
    )
    comparison = read_json(comparison_path)
    candidate_hashes = comparison.get("candidate_artifact_hashes", {})
    selected_evidence = authorization.get("selected_candidate_evidence")
    comparison_rows_json = comparison.get("models")
    comparison_ids = (
        [row.get("model_id") for row in comparison_rows_json]
        if isinstance(comparison_rows_json, list)
        and all(isinstance(row, dict) for row in comparison_rows_json)
        else []
    )
    selected_rows_json = (
        [row for row in comparison_rows_json if row.get("selected") is True]
        if comparison_ids
        else []
    )
    checks["comparison_selected_model_lineage"] = (
        comparison.get("selected_model_id") == selected_model_id
        and comparison.get("manifest_sha256") == manifest_sha256
        and comparison.get("config_sha256") == authorization.get("config_sha256")
        and comparison.get("weights") == EXPECTED_WEIGHTS
        and comparison.get("complete_model_count") == len(expected_candidate_ids)
        and comparison_ids == expected_candidate_ids
        and comparison.get("candidate_model_ids") == expected_candidate_ids
        and len(selected_rows_json) == 1
        and selected_rows_json[0].get("model_id") == selected_model_id
        and isinstance(candidate_hashes, dict)
        and set(candidate_hashes) == set(expected_candidate_ids)
        and candidate_hashes.get(selected_model_id) == selected_evidence
    )
    with (comparison_path.parent / "model_comparison.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        comparison_rows = list(csv.DictReader(handle, delimiter="\t"))
    comparison_selected = [row for row in comparison_rows if row.get("selected") == "True"]
    comparison_tsv_ids = [row.get("model_id") for row in comparison_rows]
    checks["comparison_table_selection"] = (
        comparison_tsv_ids == expected_candidate_ids
        and len(comparison_selected) == 1
        and comparison_selected[0].get("model_id") == selected_model_id
    )

    fasta_path = _resolved(frozen_config.get("paths", {}).get("v0_fasta", ""))
    if production or authorization.get("schema_version") == 3:
        identity_payload = content_identity_payload(
            config=frozen_config,
            manifest_sha256=manifest_sha256,
            fasta_sha256=sha256_file(fasta_path) if fasta_path.is_file() else "",
            selection_decision_sha256=selection_decision_sha256(comparison),
            weights=EXPECTED_WEIGHTS,
            candidate_model_ids=expected_candidate_ids,
            selected_model_id=selected_model_id,
            selected_candidate_evidence=selected_evidence,
        )
        expected_identity = _ledger_canonical_sha256(identity_payload)
    else:
        identity_payload = {
            "schema_version": 1,
            "project_name": frozen_config.get("project", {}).get("name"),
            "project_version": frozen_config.get("project", {}).get("version"),
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": manifest_sha256,
            "model_input_fasta_path": str(fasta_path),
            "model_input_fasta_sha256": (
                sha256_file(fasta_path) if fasta_path.is_file() else None
            ),
            "config_path": str(config_path),
            "config_sha256": sha256_file(config_path) if config_path.is_file() else None,
            "comparison_path": str(comparison_path),
            "comparison_sha256": comparison_hashes,
            "weights": EXPECTED_WEIGHTS,
            "candidate_model_ids": expected_candidate_ids,
            "selected_model_id": selected_model_id,
            "selected_result_dir": str(result_dir.resolve()),
            "selected_embedding_dir": str(
                _resolved(authorization.get("selected_embedding_dir", ""))
            ),
            "selected_candidate_evidence": selected_evidence,
        }
        expected_identity = _canonical_sha256(identity_payload)
    checks["project_test_identity_binding"] = (
        fasta_path.is_file()
        and authorization.get("model_input_fasta_path") == str(fasta_path)
        and authorization.get("model_input_fasta_sha256") == sha256_file(fasta_path)
        and authorization.get("project_test_identity_payload") == identity_payload
        and authorization.get("project_test_identity")
        == expected_identity
    )
    if production:
        ledger_mode, registry_root, expected_state_dir, claim_path = (
            resolve_test_state_locations(
                config=frozen_config,
                manifest_sha256=manifest_sha256,
                identity=expected_identity,
            )
        )
        assert registry_root is not None and claim_path is not None
        claim = read_json(claim_path)
        expected_registry_artifacts = sorted(
            [
                claim_path.resolve(),
                authorization_path.resolve(),
                reservation_path.resolve(),
                receipt_path.resolve(),
            ]
        )
        checks["production_fixed_external_ledger"] = (
            ledger_mode == PRODUCTION_LEDGER_MODE
            and state_dir == expected_state_dir
            and authorization.get("ledger_mode") == ledger_mode
            and _resolved(authorization.get("ledger_registry_root", ""))
            == registry_root
            and _resolved(authorization.get("identity_claim_path", "")) == claim_path
            and authorization.get("identity_claim_sha256") == sha256_file(claim_path)
            and claim.get("status") == "identity_claimed_fail_closed"
            and claim.get("project_test_identity_payload") == identity_payload
            and claim.get("project_test_identity") == expected_identity
            and _resolved(claim.get("project_test_state_dir", "")) == state_dir
            and matching_identity_artifacts(registry_root, expected_identity)
            == expected_registry_artifacts
            and all(
                artifact.get("ledger_mode") == ledger_mode
                and artifact.get("identity_claim_path") == str(claim_path)
                and artifact.get("identity_claim_sha256") == sha256_file(claim_path)
                for artifact in (reservation, receipt, marker, test_metrics)
            )
        )
    elif authorization.get("schema_version") == 3:
        ledger_mode, registry_root, expected_state_dir, claim_path = (
            resolve_test_state_locations(
                config=frozen_config,
                manifest_sha256=manifest_sha256,
                identity=expected_identity,
            )
        )
        checks["production_fixed_external_ledger"] = (
            ledger_mode == "nonproduction_temporary_state"
            and registry_root is None
            and claim_path is None
            and state_dir == expected_state_dir
            and authorization.get("ledger_mode") == ledger_mode
            and authorization.get("ledger_registry_root") is None
            and authorization.get("identity_claim_path") is None
            and authorization.get("identity_claim_sha256") is None
        )
    else:
        checks["production_fixed_external_ledger"] = True

    embedding_dir = _resolved(authorization.get("selected_embedding_dir", ""))
    embedding_metadata_path = embedding_dir / "metadata.json"
    embedding_checksums_path = embedding_dir / "CHECKSUMS.sha256"
    input_hashes = (
        selected_evidence.get("input_sha256")
        if isinstance(selected_evidence, dict)
        else None
    )
    embedding_hashes = (
        selected_evidence.get("embedding_artifact_sha256")
        if isinstance(selected_evidence, dict)
        else None
    )
    model_hashes = (
        selected_evidence.get("model_sha256")
        if isinstance(selected_evidence, dict)
        else None
    )
    required_inputs = {
        "embedding_metadata": embedding_metadata_path,
        "embedding_checksums": embedding_checksums_path,
        "calibration": result_dir / "calibration.json",
        "cross_validation": result_dir / "metrics" / "cross_validation.json",
        "validation": result_dir / "metrics" / "validation_metrics.json",
    }
    checks["selected_input_artifact_lineage"] = (
        isinstance(input_hashes, dict)
        and set(input_hashes) == EXPECTED_EVIDENCE_INPUTS
        and all(
            path.is_file() and sha256_file(path) == input_hashes[name]
            for name, path in required_inputs.items()
        )
    )
    verified_embedding = _verify_checksum_manifest(embedding_checksums_path, embedding_dir)
    embedding_metadata = read_json(embedding_metadata_path)
    checks["selected_embedding_artifact_lineage"] = (
        set(verified_embedding) == EXPECTED_EMBEDDING_FILES
        and embedding_hashes == verified_embedding
        and embedding_metadata.get("status") == "complete"
        and embedding_metadata.get("benchmark_model_id") == selected_model_id
        and embedding_metadata.get("manifest_sha256") == manifest_sha256
        and calibration.get("embedding_metadata_sha256")
        == sha256_file(embedding_metadata_path)
    )
    calibration_heads = calibration.get("heads", {})
    checks["selected_classifier_artifact_lineage"] = (
        isinstance(model_hashes, dict)
        and set(model_hashes) == {"head1", "head2", "head3_phylum"}
        and set(calibration_heads) == set(model_hashes)
        and all(
            _resolved(calibration_heads[head]["model_path"]).is_file()
            and calibration_heads[head].get("model_sha256") == digest
            and sha256_file(_resolved(calibration_heads[head]["model_path"])) == digest
            for head, digest in model_hashes.items()
        )
    )
    return checks


def audit_result(manifest_path: Path, result_dir: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    result_dir = result_dir.resolve()
    calibration_path = result_dir / "calibration.json"
    marker_path = result_dir / "FINAL_TEST_EVALUATED.json"
    marker = read_json(marker_path)
    calibration = read_json(calibration_path)
    metrics_path = _resolved(marker["metrics_path"])
    predictions_path = _resolved(marker["predictions_path"])
    test_metrics = read_json(metrics_path)

    checks = {
        "test_metrics_schema": test_metrics.get("schema_version") == 4,
        "test_marker_schema": (
            marker.get("schema_version") == 3
            and marker.get("status") == "complete_single_test_evaluation"
        ),
        "canonical_metrics_path": (
            metrics_path == (result_dir / "metrics" / "frozen_test_metrics.json")
        ),
        "canonical_predictions_path": (
            predictions_path
            == (result_dir / "predictions" / "frozen_test_predictions.tsv")
        ),
        "calibration_checksum": sha256_file(calibration_path)
        == marker["calibration_sha256"],
        "metrics_checksum": sha256_file(metrics_path) == marker["metrics_sha256"],
        "predictions_checksum": (
            sha256_file(predictions_path) == marker["predictions_sha256"]
        ),
        "manifest_checksum": (
            sha256_file(manifest_path) == calibration["manifest_sha256"]
        ),
    }
    completion_markers = sorted(result_dir.rglob("FINAL_TEST_EVALUATED*.json"))
    checks["unique_canonical_test_completion_marker"] = completion_markers == [marker_path]
    for head_name, head in calibration["heads"].items():
        checks[f"{head_name}_model_checksum"] = (
            sha256_file(_resolved(head["model_path"])) == head["model_sha256"]
        )

    state_dir = _resolved(marker.get("project_test_state_dir", ""))
    authorization = read_json(state_dir / "TEST_SELECTION_AUTHORIZATION.json")
    embedding_dir = _resolved(authorization.get("selected_embedding_dir", ""))
    manifest_test_rows = read_manifest_test_rows(manifest_path)
    prediction_rows = read_prediction_rows(predictions_path)
    reinferred_rows, reinference_provenance = _reinfer_frozen_test_predictions(
        manifest_path, embedding_dir, calibration
    )
    expected_ids = [row["protein_id"] for row in manifest_test_rows]
    prediction_ids = [row["protein_id"] for row in prediction_rows]
    expected_id_set = set(expected_ids)
    prediction_id_set = set(prediction_ids)
    expected_test = len(expected_ids)
    expected_head2_test = sum(row["head2_mask"] == "1" for row in manifest_test_rows)
    expected_head3_known_test = sum(
        row["head3_mask"] == "1" for row in manifest_test_rows
    )
    expected_head3_scope_test = sum(
        row["head3_scope_mask"] == "1" for row in manifest_test_rows
    )
    checks["manifest_test_ids_unique"] = len(expected_ids) == len(expected_id_set)
    checks["prediction_row_count"] = len(prediction_ids) == expected_test
    checks["prediction_ids_unique"] = len(prediction_ids) == len(prediction_id_set)
    checks["prediction_ids_no_missing"] = expected_id_set <= prediction_id_set
    checks["prediction_ids_no_extra"] = prediction_id_set <= expected_id_set
    checks["prediction_id_set_exact"] = prediction_id_set == expected_id_set
    checks["prediction_id_order_exact"] = prediction_ids == expected_ids
    checks["reinferred_prediction_id_order_exact"] = [
        row["protein_id"] for row in reinferred_rows
    ] == expected_ids
    if len(reinferred_rows) != len(prediction_rows):
        raise RuntimeError("frozen_model_reinference: prediction row count mismatch")
    for row_number, (expected_row, stored_row) in enumerate(
        zip(reinferred_rows, prediction_rows, strict=True)
    ):
        if expected_row != stored_row:
            differing = sorted(
                field
                for field in EXPECTED_PREDICTION_FIELDS
                if expected_row.get(field) != stored_row.get(field)
            )
            raise RuntimeError(
                "frozen_model_reinference: predictions.tsv differs from frozen "
                f"embedding+joblib inference at row {row_number}: {differing}"
            )
    checks["frozen_model_probability_reinference"] = True
    checks["frozen_embedding_row_alignment"] = (
        reinference_provenance["embedding_row_count"] == len(expected_ids)
        and reinference_provenance["manifest_sha256"] == sha256_file(manifest_path)
        and reinference_provenance["embedding_metadata_sha256"]
        == calibration["embedding_metadata_sha256"]
    )
    frozen_inference_artifacts = test_metrics.get("frozen_inference_artifacts")
    checks["frozen_inference_artifact_provenance"] = (
        isinstance(frozen_inference_artifacts, dict)
        and _resolved(frozen_inference_artifacts.get("embedding_dir", ""))
        == embedding_dir
        and frozen_inference_artifacts.get("embedding_metadata_sha256")
        == sha256_file(embedding_dir / "metadata.json")
        and frozen_inference_artifacts.get("embedding_index_sha256")
        == sha256_file(embedding_dir / "index.tsv")
        and frozen_inference_artifacts.get("embedding_vectors_sha256")
        == sha256_file(embedding_dir / "embeddings.float16.npy")
        and frozen_inference_artifacts.get("model_sha256")
        == reinference_provenance["model_sha256"]
    )
    known_classes = set(calibration["heads"]["head3_phylum"]["classes"])
    allowed_head3_predictions = known_classes | {H3_NOT_REACHED, H3_UNKNOWN}
    checks["head3_prediction_value_contract"] = all(
        row["head3_predicted"] in allowed_head3_predictions
        for row in prediction_rows
    )

    frozen_config = load_config(_resolved(authorization["config_path"]))
    recomputed, evidence_checks = _independently_recompute_test_sections(
        manifest_test_rows,
        reinferred_rows,
        calibration,
        seed=int(frozen_config["project"]["seed"]),
    )
    _assert_nested_close(recomputed["heads"], test_metrics.get("heads"), "heads")
    _assert_nested_close(
        recomputed["operational_cascade"],
        test_metrics.get("operational_cascade"),
        "operational_cascade",
    )
    checks.update(evidence_checks)
    checks["independent_metrics_recomputation"] = True

    checks["head1_test_count"] = test_metrics["heads"]["head1"]["n"] == expected_test
    checks["head2_oracle_test_count"] = (
        test_metrics["heads"]["head2"]["oracle_conditional"]["n"]
        == expected_head2_test
    )
    checks["head3_known_test_count"] = (
        test_metrics["heads"]["head3_phylum"]["known_class_n"]
        == expected_head3_known_test
    )
    checks["head3_scope_test_count"] = (
        test_metrics["heads"]["head3_phylum"]["scope_n"]
        == expected_head3_scope_test
    )
    checks["marker_selected_model_lineage"] = (
        marker.get("selected_model_id") == authorization.get("selected_model_id")
    )
    checks.update(
        _selection_lineage_checks(
            manifest_path,
            result_dir,
            calibration,
            marker_path,
            marker,
            metrics_path,
            predictions_path,
            test_metrics,
        )
    )
    if not all(checks.values()):
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise RuntimeError(f"V0 result validation failed: {failed}")

    return {
        "status": "pass",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "expected_test_records": expected_test,
        "prediction_records": len(prediction_ids),
        "frozen_test_marker": str(marker_path),
        "selected_model_id": read_json(
            state_dir / "TEST_SELECTION_AUTHORIZATION.json"
        )["selected_model_id"],
        "selection_authorization_id": marker["selection_authorization_id"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    args = parser.parse_args()

    result_dir = args.result_dir.resolve()
    validation = audit_result(args.manifest, result_dir)
    validation_path = result_dir / "RESULT_VALIDATION.json"
    atomic_json(validation_path, validation)

    files = sorted(
        path
        for path in result_dir.rglob("*")
        if path.is_file() and path.name != "CHECKSUMS.sha256"
    )
    checksum_path = result_dir / "CHECKSUMS.sha256"
    checksum_path.write_text(
        "".join(
            f"{sha256_file(path)}  {path.relative_to(result_dir)}\n" for path in files
        ),
        encoding="utf-8",
    )
    print(json.dumps(validation, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
