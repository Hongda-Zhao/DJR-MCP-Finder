#!/usr/bin/env python3
"""Create six fail-closed reuse attestations for the frozen 650M/6B embeddings.

This step performs no embedding, prediction, calibration, training, or scoring.
It only proves that the three frozen input shards for each reused encoder still
match their checksum manifests and the schema-5 input identities.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REUSED_MODELS = ("esm2_650m", "esmc_6b")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_checksum_manifest(directory: Path) -> str:
    manifest = directory / "CHECKSUMS.sha256"
    if not directory.is_dir() or not manifest.is_file():
        raise FileNotFoundError(f"Missing frozen embedding bundle: {directory}")
    seen: set[str] = set()
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        expected, relative = raw.split(maxsplit=1)
        relative = relative.lstrip("* ")
        item = Path(relative)
        if item.is_absolute() or ".." in item.parts or relative in seen:
            raise RuntimeError(f"Unsafe or duplicate checksum entry: {raw}")
        target = directory / item
        if not target.is_file() or sha256(target) != expected:
            raise RuntimeError(f"Frozen embedding checksum mismatch: {target}")
        seen.add(relative)
    required = {"completed.npy", "embeddings.float16.npy", "index.tsv", "metadata.json"}
    if not required.issubset(seen):
        raise RuntimeError(f"Incomplete checksum manifest in {directory}: {sorted(seen)}")
    return sha256(manifest)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    output_dir = Path(config["reuse_attestation_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    if list(output_dir.iterdir()):
        raise RuntimeError(f"Refusing to reuse non-empty attestation directory: {output_dir}")

    rows: list[tuple[Path, dict[str, Any]]] = []
    attested_utc = datetime.now(timezone.utc).isoformat()
    for shard_id, input_spec in config["inputs"].items():
        expected_records = int(input_spec["expected_records"])
        for model_id in REUSED_MODELS:
            embedding_dir = Path(config["embedding_registries"][shard_id][model_id])
            checksums_sha = verify_checksum_manifest(embedding_dir)
            metadata_path = embedding_dir / "metadata.json"
            metadata = load_json(metadata_path)
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
                "manifest_sha256": input_spec["manifest_sha256"],
                "fasta_sha256": input_spec["fasta_sha256"],
            }
            if observed != expected:
                raise RuntimeError(
                    f"Frozen embedding identity mismatch for {model_id}/{shard_id}: "
                    f"observed={observed}, expected={expected}"
                )
            index_records = sum(
                1 for _ in (embedding_dir / "index.tsv").open(encoding="utf-8")
            ) - 1
            if index_records != expected_records:
                raise RuntimeError(
                    f"Frozen embedding index count mismatch for {model_id}/{shard_id}: "
                    f"{index_records} != {expected_records}"
                )
            destination = output_dir / f"{shard_id}_{model_id}.json"
            rows.append(
                (
                    destination,
                    {
                        "schema_version": 1,
                        "analysis_id": config["analysis_id"],
                        "attestation_kind": "reuse",
                        "status": "reused_checksum_attested",
                        "model_id": model_id,
                        "shard_id": shard_id,
                        "records": expected_records,
                        "embedded_records": expected_records,
                        "test_records_embedded": 0,
                        "prediction_or_metric_records_created": 0,
                        "training_operations": 0,
                        "calibration_operations": 0,
                        "manifest_sha256": input_spec["manifest_sha256"],
                        "fasta_sha256": input_spec["fasta_sha256"],
                        "embedding_output": str(embedding_dir),
                        "embedding_checksums_sha256": checksums_sha,
                        "embedding_metadata_sha256": sha256(metadata_path),
                        "resolved_model_revision": metadata.get("resolved_model_revision"),
                        "source_completed_utc": metadata.get("completed_utc"),
                        "attested_utc": attested_utc,
                        "schema4_result_checksums_sha256": config[
                            "schema4_result_checksums_sha256"
                        ],
                        "schema4_validation_sha256": config["schema4_validation_sha256"],
                    },
                )
            )

    if len(rows) != 6 or len({path.name for path, _ in rows}) != 6:
        raise RuntimeError("Reuse attestation matrix is not exactly 2 models x 3 shards")

    created: list[Path] = []
    try:
        for destination, payload in rows:
            temporary = destination.with_name(f".{destination.name}.tmp.{os.getpid()}")
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

    print(f"reuse_attestations=6 Test=0 output={output_dir}")


if __name__ == "__main__":
    main()
