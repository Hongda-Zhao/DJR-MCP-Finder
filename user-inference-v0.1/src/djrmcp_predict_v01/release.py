"""Checksum-verified, pickle-free mixed-encoder release loading."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


EXPECTED_HEADS = ("head1", "head2", "head3_phylum")
EXPECTED_ENCODERS = ("esm2_3b", "esmc_6b")
EXPECTED_HEAD_ENCODERS = {
    "head1": "esm2_3b",
    "head2": "esm2_3b",
    "head3_phylum": "esmc_6b",
}
CANONICAL_ARTIFACT_SHA256 = {
    "PARITY_REPORT.json": "22b3f8d49e31365f1c9fbbf722a434bda1bbd393bd4dad71a873ec2a9b81dc3b",
    "THIRD_PARTY_NOTICES.md": "1fef3e62e8043e7b0ce34ccf9ae6d1775fc60480f6706f9156844a14450708f4",
    "heads/head1.npz": "4cadabc814b044d07dece3ab7e03f3df051cca2256d5393e95500d17cc282587",
    "heads/head2.npz": "32f840e196fbdec5d507bab3191b76aebef25ebcdf92fcb483932a8654d9ce32",
    "heads/head3_phylum.npz": "8c0597145a4790c23a4235884e5eb54a4f9d2d324853be78e791dcafd51c3dea",
    "release.json": "b6b0098c4f6f5fc7becbf263243f68414cdd8d783e6d21f360dc1fb58f46244d",
}
FULL_GIT_SHA = re.compile(r"[0-9a-f]{40}")


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Release artifact path is not safe: {value!r}")
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"Release artifact escapes release root: {value!r}")
    return resolved


def verify_checksum_manifest(root: str | Path) -> dict[str, str]:
    release_root = Path(root)
    manifest_path = release_root / "CHECKSUMS.sha256"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise FileNotFoundError(f"Missing checksum manifest: {manifest_path}")
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
    if "release.json" not in observed:
        raise ValueError("Checksum manifest does not bind release.json")
    actual_files: set[str] = set()
    for path in release_root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Release contains a symbolic link: {path}")
        if path.is_file() and path.name != "CHECKSUMS.sha256":
            actual_files.add(path.relative_to(release_root).as_posix())
    if actual_files != set(observed):
        raise ValueError(
            "Checksum manifest does not exactly cover the release directory: "
            f"unbound={sorted(actual_files - set(observed))}, "
            f"missing={sorted(set(observed) - actual_files)}"
        )
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
    encoder_id: str
    classes: tuple[str, ...]
    temperature: float
    threshold: float
    scaler_mean: np.ndarray
    scaler_scale: np.ndarray
    classifier_coef: np.ndarray
    classifier_intercept: np.ndarray
    artifact_sha256: str
    source_joblib_sha256: str

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
        scaled = values.copy()
        scaled -= self.scaler_mean
        scaled /= self.scaler_scale
        scores = scaled @ self.classifier_coef.T
        scores += self.classifier_intercept
        return scores[:, 0] if scores.shape[1] == 1 else scores

    def probabilities(self, embeddings: np.ndarray) -> np.ndarray:
        return probabilities_from_logits(self.decision_function(embeddings), self.temperature)


@dataclass(frozen=True)
class ReleaseBundle:
    root: Path
    metadata: dict[str, Any]
    encoders: dict[str, dict[str, Any]]
    heads: dict[str, FrozenLinearHead]
    release_json_sha256: str

    @property
    def release_id(self) -> str:
        return str(self.metadata["release_id"])

    @property
    def release_status(self) -> str:
        return str(self.metadata["release_status"])


def _validate_encoder(name: str, spec: Any) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise ValueError(f"Encoder {name} contract must be an object")
    required = {
        "model_name",
        "model_revision",
        "backend",
        "dimension",
        "compute_precision",
        "window_residues",
        "stride",
        "record_batch_size",
        "window_batch_size",
        "classifier_input_quantization",
    }
    missing = sorted(required - set(spec))
    if missing:
        raise ValueError(f"Encoder {name} is missing fields: {missing}")
    if FULL_GIT_SHA.fullmatch(str(spec["model_revision"]).lower()) is None:
        raise ValueError(f"Encoder {name} model revision is not a full git SHA")
    if int(spec["dimension"]) <= 0:
        raise ValueError(f"Encoder {name} dimension must be positive")
    if int(spec["window_residues"]) <= 0 or int(spec["stride"]) <= 0:
        raise ValueError(f"Encoder {name} window/stride must be positive")
    if int(spec["record_batch_size"]) <= 0 or int(spec["window_batch_size"]) <= 0:
        raise ValueError(f"Encoder {name} record/window batch size must be positive")
    if spec["classifier_input_quantization"] != "float16_roundtrip":
        raise ValueError(f"Encoder {name} has an unsupported classifier input contract")
    if name == "esm2_3b":
        if spec["backend"] != "transformer_residue" or spec["compute_precision"] != "float16":
            raise ValueError("ESM-2 3B must use transformer_residue/float16")
        if str(spec.get("transformers_version")) != "5.14.1":
            raise ValueError("ESM-2 3B must use frozen Transformers 5.14.1")
    if name == "esmc_6b":
        if spec["backend"] != "esmc_transformer" or spec["compute_precision"] != "bfloat16":
            raise ValueError("ESM-C 6B must use esmc_transformer/bfloat16")
        revision = str(spec.get("transformers_code_revision", "")).lower()
        if FULL_GIT_SHA.fullmatch(revision) is None:
            raise ValueError("ESM-C Transformers code revision is not a full git SHA")
    return dict(spec)


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
        mean = np.asarray(arrays["scaler_mean"], dtype=np.float32)
        scale = np.asarray(arrays["scaler_scale"], dtype=np.float32)
        coef = np.asarray(arrays["classifier_coef"], dtype=np.float32)
        intercept = np.asarray(arrays["classifier_intercept"], dtype=np.float32)

    dimension = int(spec["input_dimension"])
    classes = tuple(str(value) for value in spec["classes"])
    encoder_id = str(spec["encoder_id"])
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
    source_sha = str(spec["source_joblib_sha256"]).lower()
    if len(source_sha) != 64 or any(value not in "0123456789abcdef" for value in source_sha):
        raise ValueError(f"{name} source joblib SHA256 is invalid")
    return FrozenLinearHead(
        name=name,
        encoder_id=encoder_id,
        classes=classes,
        temperature=temperature,
        threshold=threshold,
        scaler_mean=mean,
        scaler_scale=scale,
        classifier_coef=coef,
        classifier_intercept=intercept,
        artifact_sha256=actual_sha,
        source_joblib_sha256=source_sha,
    )


def load_release(root: str | Path, *, strict_candidate: bool = True) -> ReleaseBundle:
    """Verify every candidate artifact before loading NumPy model weights."""

    release_root = Path(root).resolve()
    manifest_entries = verify_checksum_manifest(release_root)
    if strict_candidate and manifest_entries != CANONICAL_ARTIFACT_SHA256:
        changed = {
            name: {
                "expected": CANONICAL_ARTIFACT_SHA256.get(name),
                "observed": manifest_entries.get(name),
            }
            for name in sorted(set(CANONICAL_ARTIFACT_SHA256) | set(manifest_entries))
            if CANONICAL_ARTIFACT_SHA256.get(name) != manifest_entries.get(name)
        }
        raise RuntimeError(f"Release differs from the canonical V0.1 candidate: {changed}")
    release_path = release_root / "release.json"
    metadata = json.loads(release_path.read_text(encoding="utf-8"))
    if metadata.get("schema_version") != 2:
        raise ValueError(f"Unsupported release schema: {metadata.get('schema_version')!r}")
    if metadata.get("release_status") != "development_candidate_external_confirmation_required":
        raise ValueError("V0.1 candidate status is missing or was promoted")
    if metadata.get("released_v0_unchanged") is not True:
        raise ValueError("Release must explicitly preserve the formal V0")
    candidate = metadata.get("candidate")
    if not isinstance(candidate, dict):
        raise ValueError("Release lacks the frozen V0.1 candidate evidence boundary")
    expected_candidate = {
        "candidate_id": "h12_esm2_3b__h3_esmc_6b",
        "nomination_status": "recommended_for_external_confirmation",
        "prospective_external_confirmation_required": True,
        "released_v0_change_permitted": False,
        "test_records": 0,
    }
    for field, expected in expected_candidate.items():
        observed = candidate.get(field)
        if field == "test_records" and isinstance(observed, bool):
            raise ValueError("Candidate Test record count must be an integer")
        if observed != expected:
            raise ValueError(
                f"Candidate field {field} differs: expected={expected!r}, "
                f"observed={observed!r}"
            )
    encoders_raw = metadata.get("encoders", {})
    if tuple(encoders_raw) != EXPECTED_ENCODERS:
        raise ValueError(
            f"Release encoders must be in order {EXPECTED_ENCODERS}; observed={tuple(encoders_raw)}"
        )
    encoders = {name: _validate_encoder(name, encoders_raw[name]) for name in EXPECTED_ENCODERS}
    heads_raw = metadata.get("heads", {})
    if tuple(heads_raw) != EXPECTED_HEADS:
        raise ValueError(
            f"Release heads must be in order {EXPECTED_HEADS}; observed={tuple(heads_raw)}"
        )
    heads = {name: _load_head(release_root, name, heads_raw[name]) for name in EXPECTED_HEADS}
    for name in EXPECTED_HEADS:
        artifact_name = str(heads_raw[name].get("artifact", ""))
        if artifact_name not in manifest_entries:
            raise ValueError(f"Checksum manifest does not bind {name} artifact")
    for name, head in heads.items():
        expected_encoder = EXPECTED_HEAD_ENCODERS[name]
        if head.encoder_id != expected_encoder:
            raise ValueError(
                f"{name} must bind to {expected_encoder}; observed={head.encoder_id}"
            )
        if head.input_dimension != int(encoders[head.encoder_id]["dimension"]):
            raise ValueError(f"{name} dimension differs from encoder {head.encoder_id}")
    routing = metadata.get("routing", {})
    if routing.get("order") != list(EXPECTED_HEADS):
        raise ValueError("Frozen H1 -> H2 -> H3 route differs")
    if routing.get("conditional_h3_embedding") is not True:
        raise ValueError("H3 embedding must be conditional on H1/H2")
    parity_spec = metadata.get("parity")
    if not isinstance(parity_spec, dict) or parity_spec.get("status") != "exact_parity":
        raise ValueError("Release lacks exact dual-encoder export parity")
    parity_name = str(parity_spec.get("report", ""))
    if parity_name not in manifest_entries:
        raise ValueError("Checksum manifest does not bind the parity report")
    parity_path = _safe_relative_path(release_root, parity_name)
    parity_report = json.loads(parity_path.read_text(encoding="utf-8"))
    if parity_report.get("status") != "exact_parity":
        raise ValueError("Parity report status differs from exact_parity")
    if parity_report.get("head_encoder_map") != EXPECTED_HEAD_ENCODERS:
        raise ValueError("Parity report Head-to-encoder map differs")
    return ReleaseBundle(
        root=release_root,
        metadata=metadata,
        encoders=encoders,
        heads=heads,
        release_json_sha256=sha256_file(release_path),
    )
