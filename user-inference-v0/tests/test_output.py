import json
from pathlib import Path

import pytest

from djrmcp_predict.output import write_run
from djrmcp_predict.release import sha256_file


def _prediction() -> dict[str, object]:
    return {
        "input_row": 1,
        "protein_id": "p1",
        "original_header": "p1 example",
        "sequence_sha256": "1" * 64,
        "length_aa": 200,
        "status": "ok",
        "head1_raw_score": 1.0,
        "head1_djr_probability": 0.9,
        "head1_prediction": "djr",
        "head2_raw_score": -1.0,
        "head2_vma_probability": 0.1,
        "head2_raw_prediction": "none",
        "head2_operational_prediction": "none",
        "head3_reached": False,
        "head3_nucleocytoviricota_probability": None,
        "head3_preplasmiviricota_probability": None,
        "head3_confidence": None,
        "head3_prediction": "not_reached",
        "final_prediction": "djr_non_vma",
        "warnings": "",
    }


def test_atomic_output_and_checksums(tmp_path: Path) -> None:
    paths = write_run(tmp_path / "run", [_prediction()], {"schema_version": 1})
    metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    assert metadata["predictions_sha256"] == sha256_file(paths["predictions"])
    assert "NA" in paths["predictions"].read_text(encoding="utf-8")
    checksums = paths["checksums"].read_text(encoding="utf-8")
    assert sha256_file(paths["predictions"]) in checksums
    assert sha256_file(paths["metadata"]) in checksums


def test_output_refuses_overwrite_by_default(tmp_path: Path) -> None:
    output = tmp_path / "run"
    write_run(output, [_prediction()], {"schema_version": 1})
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        write_run(output, [_prediction()], {"schema_version": 1})


def test_explicit_overwrite_replaces_standard_files(tmp_path: Path) -> None:
    output = tmp_path / "run"
    write_run(output, [_prediction()], {"schema_version": 1})
    write_run(output, [_prediction()], {"schema_version": 2}, overwrite=True)
    assert json.loads((output / "run_metadata.json").read_text())["schema_version"] == 2

