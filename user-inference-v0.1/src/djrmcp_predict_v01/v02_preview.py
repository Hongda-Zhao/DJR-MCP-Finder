"""V0.2 deployment-policy preview over the frozen V0.1 inference pipeline.

This is an abstention policy, not a newly trained scientific model.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import sys
import tempfile
from collections import Counter
from collections.abc import Sequence
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from . import __version__, cli
from .fasta import ProteinRecord, read_protein_fasta
from .output import PREDICTION_FIELDS, write_run
from .release import load_release, sha256_file

MIN_LENGTH_AA = 250
SHORT_LABEL = "mcp_unreliable_short_sequence"
POLICY = {
    "id": "v02-preview-length-guard-250-v1",
    "minimum_scored_length_aa": MIN_LENGTH_AA,
    "comparison": "length_aa < 250",
    "short_input_label": SHORT_LABEL,
    "short_input_display_label": "MCP unreliable: sequence shorter than 250 aa",
    "reason": "length_below_250_aa",
    "basis": "user_selected_conservative_abstention; not a biological minimum",
    "length_definition": "FASTA whitespace removed; uppercase residues; X counts",
    "new_model_trained": False,
}


def _short_row(record: ProteinRecord) -> dict[str, Any]:
    row = dict.fromkeys(PREDICTION_FIELDS)
    for field in PREDICTION_FIELDS:
        if field.startswith("head") and field.endswith(("encoder", "prediction")):
            row[field] = "not_reached"
    row.update(
        input_row=record.input_row,
        protein_id=record.protein_id,
        original_header=record.original_header,
        sequence_sha256=record.sequence_sha256,
        length_aa=record.length_aa,
        status="not_evaluated_short_sequence",
        head3_reached=False,
        final_prediction=SHORT_LABEL,
        warnings=";".join((*record.warnings, "length_below_250_aa")),
    )
    return row


def _read_baseline(output: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    receipt = (output / "CHECKSUMS.sha256").read_text().splitlines()
    expected = [
        f"{sha256_file(output / name)}  {name}" for name in ("predictions.tsv", "run_metadata.json")
    ]
    if receipt != expected:
        raise RuntimeError("V0.1 output checksum receipt does not match")
    metadata = json.loads((output / "run_metadata.json").read_text())
    if metadata.get("predictions_sha256") != sha256_file(output / "predictions.tsv"):
        raise RuntimeError("V0.1 metadata prediction checksum does not match")
    with (output / "predictions.tsv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != PREDICTION_FIELDS:
            raise RuntimeError("Unexpected V0.1 prediction columns")
        return list(reader), metadata


def _predict(args: argparse.Namespace) -> int:
    targets = ("predictions.tsv", "run_metadata.json", "CHECKSUMS.sha256")
    if not args.overwrite and any((args.outdir / name).exists() for name in targets):
        raise FileExistsError("Refusing to overwrite output; use --overwrite or a new --outdir")
    args.outdir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".djrmcp-v02-policy-", dir=args.outdir.parent) as tmp:
        stage = Path(tmp)
        snapshot = stage / "input.faa"
        shutil.copyfile(args.fasta, snapshot)
        input_sha = sha256_file(snapshot)
        # Validate the entire input before routing, including short records.
        records = read_protein_fasta(snapshot)
        eligible = [record for record in records if record.length_aa >= MIN_LENGTH_AA]
        scored: dict[str, dict[str, Any]] = {}
        baseline_metadata = None
        if eligible:
            selected = stage / "eligible.faa"
            selected.write_text(
                "".join(f">{record.original_header}\n{record.sequence}\n" for record in eligible),
                encoding="utf-8",
            )
            baseline_args = argparse.Namespace(**vars(args))
            baseline_args.fasta = selected
            baseline_args.outdir = stage / "baseline"
            baseline_args.overwrite = False
            # Keep the baseline computation and score serialization unchanged.
            with redirect_stdout(io.StringIO()):
                result = cli._predict_command(baseline_args)
            if result != 0:
                raise RuntimeError(f"V0.1 inference failed with exit code {result}")
            rows, baseline_metadata = _read_baseline(baseline_args.outdir)
            if len(rows) != len(eligible):
                raise RuntimeError("V0.1 returned the wrong number of eligible records")
            for index, (record, row) in enumerate(zip(eligible, rows, strict=True), start=1):
                identity = (
                    row["input_row"],
                    row["protein_id"],
                    row["sequence_sha256"],
                    row["original_header"],
                    row["length_aa"],
                )
                expected = (
                    str(index),
                    record.protein_id,
                    record.sequence_sha256,
                    record.original_header,
                    str(record.length_aa),
                )
                if identity != expected:
                    raise RuntimeError("V0.1 output identity/order differs from eligible FASTA")
                scored[record.protein_id] = {**row, "input_row": record.input_row}
        predictions = [
            scored[record.protein_id] if record.length_aa >= MIN_LENGTH_AA else _short_row(record)
            for record in records
        ]
        if sha256_file(snapshot) != input_sha:
            raise RuntimeError("Private input snapshot changed during inference")

    counts = dict(sorted(Counter(row["final_prediction"] for row in predictions).items()))
    metadata = {
        "schema_version": 1,
        "schema_name": "djrmcp_v02_policy_preview",
        "status": "complete",
        "policy": POLICY,
        "software": {"package": "djrmcp-user-inference-v01", "version": __version__},
        "input": {
            "path": str(args.fasta.resolve()),
            "sha256": input_sha,
            "record_count": len(records),
            "exact_unique_sequence_count": len({r.sequence_sha256 for r in records}),
            "total_residues": sum(r.length_aa for r in records),
        },
        "routing": {
            "scored_record_count": len(eligible),
            "abstained_record_count": len(records) - len(eligible),
            "scoring_coverage": len(eligible) / len(records),
            "baseline_pipeline_started": bool(eligible),
        },
        # The nested baseline input is the eligible subset, not the original input.
        "baseline_subset_run": baseline_metadata,
        "final_prediction_counts": counts,
        "interpretation": (
            "Short inputs are unevaluated, not negative or MCP-positive. Scores are NA. "
            "Inputs >=250 aa use frozen V0.1; their accuracy is not guaranteed by length. "
            "This policy preview is not a trained or released scientific Model V0.2."
        ),
    }
    paths = write_run(args.outdir, predictions, metadata, overwrite=args.overwrite)
    print(
        json.dumps(
            {
                "status": "complete",
                "policy_id": POLICY["id"],
                "final_prediction_counts": counts,
                "routing": metadata["routing"],
                **{name: str(path.resolve()) for name, path in paths.items()},
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = cli.build_parser()
    parser.prog = "djrmcp-predict-v02-preview"
    parser.description = "V0.2 policy preview: abstain below 250 aa; otherwise use frozen V0.1"
    args = parser.parse_args(argv)
    try:
        if args.command == "predict":
            return _predict(args)
        if args.command == "validate-fasta":
            return cli._validate_command(args.fasta)
        if args.command == "model-info":
            print(
                json.dumps(
                    {
                        "policy": POLICY,
                        "baseline": cli._release_summary(load_release(args.release)),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
