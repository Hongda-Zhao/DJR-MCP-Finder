import csv
import hashlib

import pytest

from djrmcp_finder.stages.embedding import load_records, sliding_windows


def test_sliding_windows_covers_tail_without_truncation() -> None:
    sequence = "A" * 1200 + "C" * 400
    windows = sliding_windows(sequence, residues=1022, stride=511)
    assert all(len(window) == 1022 for window in windows)
    assert windows[0] == sequence[:1022]
    assert windows[-1] == sequence[-1022:]
    assert windows[-1].endswith("C" * 400)


def test_short_sequence_has_one_window() -> None:
    assert sliding_windows("ACDE", residues=1022, stride=511) == ["ACDE"]


def test_load_records_checks_manifest_hash(tmp_path) -> None:
    fasta = tmp_path / "records.faa"
    manifest = tmp_path / "manifest.tsv"
    fasta.write_text(">p1\nACDE\n", encoding="utf-8")
    digest = hashlib.sha256(b"ACDE").hexdigest()
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["protein_id", "sequence_sha256", "split", "length_aa"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(
            {"protein_id": "p1", "sequence_sha256": digest, "split": "train", "length_aa": 4}
        )
    records = load_records(manifest, fasta)
    assert records[0].protein_id == "p1"
    assert records[0].sequence == "ACDE"

    text = manifest.read_text(encoding="utf-8").replace(digest, "0" * 64)
    manifest.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        load_records(manifest, fasta)
