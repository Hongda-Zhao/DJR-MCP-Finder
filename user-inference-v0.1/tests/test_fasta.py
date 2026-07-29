from __future__ import annotations

from pathlib import Path

import pytest

from djrmcp_predict_v01.fasta import read_protein_fasta


def test_valid_multiline_fasta_preserves_header_normalizes_and_warns(tmp_path: Path) -> None:
    path = tmp_path / "input.faa"
    path.write_text(
        ">p1 full header\nacdefghiklmnpqrstvwy\nACDEFGHIKLMNPQRSTVWY\n",
        encoding="utf-8",
    )

    records = read_protein_fasta(path)

    assert records[0].protein_id == "p1"
    assert records[0].original_header == "p1 full header"
    assert records[0].sequence == "ACDEFGHIKLMNPQRSTVWY" * 2
    assert records[0].warnings == ("length_outside_training_range_130_2906",)
    assert len(records[0].sequence_sha256) == 64


@pytest.mark.parametrize(
    "payload, message",
    [
        ("", "No FASTA records"),
        (">p1\n", "Empty protein sequence"),
        (">p1\nACD*EF\n", "Unsupported residue"),
        (">p1\nACDE\n>p1\nFGHI\n", "Duplicate FASTA identifier"),
        (">dna\n" + "ACGT" * 10 + "\n", "appears to be nucleotide"),
        ("ACDE\n", "before the first FASTA header"),
    ],
)
def test_invalid_fasta_fails_closed(tmp_path: Path, payload: str, message: str) -> None:
    path = tmp_path / "invalid.faa"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        read_protein_fasta(path)


def test_same_sequence_different_ids_is_allowed_and_identity_matches(tmp_path: Path) -> None:
    sequence = "ACDEFGHIKLMNPQRSTVWY" * 7
    path = tmp_path / "duplicates.faa"
    path.write_text(f">a one\n{sequence}\n>b two\n{sequence}\n", encoding="utf-8")

    records = read_protein_fasta(path)

    assert [record.protein_id for record in records] == ["a", "b"]
    assert records[0].sequence_sha256 == records[1].sequence_sha256


def test_high_x_fraction_is_retained_with_warning(tmp_path: Path) -> None:
    path = tmp_path / "x.faa"
    path.write_text(">x\n" + "ACDEFGHIK" * 14 + "X" * 15 + "\n", encoding="utf-8")

    record = read_protein_fasta(path)[0]

    assert "more_than_10pct_X" in record.warnings
    assert "length_outside_training_range_130_2906" not in record.warnings
