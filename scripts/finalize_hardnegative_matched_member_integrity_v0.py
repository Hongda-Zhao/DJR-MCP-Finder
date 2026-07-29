#!/usr/bin/env python3
"""Finalize per-member positive exclusion and all-node integrity for HardNeg.

Positive evidence and exact all-node overlap exclude records individually.
Ordinary (non-exact) 30/80 homology never excludes a record; it is retained as
a relationship stratum and used to build dependence blocks.  The output is an
auxiliary, post-freeze robustness cohort and cannot feed model selection,
training, calibration, thresholds, or Test interpretation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator


PROJECT_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_DIR / "src"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from djrmcp_finder.archive import ArchiveError, _atomic_rename_noreplace  # noqa: E402


ANALYSIS_ID = "project_v0_hardnegative_matched_member_integrity"
EXPECTED_CANDIDATES = 3_478
EXPECTED_ALL_NODES = 27_427
ACTIVE_SPLITS = {"train", "validation", "test"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ACCESSION_RE = re.compile(
    r"^AF-([A-Z0-9]+)-F[0-9]+(?:-model_v[0-9]+)?(?:\.(?:cif|pdb))?$", re.I
)

MMSEQS_FIELDS = (
    "query", "target", "pident", "qcov", "tcov", "alnlen", "evalue", "bits"
)
FOLDSEEK_FIELDS = (
    "query", "target", "evalue", "bits", "prob", "alntmscore",
    "qtmscore", "ttmscore", "qcov", "tcov", "lddt",
)

MIN_IDENTITY_PCT = 30.0
MIN_QUERY_COVERAGE = 0.80
MIN_TARGET_COVERAGE = 0.80
HMM_MAX_IEVALUE = 1e-3
HMM_MIN_COVERAGE = 0.60
STRUCTURE_MAX_EVALUE = 1e-3
STRUCTURE_MIN_PROB = 0.90
STRUCTURE_MIN_ALNTMSCORE = 0.50
STRUCTURE_MIN_QCOV = 0.60
STRUCTURE_MIN_LDDT = 0.50

LEGAL_MANIFEST = "legal/member_manifest.tsv"
LEGAL_FASTA = "legal/member_sequences.faa"
LEGAL_SUMMARY = "legal/summary.json"
EXCLUDED_ENTITIES = "legal/excluded_entities.tsv"
EVIDENCE_NAME = "integrity_evidence.tsv"
RELATIONSHIP_NAME = "ordinary_relationships.tsv"
BLOCK_NAME = "dependence_blocks.tsv"
METADATA_COPY_NAME = "RUN_METADATA.txt"
CHECKSUM_NAME = "CHECKSUMS.sha256"
LEGAL_CHECKSUM_NAME = "legal/CHECKSUMS.sha256"

LEGAL_FIELDS = (
    "protein_id",
    "source_member_id",
    "source_dataset",
    "source_cluster_id",
    "source_cluster_key",
    "paired_representative_id",
    "paired_representative_protein_id",
    "global_component_id",
    "original_global_component_id",
    "parent_split",
    "split",
    "sequence_sha256",
    "length_aa",
    "head1_label",
    "head1_mask",
    "head2_label",
    "head2_mask",
    "head3_phylum_label",
    "head3_mask",
    "score_head1",
    "score_head2",
    "h3_analysis_included",
    "analysis_included",
    "dependence_block_id",
    "train_relationship_stratum",
    "assigned_family",
    "test_record",
)

EVIDENCE_FIELDS = (
    "protein_id",
    "source_member_id",
    "paired_representative_id",
    "assigned_family",
    "legal",
    "exclusion_reasons",
    "positive_exact_sequence",
    "positive_exact_accession",
    "positive_mmseqs_gate",
    "positive_mmseqs_target",
    "positive_mmseqs_pident_pct",
    "positive_mmseqs_qcov",
    "positive_mmseqs_tcov",
    "positive_hmm_gate",
    "positive_hmm_name",
    "positive_hmm_i_evalue",
    "positive_hmm_coverage",
    "positive_structure_gate",
    "positive_structure_query",
    "positive_structure_evalue",
    "positive_structure_prob",
    "positive_structure_alntmscore",
    "positive_structure_qcov",
    "positive_structure_lddt",
    "all_node_exact_id_overlap",
    "all_node_exact_sequence_overlap",
    "exact_overlap_splits",
    "cross_split_exact_conflict",
    "qualifying_all_node_relationships",
    "train_relationship_stratum",
    "dependence_block_id",
)

RELATIONSHIP_FIELDS = (
    "query_id",
    "source_member_id",
    "target_id",
    "target_split",
    "target_global_component_id",
    "pident_pct",
    "qcov_fraction",
    "tcov_fraction",
    "alignment_length",
    "evalue",
    "bit_score",
    "ordinary_nonexact_relationship",
)


class UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}
        self.rank = {value: 0 for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sequence_sha256(sequence: str) -> str:
    return hashlib.sha256(sequence.encode("ascii")).hexdigest()


def _require_file(path: Path, label: str, *, allow_empty: bool = False) -> None:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(f"{label} must be an existing regular file: {path}")
    if not allow_empty and path.stat().st_size == 0:
        raise ValueError(f"{label} is empty: {path}")


def _valid_sha(value: str, context: str) -> str:
    value = value.strip().lower()
    if not SHA256_RE.fullmatch(value):
        raise ValueError(f"Invalid SHA-256 for {context}: {value!r}")
    return value


def read_tsv(path: Path, required: Iterable[str], label: str) -> list[dict[str, str]]:
    _require_file(path, label)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = list(reader.fieldnames or [])
        if not fields or len(fields) != len(set(fields)):
            raise ValueError(f"{label} has empty/duplicate header: {path}")
        missing = sorted(set(required) - set(fields))
        if missing:
            raise ValueError(f"{label} missing fields {missing}: {path}")
        rows: list[dict[str, str]] = []
        for line_number, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Malformed {label} row at {path}:{line_number}")
            rows.append({key: value.strip() for key, value in row.items()})
    return rows


def index_unique(
    rows: Iterable[dict[str, str]], field: str, label: str
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        key = row[field]
        if not key or key in result:
            raise ValueError(f"Empty/duplicate {field} in {label}: {key!r}")
        result[key] = row
    return result


def read_fasta(path: Path, label: str) -> dict[str, str]:
    _require_file(path, label)
    result: dict[str, str] = {}
    record_id: str | None = None
    chunks: list[str] = []

    def flush() -> None:
        nonlocal record_id, chunks
        if record_id is None:
            return
        if record_id in result:
            raise ValueError(f"Duplicate FASTA ID in {label}: {record_id}")
        sequence = "".join(chunks).upper().rstrip("*")
        if not sequence or not sequence.isascii() or not sequence.isalpha():
            raise ValueError(f"Invalid/empty FASTA sequence in {label}: {record_id}")
        result[record_id] = sequence

    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                flush()
                record_id = line[1:].split()[0]
                chunks = []
                if not record_id:
                    raise ValueError(f"Empty FASTA ID at {path}:{line_number}")
            else:
                if record_id is None:
                    raise ValueError(f"Sequence before header at {path}:{line_number}")
                chunks.append("".join(line.split()))
    flush()
    return result


def verify_candidate_checksums(checksum_path: Path, manifest: Path, fasta: Path) -> None:
    _require_file(checksum_path, "candidate checksum manifest")
    if manifest.parent.resolve() != checksum_path.parent.resolve() or fasta.parent.resolve() != checksum_path.parent.resolve():
        raise ValueError("Candidate manifest, FASTA and checksum file must share a directory")
    observed: dict[str, str] = {}
    for line_number, raw in enumerate(checksum_path.read_text().splitlines(), 1):
        if not raw.strip():
            continue
        fields = raw.split(maxsplit=1)
        if len(fields) != 2:
            raise ValueError(f"Malformed candidate checksum row {line_number}")
        expected, name = fields[0].lower(), fields[1].strip().lstrip("*")
        _valid_sha(expected, f"candidate checksum row {line_number}")
        if Path(name).name != name or name in observed:
            raise ValueError(f"Unsafe/duplicate candidate checksum target: {name}")
        target = checksum_path.parent / name
        _require_file(target, "candidate checksum target", allow_empty=True)
        actual = file_sha256(target)
        if actual != expected:
            raise ValueError(f"Candidate checksum mismatch: {target}")
        observed[name] = actual
    for path in (manifest, fasta):
        if observed.get(path.name) != file_sha256(path):
            raise ValueError(f"Candidate checksums do not bind {path.name}")


def accession(identifier: str) -> str:
    base = Path(identifier).name
    match = ACCESSION_RE.fullmatch(base)
    if match:
        return match.group(1).upper()
    return base.split("|")[0].upper()


def _parse_float(value: str, context: str) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise ValueError(f"Invalid float for {context}: {value!r}") from error
    if not math.isfinite(result):
        raise ValueError(f"Non-finite float for {context}: {value!r}")
    return result


def iter_mmseqs(path: Path, label: str) -> Iterator[dict[str, Any]]:
    _require_file(path, label, allow_empty=True)
    with path.open(encoding="utf-8", newline="") as handle:
        for line_number, fields in enumerate(csv.reader(handle, delimiter="\t"), 1):
            if not fields or (len(fields) == 1 and not fields[0]):
                continue
            if len(fields) != len(MMSEQS_FIELDS):
                raise ValueError(f"Malformed {label} row at {path}:{line_number}")
            raw = dict(zip(MMSEQS_FIELDS, fields))
            yield {
                **raw,
                "pident_value": _parse_float(raw["pident"], f"{label} pident line {line_number}"),
                "qcov_value": _parse_float(raw["qcov"], f"{label} qcov line {line_number}"),
                "tcov_value": _parse_float(raw["tcov"], f"{label} tcov line {line_number}"),
                "alnlen_value": int(raw["alnlen"]),
                "evalue_value": _parse_float(raw["evalue"], f"{label} evalue line {line_number}"),
                "bits_value": _parse_float(raw["bits"], f"{label} bits line {line_number}"),
            }


def qualifies_30_80(row: dict[str, Any]) -> bool:
    return (
        row["pident_value"] >= MIN_IDENTITY_PCT
        and row["qcov_value"] >= MIN_QUERY_COVERAGE
        and row["tcov_value"] >= MIN_TARGET_COVERAGE
    )


def parse_hmm(paths: list[Path], aliases: dict[str, str]) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for path in paths:
        _require_file(path, "positive HMM domtblout", allow_empty=True)
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line or line.startswith("#"):
                continue
            fields = line.split(maxsplit=22)
            if len(fields) < 22:
                raise ValueError(f"Malformed HMM domtblout row at {path}:{line_number}")
            target = aliases.get(fields[3])
            if target is None:
                raise ValueError(f"Unknown candidate in HMM output at {path}:{line_number}: {fields[3]}")
            hmm_len = int(fields[2])
            hmm_from, hmm_to = int(fields[15]), int(fields[16])
            row = {
                "hmm_name": fields[0],
                "i_evalue": _parse_float(fields[12], "HMM i-Evalue"),
                "domain_score": _parse_float(fields[13], "HMM domain score"),
                "coverage": (hmm_to - hmm_from + 1) / hmm_len,
            }
            current = best.get(target)
            if current is None or (row["i_evalue"], -row["domain_score"]) < (
                current["i_evalue"], -current["domain_score"]
            ):
                best[target] = row
    return best


def parse_foldseek(path: Path, aliases: dict[str, str]) -> dict[str, dict[str, Any]]:
    _require_file(path, "positive Foldseek output", allow_empty=True)
    best: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for line_number, fields in enumerate(csv.reader(handle, delimiter="\t"), 1):
            if not fields or (len(fields) == 1 and not fields[0]):
                continue
            if len(fields) != len(FOLDSEEK_FIELDS):
                raise ValueError(f"Malformed Foldseek row at {path}:{line_number}")
            raw = dict(zip(FOLDSEEK_FIELDS, fields))
            candidate = aliases.get(raw["target"])
            if candidate is None:
                candidate = aliases.get(Path(raw["target"]).name)
            if candidate is None:
                candidate = aliases.get(raw["query"])
            if candidate is None:
                raise ValueError(f"Foldseek row has no candidate endpoint at {path}:{line_number}")
            row = {
                **raw,
                "evalue_value": _parse_float(raw["evalue"], "Foldseek evalue"),
                "bits_value": _parse_float(raw["bits"], "Foldseek bits"),
                "prob_value": _parse_float(raw["prob"], "Foldseek prob"),
                "alntmscore_value": _parse_float(raw["alntmscore"], "Foldseek alntmscore"),
                "qcov_value": _parse_float(raw["qcov"], "Foldseek qcov"),
                "lddt_value": _parse_float(raw["lddt"], "Foldseek lddt"),
            }
            current = best.get(candidate)
            score = (row["prob_value"], row["alntmscore_value"], row["bits_value"])
            if current is None or score > (
                current["prob_value"], current["alntmscore_value"], current["bits_value"]
            ):
                best[candidate] = row
    return best


def read_run_metadata(path: Path) -> dict[str, str]:
    _require_file(path, "integrity run metadata")
    result: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        if "=" not in raw:
            raise ValueError(f"Malformed run metadata at {path}:{line_number}")
        key, value = raw.split("=", 1)
        if not key or key in result:
            raise ValueError(f"Empty/duplicate run metadata key at {path}:{line_number}")
        result[key] = value
    expected = {
        "status": "complete",
        "analysis_id": ANALYSIS_ID,
        "min_seq_id": "0.30",
        "min_query_coverage": "0.80",
        "min_target_coverage": "0.80",
        "cov_mode": "0",
        "sensitivity": "7.5",
        "hmm_max_ievalue": "1e-3",
        "hmm_min_coverage": "0.60",
        "structure_max_evalue": "1e-3",
        "structure_min_probability": "0.90",
        "structure_min_alntmscore": "0.50",
        "structure_min_qcov": "0.60",
        "structure_min_lddt": "0.50",
        "exact_positive_exclusion": "complete",
        "mmseqs_positive_exclusion": "complete",
        "cellular_hmm_positive_exclusion": "complete",
        "viral_hmm_positive_exclusion": "complete",
        "foldseek_positive_exclusion": "complete",
        "candidate_vs_all_nodes": "complete",
        "candidate_vs_candidate": "complete_self_edges_removed",
    }
    for key, expected_value in expected.items():
        if result.get(key) != expected_value:
            raise ValueError(
                f"Integrity run metadata mismatch for {key}: "
                f"expected={expected_value!r}, observed={result.get(key)!r}"
            )
    for key in ("mmseqs_version", "hmmer_version", "foldseek_version"):
        if not result.get(key):
            raise ValueError(f"Integrity run metadata lacks {key}")
    return result


def _stratum(max_identity: float | None) -> str:
    if max_identity is None:
        return "no_hit"
    if max_identity < 50.0:
        return "30_<50"
    if max_identity < 70.0:
        return "50_<70"
    return ">=70"


def _write_tsv(path: Path, rows: Iterable[dict[str, Any]], fields: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(fields), delimiter="\t", lineterminator="\n", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_fasta(path: Path, rows: list[dict[str, Any]], sequences: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            sequence = sequences[str(row["protein_id"])]
            handle.write(
                f">{row['protein_id']} source_member={row['source_member_id']} "
                f"block={row['dependence_block_id']} sha256={row['sequence_sha256']}\n"
            )
            for start in range(0, len(sequence), 80):
                handle.write(sequence[start : start + 80] + "\n")


def _write_checksums(root: Path, names: list[str]) -> None:
    with (root / CHECKSUM_NAME).open("x", encoding="utf-8") as handle:
        for name in sorted(names):
            handle.write(f"{file_sha256(root / name)}  {name}\n")


def _verify_checksums(root: Path, names: set[str]) -> None:
    observed: set[str] = set()
    for line_number, raw in enumerate((root / CHECKSUM_NAME).read_text().splitlines(), 1):
        fields = raw.split(maxsplit=1)
        if len(fields) != 2:
            raise RuntimeError(f"Malformed output checksum row {line_number}")
        expected, name = fields[0], fields[1].strip().lstrip("*")
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or name in observed:
            raise RuntimeError(f"Unsafe/duplicate output checksum target: {name}")
        if file_sha256(root / relative) != expected:
            raise RuntimeError(f"Output checksum mismatch: {name}")
        observed.add(name)
    if observed != names:
        raise RuntimeError("Output checksum target set mismatch")


def _write_and_verify_legal_checksums(root: Path) -> None:
    legal_root = root / "legal"
    names = ("excluded_entities.tsv", "member_manifest.tsv", "member_sequences.faa", "summary.json")
    with (legal_root / "CHECKSUMS.sha256").open("x", encoding="utf-8") as handle:
        for name in names:
            handle.write(f"{file_sha256(legal_root / name)}  {name}\n")
    observed: set[str] = set()
    for raw in (legal_root / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines():
        expected, name = raw.split(maxsplit=1)
        name = name.strip().lstrip("*")
        if Path(name).name != name or name in observed:
            raise RuntimeError(f"Unsafe/duplicate legal checksum target: {name}")
        if file_sha256(legal_root / name) != expected:
            raise RuntimeError(f"Legal bundle checksum mismatch: {name}")
        observed.add(name)
    if observed != set(names):
        raise RuntimeError("Legal bundle checksum target set mismatch")


def finalize(
    *,
    candidate_manifest_path: Path,
    candidate_fasta_path: Path,
    candidate_checksums_path: Path,
    positive_fasta_path: Path,
    positive_mmseqs_path: Path,
    positive_hmm_paths: list[Path],
    positive_foldseek_path: Path,
    all_node_membership_path: Path,
    all_node_fasta_path: Path,
    candidate_vs_all_nodes_path: Path,
    candidate_vs_candidate_path: Path,
    run_metadata_path: Path,
    output_dir: Path,
    expected_candidates: int = EXPECTED_CANDIDATES,
    expected_all_nodes: int = EXPECTED_ALL_NODES,
) -> dict[str, Any]:
    """Apply integrity gates and atomically publish the legal cohort."""

    if os.path.lexists(output_dir):
        raise FileExistsError(f"Refusing to overwrite output directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    verify_candidate_checksums(candidate_checksums_path, candidate_manifest_path, candidate_fasta_path)
    run_metadata = read_run_metadata(run_metadata_path)

    candidate_rows = read_tsv(
        candidate_manifest_path,
        (
            "protein_id", "source_member_id", "source_dataset", "source_cluster_id",
            "source_cluster_key", "paired_representative_id",
            "paired_representative_protein_id", "original_global_component_id",
            "parent_split", "split", "sequence_sha256", "length_aa", "head1_label",
            "head1_mask", "head2_mask", "head3_mask", "assigned_family", "test_record",
        ),
        "candidate manifest",
    )
    if len(candidate_rows) != expected_candidates:
        raise ValueError(
            f"Candidate count mismatch: expected={expected_candidates}, observed={len(candidate_rows)}"
        )
    candidate_by_id = index_unique(candidate_rows, "protein_id", "candidate manifest")
    member_to_id: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for row in candidate_rows:
        protein_id, member_id = row["protein_id"], row["source_member_id"]
        if member_id in member_to_id:
            raise ValueError(f"Duplicate source_member_id: {member_id}")
        member_to_id[member_id] = protein_id
        for alias in (protein_id, member_id, Path(member_id).name):
            if alias in aliases and aliases[alias] != protein_id:
                raise ValueError(f"Ambiguous candidate alias: {alias}")
            aliases[alias] = protein_id
        row["sequence_sha256"] = _valid_sha(row["sequence_sha256"], protein_id)
        if not (
            row["source_dataset"] == "hard_non_djr"
            and row["parent_split"] == "validation"
            and row["split"] == "validation_matched_member"
            and row["head1_label"] == "non_djr"
            and row["head1_mask"] == "1"
            and row["head2_mask"] == "0"
            and row["head3_mask"] == "0"
            and row["test_record"] == "0"
        ):
            raise ValueError(f"Candidate label/split contract mismatch: {protein_id}")

    candidate_sequences = read_fasta(candidate_fasta_path, "candidate FASTA")
    if set(candidate_sequences) != set(candidate_by_id):
        raise ValueError("Candidate FASTA/manifest ID set mismatch")
    for protein_id, sequence in candidate_sequences.items():
        if sequence_sha256(sequence) != candidate_by_id[protein_id]["sequence_sha256"]:
            raise ValueError(f"Candidate FASTA SHA mismatch: {protein_id}")
        if len(sequence) != int(candidate_by_id[protein_id]["length_aa"]):
            raise ValueError(f"Candidate FASTA length mismatch: {protein_id}")

    membership_rows = read_tsv(
        all_node_membership_path,
        ("node_id", "global_component_id", "split", "sequence_sha256"),
        "all-node membership",
    )
    if len(membership_rows) != expected_all_nodes:
        raise ValueError(
            f"All-node count mismatch: expected={expected_all_nodes}, observed={len(membership_rows)}"
        )
    membership_by_id = index_unique(membership_rows, "node_id", "all-node membership")
    sha_to_nodes: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in membership_rows:
        if row["split"] not in ACTIVE_SPLITS or not row["global_component_id"]:
            raise ValueError(f"Invalid all-node membership row: {row['node_id']}")
        row["sequence_sha256"] = _valid_sha(row["sequence_sha256"], row["node_id"])
        sha_to_nodes[row["sequence_sha256"]].append(row)
    all_node_sequences = read_fasta(all_node_fasta_path, "all-node FASTA")
    if set(all_node_sequences) != set(membership_by_id):
        raise ValueError("All-node FASTA/membership ID set mismatch")
    for node_id, sequence in all_node_sequences.items():
        if sequence_sha256(sequence) != membership_by_id[node_id]["sequence_sha256"]:
            raise ValueError(f"All-node FASTA SHA mismatch: {node_id}")

    positive_sequences = read_fasta(positive_fasta_path, "combined positive FASTA")
    positive_shas = {sequence_sha256(sequence) for sequence in positive_sequences.values()}
    positive_accessions = {accession(record_id) for record_id in positive_sequences}

    positive_mmseqs: dict[str, dict[str, Any]] = {}
    for row in iter_mmseqs(positive_mmseqs_path, "positive MMseqs output"):
        query = aliases.get(row["query"])
        if query is None:
            raise ValueError(f"Unknown candidate query in positive MMseqs output: {row['query']}")
        if not qualifies_30_80(row):
            continue
        current = positive_mmseqs.get(query)
        if current is None or (row["evalue_value"], -row["bits_value"]) < (
            current["evalue_value"], -current["bits_value"]
        ):
            positive_mmseqs[query] = row
    hmm_hits = parse_hmm(positive_hmm_paths, aliases)
    foldseek_hits = parse_foldseek(positive_foldseek_path, aliases)

    qualifying_all_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    relationship_rows: list[dict[str, Any]] = []
    for edge in iter_mmseqs(candidate_vs_all_nodes_path, "candidate-vs-all-node MMseqs output"):
        query = aliases.get(edge["query"])
        if query is None or edge["target"] not in membership_by_id:
            raise ValueError(
                f"Unknown endpoint in candidate-vs-all-node output: {edge['query']}->{edge['target']}"
            )
        if not qualifies_30_80(edge):
            continue
        target = membership_by_id[edge["target"]]
        exact = candidate_by_id[query]["sequence_sha256"] == target["sequence_sha256"]
        record = {
            "query_id": query,
            "source_member_id": candidate_by_id[query]["source_member_id"],
            "target_id": edge["target"],
            "target_split": target["split"],
            "target_global_component_id": target["global_component_id"],
            "pident_pct": f"{edge['pident_value']:.6g}",
            "qcov_fraction": f"{edge['qcov_value']:.6g}",
            "tcov_fraction": f"{edge['tcov_value']:.6g}",
            "alignment_length": edge["alnlen"],
            "evalue": edge["evalue"],
            "bit_score": edge["bits"],
            "ordinary_nonexact_relationship": "no" if exact else "yes",
            "_identity": edge["pident_value"],
            "_component": target["global_component_id"],
            "_split": target["split"],
        }
        qualifying_all_node[query].append(record)
        relationship_rows.append(record)

    candidate_edges: list[tuple[str, str]] = []
    for edge in iter_mmseqs(candidate_vs_candidate_path, "candidate-vs-candidate MMseqs output"):
        left, right = aliases.get(edge["query"]), aliases.get(edge["target"])
        if left is None or right is None:
            raise ValueError(
                f"Unknown endpoint in candidate-vs-candidate output: {edge['query']}->{edge['target']}"
            )
        if left == right:
            raise ValueError("Candidate-vs-candidate output must have self edges removed")
        if qualifies_30_80(edge):
            candidate_edges.append((left, right))

    uf = UnionFind(candidate_by_id)
    by_source_cluster: dict[str, list[str]] = defaultdict(list)
    by_all_node_component: dict[str, list[str]] = defaultdict(list)
    for row in candidate_rows:
        by_source_cluster[row["source_cluster_key"]].append(row["protein_id"])
    for values in by_source_cluster.values():
        for value in values[1:]:
            uf.union(values[0], value)
    for left, right in candidate_edges:
        uf.union(left, right)
    for query, relations in qualifying_all_node.items():
        for relation in relations:
            by_all_node_component[relation["_component"]].append(query)
    for values in by_all_node_component.values():
        unique = sorted(set(values))
        for value in unique[1:]:
            uf.union(unique[0], value)
    components: dict[str, list[str]] = defaultdict(list)
    for protein_id in sorted(candidate_by_id):
        components[uf.find(protein_id)].append(protein_id)
    block_by_id: dict[str, str] = {}
    block_rows: list[dict[str, Any]] = []
    for members in sorted(components.values(), key=lambda values: tuple(values)):
        block_id = "HNMB_" + hashlib.sha256("\n".join(members).encode()).hexdigest()[:16]
        for member in members:
            block_by_id[member] = block_id
        block_rows.append(
            {
                "dependence_block_id": block_id,
                "block_size": len(members),
                "source_cluster_count": len(
                    {candidate_by_id[value]["source_cluster_key"] for value in members}
                ),
                "all_node_component_count": len(
                    {
                        relation["_component"]
                        for value in members
                        for relation in qualifying_all_node.get(value, [])
                    }
                ),
                "member_protein_ids": ";".join(members),
            }
        )

    evidence_rows: list[dict[str, Any]] = []
    legal_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    exclusion_counts: Counter[str] = Counter()
    stratum_counts: Counter[str] = Counter()
    for row in candidate_rows:
        protein_id = row["protein_id"]
        sequence_sha = row["sequence_sha256"]
        source_member_id = row["source_member_id"]
        exact_nodes = sha_to_nodes.get(sequence_sha, [])
        exact_id_nodes = [
            membership_by_id[value]
            for value in {protein_id, source_member_id, Path(source_member_id).name}
            if value in membership_by_id
        ]
        exact_splits = sorted({node["split"] for node in exact_nodes + exact_id_nodes})
        positive_exact_sequence = sequence_sha in positive_shas
        positive_exact_accession = accession(source_member_id) in positive_accessions
        mmseqs = positive_mmseqs.get(protein_id)
        hmm = hmm_hits.get(protein_id)
        foldseek = foldseek_hits.get(protein_id)
        hmm_gate = bool(
            hmm
            and hmm["i_evalue"] <= HMM_MAX_IEVALUE
            and hmm["coverage"] >= HMM_MIN_COVERAGE
        )
        structure_gate = bool(
            foldseek
            and foldseek["evalue_value"] <= STRUCTURE_MAX_EVALUE
            and foldseek["prob_value"] >= STRUCTURE_MIN_PROB
            and foldseek["alntmscore_value"] >= STRUCTURE_MIN_ALNTMSCORE
            and foldseek["qcov_value"] >= STRUCTURE_MIN_QCOV
            and foldseek["lddt_value"] >= STRUCTURE_MIN_LDDT
        )
        reasons: list[str] = []
        flags = (
            ("positive_exact_sequence", positive_exact_sequence),
            ("positive_exact_accession", positive_exact_accession),
            ("positive_mmseqs_30_80", mmseqs is not None),
            ("positive_hmm", hmm_gate),
            ("positive_foldseek", structure_gate),
            ("all_node_exact_id_overlap", bool(exact_id_nodes)),
            ("all_node_exact_sequence_overlap", bool(exact_nodes)),
        )
        for reason, present in flags:
            if present:
                reasons.append(reason)
                exclusion_counts[reason] += 1
        train_identities = [
            relation["_identity"]
            for relation in qualifying_all_node.get(protein_id, [])
            if relation["_split"] == "train" and relation["ordinary_nonexact_relationship"] == "yes"
        ]
        stratum = _stratum(max(train_identities) if train_identities else None)
        stratum_counts[stratum] += 1
        evidence = {
            "protein_id": protein_id,
            "source_member_id": source_member_id,
            "paired_representative_id": row["paired_representative_id"],
            "assigned_family": row["assigned_family"],
            "legal": "no" if reasons else "yes",
            "exclusion_reasons": ";".join(reasons),
            "positive_exact_sequence": "yes" if positive_exact_sequence else "no",
            "positive_exact_accession": "yes" if positive_exact_accession else "no",
            "positive_mmseqs_gate": "yes" if mmseqs else "no",
            "positive_mmseqs_target": mmseqs["target"] if mmseqs else "",
            "positive_mmseqs_pident_pct": mmseqs["pident"] if mmseqs else "",
            "positive_mmseqs_qcov": mmseqs["qcov"] if mmseqs else "",
            "positive_mmseqs_tcov": mmseqs["tcov"] if mmseqs else "",
            "positive_hmm_gate": "yes" if hmm_gate else "no",
            "positive_hmm_name": hmm["hmm_name"] if hmm else "",
            "positive_hmm_i_evalue": f"{hmm['i_evalue']:.6g}" if hmm else "",
            "positive_hmm_coverage": f"{hmm['coverage']:.6g}" if hmm else "",
            "positive_structure_gate": "yes" if structure_gate else "no",
            "positive_structure_query": foldseek["query"] if foldseek else "",
            "positive_structure_evalue": foldseek["evalue"] if foldseek else "",
            "positive_structure_prob": foldseek["prob"] if foldseek else "",
            "positive_structure_alntmscore": foldseek["alntmscore"] if foldseek else "",
            "positive_structure_qcov": foldseek["qcov"] if foldseek else "",
            "positive_structure_lddt": foldseek["lddt"] if foldseek else "",
            "all_node_exact_id_overlap": "yes" if exact_id_nodes else "no",
            "all_node_exact_sequence_overlap": "yes" if exact_nodes else "no",
            "exact_overlap_splits": ";".join(exact_splits),
            "cross_split_exact_conflict": "yes" if any(split != "validation" for split in exact_splits) else "no",
            "qualifying_all_node_relationships": len(qualifying_all_node.get(protein_id, [])),
            "train_relationship_stratum": stratum,
            "dependence_block_id": block_by_id[protein_id],
        }
        evidence_rows.append(evidence)
        if reasons:
            excluded_rows.append(evidence)
            continue
        legal = {field: row.get(field, "") for field in LEGAL_FIELDS}
        legal.update(
            {
                "global_component_id": block_by_id[protein_id],
                "paired_representative_protein_id": row.get(
                    "paired_representative_protein_id", ""
                ),
                "split": "robustness_validation",
                "head2_label": "",
                "head3_phylum_label": "",
                "score_head1": "1",
                "score_head2": "0",
                "h3_analysis_included": "0",
                "analysis_included": "1",
                "dependence_block_id": block_by_id[protein_id],
                "train_relationship_stratum": stratum,
                "test_record": "0",
            }
        )
        legal_rows.append(legal)

    legal_ids = {row["protein_id"] for row in legal_rows}
    if len(legal_ids) + len(excluded_rows) != len(candidate_rows):
        raise RuntimeError("Legal/excluded partition does not cover the candidate inventory")
    if legal_ids & {row["protein_id"] for row in excluded_rows}:
        raise RuntimeError("Legal/excluded partition overlaps")

    summary: dict[str, Any] = {
        "schema_version": 1,
        "analysis_id": ANALYSIS_ID,
        "project_version": "V0",
        "status": "PASS" if legal_rows else "FAIL_CLOSED_NO_LEGAL_MEMBERS",
        "artifact_role": "auxiliary_post_freeze_hardnegative_validation_matched_member_robustness",
        "model_state": "frozen",
        "selection_feedback_permitted": False,
        "release_gate": False,
        "training_permitted": False,
        "calibration_fitting_permitted": False,
        "threshold_tuning_permitted": False,
        "test_artifact_access_permitted": False,
        "counts": {
            "candidate_members": len(candidate_rows),
            "legal_members": len(legal_rows),
            "excluded_members": len(excluded_rows),
            "legal_source_clusters": len({row["source_cluster_key"] for row in legal_rows}),
            "dependence_blocks_all_candidates": len(block_rows),
            "ordinary_candidate_all_node_relationships": sum(
                row["ordinary_nonexact_relationship"] == "yes" for row in relationship_rows
            ),
            "exact_candidate_all_node_relationships": sum(
                row["ordinary_nonexact_relationship"] == "no" for row in relationship_rows
            ),
        },
        "exclusion_reason_counts_nonexclusive": dict(sorted(exclusion_counts.items())),
        "train_relationship_stratum_counts_all_candidates": dict(sorted(stratum_counts.items())),
        "thresholds": {
            "mmseqs_min_identity_pct": MIN_IDENTITY_PCT,
            "mmseqs_min_query_coverage": MIN_QUERY_COVERAGE,
            "mmseqs_min_target_coverage": MIN_TARGET_COVERAGE,
            "hmm_max_i_evalue": HMM_MAX_IEVALUE,
            "hmm_min_coverage": HMM_MIN_COVERAGE,
            "foldseek_max_evalue": STRUCTURE_MAX_EVALUE,
            "foldseek_min_probability": STRUCTURE_MIN_PROB,
            "foldseek_min_alntmscore": STRUCTURE_MIN_ALNTMSCORE,
            "foldseek_min_qcov": STRUCTURE_MIN_QCOV,
            "foldseek_min_lddt": STRUCTURE_MIN_LDDT,
            "foldseek_qtmscore_used_for_exclusion": False,
        },
        "label_contract": {
            "head1": "non_djr; only scored head; report false-positive rate/specificity",
            "head2": "not_applicable",
            "head3": "not_applicable",
        },
        "ordinary_homology_policy": (
            "Non-exact 30/80 homology is retained, stratified and block-aware; it is not an exclusion."
        ),
        "input_sha256": {
            "candidate_manifest": file_sha256(candidate_manifest_path),
            "candidate_fasta": file_sha256(candidate_fasta_path),
            "candidate_checksums": file_sha256(candidate_checksums_path),
            "positive_fasta": file_sha256(positive_fasta_path),
            "positive_mmseqs": file_sha256(positive_mmseqs_path),
            "positive_foldseek": file_sha256(positive_foldseek_path),
            "all_node_membership": file_sha256(all_node_membership_path),
            "all_node_fasta": file_sha256(all_node_fasta_path),
            "candidate_vs_all_nodes": file_sha256(candidate_vs_all_nodes_path),
            "candidate_vs_candidate": file_sha256(candidate_vs_candidate_path),
            "run_metadata": file_sha256(run_metadata_path),
            **{
                f"positive_hmm_{index:02d}": file_sha256(path)
                for index, path in enumerate(positive_hmm_paths, 1)
            },
        },
        "run_metadata": run_metadata,
    }
    if not legal_rows:
        raise RuntimeError("Fail closed: positive/exact exclusions left no legal HardNeg members")

    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.building-", dir=output_dir.parent))
    published = False
    try:
        _write_tsv(stage / LEGAL_MANIFEST, legal_rows, LEGAL_FIELDS)
        _write_fasta(stage / LEGAL_FASTA, legal_rows, candidate_sequences)
        _write_tsv(stage / EXCLUDED_ENTITIES, excluded_rows, EVIDENCE_FIELDS)
        _write_tsv(stage / EVIDENCE_NAME, evidence_rows, EVIDENCE_FIELDS)
        _write_tsv(stage / RELATIONSHIP_NAME, relationship_rows, RELATIONSHIP_FIELDS)
        _write_tsv(
            stage / BLOCK_NAME,
            block_rows,
            (
                "dependence_block_id", "block_size", "source_cluster_count",
                "all_node_component_count", "member_protein_ids",
            ),
        )
        (stage / LEGAL_SUMMARY).write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (stage / METADATA_COPY_NAME).write_text(run_metadata_path.read_text(encoding="utf-8"), encoding="utf-8")
        _write_and_verify_legal_checksums(stage)
        targets = [
            LEGAL_MANIFEST, LEGAL_FASTA, LEGAL_SUMMARY, EXCLUDED_ENTITIES,
            LEGAL_CHECKSUM_NAME, EVIDENCE_NAME, RELATIONSHIP_NAME, BLOCK_NAME,
            METADATA_COPY_NAME,
        ]
        _write_checksums(stage, targets)
        _verify_checksums(stage, set(targets))
        try:
            _atomic_rename_noreplace(stage, output_dir)
        except ArchiveError as error:
            if os.path.lexists(output_dir):
                raise FileExistsError(f"Refusing to overwrite output directory: {output_dir}") from error
            raise
        published = True
        return summary
    finally:
        if not published and stage.exists():
            shutil.rmtree(stage)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-manifest", required=True, type=Path)
    parser.add_argument("--candidate-fasta", required=True, type=Path)
    parser.add_argument("--candidate-checksums", required=True, type=Path)
    parser.add_argument("--positive-fasta", required=True, type=Path)
    parser.add_argument("--positive-mmseqs", required=True, type=Path)
    parser.add_argument("--positive-hmm-domtbl", action="append", required=True, type=Path)
    parser.add_argument("--positive-foldseek", required=True, type=Path)
    parser.add_argument("--all-node-membership", required=True, type=Path)
    parser.add_argument("--all-node-fasta", required=True, type=Path)
    parser.add_argument("--candidate-vs-all-nodes", required=True, type=Path)
    parser.add_argument("--candidate-vs-candidate", required=True, type=Path)
    parser.add_argument("--run-metadata", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-candidates", type=int, default=EXPECTED_CANDIDATES)
    parser.add_argument("--expected-all-nodes", type=int, default=EXPECTED_ALL_NODES)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = finalize(
        candidate_manifest_path=args.candidate_manifest,
        candidate_fasta_path=args.candidate_fasta,
        candidate_checksums_path=args.candidate_checksums,
        positive_fasta_path=args.positive_fasta,
        positive_mmseqs_path=args.positive_mmseqs,
        positive_hmm_paths=args.positive_hmm_domtbl,
        positive_foldseek_path=args.positive_foldseek,
        all_node_membership_path=args.all_node_membership,
        all_node_fasta_path=args.all_node_fasta,
        candidate_vs_all_nodes_path=args.candidate_vs_all_nodes,
        candidate_vs_candidate_path=args.candidate_vs_candidate,
        run_metadata_path=args.run_metadata,
        output_dir=args.output_dir,
        expected_candidates=args.expected_candidates,
        expected_all_nodes=args.expected_all_nodes,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
