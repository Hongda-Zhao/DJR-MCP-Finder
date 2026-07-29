"""Isolated ESM-2 and ESM-C workers for sequential mixed inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .embedder import FrozenTransformerEmbedder
from .fasta import ProteinRecord, read_protein_fasta
from .predictor import Predictor
from .release import load_release, sha256_file


H12_FILES = ("h12.json", "h3_subset.faa", "h3_subset.json", "h12_runtime.json")
H3_FILES = ("h3.json", "h3_runtime.json")


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, payload: Any) -> None:
    _atomic_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def subset_identity_sha256(entries: Sequence[dict[str, Any]]) -> str:
    identity = [
        {
            "subset_row": int(entry["subset_row"]),
            "sequence_sha256": str(entry["sequence_sha256"]),
            "length_aa": int(entry["length_aa"]),
        }
        for entry in entries
    ]
    canonical = json.dumps(identity, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_checksum_receipt(stage: Path, worker: str, names: Sequence[str]) -> Path:
    lines: list[str] = []
    for name in names:
        path = stage / name
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"Worker output is missing or unsafe: {path}")
        lines.append(f"{sha256_file(path)}  {name}\n")
    receipt = stage / f"{worker}.CHECKSUMS.sha256"
    _atomic_text(receipt, "".join(lines))
    return receipt


def verify_checksum_receipt(stage: Path, worker: str, expected: Sequence[str]) -> None:
    """Verify exact stage outputs before the controller trusts any worker JSON."""

    root = stage.resolve()
    receipt = stage / f"{worker}.CHECKSUMS.sha256"
    if not receipt.is_file() or receipt.is_symlink():
        raise RuntimeError(f"Missing worker checksum receipt: {receipt}")
    observed: list[str] = []
    for line_number, line in enumerate(receipt.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError(f"Malformed {worker} receipt line {line_number}")
        digest, name = parts[0].lower(), parts[1].lstrip(" *")
        if len(digest) != 64 or any(value not in "0123456789abcdef" for value in digest):
            raise RuntimeError(f"Invalid checksum in {worker} receipt line {line_number}")
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"Unsafe path in {worker} receipt: {name}")
        candidate = stage / relative
        if candidate.is_symlink():
            raise RuntimeError(f"Unsafe symbolic link in {worker} receipt: {candidate}")
        path = candidate.resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise RuntimeError(f"Unsafe worker artifact: {path}")
        if sha256_file(path) != digest:
            raise RuntimeError(f"Worker checksum mismatch for {name}")
        if name in observed:
            raise RuntimeError(f"Duplicate worker checksum entry: {name}")
        observed.append(name)
    if observed != list(expected):
        raise RuntimeError(
            f"{worker} receipt file set/order differs: expected={list(expected)}, "
            f"observed={observed}"
        )


def _write_subset_fasta(path: Path, entries: Sequence[dict[str, Any]]) -> None:
    lines: list[str] = []
    for entry in entries:
        lines.append(
            f">h3_{int(entry['subset_row']):06d} "
            f"source={entry['representative_protein_id']} "
            f"sha256={entry['sequence_sha256']}\n"
        )
        sequence = str(entry["sequence"])
        lines.extend(sequence[start : start + 80] + "\n" for start in range(0, len(sequence), 80))
    _atomic_text(path, "".join(lines))


def run_h12(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    records = read_protein_fasta(args.fasta)
    release = load_release(args.release)
    embedder = FrozenTransformerEmbedder(
        release.encoders["esm2_3b"],
        device=args.device,
        cache_dir=args.cache_dir,
        local_files_only=args.offline,
    )
    predictor = Predictor(release)
    rows, counts = predictor.embed_h12_records(records, embedder)

    by_hash: OrderedDict[str, ProteinRecord] = OrderedDict()
    routed = {str(row["sequence_sha256"]) for row in rows if row["head3_reached"]}
    for record in records:
        if record.sequence_sha256 in routed:
            by_hash.setdefault(record.sequence_sha256, record)
    subset: list[dict[str, Any]] = []
    for index, record in enumerate(by_hash.values(), 1):
        subset.append(
            {
                "subset_row": index,
                "representative_protein_id": record.protein_id,
                "sequence_sha256": record.sequence_sha256,
                "length_aa": record.length_aa,
                "sequence": record.sequence,
            }
        )
    subset_public = [
        {key: value for key, value in entry.items() if key != "sequence"} for entry in subset
    ]
    identity_sha = subset_identity_sha256(subset_public)
    _atomic_json(
        args.stage / "h12.json",
        {
            "schema_version": 1,
            "worker": "h12",
            "package_version": __version__,
            "release_json_sha256": release.release_json_sha256,
            "rows": rows,
        },
    )
    _write_subset_fasta(args.stage / "h3_subset.faa", subset)
    _atomic_json(
        args.stage / "h3_subset.json",
        {
            "schema_version": 1,
            "ordered_identity_sha256": identity_sha,
            "exact_unique_sequence_count": len(subset_public),
            "entries": subset_public,
        },
    )
    _atomic_json(
        args.stage / "h12_runtime.json",
        {
            "schema_version": 1,
            "worker": "h12",
            "package_version": __version__,
            "encoder_id": "esm2_3b",
            "release_json_sha256": release.release_json_sha256,
            "elapsed_seconds": time.perf_counter() - started,
            "input_record_count": counts["input_record_count"],
            "embedded_unique_sequence_count": counts["embedded_unique_sequence_count"],
            "h1_positive_count": sum(
                row["head1_prediction"] == release.heads["head1"].classes[1]
                for row in rows
            ),
            "h3_routed_record_count": sum(bool(row["head3_reached"]) for row in rows),
            "h3_routed_unique_sequence_count": len(subset_public),
            "h3_subset_identity_sha256": identity_sha,
            "encoder_runtime": embedder.runtime_metadata(),
        },
    )
    write_checksum_receipt(args.stage, "h12", H12_FILES)
    return 0


def run_h3(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    verify_checksum_receipt(args.stage, "h12", H12_FILES)
    release = load_release(args.release)
    subset_payload = json.loads((args.stage / "h3_subset.json").read_text(encoding="utf-8"))
    entries = subset_payload.get("entries", [])
    if not entries:
        raise RuntimeError("H3 worker was invoked with an empty routed subset")
    if subset_identity_sha256(entries) != subset_payload.get("ordered_identity_sha256"):
        raise RuntimeError("H3 subset identity digest differs")
    records = read_protein_fasta(args.stage / "h3_subset.faa")
    observed = [record.sequence_sha256 for record in records]
    expected = [str(entry["sequence_sha256"]) for entry in entries]
    if observed != expected:
        raise RuntimeError(
            f"H3 subset FASTA identities differ: expected={expected}, observed={observed}"
        )
    embedder = FrozenTransformerEmbedder(
        release.encoders["esmc_6b"],
        device=args.device,
        cache_dir=args.cache_dir,
        local_files_only=args.offline,
    )
    embeddings = embedder.embed_sequences([record.sequence for record in records])
    rows = Predictor(release).predict_h3(expected, embeddings)
    _atomic_json(
        args.stage / "h3.json",
        {
            "schema_version": 1,
            "worker": "h3",
            "package_version": __version__,
            "release_json_sha256": release.release_json_sha256,
            "h3_subset_identity_sha256": subset_payload["ordered_identity_sha256"],
            "rows": rows,
        },
    )
    _atomic_json(
        args.stage / "h3_runtime.json",
        {
            "schema_version": 1,
            "worker": "h3",
            "package_version": __version__,
            "encoder_id": "esmc_6b",
            "release_json_sha256": release.release_json_sha256,
            "elapsed_seconds": time.perf_counter() - started,
            "embedded_unique_sequence_count": len(records),
            "h3_subset_identity_sha256": subset_payload["ordered_identity_sha256"],
            "encoder_runtime": embedder.runtime_metadata(),
        },
    )
    write_checksum_receipt(args.stage, "h3", H3_FILES)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m djrmcp_predict_v01.worker")
    parser.add_argument("worker", choices=("h12", "h3"))
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--fasta", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.stage = args.stage.resolve()
        args.stage.mkdir(parents=True, exist_ok=True)
        if args.worker == "h12":
            if args.fasta is None:
                raise ValueError("The H12 worker requires --fasta")
            return run_h12(args)
        return run_h3(args)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
