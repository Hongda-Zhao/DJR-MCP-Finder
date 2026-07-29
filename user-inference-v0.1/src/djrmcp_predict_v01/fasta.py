"""Strict parsing and validation for user-supplied protein FASTA files."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


ALLOWED_RESIDUES = frozenset("ACDEFGHIKLMNPQRSTVWXY")
TRAINING_LENGTH_MIN = 130
TRAINING_LENGTH_MAX = 2906


@dataclass(frozen=True)
class ProteinRecord:
    """One validated input protein, preserving input order and full header."""

    input_row: int
    protein_id: str
    original_header: str
    sequence: str
    sequence_sha256: str
    length_aa: int
    warnings: tuple[str, ...]


def _finalize_record(
    *,
    input_row: int,
    header: str,
    chunks: list[str],
    seen_ids: set[str],
    path: Path,
) -> ProteinRecord:
    protein_id = header.split()[0] if header.split() else ""
    if not protein_id:
        raise ValueError(f"Empty FASTA identifier in {path} at record {input_row}")
    if protein_id in seen_ids:
        raise ValueError(f"Duplicate FASTA identifier: {protein_id}")
    seen_ids.add(protein_id)

    sequence = "".join(chunks).upper()
    if not sequence:
        raise ValueError(f"Empty protein sequence for {protein_id}")
    try:
        sequence.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"Non-ASCII residue in sequence {protein_id}") from exc

    invalid = sorted(set(sequence) - ALLOWED_RESIDUES)
    if invalid:
        raise ValueError(
            f"Unsupported residue(s) in {protein_id}: {''.join(invalid)}; "
            f"allowed={''.join(sorted(ALLOWED_RESIDUES))}"
        )
    if len(sequence) >= 30 and set(sequence) <= set("ACGT"):
        raise ValueError(
            f"Sequence {protein_id} contains only A/C/G/T and appears to be nucleotide FASTA"
        )

    warnings: list[str] = []
    if not TRAINING_LENGTH_MIN <= len(sequence) <= TRAINING_LENGTH_MAX:
        warnings.append("length_outside_training_range_130_2906")
    if sequence.count("X") / len(sequence) > 0.10:
        warnings.append("more_than_10pct_X")

    return ProteinRecord(
        input_row=input_row,
        protein_id=protein_id,
        original_header=header,
        sequence=sequence,
        sequence_sha256=hashlib.sha256(sequence.encode("ascii")).hexdigest(),
        length_aa=len(sequence),
        warnings=tuple(warnings),
    )


def read_protein_fasta(path: str | Path) -> list[ProteinRecord]:
    """Read a complete FASTA file and fail before inference on any invalid record."""

    fasta_path = Path(path)
    if not fasta_path.is_file():
        raise FileNotFoundError(f"Input FASTA does not exist: {fasta_path}")

    records: list[ProteinRecord] = []
    seen_ids: set[str] = set()
    current_header: str | None = None
    chunks: list[str] = []

    with fasta_path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current_header is not None:
                    records.append(
                        _finalize_record(
                            input_row=len(records) + 1,
                            header=current_header,
                            chunks=chunks,
                            seen_ids=seen_ids,
                            path=fasta_path,
                        )
                    )
                current_header = line[1:].strip()
                if not current_header:
                    raise ValueError(f"Empty FASTA header at {fasta_path}:{line_number}")
                chunks = []
                continue
            if current_header is None:
                raise ValueError(
                    f"Sequence appears before the first FASTA header at "
                    f"{fasta_path}:{line_number}"
                )
            chunks.append("".join(line.split()))

    if current_header is not None:
        records.append(
            _finalize_record(
                input_row=len(records) + 1,
                header=current_header,
                chunks=chunks,
                seen_ids=seen_ids,
                path=fasta_path,
            )
        )
    if not records:
        raise ValueError(f"No FASTA records found in {fasta_path}")
    return records
