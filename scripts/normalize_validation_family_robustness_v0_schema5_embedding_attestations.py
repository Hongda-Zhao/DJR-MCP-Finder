#!/usr/bin/env python3
"""Normalize 18 materialization receipts and six reuse attestations.

Raw workstation receipts remain immutable and retain their original ``/lab``
paths.  The normalized records bind those receipts to byte-identical bundles
under the schema-5 ``/aptmp`` registry without pretending that the raw receipt
was created at the destination.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

import yaml

from attest_validation_family_robustness_v0_schema5_reuse import (
    REUSED_MODELS,
    load_json,
    sha256,
    verify_checksum_manifest,
)


def first(payload: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return default


def exact_jsons(directory: Path, expected: int) -> list[Path]:
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    paths = sorted(directory.glob("*.json"))
    if len(paths) != expected or any(path.name.startswith(".") for path in paths):
        raise RuntimeError(f"Expected exactly {expected} JSON records in {directory}")
    return paths


def validate_destination_bundle(
    config: Mapping[str, Any], model_id: str, shard_id: str
) -> tuple[Path, str, dict[str, Any]]:
    spec = config["inputs"][shard_id]
    expected_records = int(spec["expected_records"])
    destination = Path(config["embedding_registries"][shard_id][model_id])
    checksums_sha = verify_checksum_manifest(destination)
    metadata = load_json(destination / "metadata.json")
    observed = {
        "model_id": metadata.get("benchmark_model_id"),
        "status": metadata.get("status"),
        "record_count": int(metadata.get("record_count", -1)),
        "completed_records": int(metadata.get("completed_records", -1)),
        "manifest_sha256": metadata.get("manifest_sha256"),
        "fasta_sha256": metadata.get("fasta_sha256"),
    }
    expected = {
        "model_id": model_id,
        "status": "complete",
        "record_count": expected_records,
        "completed_records": expected_records,
        "manifest_sha256": spec["manifest_sha256"],
        "fasta_sha256": spec["fasta_sha256"],
    }
    if observed != expected:
        raise RuntimeError(
            f"Destination bundle mismatch for {model_id}/{shard_id}: "
            f"observed={observed}, expected={expected}"
        )
    return destination, checksums_sha, metadata


def normalize_one(
    config: Mapping[str, Any], source_path: Path, kind: str
) -> tuple[str, dict[str, Any]]:
    source = load_json(source_path)
    model_id = str(source.get("model_id", ""))
    shard_id = str(source.get("shard_id", ""))
    materialized = set(config["models"]) - set(REUSED_MODELS)
    expected_models = materialized if kind == "materialization" else set(REUSED_MODELS)
    if model_id not in expected_models or shard_id not in config["inputs"]:
        raise RuntimeError(f"Unexpected {kind} identity in {source_path}")
    spec = config["inputs"][shard_id]
    expected_records = int(spec["expected_records"])
    embedded_records = int(
        first(
            source,
            "embedded_records",
            "records",
            default=source.get("embedding", {}).get("completed_records", -1),
        )
    )
    if (
        source.get("status") not in {"complete", "PASS", "reused_checksum_attested"}
        or embedded_records != expected_records
        or int(first(source, "test_records_embedded", "test_records", default=-1)) != 0
        or int(first(source, "prediction_or_metric_records_created", default=-1)) != 0
        or int(first(source, "training_operations", default=-1)) != 0
        or int(first(source, "calibration_operations", default=-1)) != 0
        or str(source.get("manifest_sha256", "")) != spec["manifest_sha256"]
        or str(source.get("fasta_sha256", "")) != spec["fasta_sha256"]
    ):
        raise RuntimeError(f"Source receipt contract mismatch: {source_path}")
    if kind == "materialization" and (
        str(first(source, "config_sha256", "materialization_config_sha256"))
        != config["embedding_materialization_config_sha256"]
        or str(first(source, "protocol_sha256", "materialization_protocol_sha256"))
        != config["embedding_materialization_protocol_sha256"]
    ):
        raise RuntimeError(f"Materialization snapshot mismatch: {source_path}")

    destination, checksums_sha, metadata = validate_destination_bundle(
        config, model_id, shard_id
    )
    source_checksums_sha = str(source.get("embedding_checksums_sha256", ""))
    if source_checksums_sha != checksums_sha:
        raise RuntimeError(
            f"Transferred bundle differs from source receipt for {model_id}/{shard_id}"
        )
    source_revision = str(
        first(
            source,
            "resolved_model_revision",
            default=source.get("embedding", {}).get("resolved_model_revision", ""),
        )
    )
    destination_revision = str(metadata.get("resolved_model_revision", ""))
    if source_revision and destination_revision and source_revision != destination_revision:
        raise RuntimeError(f"Model revision changed for {model_id}/{shard_id}")

    normalized = {
        "schema_version": 1,
        "analysis_id": config["analysis_id"],
        "attestation_kind": kind,
        "status": "complete" if kind == "materialization" else "reused_checksum_attested",
        "model_id": model_id,
        "shard_id": shard_id,
        "records": expected_records,
        "embedded_records": expected_records,
        "test_records_embedded": 0,
        "prediction_or_metric_records_created": 0,
        "training_operations": 0,
        "calibration_operations": 0,
        "manifest_sha256": spec["manifest_sha256"],
        "fasta_sha256": spec["fasta_sha256"],
        "embedding_output": str(destination),
        "embedding_checksums_sha256": checksums_sha,
        "embedding_metadata_sha256": sha256(destination / "metadata.json"),
        "resolved_model_revision": destination_revision,
        "source_receipt_or_attestation": str(source_path),
        "source_receipt_or_attestation_sha256": sha256(source_path),
        "source_embedding_output": str(source.get("embedding_output", "")),
        "source_embedding_checksums_sha256": source_checksums_sha,
        "normalization_role": "path_rebinding_only_no_numeric_recomputation",
    }
    if kind == "materialization":
        gpu_seconds = float(first(source, "gpu_seconds", default=-1))
        wall_seconds = float(first(source, "wall_seconds", default=-1))
        peak_memory = int(first(source, "peak_gpu_memory_bytes", default=-1))
        if gpu_seconds <= 0 or wall_seconds <= 0 or peak_memory <= 0:
            raise RuntimeError(f"Materialization resource evidence is incomplete: {source_path}")
        normalized["config_sha256"] = config["embedding_materialization_config_sha256"]
        normalized["protocol_sha256"] = config["embedding_materialization_protocol_sha256"]
        normalized["gpu_seconds"] = gpu_seconds
        normalized["wall_seconds"] = wall_seconds
        normalized["peak_gpu_memory_bytes"] = peak_memory
    return f"{shard_id}_{model_id}.json", normalized


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))

    materialization = exact_jsons(Path(config["materialization_receipt_dir"]), 18)
    reuse = exact_jsons(Path(config["reuse_attestation_dir"]), 6)
    output_dir = Path(config["normalized_embedding_attestation_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    if list(output_dir.iterdir()):
        raise RuntimeError(f"Refusing to reuse non-empty normalized directory: {output_dir}")

    rows = [normalize_one(config, path, "materialization") for path in materialization]
    rows.extend(normalize_one(config, path, "reuse") for path in reuse)
    identities = {
        (payload["model_id"], payload["shard_id"]) for _, payload in rows
    }
    expected = {
        (model_id, shard_id)
        for model_id in config["models"]
        for shard_id in config["inputs"]
    }
    if len(rows) != 24 or identities != expected:
        raise RuntimeError(
            f"Normalized matrix mismatch: rows={len(rows)}, "
            f"missing={sorted(expected - identities)}, extra={sorted(identities - expected)}"
        )

    created: list[Path] = []
    try:
        for name, payload in sorted(rows):
            destination = output_dir / name
            temporary = destination.with_name(f".{name}.tmp.{os.getpid()}")
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
            created.append(destination)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise

    print(f"normalized_embedding_attestations=24 Test=0 output={output_dir}")


if __name__ == "__main__":
    main()
