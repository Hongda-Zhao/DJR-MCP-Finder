"""Command-line interface for frozen DJR-MCP Finder user inference."""

from __future__ import annotations

import argparse
import json
import platform
import shlex
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Sequence

import numpy as np

from . import __version__
from .embedder import EsmcEmbedder
from .fasta import read_protein_fasta
from .output import write_run
from .predictor import Predictor
from .release import load_release, sha256_file


DEFAULT_RELEASE = (
    Path(__file__).resolve().parent / "assets" / "project-v0-esmc6b-r1"
)


def _add_release(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--release",
        type=Path,
        default=DEFAULT_RELEASE,
        help="Checksum-bearing frozen model release directory",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="djrmcp-predict",
        description="Predict DJR-MCP project-V0 outputs for a user protein FASTA",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    predict = subparsers.add_parser("predict", help="Run frozen ESM-C 6B inference")
    predict.add_argument("fasta", type=Path)
    predict.add_argument("--outdir", type=Path, required=True)
    predict.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    predict.add_argument("--cache-dir", type=Path, default=None)
    predict.add_argument(
        "--offline",
        action="store_true",
        help="Require the pinned ESM-C checkpoint to exist in the local cache",
    )
    predict.add_argument(
        "--overwrite",
        action="store_true",
        help="Atomically replace the three standard output files if they exist",
    )
    _add_release(predict)

    validate = subparsers.add_parser(
        "validate-fasta", help="Validate a protein FASTA without loading ESM-C"
    )
    validate.add_argument("fasta", type=Path)

    model_info = subparsers.add_parser(
        "model-info", help="Verify and display the frozen model release"
    )
    _add_release(model_info)
    return parser


def _release_summary(release: object) -> dict[str, object]:
    bundle = release
    return {
        "release_id": bundle.release_id,
        "release_json_sha256": bundle.release_json_sha256,
        "embedding": bundle.embedding,
        "heads": {
            name: {
                "classes": list(head.classes),
                "temperature": head.temperature,
                "threshold": head.threshold,
                "artifact_sha256": head.artifact_sha256,
            }
            for name, head in bundle.heads.items()
        },
        "limitations": bundle.metadata.get("limitations", []),
    }


def _validate_command(path: Path) -> int:
    records = read_protein_fasta(path)
    warning_counts = Counter(warning for record in records for warning in record.warnings)
    print(
        json.dumps(
            {
                "status": "valid",
                "fasta": str(path.resolve()),
                "fasta_sha256": sha256_file(path),
                "record_count": len(records),
                "exact_unique_sequence_count": len(
                    {record.sequence_sha256 for record in records}
                ),
                "total_residues": sum(record.length_aa for record in records),
                "warnings": dict(sorted(warning_counts.items())),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _predict_command(args: argparse.Namespace) -> int:
    started_wall = time.perf_counter()
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    records = read_protein_fasta(args.fasta)
    release = load_release(args.release)
    embedder = EsmcEmbedder(
        release.embedding,
        device=args.device,
        cache_dir=args.cache_dir,
        local_files_only=args.offline,
    )
    predictions = Predictor(release).predict_records(records, embedder)
    completed_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    warning_counts = Counter(warning for record in records for warning in record.warnings)
    final_counts = Counter(row["final_prediction"] for row in predictions)
    runtime = embedder.runtime_metadata()
    metadata = {
        "schema_version": 1,
        "status": "complete",
        "started_utc": started_utc,
        "completed_utc": completed_utc,
        "elapsed_seconds": time.perf_counter() - started_wall,
        "software": {
            "package": "djrmcp-user-inference",
            "version": __version__,
            "python": ".".join(str(part) for part in sys.version_info[:3]),
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
        "command": shlex.join(sys.argv),
        "input": {
            "path": str(args.fasta.resolve()),
            "sha256": sha256_file(args.fasta),
            "record_count": len(records),
            "exact_unique_sequence_count": len(
                {record.sequence_sha256 for record in records}
            ),
            "total_residues": sum(record.length_aa for record in records),
            "warning_counts": dict(sorted(warning_counts.items())),
        },
        "release": _release_summary(release),
        "runtime": runtime,
        "final_prediction_counts": dict(sorted(final_counts.items())),
        "interpretation": {
            "probability_note": (
                "Values are frozen calibrated model scores under the development-data "
                "distribution, not prevalence-adjusted posterior probabilities."
            ),
            "unknown_note": (
                "vma::unknown/other means rejection from the two known H3 phyla after "
                "passing H1 and H2; it is not a general unknown-virus detector."
            ),
        },
    }
    paths = write_run(args.outdir, predictions, metadata, overwrite=args.overwrite)
    print(
        json.dumps(
            {
                "status": "complete",
                "record_count": len(records),
                "final_prediction_counts": dict(sorted(final_counts.items())),
                "predictions": str(paths["predictions"].resolve()),
                "metadata": str(paths["metadata"].resolve()),
                "checksums": str(paths["checksums"].resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-fasta":
            return _validate_command(args.fasta)
        if args.command == "model-info":
            print(json.dumps(_release_summary(load_release(args.release)), indent=2, sort_keys=True))
            return 0
        if args.command == "predict":
            return _predict_command(args)
    except (FileNotFoundError, FileExistsError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
