"""Public CLI orchestrating isolated mixed-encoder workers."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from . import __version__
from .fasta import read_protein_fasta
from .output import write_run
from .predictor import Predictor
from .release import ReleaseBundle, load_release, sha256_file
from .worker import H12_FILES, H3_FILES, verify_checksum_receipt


DEFAULT_RELEASE = (
    Path(__file__).resolve().parent / "assets" / "project-v0.1-mixed-r1"
)


def _add_release(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--release",
        type=Path,
        default=DEFAULT_RELEASE,
        help="Checksum-bearing V0.1 candidate model release directory",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="djrmcp-predict-v01",
        description=(
            "Predict the externally-unconfirmed DJR-MCP V0.1 mixed-encoder candidate "
            "for a user protein FASTA"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    predict = subparsers.add_parser("predict", help="Run H1/H2, then conditional H3")
    predict.add_argument("fasta", type=Path)
    predict.add_argument("--outdir", type=Path, required=True)
    predict.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    predict.add_argument("--cache-dir", type=Path, default=None)
    predict.add_argument(
        "--offline",
        action="store_true",
        help="Require both pinned checkpoints to exist in the local cache",
    )
    predict.add_argument(
        "--overwrite",
        action="store_true",
        help="Atomically replace the three standard output files if they exist",
    )
    predict.add_argument(
        "--esm2-python",
        type=Path,
        default=Path(os.environ.get("DJRMCP_ESM2_PYTHON", sys.executable)),
        help="Python interpreter containing frozen ESM-2 dependencies",
    )
    predict.add_argument(
        "--esmc-python",
        type=Path,
        default=Path(os.environ.get("DJRMCP_ESMC_PYTHON", sys.executable)),
        help="Python interpreter containing frozen ESM-C dependencies",
    )
    _add_release(predict)

    validate = subparsers.add_parser(
        "validate-fasta", help="Validate a protein FASTA without loading either model"
    )
    validate.add_argument("fasta", type=Path)

    model_info = subparsers.add_parser(
        "model-info", help="Verify and display the frozen candidate release"
    )
    _add_release(model_info)
    return parser


def _release_summary(release: ReleaseBundle) -> dict[str, Any]:
    return {
        "release_id": release.release_id,
        "release_status": release.release_status,
        "release_json_sha256": release.release_json_sha256,
        "released_v0_unchanged": release.metadata["released_v0_unchanged"],
        "encoders": release.encoders,
        "heads": {
            name: {
                "encoder_id": head.encoder_id,
                "classes": list(head.classes),
                "temperature": head.temperature,
                "threshold": head.threshold,
                "artifact_sha256": head.artifact_sha256,
                "source_joblib_sha256": head.source_joblib_sha256,
            }
            for name, head in release.heads.items()
        },
        "routing": release.metadata["routing"],
        "limitations": release.metadata.get("limitations", []),
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


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read verified worker JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Worker payload is not an object: {path}")
    return payload


def _run_worker(
    python: Path,
    worker: str,
    *,
    release: Path,
    stage: Path,
    device: str,
    cache_dir: Path | None,
    offline: bool,
    fasta: Path | None = None,
) -> None:
    if not python.is_file():
        raise FileNotFoundError(f"{worker} Python interpreter does not exist: {python}")
    command = [
        str(python),
        "-m",
        "djrmcp_predict_v01.worker",
        worker,
        "--release",
        str(release),
        "--stage",
        str(stage),
        "--device",
        device,
    ]
    if cache_dir is not None:
        command.extend(["--cache-dir", str(cache_dir)])
    if offline:
        command.append("--offline")
    if fasta is not None:
        command.extend(["--fasta", str(fasta)])
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{worker} worker failed with exit code {completed.returncode}")


def _validate_worker_payload(
    payload: dict[str, Any], *, worker: str, release_sha: str
) -> None:
    if payload.get("schema_version") != 1 or payload.get("worker") != worker:
        raise RuntimeError(f"Unexpected {worker} worker payload contract")
    if payload.get("package_version") != __version__:
        raise RuntimeError(f"{worker} worker package version differs from the controller")
    if payload.get("release_json_sha256") != release_sha:
        raise RuntimeError(f"{worker} worker used a different release")
    if not isinstance(payload.get("rows"), list):
        raise RuntimeError(f"{worker} worker payload lacks rows")


def _validate_runtime_payload(
    payload: dict[str, Any], *, worker: str, encoder_id: str, release_sha: str
) -> None:
    if payload.get("schema_version") != 1 or payload.get("worker") != worker:
        raise RuntimeError(f"Unexpected {worker} runtime payload contract")
    if payload.get("package_version") != __version__:
        raise RuntimeError(f"{worker} runtime package version differs from the controller")
    if payload.get("encoder_id") != encoder_id:
        raise RuntimeError(f"{worker} runtime encoder identity differs")
    if payload.get("release_json_sha256") != release_sha:
        raise RuntimeError(f"{worker} runtime used a different release")


def _predict_command(args: argparse.Namespace) -> int:
    started_wall = time.perf_counter()
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    release = load_release(args.release)

    output_parent = args.outdir.resolve().parent
    output_parent.mkdir(parents=True, exist_ok=True)
    if args.outdir.exists() and not args.outdir.is_dir():
        raise FileExistsError(f"Output path exists and is not a directory: {args.outdir}")
    standard_outputs = [
        args.outdir / "predictions.tsv",
        args.outdir / "run_metadata.json",
        args.outdir / "CHECKSUMS.sha256",
    ]
    existing = [str(path) for path in standard_outputs if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing inference output: {existing}; "
            "choose a new --outdir or pass --overwrite"
        )
    with tempfile.TemporaryDirectory(prefix=".djrmcp-v01-stage-", dir=output_parent) as name:
        stage = Path(name)
        staged_input = stage / "validated_input.faa"
        shutil.copyfile(args.fasta, staged_input)
        input_sha256 = sha256_file(staged_input)
        records = read_protein_fasta(staged_input)
        _run_worker(
            args.esm2_python,
            "h12",
            release=release.root,
            stage=stage,
            device=args.device,
            cache_dir=args.cache_dir,
            offline=args.offline,
            fasta=staged_input,
        )
        verify_checksum_receipt(stage, "h12", H12_FILES)
        if sha256_file(staged_input) != input_sha256:
            raise RuntimeError("Private input snapshot changed during H12 inference")
        h12_payload = _load_json(stage / "h12.json")
        _validate_worker_payload(
            h12_payload, worker="h12", release_sha=release.release_json_sha256
        )
        h12_rows = h12_payload["rows"]
        if len(h12_rows) != len(records):
            raise RuntimeError("H12 worker returned the wrong number of input rows")
        expected_identities = [
            (record.input_row, record.protein_id, record.sequence_sha256) for record in records
        ]
        observed_identities = [
            (int(row["input_row"]), str(row["protein_id"]), str(row["sequence_sha256"]))
            for row in h12_rows
        ]
        if observed_identities != expected_identities:
            raise RuntimeError("H12 worker input identity/order differs from validated FASTA")

        subset = _load_json(stage / "h3_subset.json")
        routed_unique = int(subset.get("exact_unique_sequence_count", -1))
        h3_started = routed_unique > 0
        h3_runtime: dict[str, Any]
        if h3_started:
            _run_worker(
                args.esmc_python,
                "h3",
                release=release.root,
                stage=stage,
                device=args.device,
                cache_dir=args.cache_dir,
                offline=args.offline,
            )
            verify_checksum_receipt(stage, "h3", H3_FILES)
            h3_payload = _load_json(stage / "h3.json")
            _validate_worker_payload(
                h3_payload, worker="h3", release_sha=release.release_json_sha256
            )
            if h3_payload.get("h3_subset_identity_sha256") != subset.get(
                "ordered_identity_sha256"
            ):
                raise RuntimeError("H3 worker receipt refers to a different routed subset")
            h3_rows = h3_payload["rows"]
            h3_runtime = _load_json(stage / "h3_runtime.json")
            _validate_runtime_payload(
                h3_runtime,
                worker="h3",
                encoder_id="esmc_6b",
                release_sha=release.release_json_sha256,
            )
        else:
            h3_rows = []
            h3_runtime = {
                "schema_version": 1,
                "worker": "h3",
                "package_version": __version__,
                "encoder_id": "esmc_6b",
                "release_json_sha256": release.release_json_sha256,
                "loaded": False,
                "skip_reason": "zero_h1_h2_gate_through_sequences",
                "embedded_unique_sequence_count": 0,
                "h3_subset_identity_sha256": subset.get("ordered_identity_sha256"),
            }
        predictions = Predictor(release).merge_h3(h12_rows, h3_rows)
        h12_runtime = _load_json(stage / "h12_runtime.json")
        _validate_runtime_payload(
            h12_runtime,
            worker="h12",
            encoder_id="esm2_3b",
            release_sha=release.release_json_sha256,
        )
        if sha256_file(staged_input) != input_sha256:
            raise RuntimeError("Private input snapshot changed during inference")

    completed_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    warning_counts = Counter(warning for record in records for warning in record.warnings)
    final_counts = Counter(row["final_prediction"] for row in predictions)
    h3_reached_count = sum(bool(row["head3_reached"]) for row in predictions)
    metadata = {
        "schema_version": 2,
        "status": "complete",
        "candidate_status": release.release_status,
        "released_v0_unchanged": True,
        "started_utc": started_utc,
        "completed_utc": completed_utc,
        "elapsed_seconds": time.perf_counter() - started_wall,
        "software": {
            "package": "djrmcp-user-inference-v01",
            "version": __version__,
            "python": ".".join(str(part) for part in sys.version_info[:3]),
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
        "command": shlex.join(sys.argv),
        "input": {
            "path": str(args.fasta.resolve()),
            "sha256": input_sha256,
            "record_count": len(records),
            "exact_unique_sequence_count": len(
                {record.sequence_sha256 for record in records}
            ),
            "total_residues": sum(record.length_aa for record in records),
            "warning_counts": dict(sorted(warning_counts.items())),
        },
        "release": _release_summary(release),
        "runtime": {
            "execution": "sequential_isolated_workers",
            "h12": h12_runtime,
            "h3": h3_runtime,
        },
        "routing": {
            "h1_positive_count": int(h12_runtime["h1_positive_count"]),
            "h3_reached_record_count": h3_reached_count,
            "h3_routed_unique_sequence_count": routed_unique,
            "h3_route_fraction": h3_reached_count / len(records),
            "h3_worker_started": h3_started,
            "h3_subset_identity_sha256": subset.get("ordered_identity_sha256"),
        },
        "final_prediction_counts": dict(sorted(final_counts.items())),
        "interpretation": {
            "candidate_note": (
                "This is an engineering V0.1 candidate recommended for prospective "
                "external confirmation; it does not replace the released V0."
            ),
            "probability_note": (
                "Values are frozen calibrated model scores under the development-data "
                "distribution, not prevalence-adjusted posterior probabilities."
            ),
            "unknown_note": (
                "vma::unknown/other rejects from the two known H3 phyla after H1/H2; "
                "it is not a general unknown-virus detector."
            ),
        },
    }
    paths = write_run(args.outdir, predictions, metadata, overwrite=args.overwrite)
    print(
        json.dumps(
            {
                "status": "complete",
                "candidate_status": release.release_status,
                "record_count": len(records),
                "h3_worker_started": h3_started,
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
            print(
                json.dumps(
                    _release_summary(load_release(args.release)), indent=2, sort_keys=True
                )
            )
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
