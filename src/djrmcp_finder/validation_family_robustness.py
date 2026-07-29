"""Self-contained inference helpers for the Validation-family auxiliary audit.

This module only loads checksum-bound embeddings and already-frozen classifier
bundles.  It exposes no fitting, calibration, threshold-selection, or benchmark
selection operation.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from djrmcp_finder.benchmark_config import expand_benchmark_model
from djrmcp_finder.benchmark_selection import load_frozen_benchmark_selection


HEADS = ("head1", "head2")
KNOWN_H3_CLASSES = ("Nucleocytoviricota", "Preplasmiviricota")
REPRESENTATION_KEYS = (
    "model_name",
    "requested_model_revision",
    "resolved_model_revision",
    "backend",
    "adapter_options",
    "embedding_dimension",
    "dtype",
    "compute_precision",
    "pooling",
    "long_sequence_policy",
    "special_token_policy",
    "window_residues",
    "stride",
)
EMBEDDING_ARTIFACT_NAMES = {
    "completed.npy",
    "embeddings.float16.npy",
    "index.tsv",
    "metadata.json",
}


@dataclass(frozen=True)
class ModelSpec:
    """Paths for one frozen benchmark model and its viral-member embedding shard."""

    model_id: str
    label: str
    original_embedding: Path
    member_embedding: Path
    result_dir: Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise RuntimeError(f"Missing TSV header: {path}")
        return list(reader)


def verify_checksum_manifest(
    directory: Path, *, exact_names: set[str] | None = None
) -> dict[str, str]:
    """Verify a flat, path-safe checksum bundle and return its entries."""

    manifest = directory / "CHECKSUMS.sha256"
    if not manifest.is_file():
        raise FileNotFoundError(f"Missing checksum manifest: {manifest}")
    verified: dict[str, str] = {}
    for line_number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split(maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError(f"Malformed checksum at {manifest}:{line_number}")
        expected, name = parts[0].lower(), parts[1].strip().lstrip("*")
        target = directory / name
        if (
            len(expected) != 64
            or any(value not in "0123456789abcdef" for value in expected)
            or Path(name).name != name
            or name in verified
            or not target.is_file()
        ):
            raise RuntimeError(f"Unsafe, duplicate, or missing checksum target: {target}")
        observed = sha256(target)
        if observed != expected:
            raise RuntimeError(f"Checksum mismatch: {target}")
        verified[name] = observed
    if not verified:
        raise RuntimeError(f"Empty checksum manifest: {manifest}")
    if exact_names is not None and set(verified) != exact_names:
        raise RuntimeError(
            f"Embedding bundle must contain {sorted(exact_names)}; "
            f"observed {sorted(verified)}"
        )
    return verified


def _load_embedding(
    manifest_path: Path, embedding_dir: Path
) -> tuple[list[dict[str, str]], np.ndarray, dict[str, Any], dict[str, str]]:
    verified = verify_checksum_manifest(
        embedding_dir, exact_names=EMBEDDING_ARTIFACT_NAMES
    )
    metadata = json.loads((embedding_dir / "metadata.json").read_text(encoding="utf-8"))
    if metadata.get("status") != "complete":
        raise RuntimeError(f"Incomplete embedding directory: {embedding_dir}")
    if metadata.get("manifest_sha256") != sha256(manifest_path):
        raise RuntimeError(f"Embedding/manifest SHA mismatch: {embedding_dir}")
    manifest = _read_tsv(manifest_path)
    index = _read_tsv(embedding_dir / "index.tsv")
    vectors = np.load(embedding_dir / "embeddings.float16.npy", mmap_mode="r")
    completed = np.load(embedding_dir / "completed.npy", mmap_mode="r")
    if len(manifest) != len(index) or vectors.shape[0] != len(manifest):
        raise RuntimeError(f"Embedding row-count mismatch: {embedding_dir}")
    if completed.shape != (len(manifest),) or not np.asarray(completed, dtype=bool).all():
        raise RuntimeError(f"Embedding completion bitmap is incomplete: {embedding_dir}")
    for row_index, (manifest_row, index_row) in enumerate(
        zip(manifest, index, strict=True)
    ):
        if int(index_row["embedding_row"]) != row_index:
            raise RuntimeError(f"Embedding index mismatch at row {row_index}")
        for field in ("protein_id", "sequence_sha256", "split"):
            if manifest_row[field] != index_row[field]:
                raise RuntimeError(
                    f"Embedding {field} mismatch at row {row_index}: {embedding_dir}"
                )
    if str(vectors.dtype) != str(metadata["dtype"]):
        raise RuntimeError(f"Embedding dtype mismatch: {embedding_dir}")
    if vectors.shape[1] != int(metadata["embedding_dimension"]):
        raise RuntimeError(f"Embedding dimension mismatch: {embedding_dir}")
    return manifest, vectors, metadata, verified


def _check_representation(
    original: dict[str, Any], member: dict[str, Any], model_id: str
) -> None:
    differences = {
        key: (original.get(key), member.get(key))
        for key in REPRESENTATION_KEYS
        if original.get(key) != member.get(key)
    }
    if differences:
        raise RuntimeError(f"Representation mismatch for {model_id}: {differences}")


def _decision_scores(estimator: Any, x: np.ndarray) -> np.ndarray:
    logits = np.asarray(estimator.decision_function(x), dtype=np.float64)
    if logits.ndim == 1:
        return logits
    if logits.ndim == 2 and logits.shape[1] == 2:
        return logits[:, 1] - logits[:, 0]
    raise RuntimeError(f"Expected binary decision scores, observed shape {logits.shape}")


def _probabilities(estimator: Any, x: np.ndarray, temperature: float) -> np.ndarray:
    logits = np.asarray(estimator.decision_function(x), dtype=np.float64)
    if logits.ndim == 1:
        scaled = np.clip(logits / temperature, -60.0, 60.0)
        positive = 1.0 / (1.0 + np.exp(-scaled))
        return np.column_stack([1.0 - positive, positive])
    scaled = logits / temperature
    scaled -= scaled.max(axis=1, keepdims=True)
    exponent = np.exp(scaled)
    return exponent / exponent.sum(axis=1, keepdims=True)


def _load_bundles(
    spec: ModelSpec, manifest_sha: str, embedding_metadata_sha: str
) -> dict[str, Any]:
    calibration_path = spec.result_dir / "calibration.json"
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    if calibration.get("manifest_sha256") != manifest_sha:
        raise RuntimeError(f"Calibration manifest mismatch for {spec.model_id}")
    if calibration.get("embedding_metadata_sha256") != embedding_metadata_sha:
        raise RuntimeError(f"Calibration embedding mismatch for {spec.model_id}")
    bundles: dict[str, Any] = {}
    for head in HEADS:
        head_calibration = calibration["heads"][head]
        model_path = spec.result_dir / "models" / f"{head}.joblib"
        if sha256(model_path) != head_calibration["model_sha256"]:
            raise RuntimeError(f"Frozen model checksum mismatch: {model_path}")
        bundle = joblib.load(model_path)
        expected_classes = (
            ["non_djr", "djr"]
            if head == "head1"
            else ["none", "viral_morphogenesis_associated"]
        )
        if bundle.get("head") != head or bundle.get("classes") != expected_classes:
            raise RuntimeError(f"Unexpected bundle schema: {model_path}")
        if (
            bundle.get("manifest_sha256") != manifest_sha
            or bundle.get("embedding_metadata_sha256") != embedding_metadata_sha
            or float(bundle["temperature"]) != float(head_calibration["temperature"])
            or float(bundle["decision_threshold"])
            != float(head_calibration["decision_threshold"])
        ):
            raise RuntimeError(f"Frozen bundle lineage mismatch: {model_path}")
        bundles[head] = bundle
    return {"calibration": calibration, "bundles": bundles}


def component_mean_bootstrap(
    representative_by_component: dict[str, float],
    member_by_component: dict[str, float],
    replicates: int,
    seed: int,
) -> tuple[float, float, np.ndarray, np.ndarray, np.ndarray]:
    """Paired component bootstrap used by the H1/H2 sensitivity audit."""

    components = sorted(
        set(representative_by_component) & set(member_by_component)
    )
    if not components:
        raise RuntimeError("No components for family-member sensitivity summary")
    representative = np.asarray(
        [representative_by_component[value] for value in components], dtype=np.float64
    )
    member = np.asarray(
        [member_by_component[value] for value in components], dtype=np.float64
    )
    rng = np.random.default_rng(seed)
    representative_bootstrap = np.empty(replicates, dtype=np.float64)
    member_bootstrap = np.empty(replicates, dtype=np.float64)
    for index in range(replicates):
        selected = rng.integers(0, len(components), size=len(components))
        representative_bootstrap[index] = float(representative[selected].mean())
        member_bootstrap[index] = float(member[selected].mean())
    return (
        float(representative.mean()),
        float(member.mean()),
        representative_bootstrap,
        member_bootstrap,
        member_bootstrap - representative_bootstrap,
    )


def load_frozen_model_predictions(
    config: dict[str, Any], model_id: str, family_rows: list[dict[str, str]]
) -> dict[str, Any]:
    """Run inference with fixed artifacts; this function cannot change model state."""

    if (
        config.get("selection_feedback_permitted") is not False
        or config.get("model_state") != "frozen"
        or config.get("evaluation_role") != "auxiliary_post_freeze_support"
    ):
        raise RuntimeError("Auxiliary frozen-model boundary is not enabled")
    benchmark_config, selection = load_frozen_benchmark_selection(
        Path(config["benchmark_config"]),
        Path(config["comparison_summary"]),
        verify_artifacts=True,
    )
    if (
        selection.get("selected_model_id") != config.get("frozen_primary_model_id")
        or selection.get("baseline_model_id") != config.get("fixed_reference_model_id")
    ):
        raise RuntimeError("Frozen benchmark receipt does not match the auxiliary model roles")
    model_config = expand_benchmark_model(benchmark_config, model_id)
    spec = ModelSpec(
        model_id=model_id,
        label=selection["models"][model_id]["label"],
        original_embedding=Path(model_config["paths"]["embedding_output"]),
        member_embedding=Path(config["member_embeddings"][model_id]),
        result_dir=Path(model_config["paths"]["result_output"]),
    )
    master_path = Path(config["master_manifest"])
    viral_manifest_path = (
        Path(config["source_family_dir"]) / "validation_source_entities.tsv"
    )
    graph_manifest_path = Path(config["graph_family_trace"])
    original_manifest, original_vectors, original_metadata, original_artifacts = (
        _load_embedding(master_path, spec.original_embedding)
    )
    shard_specs = (
        (
            "viral_source_family",
            viral_manifest_path,
            spec.member_embedding,
            {"viral_vma_djr"},
        ),
        (
            "validation_graph_family",
            graph_manifest_path,
            Path(config["graph_member_embeddings"][model_id]),
            {"cellular_djr_none", "background_non_djr"},
        ),
    )
    shard_payloads: dict[str, dict[str, Any]] = {}
    member_location: dict[str, tuple[np.ndarray, int, str]] = {}
    for shard_id, manifest_path, embedding_dir, expected_sources in shard_specs:
        shard_manifest, shard_vectors, shard_metadata, shard_artifacts = _load_embedding(
            manifest_path, embedding_dir
        )
        _check_representation(original_metadata, shard_metadata, model_id)
        observed_sources = {row["source_dataset"] for row in shard_manifest}
        if observed_sources != expected_sources:
            raise RuntimeError(
                f"Unexpected sources in {shard_id} for {model_id}: {observed_sources}"
            )
        for index, row in enumerate(shard_manifest):
            protein_id = row["protein_id"]
            if protein_id in member_location:
                raise RuntimeError(
                    f"Member ID occurs in multiple embedding shards: {protein_id}"
                )
            member_location[protein_id] = (shard_vectors, index, shard_id)
        shard_payloads[shard_id] = {
            "manifest_path": manifest_path,
            "embedding_dir": embedding_dir,
            "manifest": shard_manifest,
            "metadata": shard_metadata,
            "artifacts": shard_artifacts,
        }
    member_artifacts = shard_payloads["viral_source_family"]["artifacts"]
    original_index = {
        row["protein_id"]: index for index, row in enumerate(original_manifest)
    }
    family_ids = [row["protein_id"] for row in family_rows]
    if len(set(family_ids)) != len(family_ids):
        raise RuntimeError("Family manifest has duplicate protein IDs")
    representative_ids = sorted({row["paired_representative_id"] for row in family_rows})
    if not set(family_ids) <= set(member_location):
        raise RuntimeError(f"Family IDs are absent from member embeddings: {model_id}")
    for row in family_rows:
        expected_shard = (
            "viral_source_family"
            if row["source_dataset"] == "viral_vma_djr"
            else "validation_graph_family"
        )
        if member_location[row["protein_id"]][2] != expected_shard:
            raise RuntimeError(
                f"Family source/shard mismatch for {row['protein_id']}: {model_id}"
            )
    if not set(representative_ids) <= set(original_index):
        raise RuntimeError(f"Validation parent IDs are absent from base embeddings: {model_id}")
    representative_x = np.asarray(
        original_vectors[[original_index[value] for value in representative_ids]],
        dtype=np.float32,
    )
    member_x = np.stack(
        [
            np.asarray(member_location[value][0][member_location[value][1]], dtype=np.float32)
            for value in family_ids
        ]
    )
    manifest_sha = sha256(master_path)
    original_metadata_sha = sha256(spec.original_embedding / "metadata.json")
    loaded = _load_bundles(spec, manifest_sha, original_metadata_sha)

    probability: dict[str, dict[str, float]] = defaultdict(dict)
    raw_score: dict[str, dict[str, float]] = defaultdict(dict)
    thresholds: dict[str, float] = {}
    temperatures: dict[str, float] = {}
    for head in HEADS:
        bundle = loaded["bundles"][head]
        temperature = float(bundle["temperature"])
        threshold = float(bundle["decision_threshold"])
        representative_probability = _probabilities(
            bundle["estimator"], representative_x, temperature
        )[:, 1]
        member_probability = _probabilities(bundle["estimator"], member_x, temperature)[:, 1]
        representative_raw = _decision_scores(bundle["estimator"], representative_x)
        member_raw = _decision_scores(bundle["estimator"], member_x)
        probability[head].update(
            zip(representative_ids, representative_probability, strict=True)
        )
        probability[head].update(zip(family_ids, member_probability, strict=True))
        raw_score[head].update(zip(representative_ids, representative_raw, strict=True))
        raw_score[head].update(zip(family_ids, member_raw, strict=True))
        thresholds[head] = threshold
        temperatures[head] = temperature

    calibration_path = spec.result_dir / "calibration.json"
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    h3_calibration = calibration["heads"]["head3_phylum"]
    h3_path = spec.result_dir / "models/head3_phylum.joblib"
    if sha256(h3_path) != h3_calibration["model_sha256"]:
        raise RuntimeError(f"Frozen H3 model checksum mismatch: {h3_path}")
    h3_bundle = joblib.load(h3_path)
    if (
        h3_bundle.get("head") != "head3_phylum"
        or h3_bundle.get("classes") != list(KNOWN_H3_CLASSES)
    ):
        raise RuntimeError(f"Unexpected H3 classes for {model_id}")
    if (
        h3_bundle.get("manifest_sha256") != manifest_sha
        or h3_bundle.get("embedding_metadata_sha256") != original_metadata_sha
        or float(h3_bundle["temperature"])
        != float(h3_calibration["temperature"])
        or float(h3_bundle["decision_threshold"])
        != float(h3_calibration["decision_threshold"])
    ):
        raise RuntimeError(f"Frozen H3 bundle lineage mismatch for {model_id}")
    h3_temperature = float(h3_bundle["temperature"])
    h3_threshold = float(h3_bundle["decision_threshold"])
    representative_h3 = _probabilities(
        h3_bundle["estimator"], representative_x, h3_temperature
    )
    member_h3 = _probabilities(h3_bundle["estimator"], member_x, h3_temperature)
    h3_probability = {
        **{
            record_id: values
            for record_id, values in zip(
                representative_ids, representative_h3, strict=True
            )
        },
        **{
            record_id: values
            for record_id, values in zip(family_ids, member_h3, strict=True)
        },
    }
    return {
        "label": spec.label,
        "probability": probability,
        "raw_score": raw_score,
        "thresholds": thresholds,
        "temperatures": temperatures,
        "h3_probability": h3_probability,
        "h3_threshold": h3_threshold,
        "h3_temperature": h3_temperature,
        "provenance": {
            "model_id": model_id,
            "model_label": spec.label,
            "inference_only": True,
            "selection_feedback_permitted": False,
            "frozen_all_split_embedding_artifact_integrity_verified": True,
            "test_vectors_selected_for_inference": 0,
            "test_predictions_or_metrics_computed": 0,
            "original_embedding_dir": str(spec.original_embedding),
            "original_embedding_checksums_sha256": sha256(
                spec.original_embedding / "CHECKSUMS.sha256"
            ),
            "original_embedding_artifacts": original_artifacts,
            "member_embedding_dir": str(spec.member_embedding),
            "member_embedding_manifest": str(viral_manifest_path),
            "member_embedding_manifest_sha256": sha256(viral_manifest_path),
            "member_embedding_validation_parent_records": sum(
                len(payload["manifest"]) for payload in shard_payloads.values()
            ),
            "member_embedding_family_records_indexed": len(family_rows),
            "member_embedding_checksums_sha256": sha256(
                spec.member_embedding / "CHECKSUMS.sha256"
            ),
            "member_embedding_artifacts": member_artifacts,
            "member_embedding_shards": {
                shard_id: {
                    "embedding_dir": str(payload["embedding_dir"]),
                    "manifest": str(payload["manifest_path"]),
                    "manifest_sha256": sha256(payload["manifest_path"]),
                    "manifest_records": len(payload["manifest"]),
                    "checksums_sha256": sha256(
                        payload["embedding_dir"] / "CHECKSUMS.sha256"
                    ),
                    "artifacts": payload["artifacts"],
                }
                for shard_id, payload in sorted(shard_payloads.items())
            },
            "result_dir": str(spec.result_dir),
            "calibration_sha256": sha256(calibration_path),
            "model_sha256": {
                head: sha256(spec.result_dir / f"models/{head}.joblib")
                for head in (*HEADS, "head3_phylum")
            },
            "thresholds": {**thresholds, "head3_phylum": h3_threshold},
            "temperatures": {**temperatures, "head3_phylum": h3_temperature},
        },
    }


def load_frozen_h1_challenge_predictions(
    config: dict[str, Any],
    model_id: str,
    manifest_path: Path,
    embedding_dir: Path,
) -> dict[str, Any]:
    """Infer H1 for an unpaired challenge with the unchanged frozen classifier."""

    if (
        config.get("selection_feedback_permitted") is not False
        or config.get("model_state") != "frozen"
        or config.get("evaluation_role") != "auxiliary_post_freeze_support"
    ):
        raise RuntimeError("Auxiliary frozen-model boundary is not enabled")
    benchmark_config, selection = load_frozen_benchmark_selection(
        Path(config["benchmark_config"]),
        Path(config["comparison_summary"]),
        verify_artifacts=True,
    )
    if (
        selection.get("selected_model_id") != config.get("frozen_primary_model_id")
        or selection.get("baseline_model_id") != config.get("fixed_reference_model_id")
    ):
        raise RuntimeError("Frozen benchmark receipt does not match the auxiliary model roles")
    model_config = expand_benchmark_model(benchmark_config, model_id)
    original_embedding = Path(model_config["paths"]["embedding_output"])
    result_dir = Path(model_config["paths"]["result_output"])
    master_path = Path(config["master_manifest"])
    _original_manifest, _original_vectors, original_metadata, original_artifacts = (
        _load_embedding(master_path, original_embedding)
    )
    challenge_manifest, challenge_vectors, challenge_metadata, challenge_artifacts = (
        _load_embedding(manifest_path, embedding_dir)
    )
    _check_representation(original_metadata, challenge_metadata, model_id)
    manifest_ids = [row["protein_id"] for row in challenge_manifest]
    if len(set(manifest_ids)) != len(manifest_ids):
        raise RuntimeError("Duplicate protein IDs in hard-negative challenge manifest")
    manifest_sha = sha256(master_path)
    original_metadata_sha = sha256(original_embedding / "metadata.json")
    spec = ModelSpec(
        model_id=model_id,
        label=selection["models"][model_id]["label"],
        original_embedding=original_embedding,
        member_embedding=embedding_dir,
        result_dir=result_dir,
    )
    loaded = _load_bundles(spec, manifest_sha, original_metadata_sha)
    bundle = loaded["bundles"]["head1"]
    temperature = float(bundle["temperature"])
    threshold = float(bundle["decision_threshold"])
    vectors = np.asarray(challenge_vectors, dtype=np.float32)
    probabilities = _probabilities(bundle["estimator"], vectors, temperature)[:, 1]
    raw_scores = _decision_scores(bundle["estimator"], vectors)
    return {
        "label": spec.label,
        "probability": dict(zip(manifest_ids, probabilities, strict=True)),
        "raw_score": dict(zip(manifest_ids, raw_scores, strict=True)),
        "threshold": threshold,
        "temperature": temperature,
        "provenance": {
            "model_id": model_id,
            "inference_only": True,
            "selection_feedback_permitted": False,
            "frozen_all_split_embedding_artifact_integrity_verified": True,
            "test_vectors_selected_for_inference": 0,
            "test_predictions_or_metrics_computed": 0,
            "manifest": str(manifest_path),
            "manifest_sha256": sha256(manifest_path),
            "manifest_records": len(challenge_manifest),
            "embedding_dir": str(embedding_dir),
            "embedding_checksums_sha256": sha256(
                embedding_dir / "CHECKSUMS.sha256"
            ),
            "embedding_artifacts": challenge_artifacts,
            "original_embedding_artifacts": original_artifacts,
            "h1_model_sha256": sha256(result_dir / "models/head1.joblib"),
            "h1_threshold": threshold,
            "h1_temperature": temperature,
        },
    }
