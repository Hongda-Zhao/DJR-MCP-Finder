#!/usr/bin/env python3
"""Embed only legal matched-HardNeg Validation members for schema 4."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import yaml

from djrmcp_finder.benchmark_config import expand_benchmark_model
from djrmcp_finder.benchmark_selection import load_frozen_benchmark_selection
from djrmcp_finder.stages import benchmark_embedding


ANALYSIS_ID = "project_v0_validation_family_robustness_schema4"
MODELS = ("esm2_650m", "esmc_6b")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise RuntimeError(f"Missing TSV header: {path}")
        return list(reader)


def fasta_sha(path: Path) -> dict[str, tuple[str, int]]:
    records: dict[str, list[str]] = {}
    current = ""
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                current = line[1:].split(maxsplit=1)[0]
                if not current or current in records:
                    raise RuntimeError(f"Duplicate/empty FASTA ID at {path}:{line_number}")
                records[current] = []
            elif not current:
                raise RuntimeError(f"Sequence before FASTA header at {path}:{line_number}")
            else:
                records[current].append(line.upper())
    result: dict[str, tuple[str, int]] = {}
    for record_id, chunks in records.items():
        sequence = "".join(chunks)
        result[record_id] = (
            hashlib.sha256(sequence.encode("ascii")).hexdigest(),
            len(sequence),
        )
    return result


def verify_flat_bundle(directory: Path) -> dict[str, str]:
    manifest = directory / "CHECKSUMS.sha256"
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
            or sha256(target) != expected
        ):
            raise RuntimeError(f"Unsafe, missing, or mismatched checksum target: {target}")
        verified[name] = expected
    if not verified:
        raise RuntimeError(f"Empty checksum bundle: {directory}")
    return verified


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/validation_family_robustness_v0_schema4.yaml"),
    )
    parser.add_argument("--model-id", required=True, choices=MODELS)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--fasta", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    payload = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if (
        payload.get("analysis_id") != ANALYSIS_ID
        or payload.get("schema_version") != 4
        or payload.get("model_state") != "frozen"
        or payload.get("selection_feedback_permitted") is not False
        or payload.get("test_policy")
        != "no_test_vector_selection_or_performance_scoring"
    ):
        raise RuntimeError("Schema-4 frozen inference contract mismatch")
    if args.model_id not in payload.get("models", []):
        raise RuntimeError("Model is outside the frozen schema-4 comparison")

    hard = payload["hardnegative_matched"]
    manifest_path = args.manifest or Path(hard["legal_manifest"])
    fasta_path = args.fasta or Path(hard["legal_fasta"])
    legal_summary_path = (
        manifest_path.parent / "summary.json"
        if args.manifest is not None
        else Path(hard["legal_summary"])
    )
    output_dir = args.output_dir or Path(hard["member_embeddings"][args.model_id])
    verified = verify_flat_bundle(manifest_path.parent)
    for path in (manifest_path, fasta_path, legal_summary_path):
        if verified.get(path.name) != sha256(path):
            raise RuntimeError(f"Legal matched-HardNeg input is not checksum-bound: {path}")

    rows = read_tsv(manifest_path)
    sequences = fasta_sha(fasta_path)
    if not rows or len(rows) != len(sequences):
        raise RuntimeError("Legal manifest/FASTA is empty or has different row counts")
    by_id = {row["protein_id"]: row for row in rows}
    if len(by_id) != len(rows) or set(by_id) != set(sequences):
        raise RuntimeError("Legal manifest/FASTA IDs are not one-to-one")
    for protein_id, row in by_id.items():
        observed_sha, observed_length = sequences[protein_id]
        if (
            row.get("source_dataset") != "hard_non_djr"
            or row.get("parent_split") != "validation"
            or row.get("split") != "robustness_validation"
            or row.get("head1_label") != "non_djr"
            or row.get("head1_mask") != "1"
            or row.get("head2_mask") != "0"
            or row.get("head3_mask") != "0"
            or row.get("score_head1", "1") != "1"
            or row.get("score_head2", "0") != "0"
            or row.get("h3_analysis_included", "0") != "0"
            or row.get("test_record", "0") != "0"
            or row.get("analysis_included", "1") != "1"
            or not row.get("paired_representative_id")
            or not row.get("dependence_block_id")
            or row.get("sequence_sha256") != observed_sha
            or int(row.get("length_aa", -1)) != observed_length
        ):
            raise RuntimeError(f"Invalid legal matched-HardNeg row: {protein_id}")

    protocol = Path(payload["protocol"])
    if not protocol.is_file():
        raise FileNotFoundError(protocol)
    benchmark_config, selection = load_frozen_benchmark_selection(
        Path(payload["benchmark_config"]),
        Path(payload["comparison_summary"]),
        verify_artifacts=False,
    )
    if (
        selection.get("selected_model_id") != payload["frozen_primary_model_id"]
        or selection.get("baseline_model_id") != payload["fixed_reference_model_id"]
    ):
        raise RuntimeError("Frozen model-selection receipt changed")
    model_config = expand_benchmark_model(benchmark_config, args.model_id)
    revision = selection["models"][args.model_id]["resolved_model_revision"]
    model_config["embedding"]["model_revision"] = revision
    model_config["paths"]["v0_manifest"] = str(manifest_path)
    model_config["paths"]["v0_fasta"] = str(fasta_path)
    model_config["paths"]["embedding_output"] = str(output_dir)
    result = benchmark_embedding.run(
        model_config,
        device_override=args.device,
        limit=args.limit,
    )
    receipt = {
        "schema_version": 1,
        "analysis_id": ANALYSIS_ID,
        "status": "complete",
        "model_id": args.model_id,
        "resolved_model_revision": revision,
        "protocol_sha256": sha256(protocol),
        "config_sha256": sha256(args.config),
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "fasta": str(fasta_path),
        "fasta_sha256": sha256(fasta_path),
        "embedded_records": len(rows),
        "test_records_embedded": 0,
        "prediction_or_metric_records_created": 0,
        "embedding_output": str(output_dir),
        "embedding": result,
    }
    receipt_path = args.receipt or output_dir.parent / f"{args.model_id}_embedding_receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
