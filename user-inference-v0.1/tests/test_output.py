from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from djrmcp_predict_v01.output import PREDICTION_FIELDS, write_run
from djrmcp_predict_v01.release import sha256_file


def _prediction() -> dict[str, object]:
    assert {"head1_encoder", "head2_encoder", "head3_encoder"} <= set(PREDICTION_FIELDS)
    values: dict[str, object] = {field: None for field in PREDICTION_FIELDS}
    values.update(
        {
            "input_row": 1,
            "protein_id": "p1",
            "original_header": "p1 example",
            "sequence_sha256": "1" * 64,
            "length_aa": 200,
            "status": "ok",
            "head1_raw_score": 1.0,
            "head1_djr_probability": 0.9,
            "head1_prediction": "djr",
            "head1_encoder": "esm2_3b",
            "head2_raw_score": -1.0,
            "head2_vma_probability": 0.1,
            "head2_raw_prediction": "none",
            "head2_operational_prediction": "none",
            "head2_encoder": "esm2_3b",
            "head3_reached": False,
            "head3_prediction": "not_reached",
            "head3_encoder": "not_reached",
            "final_prediction": "djr_non_vma",
            "warnings": "",
        }
    )
    return values


def test_atomic_output_metadata_and_checksums(tmp_path: Path) -> None:
    paths = write_run(
        tmp_path / "run",
        [_prediction()],
        {"schema_version": 2, "release_id": "tiny-v0.1-mixed-release"},
    )

    metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    assert metadata["predictions_sha256"] == sha256_file(paths["predictions"])
    with paths["predictions"].open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle, delimiter="\t"))
    assert row["head1_encoder"] == "esm2_3b"
    assert row["head2_encoder"] == "esm2_3b"
    assert row["head3_encoder"] == "not_reached"
    assert row["head3_nucleocytoviricota_probability"] == "NA"

    checksums = paths["checksums"].read_text(encoding="utf-8").splitlines()
    assert checksums == [
        f"{sha256_file(paths['predictions'])}  predictions.tsv",
        f"{sha256_file(paths['metadata'])}  run_metadata.json",
    ]
    assert not list((tmp_path / "run").glob("*.tmp"))


def test_output_refuses_overwrite_by_default(tmp_path: Path) -> None:
    output = tmp_path / "run"
    write_run(output, [_prediction()], {"schema_version": 2})

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        write_run(output, [_prediction()], {"schema_version": 2})


def test_explicit_overwrite_replaces_standard_files(tmp_path: Path) -> None:
    output = tmp_path / "run"
    write_run(output, [_prediction()], {"schema_version": 2, "marker": "first"})
    write_run(
        output,
        [_prediction()],
        {"schema_version": 2, "marker": "second"},
        overwrite=True,
    )

    assert json.loads((output / "run_metadata.json").read_text())["marker"] == "second"


def test_empty_prediction_set_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No predictions"):
        write_run(tmp_path / "run", [], {"schema_version": 2})
