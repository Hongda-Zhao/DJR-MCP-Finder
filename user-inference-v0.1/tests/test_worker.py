from __future__ import annotations

from pathlib import Path

import pytest

from djrmcp_predict_v01.worker import (
    subset_identity_sha256,
    verify_checksum_receipt,
    write_checksum_receipt,
)


def _stage(tmp_path: Path) -> tuple[Path, tuple[str, ...]]:
    stage = tmp_path / "stage"
    stage.mkdir()
    names = ("rows.json", "runtime.json")
    (stage / names[0]).write_text('{"rows": []}\n', encoding="utf-8")
    (stage / names[1]).write_text('{"status": "complete"}\n', encoding="utf-8")
    return stage, names


def test_worker_receipt_binds_exact_ordered_file_set(tmp_path: Path) -> None:
    stage, names = _stage(tmp_path)

    receipt = write_checksum_receipt(stage, "h12", names)

    verify_checksum_receipt(stage, "h12", names)
    assert receipt.name == "h12.CHECKSUMS.sha256"
    assert [line.split(maxsplit=1)[1] for line in receipt.read_text().splitlines()] == list(
        names
    )


def test_worker_receipt_detects_artifact_tamper(tmp_path: Path) -> None:
    stage, names = _stage(tmp_path)
    write_checksum_receipt(stage, "h12", names)
    (stage / names[0]).write_text('{"rows": ["tampered"]}\n', encoding="utf-8")

    with pytest.raises(RuntimeError, match="checksum mismatch"):
        verify_checksum_receipt(stage, "h12", names)


def test_worker_receipt_rejects_missing_or_reordered_coverage(tmp_path: Path) -> None:
    stage, names = _stage(tmp_path)
    write_checksum_receipt(stage, "h12", names)

    with pytest.raises(RuntimeError, match="file set/order differs"):
        verify_checksum_receipt(stage, "h12", tuple(reversed(names)))


def test_worker_receipt_rejects_unsafe_path(tmp_path: Path) -> None:
    stage, names = _stage(tmp_path)
    receipt = write_checksum_receipt(stage, "h12", names)
    first_digest = receipt.read_text(encoding="utf-8").split()[0]
    receipt.write_text(f"{first_digest}  ../escape.json\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Unsafe path"):
        verify_checksum_receipt(stage, "h12", names)


def test_worker_receipt_rejects_symlinked_artifact(tmp_path: Path) -> None:
    stage, names = _stage(tmp_path)
    write_checksum_receipt(stage, "h12", names)
    source = stage / names[0]
    real = stage / "real_rows.json"
    source.replace(real)
    source.symlink_to(real.name)

    with pytest.raises(RuntimeError, match="symbolic link"):
        verify_checksum_receipt(stage, "h12", names)


def test_h3_subset_identity_is_deterministic_and_order_sensitive() -> None:
    entries = [
        {"subset_row": 1, "sequence_sha256": "a" * 64, "length_aa": 130},
        {"subset_row": 2, "sequence_sha256": "b" * 64, "length_aa": 200},
    ]

    observed = subset_identity_sha256(entries)

    assert observed == subset_identity_sha256([dict(entry) for entry in entries])
    assert observed != subset_identity_sha256(list(reversed(entries)))
    assert len(observed) == 64
