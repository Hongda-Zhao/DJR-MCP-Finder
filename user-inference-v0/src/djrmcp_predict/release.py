"""Checksum-verified, pickle-free frozen linear-head release loading."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


EXPECTED_HEADS = ("head1", "head2", "head3_phylum")


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Release artifact path is not a safe relative path: {value!r}")
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"Release artifact escapes release root: {value!r}")
    return resolved


def verify_checksum_manifest(root: str | Path) -> dict[str, str]:
    release_root = Path(root)
    manifest_path = release_root / "CHECKSUMS.sha256"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing release checksum manifest: {manifest_path}")
    observed: dict[str, str] = {}
    for line_number, raw in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split(maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"Malformed checksum line {line_number}: {raw!r}")
        digest, name = parts[0].lower(), parts[1].lstrip(" *")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError(f"Invalid SHA256 at line {line_number}")
        if name in observed:
            raise ValueError(f"Duplicate checksum entry: {name}")
        artifact = _safe_relative_path(release_root, name)
        if not artifact.is_file():
            raise FileNotFoundError(f"Missing release artifact: {artifact}")
        actual = sha256_file(artifact)
        if actual != digest:
            raise RuntimeError(
                f"Release checksum mismatch for {name}: expected={digest}, observed={actual}"
            )
        observed[name] = digest
    return observed


def probabilities_from_logits(logits: np.ndarray, temperature: float) -> np.ndarray:
    scores = np.asarray(logits, dtype=np.float64)
    if not np.isfinite(temperature) or temperature <= 0:
        raise ValueError("Temperature must be finite and positive")
    if scores.ndim == 1:
        scaled = np.clip(scores / temperature, -60.0, 60.0)
        positive = 1.0 / (1.0 + np.exp(-scaled))
        return np.column_stack([1.0 - positive, positive])
    if scores.ndim != 2:
        raise ValueError("Logits must be 1D binary or 2D multiclass scores")
    scaled = scores / temperature
    scaled -= scaled.max(axis=1, keepdims=True)
    exponent = np.exp(scaled)
    return exponent / exponent.sum(axis=1, keepdims=True)


@dataclass(frozen=True)
class FrozenLinearHead:
    name: str
    classes: tuple[str, ...]
    temperature: float
    threshold: float
    scaler_mean: np.ndarray
    scaler_scale: np.ndarray
    classifier_coef: np.ndarray
    classifier_intercept: np.ndarray
    artifact_sha256: str

    @property
    def input_dimension(self) -> int:
        return int(self.scaler_mean.shape[0])

    def decision_function(self, embeddings: np.ndarray) -> np.ndarray:
        values = np.asarray(embeddings, dtype=np.float32)
        if values.ndim != 2 or values.shape[1] != self.input_dimension:
            raise ValueError(
                f"{self.name} expected (*, {self.input_dimension}) embeddings; "
                f"observed {values.shape}"
            )
        if not np.isfinite(values).all():
            raise ValueError(f"{self.name} embeddings contain non-finite values")
        # Match sklearn StandardScaler's float32 in-place arithmetic exactly.
        scaled = values.copy()
        scaled -= self.scaler_mean
        scaled /= self.scaler_scale
        scores = scaled @ self.classifier_coef.T
        scores += self.classifier_intercept
        if scores.shape[1] == 1:
            return scores[:, 0]
        return scores

    def probabilities(self, embeddings: np.ndarray) -> np.ndarray:
        return probabilities_from_logits(self.decision_function(embeddings), self.temperature)


@dataclass(frozen=True)
class ReleaseBundle:
    root: Path
    metadata: dict[str, Any]
    heads: dict[str, FrozenLinearHead]
    release_json_sha256: str

    @property
    def release_id(self) -> str:
        return str(self.metadata["release_id"])

    @property
    def embedding(self) -> dict[str, Any]:
        return dict(self.metadata["embedding"])


def _load_head(root: Path, name: str, spec: dict[str, Any]) -> FrozenLinearHead:
    artifact = _safe_relative_path(root, str(spec["artifact"]))
    expected_sha = str(spec["sha256"]).lower()
    actual_sha = sha256_file(artifact)
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"Head checksum mismatch for {name}: expected={expected_sha}, observed={actual_sha}"
        )
    with np.load(artifact, allow_pickle=False) as arrays:
        required = {
            "scaler_mean",
            "scaler_scale",
            "classifier_coef",
            "classifier_intercept",
        }
        if set(arrays.files) != required:
            raise ValueError(
                f"{name} artifact fields differ: expected={sorted(required)}, "
                f"observed={sorted(arrays.files)}"
            )
        # sklearn 1.9 casts StandardScaler parameters to float32 for float32 inputs.
        # Store/use that deployed representation to preserve exact threshold decisions.
        mean = np.asarray(arrays["scaler_mean"], dtype=np.float32)
        scale = np.asarray(arrays["scaler_scale"], dtype=np.float32)
        coef = np.asarray(arrays["classifier_coef"], dtype=np.float32)
        intercept = np.asarray(arrays["classifier_intercept"], dtype=np.float32)

    dimension = int(spec["input_dimension"])
    classes = tuple(str(value) for value in spec["classes"])
    if mean.shape != (dimension,) or scale.shape != (dimension,):
        raise ValueError(f"{name} scaler shape does not match dimension {dimension}")
    if coef.ndim != 2 or coef.shape[1] != dimension:
        raise ValueError(f"{name} classifier coefficient shape is invalid: {coef.shape}")
    if intercept.shape != (coef.shape[0],):
        raise ValueError(f"{name} classifier intercept shape is invalid: {intercept.shape}")
    if len(classes) != 2 or coef.shape[0] not in {1, len(classes)}:
        raise ValueError(f"{name} class/coefficient contract is invalid")
    if not np.isfinite(mean).all() or not np.isfinite(scale).all() or np.any(scale <= 0):
        raise ValueError(f"{name} scaler values are invalid")
    if not np.isfinite(coef).all() or not np.isfinite(intercept).all():
        raise ValueError(f"{name} classifier values are invalid")
    temperature = float(spec["temperature"])
    threshold = float(spec["threshold"])
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"{name} threshold must be in [0, 1]")

    return FrozenLinearHead(
        name=name,
        classes=classes,
        temperature=temperature,
        threshold=threshold,
        scaler_mean=mean,
        scaler_scale=scale,
        classifier_coef=coef,
        classifier_intercept=intercept,
        artifact_sha256=actual_sha,
    )


def load_release(root: str | Path) -> ReleaseBundle:
    """Verify every release artifact before loading NumPy model weights."""

    release_root = Path(root).resolve()
    verify_checksum_manifest(release_root)
    release_path = release_root / "release.json"
    metadata = json.loads(release_path.read_text(encoding="utf-8"))
    if metadata.get("schema_version") != 1:
        raise ValueError(f"Unsupported release schema: {metadata.get('schema_version')!r}")
    if tuple(metadata.get("heads", {}).keys()) != EXPECTED_HEADS:
        raise ValueError(
            f"Release heads must be in frozen order {EXPECTED_HEADS}; "
            f"observed={tuple(metadata.get('heads', {}).keys())}"
        )
    embedding = metadata.get("embedding")
    if not isinstance(embedding, dict) or int(embedding.get("dimension", 0)) <= 0:
        raise ValueError("Release embedding contract is missing or invalid")
    heads = {
        name: _load_head(release_root, name, metadata["heads"][name])
        for name in EXPECTED_HEADS
    }
    dimensions = {head.input_dimension for head in heads.values()}
    if dimensions != {int(embedding["dimension"])}:
        raise ValueError("Embedding dimension and linear-head dimensions differ")
    return ReleaseBundle(
        root=release_root,
        metadata=metadata,
        heads=heads,
        release_json_sha256=sha256_file(release_path),
    )
