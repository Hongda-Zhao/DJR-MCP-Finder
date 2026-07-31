"""Atomic, checksum-bearing inference output files."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Sequence

from .release import sha256_file


PREDICTION_FIELDS = [
    "input_row",
    "protein_id",
    "original_header",
    "sequence_sha256",
    "length_aa",
    "status",
    "head1_raw_score",
    "head1_djr_probability",
    "head1_prediction",
    "head2_raw_score",
    "head2_mcp_probability",
    "head2_raw_prediction",
    "head2_operational_prediction",
    "head3_reached",
    "head3_nucleocytoviricota_probability",
    "head3_preplasmiviricota_probability",
    "head3_confidence",
    "head3_prediction",
    "final_prediction",
    "warnings",
]


def _display(value: Any) -> Any:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:.17g}"
    return value


def _temporary_path(parent: Path, prefix: str) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=parent)
    os.close(descriptor)
    return Path(name)


def write_run(
    outdir: str | Path,
    predictions: Sequence[dict[str, Any]],
    metadata: dict[str, Any],
    *,
    overwrite: bool = False,
) -> dict[str, Path]:
    output = Path(outdir)
    output.mkdir(parents=True, exist_ok=True)
    targets = {
        "predictions": output / "predictions.tsv",
        "metadata": output / "run_metadata.json",
        "checksums": output / "CHECKSUMS.sha256",
    }
    existing = [str(path) for path in targets.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing inference output: {existing}; "
            "choose a new --outdir or pass --overwrite"
        )
    if not predictions:
        raise ValueError("No predictions to write")

    prediction_tmp = _temporary_path(output, ".predictions.")
    metadata_tmp = _temporary_path(output, ".metadata.")
    checksums_tmp = _temporary_path(output, ".checksums.")
    try:
        with prediction_tmp.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                delimiter="\t",
                fieldnames=PREDICTION_FIELDS,
                lineterminator="\n",
                extrasaction="raise",
            )
            writer.writeheader()
            for row in predictions:
                writer.writerow({field: _display(row[field]) for field in PREDICTION_FIELDS})
        prediction_sha = sha256_file(prediction_tmp)
        final_metadata = dict(metadata)
        final_metadata["predictions_sha256"] = prediction_sha
        metadata_tmp.write_text(
            json.dumps(final_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        metadata_sha = sha256_file(metadata_tmp)
        checksums_tmp.write_text(
            f"{prediction_sha}  predictions.tsv\n{metadata_sha}  run_metadata.json\n",
            encoding="utf-8",
        )
        os.replace(prediction_tmp, targets["predictions"])
        os.replace(metadata_tmp, targets["metadata"])
        os.replace(checksums_tmp, targets["checksums"])
    finally:
        for temporary in (prediction_tmp, metadata_tmp, checksums_tmp):
            temporary.unlink(missing_ok=True)
    return targets
