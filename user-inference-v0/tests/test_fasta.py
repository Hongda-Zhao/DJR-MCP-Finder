from pathlib import Path

import pytest

from djrmcp_predict.fasta import read_protein_fasta


def test_valid_multiline_fasta_preserves_header_and_warns(tmp_path: Path) -> None:
    path = tmp_path / "input.faa"
    path.write_text(
        ">p1 full header\nacdefghiklmnpqrstvwy\nACDEFGHIKLMNPQRSTVWY\n",
        encoding="utf-8",
    )
    records = read_protein_fasta(path)
    assert records[0].protein_id == "p1"
    assert records[0].original_header == "p1 full header"
    assert records[0].sequence.startswith("ACDE")
    assert records[0].warnings == ("length_outside_training_range_130_2906",)


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


def test_same_sequence_different_ids_is_allowed(tmp_path: Path) -> None:
    sequence = "ACDEFGHIKLMNPQRSTVWY" * 7
    path = tmp_path / "duplicates.faa"
    path.write_text(f">a\n{sequence}\n>b\n{sequence}\n", encoding="utf-8")
    records = read_protein_fasta(path)
    assert len(records) == 2
    assert records[0].sequence_sha256 == records[1].sequence_sha256

