#!/usr/bin/env python3
"""Export the checksum-pinned V0.1 mixed candidate as pickle-free NumPy heads.

This command is deliberately an offline, trusted-source export step.  It verifies
the two frozen calibration files and the three selected joblib classifiers before
unpickling them, converts only the linear StandardScaler/classifier parameters to
``.npz``, and requires exact score/probability/decision parity on the encoder-
specific frozen embedding matrices.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np


HEAD_ORDER = ("head1", "head2", "head3_phylum")
HEAD_ENCODERS = {
    "head1": "esm2_3b",
    "head2": "esm2_3b",
    "head3_phylum": "esmc_6b",
}

RELEASE_ID = "project-v0.1-candidate-esm2-3b-esmc-6b-user-inference"
RELEASE_STATUS = "development_candidate_external_confirmation_required"
CANDIDATE_ID = "h12_esm2_3b__h3_esmc_6b"

TRAINING_MANIFEST_SHA256 = (
    "94aa5aff80a18367d36c06fb2f51155f3b52bd8fff4b5be2aa682d891ab84dc7"
)

CALIBRATION_SPECS: dict[str, dict[str, Any]] = {
    "esm2_3b": {
        "sha256": "14ca860b6cf2723aebfcc81744dbae98dcdc328459390f5ae9f7da9569b06e95",
        "embedding_metadata_sha256": (
            "d40bf64e80ccfe7c1c9582abfdd5e2d5723013fc0d0b44a0004a3fa83a41ae59"
        ),
        "selected_heads": ("head1", "head2"),
    },
    "esmc_6b": {
        "sha256": "c654e402428c35b5284ad12aed5418bf9116104ff951daa7b84d349e94c28747",
        "embedding_metadata_sha256": (
            "4fadbbbf5d7a3961c489cdeab4124c66f032e57e0f58375cadfffacae330ae41"
        ),
        "selected_heads": ("head3_phylum",),
    },
}

PARITY_EMBEDDING_SHA256 = {
    "esm2_3b": "c9fcf47cf43f4f9aa978651d2b709c624185e74994dd792d53cbedbc3da2f988",
    "esmc_6b": "9b422c20091f29456068f6cbc22b6a639368f7e46b60782aae6382004e28b7b6",
}

ENCODER_SPECS: dict[str, dict[str, Any]] = {
    "esm2_3b": {
        "model_name": "facebook/esm2_t36_3B_UR50D",
        "model_revision": "476b639933c8baad5ad09a60ac1a87f987b656fc",
        "backend": "transformer_residue",
        "model_loader": "auto",
        "tokenizer_loader": "auto",
        "transformers_version": "5.14.1",
        "dimension": 2560,
        "compute_precision": "float16",
        "output_dtype": "float16",
        "record_batch_size": 2,
        "window_batch_size": 2,
        "window_residues": 1022,
        "stride": 511,
        "pooling": "residue_mean_then_window_mean",
        "long_sequence_policy": "overlapping_windows_no_truncation",
        "special_token_policy": (
            "special_and_padding_tokens_excluded_by_tokenizer_mask"
        ),
        "sequence_format": "raw",
        "sequence_prefix": "",
        "replace_rare_with_x": False,
        "trust_remote_code": False,
        "classifier_input_quantization": "float16_roundtrip",
        "license": "MIT",
    },
    "esmc_6b": {
        "model_name": "Biohub/ESMC-6B",
        "model_revision": "45b0fa5d7fb06faefbd5e3b89bdcef35d564e79a",
        "backend": "esmc_transformer",
        "model_loader": "masked_lm",
        "tokenizer_loader": "auto",
        "transformers_repository": "https://github.com/Biohub/transformers.git",
        "transformers_code_revision": (
            "ef32577f55da19a4989cd7b22e004dc43a4998cb"
        ),
        "transformers_version": "4.57.6",
        "dimension": 2560,
        "compute_precision": "bfloat16",
        "output_dtype": "float16",
        "record_batch_size": 1,
        "window_batch_size": 1,
        "window_residues": 1022,
        "stride": 511,
        "pooling": "residue_mean_then_window_mean",
        "long_sequence_policy": "overlapping_windows_no_truncation",
        "special_token_policy": (
            "bos_eos_and_padding_excluded; sequence_only_residues_mean_pooled"
        ),
        "sequence_format": "raw",
        "sequence_prefix": "",
        "replace_rare_with_x": False,
        "trust_remote_code": False,
        "classifier_input_quantization": "float16_roundtrip",
        "license": "MIT",
    },
}

HEAD_SPECS: dict[str, dict[str, Any]] = {
    "head1": {
        "encoder_id": "esm2_3b",
        "source_model_path": (
            "results/model_benchmark_v0_metric_revision_1/esm2_3b/models/head1.joblib"
        ),
        "source_joblib_sha256": (
            "a6ba94cb38a71e73b3a24559bd5c416cfd8061e8fcb826f0a16df5c0d6a0264b"
        ),
        "classes": ("non_djr", "djr"),
        "best_parameter_name": "alpha",
        "best_parameter": 1e-5,
        "temperature": 879.5286685349943,
        "threshold": 0.9354350741395616,
        "estimator": "SGDClassifier",
    },
    "head2": {
        "encoder_id": "esm2_3b",
        "source_model_path": (
            "results/model_benchmark_v0_metric_revision_1/esm2_3b/models/head2.joblib"
        ),
        "source_joblib_sha256": (
            "b65ea84c6a8894bdfd453886452555847c248684498f8f61a316be766af31a50"
        ),
        "classes": ("none", "viral_morphogenesis_associated"),
        "best_parameter_name": "C",
        "best_parameter": 0.01,
        "temperature": 0.9041698059234516,
        "threshold": 0.9722235071411139,
        "estimator": "LogisticRegression",
    },
    "head3_phylum": {
        "encoder_id": "esmc_6b",
        "source_model_path": (
            "results/model_benchmark_v0_metric_revision_1/esmc_6b/models/"
            "head3_phylum.joblib"
        ),
        "source_joblib_sha256": (
            "88c3f87f349d65e19e33a38130ee8095afc49c29c3d8a254336208338e9e06ba"
        ),
        "classes": ("Nucleocytoviricota", "Preplasmiviricota"),
        "best_parameter_name": "C",
        "best_parameter": 10.0,
        "temperature": 4.2474179687096845,
        "threshold": 0.7126488980564439,
        "estimator": "LogisticRegression",
    },
}


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def probabilities(logits: np.ndarray, temperature: float) -> np.ndarray:
    scores = np.asarray(logits, dtype=np.float64)
    if scores.ndim == 1:
        scaled = np.clip(scores / temperature, -60.0, 60.0)
        positive = 1.0 / (1.0 + np.exp(-scaled))
        return np.column_stack([1.0 - positive, positive])
    if scores.ndim != 2:
        raise ValueError(f"Expected 1D/2D logits, observed shape={scores.shape}")
    scaled = scores / temperature
    scaled -= scaled.max(axis=1, keepdims=True)
    exponent = np.exp(scaled)
    return exponent / exponent.sum(axis=1, keepdims=True)


def manual_decision(arrays: Mapping[str, np.ndarray], values: np.ndarray) -> np.ndarray:
    x = np.asarray(values, dtype=np.float32).copy()
    x -= arrays["scaler_mean"]
    x /= arrays["scaler_scale"]
    scores = x @ arrays["classifier_coef"].T
    scores += arrays["classifier_intercept"]
    return scores[:, 0] if scores.shape[1] == 1 else scores


def _require_exact(label: str, observed: Any, expected: Any) -> None:
    if observed != expected:
        raise ValueError(f"{label} differs: expected={expected!r}, observed={observed!r}")


def _trusted_source_path(project_root: Path, relative_value: str) -> Path:
    relative = Path(relative_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe source model path: {relative_value!r}")
    target = (project_root / relative).resolve()
    try:
        target.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"Source model escapes project root: {relative_value!r}") from exc
    if not target.is_file():
        raise FileNotFoundError(target)
    return target


def load_calibration(path: Path, encoder_id: str) -> dict[str, Any]:
    expected = CALIBRATION_SPECS[encoder_id]
    observed_sha = sha256_file(path)
    if observed_sha != expected["sha256"]:
        raise RuntimeError(
            f"Frozen calibration changed for {encoder_id}: "
            f"expected={expected['sha256']}, observed={observed_sha}"
        )
    calibration = json.loads(path.read_text(encoding="utf-8"))
    _require_exact(
        f"{encoder_id} training manifest",
        calibration.get("manifest_sha256"),
        TRAINING_MANIFEST_SHA256,
    )
    _require_exact(
        f"{encoder_id} embedding metadata",
        calibration.get("embedding_metadata_sha256"),
        expected["embedding_metadata_sha256"],
    )
    _require_exact(f"{encoder_id} test_evaluated", calibration.get("test_evaluated"), False)
    if not isinstance(calibration.get("heads"), dict):
        raise ValueError(f"{encoder_id} calibration lacks heads")
    return calibration


def _verify_estimator(head_name: str, classifier: Any) -> None:
    fixed = HEAD_SPECS[head_name]
    _require_exact(f"{head_name} estimator", type(classifier).__name__, fixed["estimator"])
    parameters = classifier.get_params()
    if head_name == "head1":
        expected_parameters = {
            "alpha": 1e-5,
            "loss": "log_loss",
            "penalty": "l2",
            "average": True,
            "max_iter": 1,
            "learning_rate": "optimal",
        }
    else:
        expected_parameters = {
            "C": fixed["best_parameter"],
            "class_weight": "balanced",
            "solver": "lbfgs",
            "max_iter": 5000,
        }
    for name, expected in expected_parameters.items():
        _require_exact(f"{head_name} classifier parameter {name}", parameters.get(name), expected)


def export_head(
    *,
    head_name: str,
    calibration: Mapping[str, Any],
    project_root: Path,
    heads_dir: Path,
) -> tuple[dict[str, Any], dict[str, np.ndarray], Any]:
    fixed = HEAD_SPECS[head_name]
    calibration_head = calibration["heads"].get(head_name)
    if not isinstance(calibration_head, dict):
        raise ValueError(f"Calibration lacks selected {head_name}")

    _require_exact(
        f"{head_name} model path",
        calibration_head.get("model_path"),
        fixed["source_model_path"],
    )
    _require_exact(
        f"{head_name} model SHA256",
        calibration_head.get("model_sha256"),
        fixed["source_joblib_sha256"],
    )
    _require_exact(
        f"{head_name} classes",
        tuple(calibration_head.get("classes", ())),
        fixed["classes"],
    )
    for field, expected in (
        ("best_parameter", fixed["best_parameter"]),
        ("temperature", fixed["temperature"]),
        ("decision_threshold", fixed["threshold"]),
    ):
        _require_exact(f"{head_name} {field}", calibration_head.get(field), expected)

    source_path = _trusted_source_path(project_root, fixed["source_model_path"])
    observed_source_sha = sha256_file(source_path)
    if observed_source_sha != fixed["source_joblib_sha256"]:
        raise RuntimeError(
            f"Source joblib checksum mismatch for {head_name}: "
            f"expected={fixed['source_joblib_sha256']}, observed={observed_source_sha}"
        )

    # The source has now been verified byte-for-byte and is trusted local material.
    source_bundle = joblib.load(source_path)
    _require_exact(f"{head_name} bundle head", source_bundle.get("head"), head_name)
    _require_exact(
        f"{head_name} bundle classes",
        tuple(source_bundle.get("classes", ())),
        fixed["classes"],
    )
    for field, expected in (
        ("best_parameter", fixed["best_parameter"]),
        ("temperature", fixed["temperature"]),
        ("decision_threshold", fixed["threshold"]),
        ("manifest_sha256", TRAINING_MANIFEST_SHA256),
        (
            "embedding_metadata_sha256",
            CALIBRATION_SPECS[fixed["encoder_id"]]["embedding_metadata_sha256"],
        ),
    ):
        _require_exact(f"{head_name} bundle {field}", source_bundle.get(field), expected)

    pipeline = source_bundle.get("estimator")
    if pipeline is None or not hasattr(pipeline, "named_steps"):
        raise TypeError(f"{head_name} source estimator is not a fitted sklearn Pipeline")
    if tuple(pipeline.named_steps) != ("scale", "classifier"):
        raise ValueError(f"{head_name} pipeline steps differ: {tuple(pipeline.named_steps)}")
    scaler = pipeline.named_steps["scale"]
    classifier = pipeline.named_steps["classifier"]
    _require_exact(f"{head_name} scaler", type(scaler).__name__, "StandardScaler")
    _verify_estimator(head_name, classifier)

    arrays = {
        "scaler_mean": np.ascontiguousarray(scaler.mean_, dtype=np.float32),
        "scaler_scale": np.ascontiguousarray(scaler.scale_, dtype=np.float32),
        "classifier_coef": np.ascontiguousarray(classifier.coef_, dtype=np.float32),
        "classifier_intercept": np.ascontiguousarray(
            classifier.intercept_, dtype=np.float32
        ),
    }
    dimension = int(ENCODER_SPECS[fixed["encoder_id"]]["dimension"])
    if arrays["scaler_mean"].shape != (dimension,):
        raise ValueError(f"{head_name} scaler dimension differs from {dimension}")
    if arrays["scaler_scale"].shape != (dimension,):
        raise ValueError(f"{head_name} scaler scale dimension differs from {dimension}")
    if arrays["classifier_coef"].ndim != 2 or arrays["classifier_coef"].shape[1] != dimension:
        raise ValueError(f"{head_name} coefficient dimension is invalid")
    if arrays["classifier_intercept"].shape != (arrays["classifier_coef"].shape[0],):
        raise ValueError(f"{head_name} intercept dimension is invalid")
    if np.any(arrays["scaler_scale"] <= 0):
        raise ValueError(f"{head_name} contains a non-positive scaler value")
    if not all(np.isfinite(value).all() for value in arrays.values()):
        raise ValueError(f"{head_name} contains non-finite exported parameters")

    artifact_name = f"{head_name}.npz"
    artifact_path = heads_dir / artifact_name
    temporary = artifact_path.with_suffix(".npz.tmp")
    with temporary.open("wb") as handle:
        np.savez(handle, **arrays)
    os.replace(temporary, artifact_path)
    artifact_sha = sha256_file(artifact_path)
    exported_spec = {
        "encoder_id": fixed["encoder_id"],
        "artifact": f"heads/{artifact_name}",
        "sha256": artifact_sha,
        "source_joblib_sha256": observed_source_sha,
        "classes": list(fixed["classes"]),
        "classifier": fixed["estimator"],
        "best_parameter_name": fixed["best_parameter_name"],
        "best_parameter": fixed["best_parameter"],
        "temperature": fixed["temperature"],
        "threshold": fixed["threshold"],
        "input_dimension": dimension,
        "threshold_rule": (
            ">= positive-class probability for H1/H2; H3 rejects to unknown/other "
            "when maximum known-class probability is below threshold"
        ),
    }
    return exported_spec, arrays, pipeline


def parity_check(
    *,
    parity_embeddings: Mapping[str, Path],
    exported: Mapping[str, tuple[dict[str, np.ndarray], Any, dict[str, Any]]],
    chunk_size: int,
) -> dict[str, Any]:
    if chunk_size <= 0:
        raise ValueError("Parity chunk size must be positive")
    report: dict[str, Any] = {
        "schema_version": 2,
        "status": "exact_parity",
        "head_encoder_map": dict(HEAD_ENCODERS),
        "encoders": {},
        "heads": {},
    }
    failures: list[str] = []

    for encoder_id in ENCODER_SPECS:
        embedding_path = parity_embeddings[encoder_id].resolve()
        if not embedding_path.is_file():
            raise FileNotFoundError(embedding_path)
        embedding_sha = sha256_file(embedding_path)
        expected_embedding_sha = PARITY_EMBEDDING_SHA256[encoder_id]
        if embedding_sha != expected_embedding_sha:
            raise RuntimeError(
                f"Frozen parity embeddings changed for {encoder_id}: "
                f"expected={expected_embedding_sha}, observed={embedding_sha}"
            )
        vectors = np.load(embedding_path, mmap_mode="r", allow_pickle=False)
        dimension = int(ENCODER_SPECS[encoder_id]["dimension"])
        if vectors.ndim != 2 or vectors.shape[1] != dimension or vectors.shape[0] == 0:
            raise ValueError(
                f"Invalid {encoder_id} parity embedding shape: {vectors.shape}"
            )
        selected_heads = [
            head_name for head_name in HEAD_ORDER if HEAD_ENCODERS[head_name] == encoder_id
        ]
        report["encoders"][encoder_id] = {
            "embedding_sha256": embedding_sha,
            "rows": int(vectors.shape[0]),
            "dimension": int(vectors.shape[1]),
            "heads": selected_heads,
            "status": "exact_parity",
        }

        for head_name in selected_heads:
            arrays, pipeline, head_spec = exported[head_name]
            exact_scores = True
            exact_probabilities = True
            exact_decisions = True
            max_score_delta = 0.0
            max_probability_delta = 0.0
            for start in range(0, len(vectors), chunk_size):
                x = np.asarray(vectors[start : start + chunk_size], dtype=np.float32)
                expected_scores = np.asarray(pipeline.decision_function(x))
                observed_scores = manual_decision(arrays, x)
                exact_scores = exact_scores and np.array_equal(
                    expected_scores, observed_scores
                )
                if expected_scores.size:
                    max_score_delta = max(
                        max_score_delta,
                        float(np.max(np.abs(expected_scores - observed_scores))),
                    )

                expected_probabilities = probabilities(
                    expected_scores, float(head_spec["temperature"])
                )
                observed_probabilities = probabilities(
                    observed_scores, float(head_spec["temperature"])
                )
                exact_probabilities = exact_probabilities and np.array_equal(
                    expected_probabilities, observed_probabilities
                )
                if expected_probabilities.size:
                    max_probability_delta = max(
                        max_probability_delta,
                        float(
                            np.max(
                                np.abs(
                                    expected_probabilities - observed_probabilities
                                )
                            )
                        ),
                    )

                threshold = float(head_spec["threshold"])
                if head_name in {"head1", "head2"}:
                    expected_decisions = expected_probabilities[:, 1] >= threshold
                    observed_decisions = observed_probabilities[:, 1] >= threshold
                else:
                    expected_decisions = np.column_stack(
                        (
                            expected_probabilities.argmax(axis=1),
                            expected_probabilities.max(axis=1) >= threshold,
                        )
                    )
                    observed_decisions = np.column_stack(
                        (
                            observed_probabilities.argmax(axis=1),
                            observed_probabilities.max(axis=1) >= threshold,
                        )
                    )
                exact_decisions = exact_decisions and np.array_equal(
                    expected_decisions, observed_decisions
                )

            head_report = {
                "encoder_id": encoder_id,
                "rows": int(vectors.shape[0]),
                "exact_raw_scores": bool(exact_scores),
                "max_abs_raw_score_delta": max_score_delta,
                "exact_probabilities": bool(exact_probabilities),
                "max_abs_probability_delta": max_probability_delta,
                "exact_threshold_decisions": bool(exact_decisions),
            }
            report["heads"][head_name] = head_report
            if not (exact_scores and exact_probabilities and exact_decisions):
                failures.append(head_name)

    if failures:
        report["status"] = "failed"
        for encoder_id, encoder_report in report["encoders"].items():
            if any(HEAD_ENCODERS[head_name] == encoder_id for head_name in failures):
                encoder_report["status"] = "failed"
        raise RuntimeError(
            "Portable mixed-head release parity failed: "
            + json.dumps(
                {"failures": failures, "heads": report["heads"]}, sort_keys=True
            )
        )
    return report


def write_checksums(release_dir: Path) -> None:
    targets = sorted(
        path
        for path in release_dir.rglob("*")
        if path.is_file() and path.name != "CHECKSUMS.sha256"
    )
    if not targets:
        raise RuntimeError("Refusing to write an empty release checksum manifest")
    content = "".join(
        f"{sha256_file(path)}  {path.relative_to(release_dir).as_posix()}\n"
        for path in targets
    )
    temporary = release_dir / ".CHECKSUMS.sha256.tmp"
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, release_dir / "CHECKSUMS.sha256")


def build_release(args: argparse.Namespace, release_dir: Path) -> dict[str, Any]:
    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        raise NotADirectoryError(project_root)
    calibrations = {
        "esm2_3b": load_calibration(args.esm2_calibration.resolve(), "esm2_3b"),
        "esmc_6b": load_calibration(args.esmc_calibration.resolve(), "esmc_6b"),
    }

    heads_dir = release_dir / "heads"
    heads_dir.mkdir(parents=True)
    head_specs: dict[str, Any] = {}
    exported: dict[str, tuple[dict[str, np.ndarray], Any, dict[str, Any]]] = {}
    for head_name in HEAD_ORDER:
        encoder_id = HEAD_ENCODERS[head_name]
        spec, arrays, pipeline = export_head(
            head_name=head_name,
            calibration=calibrations[encoder_id],
            project_root=project_root,
            heads_dir=heads_dir,
        )
        head_specs[head_name] = spec
        exported[head_name] = (arrays, pipeline, spec)

    parity = parity_check(
        parity_embeddings={
            "esm2_3b": args.esm2_parity_embeddings,
            "esmc_6b": args.esmc_parity_embeddings,
        },
        exported=exported,
        chunk_size=args.parity_chunk_size,
    )
    atomic_json(release_dir / "PARITY_REPORT.json", parity)

    release = {
        "schema_version": 2,
        "release_id": RELEASE_ID,
        "release_status": RELEASE_STATUS,
        "released_v0_unchanged": True,
        "candidate": {
            "candidate_id": CANDIDATE_ID,
            "nomination_status": "recommended_for_external_confirmation",
            "nomination_primary_evidence": "train_only_shared_five_fold_cv",
            "mean_train_cv_score": 0.9976446243098959,
            "prospective_external_confirmation_required": True,
            "released_v0_change_permitted": False,
            "test_records": 0,
            "interpretation": (
                "train_cv_nominated_schema5_diagnostic_only_not_independent_validation"
            ),
        },
        "source_project": "DJR-MCP-Finder project V0; data-curation V3",
        "source_calibrations": {
            encoder_id: {
                "sha256": CALIBRATION_SPECS[encoder_id]["sha256"],
                "training_manifest_sha256": TRAINING_MANIFEST_SHA256,
                "training_embedding_metadata_sha256": CALIBRATION_SPECS[encoder_id][
                    "embedding_metadata_sha256"
                ],
                "selected_heads": list(CALIBRATION_SPECS[encoder_id]["selected_heads"]),
            }
            for encoder_id in ENCODER_SPECS
        },
        "encoders": ENCODER_SPECS,
        "heads": head_specs,
        "routing": {
            "order": list(HEAD_ORDER),
            "head1_positive_class": "djr",
            "head2_positive_class": "viral_morphogenesis_associated",
            "head1_head2_share_embedding": True,
            "conditional_h3_embedding": True,
            "head3_not_reached_label": "not_reached",
            "head3_rejection_label": "unknown/other",
        },
        "training_domain": {
            "representative_count": 11060,
            "length_min": 130,
            "length_max": 2906,
            "allowed_residues": "ACDEFGHIKLMNPQRSTVWXY",
        },
        "parity": {
            "report": "PARITY_REPORT.json",
            "status": parity["status"],
            "encoders": {
                encoder_id: {
                    "embedding_sha256": parity["encoders"][encoder_id][
                        "embedding_sha256"
                    ],
                    "rows": parity["encoders"][encoder_id]["rows"],
                    "dimension": parity["encoders"][encoder_id]["dimension"],
                    "heads": parity["encoders"][encoder_id]["heads"],
                }
                for encoder_id in ENCODER_SPECS
            },
        },
        "limitations": [
            "This is a development candidate for prospective external confirmation, "
            "not a replacement for released V0.",
            "No prospective external Test records were evaluated during candidate nomination.",
            "Scores are not prevalence-adjusted posterior probabilities.",
            "H3 unknown/other rejects only from two known phyla and is not a general OOD detector.",
            "Inputs outside the training length/alphabet domain require extra caution.",
            "The two frozen encoders require separately pinned runtime environments "
            "unless cross-environment parity is established.",
        ],
        "export_environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy": np.__version__,
            "joblib": joblib.__version__,
            "scikit_learn": __import__("sklearn").__version__,
        },
    }
    atomic_json(release_dir / "release.json", release)
    write_checksums(release_dir)
    return release


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--esm2-calibration", required=True, type=Path)
    parser.add_argument("--esmc-calibration", required=True, type=Path)
    parser.add_argument("--esm2-parity-embeddings", required=True, type=Path)
    parser.add_argument("--esmc-parity-embeddings", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--parity-chunk-size", type=int, default=512)
    args = parser.parse_args()

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output_was_empty = False
    if output.exists():
        if not output.is_dir():
            raise FileExistsError(f"Output exists and is not a directory: {output}")
        if any(output.iterdir()):
            raise FileExistsError(f"Refusing to overwrite non-empty output: {output}")
        output_was_empty = True

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.export-", dir=output.parent)
    )
    try:
        release = build_release(args, temporary)
        if output_was_empty:
            output.rmdir()
        os.replace(temporary, output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    print(
        json.dumps(
            {
                "status": "complete",
                "release": str(output),
                "release_id": release["release_id"],
                "release_status": release["release_status"],
                "parity": release["parity"]["status"],
                "released_v0_unchanged": release["released_v0_unchanged"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
