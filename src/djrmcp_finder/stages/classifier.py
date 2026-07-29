"""Train, calibrate, and evaluate the three conditional V0 classifier heads.

The public entry point has two explicit phases.  ``calibrate`` uses only train and
validation rows and writes frozen model/threshold artifacts.  ``test`` refuses to
run without those artifacts and creates a marker that prevents accidental repeated
evaluation of the frozen test set.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression, SGDClassifier
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
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ..config import load_config
from ..cv_folds import load_frozen_cv_fold_map
from ..test_ledger import (
    PRODUCTION_LEDGER_MODE,
    PRODUCTION_MANIFEST_SHA256,
    canonical_sha256 as _ledger_canonical_sha256,
    content_identity_payload,
    matching_identity_artifacts,
    resolve_test_state_locations,
    selection_decision_sha256,
)
from .embedding import atomic_json, sha256_file, utc_now


HEAD_SPECS: dict[str, dict[str, Any]] = {
    "head1": {
        "mask": "head1_mask",
        "label": "head1_label",
        "classes": ["non_djr", "djr"],
        "kind": "binary",
    },
    "head2": {
        "mask": "head2_mask",
        "label": "head2_label",
        "classes": ["none", "viral_morphogenesis_associated"],
        "kind": "binary",
    },
    "head3_phylum": {
        "mask": "head3_mask",
        "label": "head3_operational_label",
        "classes": ["Nucleocytoviricota", "Preplasmiviricota"],
        "kind": "multiclass",
    },
}
H3_EXTERNAL_UNKNOWN_LABEL = "unknown/other"
H3_NOT_REACHED_LABEL = "not_reached"
H3_NOT_APPLICABLE_LABEL = "not_applicable"
H3_OPERATIONAL_OUTPUTS = [
    *HEAD_SPECS["head3_phylum"]["classes"],
    H3_EXTERNAL_UNKNOWN_LABEL,
]
FULL_PATH_LABELS = [
    "non_djr",
    "djr_non_vma",
    *[f"vma::{label}" for label in H3_OPERATIONAL_OUTPUTS],
]
TEST_COMPONENT_BOOTSTRAP_REPLICATES = 10_000
TEST_SELECTION_WEIGHTS = {"head1": 0.60, "head2": 0.30, "head3_phylum": 0.10}
TEST_COMPARISON_FILES = {
    "model_comparison.json",
    "model_comparison.tsv",
    "fold_scores.tsv",
}
TEST_SELECTED_INPUT_FILES = {
    "embedding_metadata": ("embedding", "metadata.json"),
    "embedding_checksums": ("embedding", "CHECKSUMS.sha256"),
    "calibration": ("result", "calibration.json"),
    "cross_validation": ("result", "metrics/cross_validation.json"),
    "validation": ("result", "metrics/validation_metrics.json"),
}
TEST_EMBEDDING_ARTIFACTS = {
    "completed.npy",
    "embeddings.float16.npy",
    "index.tsv",
    "metadata.json",
}


def _format_head3_prediction(
    prediction: int | None, classes: Sequence[str]
) -> str:
    if prediction is None:
        return H3_NOT_REACHED_LABEL
    if prediction == -1:
        return H3_EXTERNAL_UNKNOWN_LABEL
    if prediction < 0 or prediction >= len(classes):
        raise ValueError(f"Invalid Head-3 prediction index: {prediction}")
    return classes[prediction]


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header")
        return list(reader)


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _atomic_joblib(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    joblib.dump(value, temporary)
    os.replace(temporary, path)


def _exclusive_json(path: Path, value: dict[str, Any]) -> None:
    """Create one immutable lifecycle JSON without an overwrite code path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(_jsonable(value), indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError as exc:
        raise RuntimeError(f"Fail-closed lifecycle artifact already exists: {path}") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _resolved(path_value: str | Path) -> Path:
    return Path(path_value).resolve()


def _canonical_sha256(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _external_project_test_state_dir(state_dir: Path, result_dir: Path) -> bool:
    state_dir = state_dir.resolve()
    result_dir = result_dir.resolve()
    return state_dir != result_dir and not state_dir.is_relative_to(result_dir)


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
    if isinstance(value, Path):
        return str(value)
    return value


def _validate_embedding_contract(
    manifest_path: Path, embedding_dir: Path
) -> tuple[list[dict[str, str]], np.ndarray]:
    metadata_path = embedding_dir / "metadata.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Missing embedding metadata: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("status") != "complete":
        raise RuntimeError(f"Embedding status is {metadata.get('status')!r}, not 'complete'")
    if metadata.get("manifest_sha256") != sha256_file(manifest_path):
        raise RuntimeError("Embedding manifest SHA256 does not match the frozen manifest")

    manifest = _read_tsv(manifest_path)
    index = _read_tsv(embedding_dir / "index.tsv")
    vectors = np.load(embedding_dir / "embeddings.float16.npy", mmap_mode="r")
    if len(manifest) != len(index) or vectors.shape[0] != len(manifest):
        raise RuntimeError(
            f"Embedding alignment mismatch: manifest={len(manifest)}, index={len(index)}, "
            f"vectors={vectors.shape[0]}"
        )
    for row_number, (manifest_row, index_row) in enumerate(zip(manifest, index, strict=True)):
        if int(index_row["embedding_row"]) != row_number:
            raise RuntimeError(f"Embedding row index mismatch at row {row_number}")
        for field in ("protein_id", "sequence_sha256", "split"):
            if manifest_row[field] != index_row[field]:
                raise RuntimeError(f"Embedding {field} mismatch at row {row_number}")
    return manifest, vectors


def _select_head(
    manifest: Sequence[dict[str, str]],
    vectors: np.ndarray,
    head_name: str,
    split: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict[str, str]], np.ndarray]:
    spec = HEAD_SPECS[head_name]
    class_to_index = {label: index for index, label in enumerate(spec["classes"])}
    rows = [
        index
        for index, row in enumerate(manifest)
        if row["split"] == split and row[spec["mask"]] == "1"
    ]
    if not rows:
        raise ValueError(f"No {head_name} rows found for split {split}")
    selected_metadata = [manifest[index] for index in rows]
    labels = []
    for row in selected_metadata:
        label = row[spec["label"]]
        if label not in class_to_index:
            raise ValueError(f"Unexpected {head_name} label: {label!r}")
        labels.append(class_to_index[label])
    x = np.asarray(vectors[rows], dtype=np.float32)
    y = np.asarray(labels, dtype=np.int64)
    groups = np.asarray([row["global_component_id"] for row in selected_metadata])
    return x, y, groups, selected_metadata, np.asarray(rows, dtype=np.int64)


def _select_head3_unknown_diagnostic(
    manifest: Sequence[dict[str, str]], vectors: np.ndarray, split: str
) -> tuple[np.ndarray, list[dict[str, str]], np.ndarray]:
    rows = np.asarray(
        [
            index
            for index, row in enumerate(manifest)
            if row["split"] == split and row["head3_unknown_diagnostic_mask"] == "1"
        ],
        dtype=np.int64,
    )
    metadata = [manifest[int(index)] for index in rows]
    if not len(rows):
        return np.empty((0, vectors.shape[1]), dtype=np.float32), metadata, rows
    return np.asarray(vectors[rows], dtype=np.float32), metadata, rows


def _balanced_without_replacement(
    indices: np.ndarray, strata: Sequence[str], requested: int, rng: np.random.Generator
) -> np.ndarray:
    if requested >= len(indices):
        return rng.permutation(indices)
    buckets: dict[str, list[int]] = defaultdict(list)
    for index, stratum in zip(indices.tolist(), strata, strict=True):
        buckets[stratum or "unknown"].append(index)
    for values in buckets.values():
        rng.shuffle(values)
    selected: list[int] = []
    keys = sorted(buckets)
    cursor = 0
    while len(selected) < requested and keys:
        key = keys[cursor % len(keys)]
        if buckets[key]:
            selected.append(buckets[key].pop())
        if not buckets[key]:
            keys.remove(key)
            cursor = 0
        else:
            cursor += 1
    return np.asarray(selected, dtype=np.int64)


def _sample_head1_epoch(
    y: np.ndarray,
    metadata: Sequence[dict[str, str]],
    negative_ratio: int,
    rng: np.random.Generator,
) -> np.ndarray:
    positives = np.flatnonzero(y == 1)
    hard = np.asarray(
        [index for index, row in enumerate(metadata) if row["source_dataset"] == "hard_non_djr"],
        dtype=np.int64,
    )
    background = np.asarray(
        [
            index
            for index, row in enumerate(metadata)
            if row["source_dataset"] == "background_non_djr"
        ],
        dtype=np.int64,
    )
    target = min(int(len(positives) * negative_ratio), len(hard) + len(background))
    hard_target = min(len(hard), target // 2)
    background_target = min(len(background), target - hard_target)
    remaining = target - hard_target - background_target
    if remaining:
        extra_hard = min(remaining, len(hard) - hard_target)
        hard_target += extra_hard
        background_target += min(remaining - extra_hard, len(background) - background_target)
    hard_strata = [metadata[index].get("family_metadata", "") for index in hard]
    sampled_hard = _balanced_without_replacement(hard, hard_strata, hard_target, rng)
    sampled_background = (
        rng.choice(background, size=background_target, replace=False)
        if background_target
        else np.asarray([], dtype=np.int64)
    )
    selected = np.concatenate([positives, sampled_hard, sampled_background])
    rng.shuffle(selected)
    return selected


def _fit_head1(
    x: np.ndarray,
    y: np.ndarray,
    metadata: Sequence[dict[str, str]],
    alpha: float,
    settings: dict[str, Any],
    seed: int,
) -> Pipeline:
    scaler = StandardScaler()
    scaled = scaler.fit_transform(x)
    estimator = SGDClassifier(
        loss="log_loss",
        penalty="l2",
        alpha=alpha,
        max_iter=1,
        tol=None,
        learning_rate="optimal",
        average=True,
        random_state=seed,
    )
    rng = np.random.default_rng(seed)
    for epoch in range(int(settings["head1_epochs"])):
        selected = _sample_head1_epoch(
            y, metadata, int(settings["head1_negative_ratio"]), rng
        )
        estimator.partial_fit(
            scaled[selected],
            y[selected],
            classes=np.asarray([0, 1], dtype=np.int64) if epoch == 0 else None,
        )
    return Pipeline([("scale", scaler), ("classifier", estimator)])


def _fit_logistic(
    x: np.ndarray, y: np.ndarray, c_value: float, settings: dict[str, Any], seed: int
) -> Pipeline:
    return Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    C=c_value,
                    class_weight="balanced",
                    max_iter=int(settings["logistic_max_iter"]),
                    solver="lbfgs",
                    random_state=seed,
                ),
            ),
        ]
    ).fit(x, y)


def _fit_model(
    head_name: str,
    x: np.ndarray,
    y: np.ndarray,
    metadata: Sequence[dict[str, str]],
    parameter: float,
    settings: dict[str, Any],
    seed: int,
) -> Pipeline:
    if head_name == "head1":
        return _fit_head1(x, y, metadata, parameter, settings, seed)
    return _fit_logistic(x, y, parameter, settings, seed)


