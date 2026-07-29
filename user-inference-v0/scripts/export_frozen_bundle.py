#!/usr/bin/env python3
"""Export trusted frozen sklearn heads into a pickle-free NumPy release bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np


HEAD_ORDER = ("head1", "head2", "head3_phylum")
MODEL_NAME = "Biohub/ESMC-6B"
MODEL_REVISION = "45b0fa5d7fb06faefbd5e3b89bdcef35d564e79a"
TRANSFORMERS_REPOSITORY = "https://github.com/Biohub/transformers.git"
TRANSFORMERS_REVISION = "ef32577f55da19a4989cd7b22e004dc43a4998cb"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
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
    scaled = scores / temperature
    scaled -= scaled.max(axis=1, keepdims=True)
    exponent = np.exp(scaled)
    return exponent / exponent.sum(axis=1, keepdims=True)


def manual_decision(arrays: dict[str, np.ndarray], x: np.ndarray) -> np.ndarray:
    values = np.asarray(x, dtype=np.float32).copy()
    values -= arrays["scaler_mean"]
    values /= arrays["scaler_scale"]
    scores = values @ arrays["classifier_coef"].T
    scores += arrays["classifier_intercept"]
    return scores[:, 0] if scores.shape[1] == 1 else scores


def export_head(
    *,
    head_name: str,
    calibration_spec: dict[str, Any],
    project_root: Path,
    heads_dir: Path,
) -> tuple[dict[str, Any], dict[str, np.ndarray], Any]:
    source_path = (project_root / calibration_spec["model_path"]).resolve()
    expected_source_sha = str(calibration_spec["model_sha256"])
    observed_source_sha = sha256_file(source_path)
    if observed_source_sha != expected_source_sha:
        raise RuntimeError(
            f"Source joblib checksum mismatch for {head_name}: "
            f"expected={expected_source_sha}, observed={observed_source_sha}"
        )
    # This script is only for trusted local project artifacts, verified before unpickling.
    source_bundle = joblib.load(source_path)
    if source_bundle.get("head") != head_name:
        raise ValueError(f"Source bundle head mismatch: {source_bundle.get('head')!r}")
    if list(source_bundle["classes"]) != list(calibration_spec["classes"]):
        raise ValueError(f"Source/calibration class mismatch for {head_name}")
    for field in ("temperature", "decision_threshold"):
        if float(source_bundle[field]) != float(calibration_spec[field]):
            raise ValueError(f"Source/calibration {field} mismatch for {head_name}")

    pipeline = source_bundle["estimator"]
    scaler = pipeline.named_steps["scale"]
    classifier = pipeline.named_steps["classifier"]
    arrays = {
        "scaler_mean": np.asarray(scaler.mean_, dtype=np.float32),
        "scaler_scale": np.asarray(scaler.scale_, dtype=np.float32),
        "classifier_coef": np.asarray(classifier.coef_, dtype=np.float32),
        "classifier_intercept": np.asarray(classifier.intercept_, dtype=np.float32),
    }
    if np.any(arrays["scaler_scale"] <= 0):
        raise ValueError(f"Non-positive scaler value in {head_name}")
    artifact_name = f"{head_name}.npz"
    artifact_path = heads_dir / artifact_name
    temporary = artifact_path.with_suffix(".npz.tmp")
    with temporary.open("wb") as handle:
        np.savez(handle, **arrays)
    os.replace(temporary, artifact_path)
    artifact_sha = sha256_file(artifact_path)
    head_spec = {
        "artifact": f"heads/{artifact_name}",
        "sha256": artifact_sha,
        "source_joblib_sha256": observed_source_sha,
        "classes": list(source_bundle["classes"]),
        "temperature": float(source_bundle["temperature"]),
        "threshold": float(source_bundle["decision_threshold"]),
        "input_dimension": int(arrays["scaler_mean"].shape[0]),
        "threshold_rule": ">= for H1/H2; H3 rejects when max_probability < threshold",
    }
    return head_spec, arrays, pipeline


def parity_check(
    embeddings_path: Path,
    exported: dict[str, tuple[dict[str, np.ndarray], Any, dict[str, Any]]],
) -> dict[str, Any]:
    vectors = np.load(embeddings_path, mmap_mode="r")
    if vectors.ndim != 2:
        raise ValueError(f"Parity embeddings must be 2D: {vectors.shape}")
    report: dict[str, Any] = {
        "embedding_sha256": sha256_file(embeddings_path),
        "rows": int(vectors.shape[0]),
        "dimension": int(vectors.shape[1]),
        "heads": {},
    }
    failures: list[str] = []
    for name, (arrays, pipeline, spec) in exported.items():
        exact_scores = True
        exact_probabilities = True
        exact_decisions = True
        max_score_delta = 0.0
        max_probability_delta = 0.0
        for start in range(0, len(vectors), 512):
            x = np.asarray(vectors[start : start + 512], dtype=np.float32)
            expected_score = np.asarray(pipeline.decision_function(x))
            observed_score = manual_decision(arrays, x)
            exact_scores = exact_scores and np.array_equal(expected_score, observed_score)
            max_score_delta = max(
                max_score_delta,
                float(np.max(np.abs(expected_score - observed_score), initial=0.0)),
            )
            expected_probability = probabilities(expected_score, float(spec["temperature"]))
            observed_probability = probabilities(observed_score, float(spec["temperature"]))
            exact_probabilities = exact_probabilities and np.array_equal(
                expected_probability, observed_probability
            )
            max_probability_delta = max(
                max_probability_delta,
                float(
                    np.max(
                        np.abs(expected_probability - observed_probability), initial=0.0
                    )
                ),
            )
            if name in {"head1", "head2"}:
                expected_decision = expected_probability[:, 1] >= float(spec["threshold"])
                observed_decision = observed_probability[:, 1] >= float(spec["threshold"])
            else:
                expected_decision = np.column_stack(
                    [
                        expected_probability.argmax(axis=1),
                        expected_probability.max(axis=1) >= float(spec["threshold"]),
                    ]
                )
                observed_decision = np.column_stack(
                    [
                        observed_probability.argmax(axis=1),
                        observed_probability.max(axis=1) >= float(spec["threshold"]),
                    ]
                )
            exact_decisions = exact_decisions and np.array_equal(
                expected_decision, observed_decision
            )
        report["heads"][name] = {
            "exact_raw_scores": exact_scores,
            "max_abs_raw_score_delta": max_score_delta,
            "exact_probabilities": exact_probabilities,
            "max_abs_probability_delta": max_probability_delta,
            "exact_threshold_decisions": exact_decisions,
        }
        if not (exact_scores and exact_probabilities and exact_decisions):
            failures.append(name)
    report["status"] = "exact_parity" if not failures else "failed"
    if failures:
        raise RuntimeError(
            "Portable release parity failed: "
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
    content = "".join(
        f"{sha256_file(path)}  {path.relative_to(release_dir)}\n" for path in targets
    )
    (release_dir / "CHECKSUMS.sha256").write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--calibration", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--parity-embeddings", required=True, type=Path)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    calibration_path = args.calibration.resolve()
    release_dir = args.output.resolve()
    heads_dir = release_dir / "heads"
    heads_dir.mkdir(parents=True, exist_ok=True)
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    if tuple(calibration.get("heads", {})) != HEAD_ORDER:
        raise ValueError("Calibration head order differs from the frozen release contract")

    head_specs: dict[str, Any] = {}
    exported: dict[str, tuple[dict[str, np.ndarray], Any, dict[str, Any]]] = {}
    for head_name in HEAD_ORDER:
        spec, arrays, pipeline = export_head(
            head_name=head_name,
            calibration_spec=calibration["heads"][head_name],
            project_root=project_root,
            heads_dir=heads_dir,
        )
        head_specs[head_name] = spec
        exported[head_name] = (arrays, pipeline, spec)

    parity = parity_check(args.parity_embeddings.resolve(), exported)
    atomic_json(release_dir / "PARITY_REPORT.json", parity)
    release = {
        "schema_version": 1,
        "release_id": "project-v0-esmc6b-r1-user-inference",
        "source_project": "DJR-MCP-Finder project V0; data-curation V3",
        "source_calibration_sha256": sha256_file(calibration_path),
        "embedding": {
            "model_name": MODEL_NAME,
            "model_revision": MODEL_REVISION,
            "transformers_repository": TRANSFORMERS_REPOSITORY,
            "transformers_code_revision": TRANSFORMERS_REVISION,
            "dimension": 2560,
            "window_residues": 1022,
            "stride": 511,
            "window_batch_size": 1,
            "pooling": "residue_mean_then_window_mean",
            "special_token_policy": "BOS/EOS/padding excluded",
            "compute_precision": "bfloat16_on_cuda",
            "classifier_input_quantization": "float16_roundtrip",
            "allowed_residues": "ACDEFGHIKLMNPQRSTVWXY",
        },
        "heads": head_specs,
        "training_domain": {
            "representative_count": 11060,
            "length_min": 130,
            "length_max": 2906,
        },
        "parity": {
            "report": "PARITY_REPORT.json",
            "status": parity["status"],
            "rows": parity["rows"],
            "embedding_sha256": parity["embedding_sha256"],
        },
        "limitations": [
            "ESM-C 6B has not been evaluated on a new prospective external Test.",
            "Scores are not prevalence-adjusted posterior probabilities.",
            "H3 unknown/other rejects only from two known phyla and is not a general OOD detector.",
            "Inputs outside the training length/alphabet domain require extra caution.",
        ],
        "export_environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy": np.__version__,
            "joblib": joblib.__version__,
        },
    }
    atomic_json(release_dir / "release.json", release)
    write_checksums(release_dir)
    print(json.dumps({"status": "complete", "release": str(release_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