def _probabilities_from_logits(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    logits = np.asarray(logits, dtype=np.float64)
    if logits.ndim == 1:
        scaled = np.clip(logits / temperature, -60.0, 60.0)
        positive = 1.0 / (1.0 + np.exp(-scaled))
        return np.column_stack([1.0 - positive, positive])
    scaled = logits / temperature
    scaled -= scaled.max(axis=1, keepdims=True)
    exponent = np.exp(scaled)
    return exponent / exponent.sum(axis=1, keepdims=True)


def _stable_log_probability_product(*scaled_binary_logits: np.ndarray) -> np.ndarray:
    """Return log of a sigmoid-probability product without underflow or ties."""

    if not scaled_binary_logits:
        raise ValueError("At least one binary logit array is required")
    arrays = [np.asarray(value, dtype=np.float64) for value in scaled_binary_logits]
    if any(value.ndim != 1 for value in arrays):
        raise ValueError("Stable log-probability product requires 1D binary logits")
    if len({len(value) for value in arrays}) != 1 or not np.isfinite(arrays).all():
        raise ValueError("Stable log-probability product inputs must be aligned and finite")
    return np.sum([-np.logaddexp(0.0, -value) for value in arrays], axis=0)


def _decision_scores(model: Pipeline, x: np.ndarray) -> np.ndarray:
    """Return untransformed float64 decision scores for ranking metrics.

    Binary sklearn estimators must expose one score per row.  Multiclass
    estimators expose one score per row and class.  Keeping this representation
    separate from calibrated probabilities prevents sigmoid/softmax saturation
    from introducing artificial ties in AP, ROC-AUC, and FPR-at-recall.
    """

    scores = np.asarray(model.decision_function(x), dtype=np.float64)
    if scores.ndim not in {1, 2}:
        raise ValueError(
            "decision_function must return a 1D binary score or 2D multiclass scores"
        )
    if len(scores) != len(x):
        raise ValueError("decision_function returned a row count mismatch")
    if not np.isfinite(scores).all():
        raise ValueError("decision_function returned non-finite scores")
    return scores


def _binary_decision_scores(model: Pipeline, x: np.ndarray) -> np.ndarray:
    """Return the positive-class raw score from a binary estimator."""

    scores = _decision_scores(model, x)
    if scores.ndim != 1:
        raise ValueError(
            "Binary ranking metrics require a 1D positive-class decision score"
        )
    return scores


def _probabilities(model: Pipeline, x: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    logits = _decision_scores(model, x)
    return _probabilities_from_logits(logits, temperature)


def _negative_log_likelihood_from_logits(
    y: np.ndarray,
    logits: np.ndarray,
    temperature: float,
    label_smoothing: float = 0.0,
) -> float:
    """Stable binary or multiclass (optionally smoothed) logit NLL."""

    truth = np.asarray(y, dtype=np.int64)
    scores = np.asarray(logits, dtype=np.float64)
    if len(truth) != len(scores) or not len(truth):
        raise ValueError("NLL truth and logits must be non-empty and aligned")
    if not np.isfinite(scores).all() or not np.isfinite(temperature) or temperature <= 0:
        raise ValueError("NLL logits and temperature must be finite and valid")
    smoothing = float(label_smoothing)
    if not np.isfinite(smoothing) or smoothing < 0.0 or smoothing >= 0.5:
        raise ValueError("NLL label_smoothing must be finite in [0, 0.5)")
    scaled = scores / temperature
    if scores.ndim == 1:
        if not set(np.unique(truth)).issubset({0, 1}):
            raise ValueError("Binary NLL labels must be 0 or 1")
        target = smoothing + (1.0 - 2.0 * smoothing) * truth
        losses = np.logaddexp(0.0, scaled) - target * scaled
        return float(np.mean(losses))
    if scores.ndim != 2 or scores.shape[1] < 2:
        raise ValueError("Multiclass NLL requires a 2D logit matrix")
    if np.any(truth < 0) or np.any(truth >= scores.shape[1]):
        raise ValueError("Multiclass NLL label is outside the logit columns")
    row_max = scaled.max(axis=1)
    log_sum_exp = row_max + np.log(
        np.exp(scaled - row_max[:, None]).sum(axis=1)
    )
    target_score = (1.0 - smoothing) * scaled[np.arange(len(truth)), truth]
    if smoothing:
        off_target_sum = scaled.sum(axis=1) - scaled[np.arange(len(truth)), truth]
        target_score += smoothing * off_target_sum / (scores.shape[1] - 1)
    return float(np.mean(log_sum_exp - target_score))


def _temperature_search_contract(settings: dict[str, Any]) -> dict[str, Any]:
    required = (
        "temperature_objective",
        "temperature_boundary_policy",
        "temperature_log10_min",
        "temperature_log10_max",
        "temperature_coarse_points",
        "temperature_fine_points",
        "temperature_label_smoothing",
    )
    missing = [key for key in required if key not in settings]
    if missing:
        raise KeyError(
            "Classifier config must explicitly freeze temperature search settings: "
            f"{missing}"
        )
    contract = {
        "log10_min": float(settings["temperature_log10_min"]),
        "log10_max": float(settings["temperature_log10_max"]),
        "coarse_points": int(settings["temperature_coarse_points"]),
        "fine_points": int(settings["temperature_fine_points"]),
        "boundary_policy": str(settings["temperature_boundary_policy"]),
        "objective": str(settings["temperature_objective"]),
        "label_smoothing": float(settings["temperature_label_smoothing"]),
    }
    if contract["objective"] != "stable_label_smoothed_logit_nll":
        raise ValueError(
            "classifier.temperature_objective must be stable_label_smoothed_logit_nll"
        )
    if contract["boundary_policy"] != "fail":
        raise ValueError("classifier.temperature_boundary_policy must be fail")
    if (
        not np.isfinite(contract["log10_min"])
        or not np.isfinite(contract["log10_max"])
        or contract["log10_min"] >= contract["log10_max"]
        or contract["coarse_points"] < 3
        or contract["fine_points"] < 3
        or not 0.0 < contract["label_smoothing"] < 0.5
    ):
        raise ValueError("Invalid explicit temperature search settings")
    return contract


def _fit_temperature(
    model: Pipeline,
    x: np.ndarray,
    y: np.ndarray,
    settings: dict[str, Any],
) -> tuple[float, float, dict[str, Any]]:
    # The feature transform and decision function are intentionally computed once;
    # only the scalar temperature changes during the deterministic search.
    logits = _decision_scores(model, x)
    contract = _temperature_search_contract(settings)
    coarse_log10 = np.linspace(
        contract["log10_min"],
        contract["log10_max"],
        contract["coarse_points"],
    )
    coarse = np.power(10.0, coarse_log10)
    losses = np.asarray(
        [
            _negative_log_likelihood_from_logits(
                y, logits, float(value), contract["label_smoothing"]
            )
            for value in coarse
        ]
    )
    best = int(np.argmin(losses))
    if best in {0, len(coarse) - 1}:
        raise RuntimeError(
            "Temperature calibration optimum hit the frozen global search boundary; "
            "expand temperature_log10_min/max in a new versioned run"
        )
    fine_log10 = np.linspace(
        coarse_log10[best - 1],
        coarse_log10[best + 1],
        contract["fine_points"],
    )
    fine = np.power(10.0, fine_log10)
    fine_losses = np.asarray(
        [
            _negative_log_likelihood_from_logits(
                y, logits, float(value), contract["label_smoothing"]
            )
            for value in fine
        ]
    )
    selected = int(np.argmin(fine_losses))
    diagnostics = {
        **contract,
        "coarse_best_index": best,
        "coarse_boundary_hit": False,
        "fine_best_index": selected,
        "fine_boundary_hit": selected in {0, len(fine) - 1},
    }
    return float(fine[selected]), float(fine_losses[selected]), diagnostics


def _cv_score(
    head_name: str,
    y: np.ndarray,
    decision_scores: np.ndarray,
    probabilities: np.ndarray,
) -> float:
    if HEAD_SPECS[head_name]["kind"] == "binary":
        score = np.asarray(decision_scores, dtype=np.float64)
        if score.ndim != 1:
            raise ValueError(
                f"{head_name} CV requires a 1D positive-class decision score"
            )
        return float(average_precision_score(y, score))
    return float(f1_score(y, probabilities.argmax(axis=1), average="macro"))


def _cross_validate(
    head_name: str,
    x: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    metadata: Sequence[dict[str, str]],
    settings: dict[str, Any],
    seed: int,
    fold_assignment: dict[str, int],
) -> tuple[float, dict[str, Any]]:
    folds = int(settings["cross_validation_folds"])
    group_values = np.asarray([str(value) for value in groups], dtype=str)
    missing_groups = sorted(set(group_values.tolist()) - set(fold_assignment))
    if missing_groups:
        raise RuntimeError(
            f"Frozen CV map lacks {head_name} Train components: {missing_groups[:5]}"
        )
    splits: list[tuple[np.ndarray, np.ndarray]] = []
    fold_diagnostics: list[dict[str, Any]] = []
    for fold in range(1, folds + 1):
        heldout_mask = np.asarray(
            [fold_assignment[group] == fold for group in group_values], dtype=bool
        )
        heldout_indices = np.flatnonzero(heldout_mask)
        train_indices = np.flatnonzero(~heldout_mask)
        if not len(heldout_indices) or not len(train_indices):
            raise RuntimeError(f"Frozen CV fold {fold} is empty for {head_name}")
        train_groups = set(group_values[train_indices].tolist())
        heldout_groups = set(group_values[heldout_indices].tolist())
        if train_groups & heldout_groups:
            raise RuntimeError(
                f"Frozen CV fold {fold} splits a global component for {head_name}"
            )
        train_classes = sorted(int(value) for value in np.unique(y[train_indices]))
        heldout_classes = sorted(int(value) for value in np.unique(y[heldout_indices]))
        expected_classes = list(range(len(HEAD_SPECS[head_name]["classes"])))
        if train_classes != expected_classes or heldout_classes != expected_classes:
            raise RuntimeError(
                f"Frozen CV fold {fold} lacks a {head_name} class: "
                f"train={train_classes}, heldout={heldout_classes}, "
                f"expected={expected_classes}"
            )
        splits.append((train_indices, heldout_indices))
        fold_diagnostics.append(
            {
                "fold": fold,
                "train_record_count": int(len(train_indices)),
                "heldout_record_count": int(len(heldout_indices)),
                "train_global_component_count": len(train_groups),
                "heldout_global_component_count": len(heldout_groups),
                "train_class_count": {
                    str(class_index): int(np.sum(y[train_indices] == class_index))
                    for class_index in expected_classes
                },
                "heldout_class_count": {
                    str(class_index): int(np.sum(y[heldout_indices] == class_index))
                    for class_index in expected_classes
                },
            }
        )
    parameters = (
        [float(value) for value in settings["head1_alpha_grid"]]
        if head_name == "head1"
        else [float(value) for value in settings["logistic_c_grid"]]
    )
    candidates = []
    for parameter_index, parameter in enumerate(parameters):
        scores = []
        for fold_index, (train_indices, heldout_indices) in enumerate(splits):
            train_metadata = [metadata[index] for index in train_indices]
            model = _fit_model(
                head_name,
                x[train_indices],
                y[train_indices],
                train_metadata,
                parameter,
                settings,
                seed + parameter_index * 100 + fold_index,
            )
            decision_scores = _decision_scores(model, x[heldout_indices])
            probabilities = _probabilities_from_logits(decision_scores)
            scores.append(
                _cv_score(
                    head_name,
                    y[heldout_indices],
                    decision_scores,
                    probabilities,
                )
            )
        candidates.append(
            {
                "parameter": parameter,
                "fold_scores": scores,
                "mean_score": float(np.mean(scores)),
                "standard_deviation": float(np.std(scores)),
            }
        )
    candidates.sort(key=lambda row: (-row["mean_score"], row["parameter"]))
    return float(candidates[0]["parameter"]), {
        "splitter": "FrozenGlobalComponentFoldMap",
        "folds": folds,
        "fold_ids": list(range(1, folds + 1)),
        "group_field": "global_component_id",
        "fold_diagnostics": fold_diagnostics,
        "primary_metric": "average_precision" if head_name != "head3_phylum" else "macro_f1",
        "primary_metric_input": (
            "raw_decision_function"
            if HEAD_SPECS[head_name]["kind"] == "binary"
            else "uncalibrated_probabilities"
        ),
        "candidates_ranked": candidates,
    }


def _select_binary_threshold(
    y: np.ndarray, positive_probability: np.ndarray, metric: str
) -> tuple[float, float]:
    candidates = np.unique(np.concatenate([[0.0], positive_probability, [1.0]]))
    best_threshold = 0.5
    best_score = -np.inf
    for threshold in candidates:
        prediction = (positive_probability >= threshold).astype(np.int64)
        if metric == "mcc":
            score = float(matthews_corrcoef(y, prediction))
        elif metric == "macro_f1":
            score = float(f1_score(y, prediction, average="macro"))
        else:
            raise ValueError(f"Unknown threshold metric: {metric}")
        if score > best_score or (score == best_score and threshold > best_threshold):
            best_score = score
            best_threshold = float(threshold)
    return best_threshold, best_score


def _fpr_at_recall(y: np.ndarray, score: np.ndarray, target: float) -> float | None:
    fpr, tpr, _ = roc_curve(y, score)
    eligible = fpr[tpr >= target]
    return float(eligible.min()) if len(eligible) else None


def _binary_metrics(
    y: np.ndarray,
    probability: np.ndarray,
    threshold: float,
    *,
    ranking_score: np.ndarray,
    ranking_score_source: str,
) -> dict[str, Any]:
    probability = np.asarray(probability, dtype=np.float64)
    ranking_score = np.asarray(ranking_score, dtype=np.float64)
    if probability.ndim != 1 or ranking_score.ndim != 1:
        raise ValueError("Binary probability and ranking score must both be 1D")
    if not (len(y) == len(probability) == len(ranking_score)):
        raise ValueError("Binary metric arrays are not aligned")
    if not np.isfinite(probability).all() or not np.isfinite(ranking_score).all():
        raise ValueError("Binary metric inputs must be finite")
    prediction = (probability >= threshold).astype(np.int64)
    precision, recall, f1, support = precision_recall_fscore_support(
        y, prediction, labels=[0, 1], zero_division=0
    )
    return {
        "n": len(y),
        "positive": int(y.sum()),
        "negative": int((y == 0).sum()),
        "threshold": threshold,
        "ranking_score_source": ranking_score_source,
        "average_precision": float(average_precision_score(y, ranking_score)),
        "roc_auc": float(roc_auc_score(y, ranking_score)),
        "mcc": float(matthews_corrcoef(y, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
        "precision_by_class": precision,
        "recall_by_class": recall,
        "f1_by_class": f1,
        "support_by_class": support,
        "confusion_matrix": confusion_matrix(y, prediction, labels=[0, 1]),
        "fpr_at_90pct_recall": _fpr_at_recall(y, ranking_score, 0.90),
        "fpr_at_95pct_recall": _fpr_at_recall(y, ranking_score, 0.95),
    }


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float | None]:
    if total == 0:
        return [None, None]
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = proportion + z * z / (2.0 * total)
    spread = z * math.sqrt(proportion * (1.0 - proportion) / total + z * z / (4 * total * total))
    return [(centre - spread) / denominator, (centre + spread) / denominator]


def _component_bootstrap_fraction(
    success: np.ndarray,
    eligible: np.ndarray,
    groups: np.ndarray,
    *,
    seed: int,
    replicates: int = TEST_COMPONENT_BOOTSTRAP_REPLICATES,
) -> dict[str, Any]:
    """Cluster-bootstrap a fraction using global components as sampling units."""

    success = np.asarray(success, dtype=bool)
    eligible = np.asarray(eligible, dtype=bool)
    groups = np.asarray(groups, dtype=str)
    if not (len(success) == len(eligible) == len(groups)) or not len(groups):
        raise ValueError("Component-bootstrap fraction arrays are not aligned")
    unique_groups, row_group = np.unique(groups, return_inverse=True)
    if not len(unique_groups):
        raise ValueError("Component-bootstrap fraction requires at least one component")
    numerator_by_group = np.bincount(
        row_group, weights=(success & eligible).astype(np.int64), minlength=len(unique_groups)
    )
    denominator_by_group = np.bincount(
        row_group, weights=eligible.astype(np.int64), minlength=len(unique_groups)
    )
    rng = np.random.default_rng(seed)
    values: list[float] = []
    probabilities = np.full(len(unique_groups), 1.0 / len(unique_groups))
    for start in range(0, replicates, 512):
        batch = min(512, replicates - start)
        counts = rng.multinomial(len(unique_groups), probabilities, size=batch)
        numerator = counts @ numerator_by_group
        denominator = counts @ denominator_by_group
        valid = denominator > 0
        values.extend((numerator[valid] / denominator[valid]).tolist())
    sampled = np.asarray(values, dtype=np.float64)
    return {
        "method": "unstratified_global_component_multinomial_percentile_bootstrap",
        "unit": "global_component_id",
        "confidence_level": 0.95,
        "replicates": replicates,
        "seed": seed,
        "component_count": int(len(unique_groups)),
        "effective_replicates": int(len(sampled)),
        "ci_95pct": (
            [float(np.quantile(sampled, 0.025)), float(np.quantile(sampled, 0.975))]
            if len(sampled)
            else [None, None]
        ),
    }


def _component_bootstrap_multiclass(
    y: np.ndarray,
    prediction: np.ndarray,
    closed_prediction: np.ndarray,
    groups: np.ndarray,
    classes: Sequence[str],
    *,
    seed: int,
    replicates: int = TEST_COMPONENT_BOOTSTRAP_REPLICATES,
) -> dict[str, Any]:
    """Component-aware CIs for known-class H3 aggregate and per-class metrics."""

    y = np.asarray(y, dtype=np.int64)
    prediction = np.asarray(prediction, dtype=np.int64)
    closed_prediction = np.asarray(closed_prediction, dtype=np.int64)
    groups = np.asarray(groups, dtype=str)
    if not (len(y) == len(prediction) == len(closed_prediction) == len(groups)):
        raise ValueError("H3 component-bootstrap arrays are not aligned")
    unique_groups, row_group = np.unique(groups, return_inverse=True)
    if not len(unique_groups):
        raise ValueError("H3 component bootstrap requires at least one component")
    class_count = len(classes)
    support = np.zeros((len(unique_groups), class_count), dtype=np.int64)
    predicted = np.zeros_like(support)
    true_positive = np.zeros_like(support)
    closed_predicted = np.zeros_like(support)
    closed_true_positive = np.zeros_like(support)
    for class_index in range(class_count):
        np.add.at(support[:, class_index], row_group, y == class_index)
        np.add.at(predicted[:, class_index], row_group, prediction == class_index)
        np.add.at(
            true_positive[:, class_index],
            row_group,
            (y == class_index) & (prediction == class_index),
        )
        np.add.at(
            closed_predicted[:, class_index], row_group, closed_prediction == class_index
        )
        np.add.at(
            closed_true_positive[:, class_index],
            row_group,
            (y == class_index) & (closed_prediction == class_index),
        )
    rng = np.random.default_rng(seed)
    probabilities = np.full(len(unique_groups), 1.0 / len(unique_groups))
    samples: dict[str, list[float]] = defaultdict(list)
    per_class_samples = {
        label: {"recall": [], "precision": []} for label in classes
    }
    for start in range(0, replicates, 512):
        batch = min(512, replicates - start)
        counts = rng.multinomial(len(unique_groups), probabilities, size=batch)
        sampled_support = counts @ support
        valid = np.all(sampled_support > 0, axis=1)
        if not np.any(valid):
            continue
        sampled_support = sampled_support[valid].astype(np.float64)
        sampled_predicted = (counts @ predicted)[valid].astype(np.float64)
        sampled_tp = (counts @ true_positive)[valid].astype(np.float64)
        sampled_closed_predicted = (counts @ closed_predicted)[valid].astype(np.float64)
        sampled_closed_tp = (counts @ closed_true_positive)[valid].astype(np.float64)
        recall = sampled_tp / sampled_support
        precision = np.divide(
            sampled_tp,
            sampled_predicted,
            out=np.zeros_like(sampled_tp),
            where=sampled_predicted > 0,
        )
        f1 = np.divide(
            2.0 * precision * recall,
            precision + recall,
            out=np.zeros_like(precision),
            where=(precision + recall) > 0,
        )
        closed_recall = sampled_closed_tp / sampled_support
        closed_precision = np.divide(
            sampled_closed_tp,
            sampled_closed_predicted,
            out=np.zeros_like(sampled_closed_tp),
            where=sampled_closed_predicted > 0,
        )
        closed_f1 = np.divide(
            2.0 * closed_precision * closed_recall,
            closed_precision + closed_recall,
            out=np.zeros_like(closed_precision),
            where=(closed_precision + closed_recall) > 0,
        )
        samples["macro_f1_unknown_as_error"].extend(np.mean(f1, axis=1).tolist())
        samples["balanced_accuracy_unknown_as_error"].extend(
            np.mean(recall, axis=1).tolist()
        )
        samples["closed_set_macro_f1"].extend(np.mean(closed_f1, axis=1).tolist())
        samples["closed_set_balanced_accuracy"].extend(
            np.mean(closed_recall, axis=1).tolist()
        )
        for class_index, label in enumerate(classes):
            per_class_samples[label]["recall"].extend(recall[:, class_index].tolist())
            per_class_samples[label]["precision"].extend(
                precision[:, class_index].tolist()
            )

    def interval(values: Sequence[float]) -> dict[str, Any]:
        array = np.asarray(values, dtype=np.float64)
        return {
            "effective_replicates": int(len(array)),
            "ci_95pct": (
                [float(np.quantile(array, 0.025)), float(np.quantile(array, 0.975))]
                if len(array)
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
        "metrics": {name: interval(values) for name, values in samples.items()},
        "per_class": {
            label: {
                metric: interval(values)
                for metric, values in metrics.items()
            }
            for label, metrics in per_class_samples.items()
        },
    }


def _binary_metric_values(
    y: np.ndarray, ranking_score: np.ndarray, prediction: np.ndarray
) -> dict[str, float] | None:
    """Return bootstrap-safe binary metrics when both truth classes are present."""

    if len(y) == 0 or set(np.unique(y)) != {0, 1}:
        return None
    precision, recall, f1, _ = precision_recall_fscore_support(
        y, prediction, labels=[0, 1], zero_division=0
    )
    return {
        "average_precision": float(average_precision_score(y, ranking_score)),
        "roc_auc": float(roc_auc_score(y, ranking_score)),
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
    ranking_score: np.ndarray,
    ranking_score_source: str,
    threshold: float,
    seed: int,
    prediction_override: np.ndarray | None = None,
    replicates: int = TEST_COMPONENT_BOOTSTRAP_REPLICATES,
) -> dict[str, Any]:
    """Percentile CI from resampling whole frozen global components.

    The Test rows themselves are never treated as independent sampling units.  A
    component drawn twice contributes all of its rows twice, which is the ordinary
    cluster bootstrap estimand required by the frozen protocol.
    """

    y = np.asarray(y, dtype=np.int64)
    probability = np.asarray(probability, dtype=np.float64)
    ranking_score = np.asarray(ranking_score, dtype=np.float64)
    groups = np.asarray(groups, dtype=str)
    if probability.ndim != 1 or ranking_score.ndim != 1:
        raise ValueError("Binary bootstrap probability and ranking score must be 1D")
    if not (
        len(y) == len(probability) == len(ranking_score) == len(groups)
    ) or len(y) == 0:
        raise ValueError("Binary bootstrap arrays are not aligned")
    if not np.isfinite(probability).all() or not np.isfinite(ranking_score).all():
        raise ValueError("Binary bootstrap inputs must be finite")
    if prediction_override is None:
        prediction = (probability >= threshold).astype(np.int64)
    else:
        prediction = np.asarray(prediction_override, dtype=np.int64)
        if len(prediction) != len(y):
            raise ValueError("Binary bootstrap prediction override is not aligned")
    unique_groups, row_group_index = np.unique(groups, return_inverse=True)
    if not len(unique_groups):
        raise ValueError("Binary bootstrap requires at least one global component")
    rng = np.random.default_rng(seed)
    samples: dict[str, list[float]] = defaultdict(list)
    ascending = np.argsort(ranking_score, kind="mergesort")
    score_starts = np.flatnonzero(
        np.concatenate(
            [
                [True],
                ranking_score[ascending][1:] != ranking_score[ascending][:-1],
            ]
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
    probabilities_by_component = np.full(
        len(unique_groups), 1.0 / len(unique_groups), dtype=np.float64
    )
    for start in range(0, replicates, batch_size):
        batch = min(batch_size, replicates - start)
        component_counts = rng.multinomial(
            len(unique_groups), probabilities_by_component, size=batch
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
        "ranking_score_source": ranking_score_source,
        "metrics": intervals,
    }


def _categorical_confusion(
    truth: Sequence[str], prediction: Sequence[str], rows: Sequence[str], columns: Sequence[str]
) -> list[list[int]]:
    row_index = {label: index for index, label in enumerate(rows)}
    column_index = {label: index for index, label in enumerate(columns)}
    matrix = [[0 for _ in columns] for _ in rows]
    for true_label, predicted_label in zip(truth, prediction, strict=True):
        if true_label not in row_index or predicted_label not in column_index:
            raise ValueError(
                f"Categorical confusion label outside contract: {true_label!r}/{predicted_label!r}"
            )
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
        raise ValueError(f"Unexpected Head-1 truth: {row['head1_label']!r}")
    if row["head2_label"] == "none":
        return "djr_non_vma"
    if row["head2_label"] != "viral_morphogenesis_associated":
        raise ValueError(f"Unexpected Head-2 truth for DJR row: {row['head2_label']!r}")
    label = row["head3_operational_label"]
    if label not in H3_OPERATIONAL_OUTPUTS:
        raise ValueError(f"Unexpected Head-3 operational truth: {label!r}")
    return f"vma::{label}"


def _prediction_path(
    head1_positive: bool, head2_positive: bool, head3_prediction: str
) -> str:
    if not head1_positive:
        if head3_prediction != H3_NOT_REACHED_LABEL:
            raise ValueError("Head 3 must be not_reached when Head 1 rejects")
        return "non_djr"
    if not head2_positive:
        if head3_prediction != H3_NOT_REACHED_LABEL:
            raise ValueError("Head 3 must be not_reached when Head 2 rejects")
        return "djr_non_vma"
    if head3_prediction not in H3_OPERATIONAL_OUTPUTS:
        raise ValueError("A row reaching Head 3 must have one of the three operational outputs")
    return f"vma::{head3_prediction}"


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
            selected_confidence = confidence[selected]
            rejected = int(np.sum(selected_confidence < threshold))
            by_value[value] = {
                "numerator": rejected,
                "denominator": int(len(selected_confidence)),
                "unknown_recall": (
                    rejected / len(selected_confidence) if len(selected_confidence) else None
                ),
                "unknown_recall_naive_row_level_descriptive_wilson_95pct_ci": _wilson(
                    rejected, int(len(selected_confidence))
                ),
                "confidence_median": (
                    float(np.median(selected_confidence))
                    if len(selected_confidence)
                    else None
                ),
                "confidence_p95": (
                    float(np.quantile(selected_confidence, 0.95))
                    if len(selected_confidence)
                    else None
                ),
            }
            if groups is not None and seed is not None:
                aligned_groups = np.asarray(groups, dtype=str)
                if len(aligned_groups) != len(confidence):
                    raise ValueError("Unknown-stratum groups are not aligned")
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


def _operational_cascade_metrics(
    metadata: Sequence[dict[str, str]],
    h1_probability: np.ndarray,
    h2_probability: np.ndarray,
    h1_threshold: float,
    h2_threshold: float,
    h3_prediction: Sequence[str],
    *,
    groups: np.ndarray | None = None,
    seed: int | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Evaluate the deployed H1 -> H2 -> H3 path without oracle leakage."""

    h1_positive = np.asarray(h1_probability >= h1_threshold, dtype=bool)
    h2_raw_positive = np.asarray(h2_probability >= h2_threshold, dtype=bool)
    h3_reached = h1_positive & h2_raw_positive
    h3_prediction = list(h3_prediction)
    if not (
        len(metadata)
        == len(h1_positive)
        == len(h2_raw_positive)
        == len(h3_prediction)
    ):
        raise ValueError("Operational cascade arrays are not aligned")
    for index, reached in enumerate(h3_reached):
        allowed = H3_OPERATIONAL_OUTPUTS if reached else [H3_NOT_REACHED_LABEL]
        if h3_prediction[index] not in allowed:
            raise ValueError(
                f"Head-3 gate/output contradiction at row {index}: {h3_prediction[index]!r}"
            )

    truth_paths = [_truth_path(row) for row in metadata]
    predicted_paths = [
        _prediction_path(bool(h1), bool(h2), h3)
        for h1, h2, h3 in zip(
            h1_positive, h2_raw_positive, h3_prediction, strict=True
        )
    ]
    path_correct = sum(
        true == predicted
        for true, predicted in zip(truth_paths, predicted_paths, strict=True)
    )

    scope = np.asarray([row["head3_scope_mask"] == "1" for row in metadata], dtype=bool)
    scope_truth = [
        row["head3_operational_label"] for row, selected in zip(metadata, scope, strict=True)
        if selected
    ]
    scope_prediction = [
        prediction for prediction, selected in zip(h3_prediction, scope, strict=True) if selected
    ]
    reached_scope = scope & h3_reached
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
    for reason in sorted(
        {row["head3_unknown_reason"] for row, selected in zip(metadata, unknown_mask) if selected}
    ):
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
                is_selected and prediction == H3_EXTERNAL_UNKNOWN_LABEL
                for is_selected, prediction in zip(selected, h3_prediction, strict=True)
            )
        )
        unknown_by_reason[reason] = {
            "numerator": correct_unknown,
            "denominator": total,
            "full_cascade_unknown_recall": (
                correct_unknown / total if total else None
            ),
            "full_cascade_unknown_recall_naive_row_level_descriptive_wilson_95pct_ci": _wilson(
                correct_unknown, total
            ),
            "reached_head3": reached,
            "attrited_before_head3": total - reached,
        }

    aligned_groups = None if groups is None else np.asarray(groups, dtype=str)
    if aligned_groups is not None:
        if seed is None or len(aligned_groups) != len(metadata):
            raise ValueError("Cascade component-bootstrap groups/seed are not aligned")
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
                    np.asarray(h3_prediction) == H3_EXTERNAL_UNKNOWN_LABEL,
                    selected,
                    aligned_groups,
                    seed=seed,
                )
            )

    h1_pass = int(h1_positive.sum())
    h3_reached_n = int(h3_reached.sum())
    scope_n = int(scope.sum())
    scope_reached_n = int(reached_scope.sum())
    output = {
        "policy": {
            "order": ["head1", "head2", "head3_phylum"],
            "head3_gate": "head1_predicted_djr AND head2_predicted_vma",
            "not_reached_label": H3_NOT_REACHED_LABEL,
            "head3_outputs": H3_OPERATIONAL_OUTPUTS,
        },
        "stage_reach_attrition": {
            "input_n": len(metadata),
            "head1_pass_djr": h1_pass,
            "head1_attrited_non_djr": len(metadata) - h1_pass,
            "head1_pass_rate": _rate(h1_pass, len(metadata)),
            "head2_reached": h1_pass,
            "head2_pass_vma": h3_reached_n,
            "head2_attrited_none": h1_pass - h3_reached_n,
            "head2_pass_rate_given_reached": _rate(h3_reached_n, h1_pass),
            "head3_reached": h3_reached_n,
            "head3_output_counts": {
                label: sum(
                    reached and prediction == label
                    for reached, prediction in zip(h3_reached, h3_prediction, strict=True)
                )
                for label in H3_OPERATIONAL_OUTPUTS
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
            "truth_labels": H3_OPERATIONAL_OUTPUTS,
            "three_output_labels": H3_OPERATIONAL_OUTPUTS,
            "reached_scope_n": len(reached_scope_truth),
            "reached_scope_confusion_3x3": _categorical_confusion(
                reached_scope_truth,
                reached_scope_prediction,
                H3_OPERATIONAL_OUTPUTS,
                H3_OPERATIONAL_OUTPUTS,
            ),
            "reached_scope_accuracy": _rate(
                reached_scope_correct, len(reached_scope_truth)
            ),
            "all_scope_n": len(scope_truth),
            "all_scope_output_labels": [H3_NOT_REACHED_LABEL, *H3_OPERATIONAL_OUTPUTS],
            "all_scope_confusion_3x4": _categorical_confusion(
                scope_truth,
                scope_prediction,
                H3_OPERATIONAL_OUTPUTS,
                [H3_NOT_REACHED_LABEL, *H3_OPERATIONAL_OUTPUTS],
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
            h3_reached,
            h1_positive,
            aligned_groups,
            seed=seed,
        )
        output["stage_reach_attrition"]["truth_head3_scope_reach_rate"][
            "component_bootstrap_95pct_ci"
        ] = _component_bootstrap_fraction(
            reached_scope,
            scope,
            aligned_groups,
            seed=seed,
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
            reached_correct,
            reached_scope,
            aligned_groups,
            seed=seed,
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


def _multiclass_metrics(
    y: np.ndarray,
    probabilities: np.ndarray,
    classes: Sequence[str],
    unknown_threshold: float,
    *,
    groups: np.ndarray | None = None,
    seed: int | None = None,
) -> tuple[dict[str, Any], np.ndarray]:
    best = probabilities.argmax(axis=1)
    confidence = probabilities.max(axis=1)
    prediction = best.copy()
    prediction[confidence < unknown_threshold] = -1
    recalls = []
    per_class: dict[str, Any] = {}
    for class_index, label in enumerate(classes):
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
    one_hot = np.eye(len(classes), dtype=np.float64)[y]
    correctness = (best == y).astype(np.float64)
    ece = _ece(confidence, correctness)
    metrics = {
        "n": len(y),
        "unknown_threshold": unknown_threshold,
        "unknown_rejections": int(np.sum(prediction == -1)),
        "unknown_rejection_fraction": float(np.mean(prediction == -1)),
        "macro_f1_unknown_as_error": float(
            f1_score(y, prediction, labels=list(range(len(classes))), average="macro", zero_division=0)
        ),
        "balanced_accuracy_unknown_as_error": float(np.mean(recalls)),
        "closed_set_macro_f1": float(f1_score(y, best, average="macro")),
        "closed_set_balanced_accuracy": float(balanced_accuracy_score(y, best)),
        "ece": ece,
        "multiclass_brier": float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
        "per_class": per_class,
    }
    if groups is not None:
        if seed is None:
            raise ValueError("H3 component bootstrap requires a frozen seed")
        bootstrap = _component_bootstrap_multiclass(
            y,
            prediction,
            best,
            np.asarray(groups, dtype=str),
            classes,
            seed=seed,
        )
        metrics["component_bootstrap_95pct_ci"] = bootstrap
        for label in classes:
            metrics["per_class"][label]["component_bootstrap_95pct_ci"] = (
                bootstrap["per_class"][label]
            )
    return metrics, prediction


def _ece(confidence: np.ndarray, correctness: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(confidence)
    value = 0.0
    for index in range(bins):
        if index == bins - 1:
            mask = (confidence >= edges[index]) & (confidence <= edges[index + 1])
        else:
            mask = (confidence >= edges[index]) & (confidence < edges[index + 1])
        if mask.any():
            value += float(mask.mean()) * abs(float(correctness[mask].mean()) - float(confidence[mask].mean()))
    return value if total else float("nan")


def _estimate_head3_open_set(
    y_validation: np.ndarray,
    validation_probabilities: np.ndarray,
    unknown_probabilities: np.ndarray,
    unknown_metadata: Sequence[dict[str, str]],
    settings: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    correct = validation_probabilities.argmax(axis=1) == y_validation
    validation_confidence = validation_probabilities.max(axis=1)
    target_recall = float(settings["head3_known_recall_target"])
    threshold = float(np.quantile(validation_confidence, 1.0 - target_recall, method="lower"))
    unknown_confidence = (
        unknown_probabilities.max(axis=1)
        if len(unknown_probabilities)
        else np.asarray([], dtype=np.float64)
    )
    known_rejected = int(np.sum(validation_confidence < threshold))
    unknown_rejected = int(np.sum(unknown_confidence < threshold))
    predicted_unknown = known_rejected + unknown_rejected
    ood_truth = np.concatenate(
        [
            np.zeros(len(validation_confidence), dtype=np.int64),
            np.ones(len(unknown_confidence), dtype=np.int64),
        ]
    )
    ood_score = np.concatenate([1.0 - validation_confidence, 1.0 - unknown_confidence])
    ood_auroc = (
        float(roc_auc_score(ood_truth, ood_score))
        if len(np.unique(ood_truth)) == 2
        else None
    )
    unknown_strata = _unknown_rejection_strata(
        unknown_confidence, unknown_metadata, threshold
    )
    return threshold, {
        "method": "validation_known_confidence_quantile",
        "known_recall_target": target_recall,
        "validation_known_acceptance": float(np.mean(validation_confidence >= threshold)),
        "validation_closed_set_accuracy": float(np.mean(correct)),
        "validation_known_false_unknown_count": known_rejected,
        "validation_unknown_diagnostic_n": int(len(unknown_confidence)),
        "validation_unknown_diagnostic_rejected": unknown_rejected,
        "validation_unknown_numerator": unknown_rejected,
        "validation_unknown_denominator": int(len(unknown_confidence)),
        "validation_unknown_recall": (
            float(np.mean(unknown_confidence < threshold))
            if len(unknown_confidence)
            else None
        ),
        "validation_unknown_recall_naive_row_level_descriptive_wilson_95pct_ci": _wilson(
            unknown_rejected, int(len(unknown_confidence))
        ),
        "validation_unknown_precision": (
            unknown_rejected / predicted_unknown if predicted_unknown else None
        ),
        "validation_ood_auroc": ood_auroc,
        "validation_unknown_by_status": unknown_strata["head3_status"],
        "validation_unknown_by_reason": unknown_strata["head3_unknown_reason"],
        "interpretation": (
            "Development-only diagnostic. Produgelaviricota and literature-only "
            "unclassified VMA proteins are excluded from known-class fitting and are "
            "not used to choose the confidence threshold."
        ),
    }


def _calibrate(config: dict[str, Any]) -> dict[str, Any]:
    paths = config["paths"]
    settings = config["classifier"]
    seed = int(config["project"]["seed"])
    manifest_path = Path(paths["v0_manifest"])
    embedding_dir = Path(paths["embedding_output"])
    result_dir = Path(paths["result_output"])
    model_dir = result_dir / "models"
    metric_dir = result_dir / "metrics"
    calibration_path = result_dir / "calibration.json"
    if settings.get("binary_ranking_score") != "raw_decision_function":
        raise ValueError(
            "classifier.binary_ranking_score must explicitly be raw_decision_function"
        )
    if calibration_path.exists():
        raise RuntimeError(
            f"Calibration artifact already exists at {calibration_path}; use a new versioned result directory"
        )
    result_dir.mkdir(parents=True, exist_ok=True)
    manifest, vectors = _validate_embedding_contract(manifest_path, embedding_dir)
    cv_fold_contract, cv_fold_assignment = load_frozen_cv_fold_map(
        config, manifest_path
    )

    calibration: dict[str, Any] = {
        "schema_version": 4,
        "binary_ranking_score_source": "raw_decision_function",
        "head3_policy": {
            "known_classes": HEAD_SPECS["head3_phylum"]["classes"],
            "unknown_diagnostic_mask": "head3_unknown_diagnostic_mask",
            "external_unknown_label": H3_EXTERNAL_UNKNOWN_LABEL,
        },
        "created_utc": utc_now(),
        "seed": seed,
        "manifest_sha256": sha256_file(manifest_path),
        "embedding_metadata_sha256": sha256_file(embedding_dir / "metadata.json"),
        "cv_fold_contract": cv_fold_contract,
        "test_evaluated": False,
        "heads": {},
    }
    validation_report: dict[str, Any] = {"created_utc": utc_now(), "heads": {}}
    cv_report: dict[str, Any] = {
        "schema_version": 3,
        "created_utc": utc_now(),
        "binary_ranking_score_source": "raw_decision_function",
        "cv_fold_contract": cv_fold_contract,
        "heads": {},
    }

    for head_offset, head_name in enumerate(HEAD_SPECS):
        x_train, y_train, groups, metadata_train, _ = _select_head(
            manifest, vectors, head_name, "train"
        )
        x_validation, y_validation, _, metadata_validation, _ = _select_head(
            manifest, vectors, head_name, "validation"
        )
        best_parameter, cv = _cross_validate(
            head_name,
            x_train,
            y_train,
            groups,
            metadata_train,
            settings,
            seed + head_offset * 1000,
            cv_fold_assignment,
        )
        model = _fit_model(
            head_name,
            x_train,
            y_train,
            metadata_train,
            best_parameter,
            settings,
            seed + head_offset * 1000,
        )
        temperature, validation_nll, temperature_search = _fit_temperature(
            model, x_validation, y_validation, settings
        )
        validation_decision_scores = _decision_scores(model, x_validation)
        probabilities = _probabilities_from_logits(
            validation_decision_scores, temperature
        )

        if HEAD_SPECS[head_name]["kind"] == "binary":
            if validation_decision_scores.ndim != 1:
                raise ValueError(
                    f"{head_name} Validation requires a 1D decision score"
                )
            threshold_metric = "mcc" if head_name == "head1" else "macro_f1"
            threshold, threshold_score = _select_binary_threshold(
                y_validation, probabilities[:, 1], threshold_metric
            )
            validation_metrics = _binary_metrics(
                y_validation,
                probabilities[:, 1],
                threshold,
                ranking_score=validation_decision_scores,
                ranking_score_source="raw_decision_function",
            )
            open_set = None
        else:
            x_unknown, metadata_unknown, _ = _select_head3_unknown_diagnostic(
                manifest, vectors, "validation"
            )
            unknown_probabilities = (
                _probabilities(model, x_unknown, temperature)
                if len(x_unknown)
                else np.empty((0, len(HEAD_SPECS[head_name]["classes"])), dtype=np.float64)
            )
            threshold, open_set = _estimate_head3_open_set(
                y_validation,
                probabilities,
                unknown_probabilities,
                metadata_unknown,
                settings,
            )
            validation_metrics, _ = _multiclass_metrics(
                y_validation,
                probabilities,
                HEAD_SPECS[head_name]["classes"],
                threshold,
            )
            threshold_metric = "known_acceptance_quantile"
            threshold_score = open_set["validation_known_acceptance"]

        model_path = model_dir / f"{head_name}.joblib"
        bundle = {
            "head": head_name,
            "classes": HEAD_SPECS[head_name]["classes"],
            "estimator": model,
            "temperature": temperature,
            "decision_threshold": threshold,
            "manifest_sha256": calibration["manifest_sha256"],
            "embedding_metadata_sha256": calibration["embedding_metadata_sha256"],
            "best_parameter": best_parameter,
        }
        _atomic_joblib(model_path, bundle)
        model_sha256 = sha256_file(model_path)
        calibration["heads"][head_name] = {
            "classes": HEAD_SPECS[head_name]["classes"],
            "best_parameter": best_parameter,
            "temperature": temperature,
            "temperature_search": temperature_search,
            "validation_nll": validation_nll,
            "decision_threshold": threshold,
            "threshold_metric": threshold_metric,
            "threshold_metric_value": threshold_score,
            "model_path": str(model_path),
            "model_sha256": model_sha256,
            "open_set": open_set,
        }
        validation_report["heads"][head_name] = _jsonable(validation_metrics)
        cv_report["heads"][head_name] = _jsonable(cv)

    atomic_json(metric_dir / "cross_validation.json", _jsonable(cv_report))
    atomic_json(metric_dir / "validation_metrics.json", _jsonable(validation_report))
    calibration["software"] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "scikit_learn": __import__("sklearn").__version__,
        "joblib": joblib.__version__,
    }
    atomic_json(calibration_path, _jsonable(calibration))
    return calibration


def _load_bundle(path: Path, expected_calibration: dict[str, Any]) -> dict[str, Any]:
    expected_hash = expected_calibration["model_sha256"]
    if sha256_file(path) != expected_hash:
        raise RuntimeError(f"Model checksum mismatch: {path}")
    return joblib.load(path)


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


def _write_predictions(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("No prediction rows")
    fieldnames = list(rows[0])
    temporary = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def _validate_test_authorization(
    config: dict[str, Any], result_dir: Path, manifest_path: Path
) -> tuple[Path, dict[str, Any]]:
    spec = config.get("test_selection_authorization")
    if not isinstance(spec, dict):
        raise RuntimeError("Test requires a machine-generated selection authorization")
    result_dir = result_dir.resolve()
    manifest_path = manifest_path.resolve()
    state_dir = _resolved(spec.get("state_dir", ""))
    authorization_path = _resolved(spec.get("path", ""))
    if (
        not _external_project_test_state_dir(state_dir, result_dir)
        or authorization_path != state_dir / "TEST_SELECTION_AUTHORIZATION.json"
    ):
        raise RuntimeError("Selection authorization is not in the external project Test state")
    if not authorization_path.is_file() or sha256_file(authorization_path) != spec.get("sha256"):
        raise RuntimeError("Selection authorization file is missing or has changed")
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    core = {key: value for key, value in authorization.items() if key != "authorization_id"}
    observed_id = _canonical_sha256(core)
    selected_model_id = config.get("embedding", {}).get("benchmark_model_id")
    registry = config.get("benchmark", {}).get("models")
    candidate_ids = list(registry) if isinstance(registry, dict) else []
    embedding_dir = _resolved(config.get("paths", {}).get("embedding_output", ""))
    fasta_path = _resolved(config.get("paths", {}).get("v0_fasta", ""))
    config_path = _resolved(authorization.get("config_path", ""))
    comparison_path = _resolved(authorization.get("comparison_path", ""))
    comparison_hashes = authorization.get("comparison_sha256")
    selected_evidence = authorization.get("selected_candidate_evidence")
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
    expected_input_paths = {
        name: (embedding_dir if location == "embedding" else result_dir) / relative
        for name, (location, relative) in TEST_SELECTED_INPUT_FILES.items()
    }
    evidence_files_valid = (
        isinstance(input_hashes, dict)
        and set(input_hashes) == set(TEST_SELECTED_INPUT_FILES)
        and all(
            path.is_file() and sha256_file(path) == input_hashes[name]
            for name, path in expected_input_paths.items()
        )
        and isinstance(embedding_hashes, dict)
        and set(embedding_hashes) == TEST_EMBEDDING_ARTIFACTS
        and all(
            (embedding_dir / name).is_file()
            and sha256_file(embedding_dir / name) == digest
            for name, digest in embedding_hashes.items()
        )
        and isinstance(model_hashes, dict)
        and set(model_hashes) == set(HEAD_SPECS)
        and all(
            (result_dir / "models" / f"{head}.joblib").is_file()
            and sha256_file(result_dir / "models" / f"{head}.joblib") == digest
            for head, digest in model_hashes.items()
        )
    )
    comparison_valid = (
        isinstance(comparison_hashes, dict)
        and set(comparison_hashes) == TEST_COMPARISON_FILES
        and comparison_path.name == "model_comparison.json"
        and all(
            (comparison_path.parent / name).is_file()
            and sha256_file(comparison_path.parent / name) == digest
            for name, digest in comparison_hashes.items()
        )
    )
    comparison_summary = (
        json.loads(comparison_path.read_text(encoding="utf-8"))
        if comparison_valid
        else {}
    )
    manifest_sha256 = sha256_file(manifest_path)
    production = manifest_sha256 == PRODUCTION_MANIFEST_SHA256
    claim_valid = True
    production_location_valid = True
    if production:
        if not config_path.is_file():
            raise RuntimeError("Frozen production benchmark config is missing")
        frozen_config = load_config(config_path)
        if "test_state_dir" in config.get("paths", {}):
            raise RuntimeError(
                "Canonical production Test ledger location cannot be overridden at runtime"
            )
        identity_payload = content_identity_payload(
            config=frozen_config,
            manifest_sha256=manifest_sha256,
            fasta_sha256=sha256_file(fasta_path) if fasta_path.is_file() else "",
            selection_decision_sha256=selection_decision_sha256(comparison_summary),
            weights=TEST_SELECTION_WEIGHTS,
            candidate_model_ids=candidate_ids,
            selected_model_id=selected_model_id,
            selected_candidate_evidence=selected_evidence,
        )
        project_test_identity = _ledger_canonical_sha256(identity_payload)
        ledger_mode, registry_root, expected_state_dir, claim_path = (
            resolve_test_state_locations(
                config=frozen_config,
                manifest_sha256=manifest_sha256,
                identity=project_test_identity,
            )
        )
        assert registry_root is not None and claim_path is not None
        production_location_valid = bool(
            ledger_mode == PRODUCTION_LEDGER_MODE
            and state_dir == expected_state_dir
            and authorization_path == expected_state_dir / "TEST_SELECTION_AUTHORIZATION.json"
            and authorization.get("ledger_mode") == ledger_mode
            and _resolved(authorization.get("ledger_registry_root", "")) == registry_root
            and _resolved(authorization.get("identity_claim_path", "")) == claim_path
        )
        if claim_path.is_file():
            claim = json.loads(claim_path.read_text(encoding="utf-8"))
            claim_valid = bool(
                authorization.get("identity_claim_sha256") == sha256_file(claim_path)
                and spec.get("identity_claim_sha256") == sha256_file(claim_path)
                and claim.get("status") == "identity_claimed_fail_closed"
                and claim.get("project_test_identity_payload") == identity_payload
                and claim.get("project_test_identity") == project_test_identity
                and _resolved(claim.get("project_test_state_dir", "")) == state_dir
            )
        else:
            claim_valid = False
        expected_registry_artifacts = sorted(
            [claim_path.resolve(), authorization_path.resolve()]
        )
        production_location_valid = bool(
            production_location_valid
            and matching_identity_artifacts(registry_root, project_test_identity)
            == expected_registry_artifacts
        )
    elif authorization.get("schema_version") == 3:
        if not config_path.is_file():
            raise RuntimeError("Frozen non-production benchmark config is missing")
        frozen_config = load_config(config_path)
        identity_payload = content_identity_payload(
            config=frozen_config,
            manifest_sha256=manifest_sha256,
            fasta_sha256=sha256_file(fasta_path) if fasta_path.is_file() else "",
            selection_decision_sha256=selection_decision_sha256(comparison_summary),
            weights=TEST_SELECTION_WEIGHTS,
            candidate_model_ids=candidate_ids,
            selected_model_id=selected_model_id,
            selected_candidate_evidence=selected_evidence,
        )
        project_test_identity = _ledger_canonical_sha256(identity_payload)
        ledger_mode, registry_root, expected_state_dir, claim_path = (
            resolve_test_state_locations(
                config=frozen_config,
                manifest_sha256=manifest_sha256,
                identity=project_test_identity,
            )
        )
        production_location_valid = bool(
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
        project = config.get("project", {})
        identity_payload = {
            "schema_version": 1,
            "project_name": project.get("name"),
            "project_version": project.get("version"),
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "model_input_fasta_path": str(fasta_path),
            "model_input_fasta_sha256": (
                sha256_file(fasta_path) if fasta_path.is_file() else None
            ),
            "config_path": str(config_path),
            "config_sha256": sha256_file(config_path) if config_path.is_file() else None,
            "comparison_path": str(comparison_path),
            "comparison_sha256": comparison_hashes,
            "weights": TEST_SELECTION_WEIGHTS,
            "candidate_model_ids": candidate_ids,
            "selected_model_id": selected_model_id,
            "selected_result_dir": str(result_dir),
            "selected_embedding_dir": str(embedding_dir),
            "selected_candidate_evidence": selected_evidence,
        }
        project_test_identity = _canonical_sha256(identity_payload)
    checks = (
        bool(candidate_ids),
        (
            authorization.get("schema_version") == 3
            if production
            else authorization.get("schema_version") in {2, 3}
        ),
        authorization.get("status") == "authorized_for_single_test_evaluation",
        authorization.get("single_test_only") is True,
        authorization.get("selection_evidence_scope") == "train_cv_and_validation_only",
        authorization.get("test_labels_or_metrics_read_for_selection") is False,
        authorization.get("authorization_id") == observed_id == spec.get("authorization_id"),
        authorization.get("project_test_state_dir") == str(state_dir),
        authorization.get("project_test_identity_payload") == identity_payload,
        authorization.get("project_test_identity")
        == project_test_identity
        == spec.get("project_test_identity"),
        authorization.get("selected_model_id")
        == selected_model_id
        == spec.get("selected_model_id"),
        authorization.get("manifest_sha256") == manifest_sha256,
        authorization.get("model_input_fasta_path") == str(fasta_path),
        authorization.get("model_input_fasta_sha256")
        == (sha256_file(fasta_path) if fasta_path.is_file() else None),
        _resolved(authorization.get("selected_result_dir", "")) == result_dir,
        _resolved(authorization.get("selected_embedding_dir", "")) == embedding_dir,
        authorization.get("weights") == TEST_SELECTION_WEIGHTS,
        authorization.get("candidate_model_ids") == candidate_ids,
        authorization.get("candidate_count") == len(candidate_ids),
        config_path.is_file(),
        authorization.get("config_sha256")
        == (sha256_file(config_path) if config_path.is_file() else None),
        comparison_valid,
        evidence_files_valid,
        production_location_valid,
        claim_valid,
    )
    if not all(checks):
        raise RuntimeError("Selection authorization lineage is invalid")
    return authorization_path, authorization


def _reserve_test_evaluation(
    state_dir: Path, authorization_path: Path, authorization: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    state_dir = state_dir.resolve()
    if (
        _resolved(authorization.get("project_test_state_dir", "")) != state_dir
        or authorization_path.resolve()
        != state_dir / "TEST_SELECTION_AUTHORIZATION.json"
    ):
        raise RuntimeError("Reservation target differs from the authorized project Test state")
    reservation_path = state_dir / "TEST_EVALUATION_RESERVED.json"
    reservation = {
        "schema_version": authorization["schema_version"],
        "status": "reserved_fail_closed",
        "reserved_utc": utc_now(),
        "pid": os.getpid(),
        "host": platform.node(),
        "authorization_id": authorization["authorization_id"],
        "authorization_path": str(authorization_path),
        "authorization_sha256": sha256_file(authorization_path),
        "selected_model_id": authorization["selected_model_id"],
        "selected_result_dir": authorization["selected_result_dir"],
        "project_test_state_dir": str(state_dir),
        "project_test_identity": authorization["project_test_identity"],
        "ledger_mode": authorization.get("ledger_mode"),
        "ledger_registry_root": authorization.get("ledger_registry_root"),
        "identity_claim_path": authorization.get("identity_claim_path"),
        "identity_claim_sha256": authorization.get("identity_claim_sha256"),
        "policy": "Reservation is never auto-removed; a crash remains fail-closed.",
    }
    payload = (json.dumps(reservation, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        descriptor = os.open(
            reservation_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444
        )
    except FileExistsError as exc:
        raise RuntimeError(
            f"Frozen Test evaluation is already reserved at {reservation_path}; refusing"
        ) from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return reservation_path, reservation


def _existing_test_completion_markers(result_dir: Path) -> list[Path]:
    if not result_dir.exists():
        return []
    return sorted(result_dir.rglob("FINAL_TEST_EVALUATED*.json"))


def _evaluate_test(config: dict[str, Any]) -> dict[str, Any]:
    paths = config["paths"]
    result_dir = Path(paths["result_output"])
    marker_path = result_dir / "FINAL_TEST_EVALUATED.json"
    existing_markers = _existing_test_completion_markers(result_dir)
    if existing_markers:
        raise RuntimeError(
            "Frozen Test completion marker already exists; refusing to read Test again: "
            f"{existing_markers}"
        )
    manifest_path = Path(paths["v0_manifest"])
    authorization_path, authorization = _validate_test_authorization(
        config, result_dir, manifest_path
    )
    state_dir = _resolved(authorization["project_test_state_dir"])
    reservation_path, reservation = _reserve_test_evaluation(
        state_dir, authorization_path, authorization
    )
    calibration_path = result_dir / "calibration.json"
    if not calibration_path.is_file():
        raise RuntimeError("Calibration must be completed before frozen test evaluation")
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    embedding_dir = Path(paths["embedding_output"])
    manifest, vectors = _validate_embedding_contract(manifest_path, embedding_dir)
    if calibration["manifest_sha256"] != sha256_file(manifest_path):
        raise RuntimeError("Calibration was created from a different manifest")
    if calibration["embedding_metadata_sha256"] != sha256_file(embedding_dir / "metadata.json"):
        raise RuntimeError("Calibration was created from different embeddings")

    selected: dict[str, dict[str, Any]] = {}
    for head_name in HEAD_SPECS:
        x, y, groups, metadata, rows = _select_head(manifest, vectors, head_name, "test")
        head_calibration = calibration["heads"][head_name]
        bundle = _load_bundle(Path(head_calibration["model_path"]), head_calibration)
        decision_score = _decision_scores(bundle["estimator"], x)
        probability = _probabilities_from_logits(
            decision_score, float(bundle["temperature"])
        )
        selected[head_name] = {
            "x": x,
            "y": y,
            "groups": groups,
            "metadata": metadata,
            "rows": rows,
            "decision_score": decision_score,
            "probability": probability,
            "bundle": bundle,
        }

    h1 = selected["head1"]
    h1_threshold = float(h1["bundle"]["decision_threshold"])
    bootstrap_seed = int(config["project"]["seed"])

    h2 = selected["head2"]
    h2_threshold = float(h2["bundle"]["decision_threshold"])

    # H1 and H2 probabilities are retained for audit, but H2 is operationally
    # reached only after H1 predicts DJR.
    all_test_rows = [index for index, row in enumerate(manifest) if row["split"] == "test"]
    all_test_x = np.asarray(vectors[all_test_rows], dtype=np.float32)
    all_test_metadata = [manifest[index] for index in all_test_rows]
    all_test_groups = np.asarray(
        [row["global_component_id"] for row in all_test_metadata], dtype=str
    )
    h1_all_decision_score = _binary_decision_scores(
        h1["bundle"]["estimator"], all_test_x
    )
    h2_all_decision_score = _binary_decision_scores(
        h2["bundle"]["estimator"], all_test_x
    )
    h1_all_probability = _probabilities_from_logits(
        h1_all_decision_score, float(h1["bundle"]["temperature"])
    )[:, 1]
    h2_all_probability = _probabilities_from_logits(
        h2_all_decision_score, float(h2["bundle"]["temperature"])
    )[:, 1]
    h1_all_truth = np.asarray(
        [int(row["head1_label"] == "djr") for row in all_test_metadata],
        dtype=np.int64,
    )
    h1_metrics = _binary_metrics(
        h1_all_truth,
        h1_all_probability,
        h1_threshold,
        ranking_score=h1_all_decision_score,
        ranking_score_source="raw_decision_function",
    )
    h1_metrics["negative_source_strata"] = _head1_negative_strata(
        all_test_metadata, h1_all_probability, h1_threshold
    )
    h1_metrics["component_bootstrap_95pct_ci"] = _component_bootstrap_binary(
        h1_all_truth,
        h1_all_probability,
        all_test_groups,
        ranking_score=h1_all_decision_score,
        ranking_score_source="raw_decision_function",
        threshold=h1_threshold,
        seed=bootstrap_seed,
    )
    h2_scope_mask = np.asarray(
        [row["head2_mask"] == "1" for row in all_test_metadata], dtype=bool
    )
    h2_oracle_truth = np.asarray(
        [
            int(row["head2_label"] == "viral_morphogenesis_associated")
            for row, selected_scope in zip(
                all_test_metadata, h2_scope_mask, strict=True
            )
            if selected_scope
        ],
        dtype=np.int64,
    )
    h2_oracle_probability = h2_all_probability[h2_scope_mask]
    h2_oracle_decision_score = h2_all_decision_score[h2_scope_mask]
    h2_oracle = _binary_metrics(
        h2_oracle_truth,
        h2_oracle_probability,
        h2_threshold,
        ranking_score=h2_oracle_decision_score,
        ranking_score_source="raw_decision_function",
    )
    h2_oracle["component_bootstrap_95pct_ci"] = _component_bootstrap_binary(
        h2_oracle_truth,
        h2_oracle_probability,
        all_test_groups[h2_scope_mask],
        ranking_score=h2_oracle_decision_score,
        ranking_score_source="raw_decision_function",
        threshold=h2_threshold,
        seed=bootstrap_seed,
    )
    end_to_end_truth = np.asarray(
        [int(row["head2_label"] == "viral_morphogenesis_associated") for row in all_test_metadata],
        dtype=np.int64,
    )
    end_to_end_prediction = (
        (h1_all_probability >= h1_threshold) & (h2_all_probability >= h2_threshold)
    ).astype(np.int64)
    end_to_end_probability = h1_all_probability * h2_all_probability
    # Preserve the original product-of-probabilities estimand without ever
    # materialising a saturated product: log(p1 * p2) = log(sigmoid(z1/T1))
    # + log(sigmoid(z2/T2)).  The logarithm is strictly monotone, so ranking is
    # exactly the intended cascade-confidence ranking in real arithmetic.
    h1_scaled_score = h1_all_decision_score / float(h1["bundle"]["temperature"])
    h2_scaled_score = h2_all_decision_score / float(h2["bundle"]["temperature"])
    end_to_end_ranking_score = _stable_log_probability_product(
        h1_scaled_score, h2_scaled_score
    )
    h2_end_to_end = _binary_metrics(
        end_to_end_truth,
        end_to_end_probability,
        h1_threshold * h2_threshold,
        ranking_score=end_to_end_ranking_score,
        ranking_score_source=(
            "stable_log_product_of_calibrated_head1_and_head2_probabilities"
        ),
    )
    # Fixed cascade predictions, rather than product-threshold predictions,
    # define the deployed result.
    h2_end_to_end["cascade_mcc"] = float(matthews_corrcoef(end_to_end_truth, end_to_end_prediction))
    h2_end_to_end["cascade_balanced_accuracy"] = float(
        balanced_accuracy_score(end_to_end_truth, end_to_end_prediction)
    )
    cascade_precision, cascade_recall, cascade_f1, _ = precision_recall_fscore_support(
        end_to_end_truth, end_to_end_prediction, labels=[0, 1], zero_division=0
    )
    h2_end_to_end["cascade_precision_by_class"] = cascade_precision
    h2_end_to_end["cascade_recall_by_class"] = cascade_recall
    h2_end_to_end["cascade_f1_by_class"] = cascade_f1
    h2_end_to_end_ci = _component_bootstrap_binary(
        end_to_end_truth,
        end_to_end_probability,
        all_test_groups,
        ranking_score=end_to_end_ranking_score,
        ranking_score_source=(
            "stable_log_product_of_calibrated_head1_and_head2_probabilities"
        ),
        threshold=h1_threshold * h2_threshold,
        seed=bootstrap_seed,
        prediction_override=end_to_end_prediction,
    )
    h2_end_to_end_ci["score"] = (
        "log(sigmoid(head1_raw_decision_score / T1)) + "
        "log(sigmoid(head2_raw_decision_score / T2)); stable log-product "
        "preserving the original product-probability ranking"
    )
    h2_end_to_end_ci["classification"] = (
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
        h2_end_to_end_ci["metrics"][target] = h2_end_to_end_ci["metrics"].pop(source)
    h2_end_to_end["component_bootstrap_95pct_ci"] = h2_end_to_end_ci

    h3 = selected["head3_phylum"]
    h3_threshold = float(h3["bundle"]["decision_threshold"])
    h3_scope_rows = np.asarray(
        [
            index
            for index, row in enumerate(manifest)
            if row["split"] == "test" and row["head3_scope_mask"] == "1"
        ],
        dtype=np.int64,
    )
    h3_scope_x = np.asarray(vectors[h3_scope_rows], dtype=np.float32)
    h3_scope_metadata = [manifest[index] for index in h3_scope_rows]
    h3_scope_probability = _probabilities(
        h3["bundle"]["estimator"],
        h3_scope_x,
        float(h3["bundle"]["temperature"]),
    )
    h3_scope_prediction = h3_scope_probability.argmax(axis=1)
    h3_scope_prediction[h3_scope_probability.max(axis=1) < h3_threshold] = -1

    known_scope_mask = np.asarray(
        [row["head3_mask"] == "1" for row in h3_scope_metadata], dtype=bool
    )
    h3_class_to_index = {
        label: index
        for index, label in enumerate(HEAD_SPECS["head3_phylum"]["classes"])
    }
    known_scope_truth = np.asarray(
        [
            h3_class_to_index[row["head3_operational_label"]]
            for row, selected_known in zip(
                h3_scope_metadata, known_scope_mask, strict=True
            )
            if selected_known
        ],
        dtype=np.int64,
    )
    known_scope_probability = h3_scope_probability[known_scope_mask]
    known_scope_groups = np.asarray(
        [row["global_component_id"] for row in h3_scope_metadata], dtype=str
    )[known_scope_mask]
    h3_metrics, _ = _multiclass_metrics(
        known_scope_truth,
        known_scope_probability,
        HEAD_SPECS["head3_phylum"]["classes"],
        h3_threshold,
        groups=known_scope_groups,
        seed=bootstrap_seed,
    )

    unknown_scope_mask = np.asarray(
        [row["head3_unknown_diagnostic_mask"] == "1" for row in h3_scope_metadata],
        dtype=bool,
    )
    metadata_unknown_test = [
        row
        for row, selected_unknown in zip(
            h3_scope_metadata, unknown_scope_mask, strict=True
        )
        if selected_unknown
    ]
    unknown_test_probability = h3_scope_probability[unknown_scope_mask]
    unknown_scope_groups = np.asarray(
        [row["global_component_id"] for row in h3_scope_metadata], dtype=str
    )[unknown_scope_mask]
    known_confidence = known_scope_probability.max(axis=1)
    unknown_confidence = (
        unknown_test_probability.max(axis=1)
        if len(unknown_test_probability)
        else np.asarray([], dtype=np.float64)
    )
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
    h3_metrics["scope_n"] = int(len(h3_scope_rows))
    h3_metrics["known_class_n"] = int(len(known_scope_truth))
    unknown_strata = _unknown_rejection_strata(
        unknown_confidence,
        metadata_unknown_test,
        h3_threshold,
        groups=unknown_scope_groups,
        seed=bootstrap_seed,
    )
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
        "statuses": sorted({row["head3_status"] for row in metadata_unknown_test}),
        "by_status": unknown_strata["head3_status"],
        "by_reason": unknown_strata["head3_unknown_reason"],
    }
    h3_metrics["unknown_diagnostic"][
        "unknown_recall_component_bootstrap_95pct_ci"
    ] = _component_bootstrap_fraction(
        unknown_confidence < h3_threshold,
        np.ones(len(unknown_confidence), dtype=bool),
        unknown_scope_groups,
        seed=bootstrap_seed,
    )
    combined_unknown_groups = np.concatenate(
        [known_scope_groups, unknown_scope_groups]
    )
    combined_rejected = np.concatenate(
        [known_confidence < h3_threshold, unknown_confidence < h3_threshold]
    )
    combined_true_unknown_rejected = np.concatenate(
        [
            np.zeros(len(known_confidence), dtype=bool),
            unknown_confidence < h3_threshold,
        ]
    )
    h3_metrics["unknown_diagnostic"][
        "unknown_precision_component_bootstrap_95pct_ci"
    ] = _component_bootstrap_fraction(
        combined_true_unknown_rejected,
        combined_rejected,
        combined_unknown_groups,
        seed=bootstrap_seed,
    )

    # Oracle H3 probabilities are recorded only for true H3-scope rows.  The
    # deployed H3 estimator is separately invoked only for rows passing both
    # upstream prediction gates.
    h3_oracle_probability_by_global_row = {
        int(row): probability
        for row, probability in zip(h3_scope_rows, h3_scope_probability, strict=True)
    }
    h3_oracle_prediction_by_global_row = {
        int(row): int(prediction)
        for row, prediction in zip(h3_scope_rows, h3_scope_prediction, strict=True)
    }
    h1_all_prediction = h1_all_probability >= h1_threshold
    h2_all_raw_prediction = h2_all_probability >= h2_threshold
    h3_reached = h1_all_prediction & h2_all_raw_prediction
    h3_reached_local_rows = np.flatnonzero(h3_reached)
    h3_operational_probability = (
        _probabilities(
            h3["bundle"]["estimator"],
            all_test_x[h3_reached_local_rows],
            float(h3["bundle"]["temperature"]),
        )
        if len(h3_reached_local_rows)
        else np.empty((0, len(HEAD_SPECS["head3_phylum"]["classes"])), dtype=np.float64)
    )
    h3_operational_prediction = h3_operational_probability.argmax(axis=1)
    if len(h3_operational_probability):
        h3_operational_prediction[
            h3_operational_probability.max(axis=1) < h3_threshold
        ] = -1
    h3_operational_probability_by_local_row = {
        int(row): probability
        for row, probability in zip(
            h3_reached_local_rows, h3_operational_probability, strict=True
        )
    }
    h3_operational_value_by_local_row = {
        int(row): int(prediction)
        for row, prediction in zip(
            h3_reached_local_rows, h3_operational_prediction, strict=True
        )
    }
    h3_classes = HEAD_SPECS["head3_phylum"]["classes"]
    operational_h3_labels = [
        _format_head3_prediction(
            h3_operational_value_by_local_row.get(local_index), h3_classes
        )
        for local_index in range(len(all_test_rows))
    ]
    cascade_metrics, truth_paths, predicted_paths = _operational_cascade_metrics(
        all_test_metadata,
        h1_all_probability,
        h2_all_probability,
        h1_threshold,
        h2_threshold,
        operational_h3_labels,
        groups=all_test_groups,
        seed=bootstrap_seed,
    )

    prediction_rows = []
    for local_index, (global_row, metadata_row) in enumerate(
        zip(all_test_rows, all_test_metadata, strict=True)
    ):
        oracle_probability = h3_oracle_probability_by_global_row.get(global_row)
        oracle_value = h3_oracle_prediction_by_global_row.get(global_row)
        operational_probability = h3_operational_probability_by_local_row.get(local_index)
        head1_predicted = "djr" if h1_all_prediction[local_index] else "non_djr"
        head2_raw_predicted = (
            "viral_morphogenesis_associated"
            if h2_all_raw_prediction[local_index]
            else "none"
        )
        head2_operational_predicted = (
            H3_NOT_REACHED_LABEL
            if not h1_all_prediction[local_index]
            else head2_raw_predicted
        )
        prediction_rows.append(
            {
                "protein_id": metadata_row["protein_id"],
                "global_component_id": metadata_row["global_component_id"],
                "source_dataset": metadata_row["source_dataset"],
                "head1_true": metadata_row["head1_label"],
                "head1_djr_probability": f"{h1_all_probability[local_index]:.17g}",
                "head1_predicted": head1_predicted,
                "head2_true": metadata_row["head2_label"],
                "head2_vma_probability": f"{h2_all_probability[local_index]:.17g}",
                "head2_raw_predicted": head2_raw_predicted,
                "head2_operational_predicted": head2_operational_predicted,
                "head3_true": metadata_row["head3_operational_label"],
                "head3_formal_phylum": metadata_row["head3_phylum_label"],
                "head3_status": metadata_row["head3_status"],
                "head3_unknown_reason": metadata_row["head3_unknown_reason"],
                "head3_oracle_nucleocytoviricota_probability": (
                    f"{oracle_probability[0]:.17g}"
                    if oracle_probability is not None
                    else "NA"
                ),
                "head3_oracle_preplasmiviricota_probability": (
                    f"{oracle_probability[1]:.17g}"
                    if oracle_probability is not None
                    else "NA"
                ),
                "head3_oracle_predicted": (
                    _format_head3_prediction(oracle_value, h3_classes)
                    if oracle_value is not None
                    else H3_NOT_APPLICABLE_LABEL
                ),
                "head3_reached": "1" if h3_reached[local_index] else "0",
                "head3_operational_nucleocytoviricota_probability": (
                    f"{operational_probability[0]:.17g}"
                    if operational_probability is not None
                    else "NA"
                ),
                "head3_operational_preplasmiviricota_probability": (
                    f"{operational_probability[1]:.17g}"
                    if operational_probability is not None
                    else "NA"
                ),
                "head3_predicted": operational_h3_labels[local_index],
                "operational_path_true": truth_paths[local_index],
                "operational_path_predicted": predicted_paths[local_index],
                "operational_path_correct": (
                    "1" if truth_paths[local_index] == predicted_paths[local_index] else "0"
                ),
            }
        )
    prediction_path = result_dir / "predictions" / "frozen_test_predictions.tsv"
    _write_predictions(prediction_path, prediction_rows)

    test_report = {
        "schema_version": 4,
        "completed_utc": utc_now(),
        "manifest_sha256": calibration["manifest_sha256"],
        "embedding_metadata_sha256": calibration["embedding_metadata_sha256"],
        "heads": {
            "head1": _jsonable(h1_metrics),
            "head2": {
                "oracle_conditional": _jsonable(h2_oracle),
                "end_to_end": _jsonable(h2_end_to_end),
            },
            "head3_phylum": _jsonable(h3_metrics),
        },
        "operational_cascade": _jsonable(cascade_metrics),
        "test_use_statement": (
            "Frozen Test was scored once after selection, temperatures, thresholds, "
            "and the H1->H2->H3 gate were frozen. H3 operational output is emitted "
            "only after both upstream predictions pass."
        ),
        "selection_authorization_id": authorization["authorization_id"],
        "project_test_identity": authorization["project_test_identity"],
        "project_test_state_dir": str(state_dir),
        "ledger_mode": authorization.get("ledger_mode"),
        "ledger_registry_root": authorization.get("ledger_registry_root"),
        "identity_claim_path": authorization.get("identity_claim_path"),
        "identity_claim_sha256": authorization.get("identity_claim_sha256"),
        "test_reservation_path": str(reservation_path),
        "frozen_inference_artifacts": {
            "embedding_dir": str(embedding_dir.resolve()),
            "embedding_metadata_sha256": sha256_file(
                embedding_dir / "metadata.json"
            ),
            "embedding_index_sha256": sha256_file(embedding_dir / "index.tsv"),
            "embedding_vectors_sha256": sha256_file(
                embedding_dir / "embeddings.float16.npy"
            ),
            "model_sha256": {
                head: calibration["heads"][head]["model_sha256"]
                for head in HEAD_SPECS
            },
        },
    }
    metric_path = result_dir / "metrics" / "frozen_test_metrics.json"
    atomic_json(metric_path, test_report)
    marker = {
        "schema_version": 3,
        "status": "complete_single_test_evaluation",
        "completed_utc": test_report["completed_utc"],
        "selected_model_id": authorization["selected_model_id"],
        "metrics_path": str(metric_path),
        "metrics_sha256": sha256_file(metric_path),
        "predictions_path": str(prediction_path),
        "predictions_sha256": sha256_file(prediction_path),
        "calibration_sha256": sha256_file(calibration_path),
        "selection_authorization_id": authorization["authorization_id"],
        "project_test_identity": authorization["project_test_identity"],
        "project_test_state_dir": str(state_dir),
        "ledger_mode": authorization.get("ledger_mode"),
        "ledger_registry_root": authorization.get("ledger_registry_root"),
        "identity_claim_path": authorization.get("identity_claim_path"),
        "identity_claim_sha256": authorization.get("identity_claim_sha256"),
        "selection_authorization_path": str(authorization_path),
        "selection_authorization_sha256": sha256_file(authorization_path),
        "test_reservation_path": str(reservation_path),
        "test_reservation_sha256": sha256_file(reservation_path),
        "reservation_status": reservation["status"],
    }
    _exclusive_json(marker_path, marker)
    return test_report


def run(config: dict[str, Any], *, phase: str) -> dict[str, Any]:
    if phase == "calibrate":
        return _calibrate(config)
    if phase == "test":
        return _evaluate_test(config)
    raise ValueError("phase must be 'calibrate' or 'test'")
