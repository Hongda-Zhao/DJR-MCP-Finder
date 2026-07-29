#!/usr/bin/env python3
"""Build the frozen HardNeg Validation matched-member candidate inventory.

The builder consumes only provenance artifacts from the successful source
reconstruction.  It selects non-representative members of the 1,000 frozen V0
HardNeg Validation anchors, materializes their original Tier-1 sequences, and
publishes a checksum-bound candidate inventory.  It does not declare a member
legal: positive exclusion and all-node integrity are deliberately separate,
fail-closed steps.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


PROJECT_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_DIR / "src"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from djrmcp_finder.archive import ArchiveError, _atomic_rename_noreplace  # noqa: E402


ANALYSIS_ID = "project_v0_hardnegative_validation_matched_member_inputs"
EXPECTED_STATUS = "FULL_OPERATIONAL_RECOVERY_PASS"
EXPECTED_MEMBER_MAP_ROWS = 36_138
EXPECTED_CLUSTER_REPRESENTATIVES = 10_880
EXPECTED_SELECTED_HARDNEG_ROWS = 5_000
EXPECTED_VALIDATION_ANCHORS = 1_000
EXPECTED_VALIDATION_MEMBERS = 3_478
EXPECTED_VALIDATION_CLUSTERS_WITH_MEMBERS = 382

MANIFEST_NAME = "candidate_manifest.tsv"
FASTA_NAME = "candidate_sequences.faa"
INPUT_CHECKSUM_NAME = "INPUT_CHECKSUMS.tsv"
SUMMARY_NAME = "summary.json"
CHECKSUM_NAME = "CHECKSUMS.sha256"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

MANIFEST_FIELDS = (
    "protein_id",
    "source_member_id",
    "source_dataset",
    "source_cluster_id",
    "source_cluster_key",
    "paired_representative_id",
    "paired_representative_protein_id",
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
    "assigned_family",
    "tier",
    "dataset_scope",
    "query",
    "query_family",
    "hmm_name",
    "hmm_family",
    "hmm_concordant",
    "taxid",
    "taxname",
    "source_fasta_record_id",
    "source_reconstruction_status",
    "test_record",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sequence_sha256(sequence: str) -> str:
    return hashlib.sha256(sequence.encode("ascii")).hexdigest()


def _require_file(path: Path, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(f"{label} must be an existing regular file: {path}")


def _valid_sha(value: str, context: str) -> str:
    normalized = value.strip().lower()
    if not SHA256_RE.fullmatch(normalized):
        raise ValueError(f"Invalid SHA-256 for {context}: {value!r}")
    return normalized


def read_tsv(path: Path, required: Iterable[str], label: str) -> list[dict[str, str]]:
    _require_file(path, label)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = list(reader.fieldnames or [])
        if not fields or len(fields) != len(set(fields)):
            raise ValueError(f"{label} has an empty or duplicate TSV header: {path}")
        missing = sorted(set(required) - set(fields))
        if missing:
            raise ValueError(f"{label} is missing fields {missing}: {path}")
        rows: list[dict[str, str]] = []
        for line_number, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Malformed {label} row at {path}:{line_number}")
            rows.append({key: value.strip() for key, value in row.items()})
    if not rows:
        raise ValueError(f"{label} is empty: {path}")
    return rows


def unique_index(
    rows: Iterable[dict[str, str]], field: str, label: str
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        key = row[field]
        if not key:
            raise ValueError(f"Empty {field} in {label}")
        if key in result:
            raise ValueError(f"Duplicate {field} in {label}: {key}")
        result[key] = row
    return result


def read_recovery_status(path: Path) -> dict[str, str]:
    _require_file(path, "recovery status")
    result: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for line_number, fields in enumerate(csv.reader(handle, delimiter="\t"), 1):
            if not fields or not any(fields):
                continue
            if len(fields) != 2 or not fields[0] or fields[0] in result:
                raise ValueError(f"Malformed/duplicate recovery status row at {path}:{line_number}")
            result[fields[0].strip()] = fields[1].strip()
    if result.get("status") != EXPECTED_STATUS:
        raise ValueError(
            f"HardNeg source reconstruction is not FULL PASS: {result.get('status')!r}"
        )
    return result


def read_fasta_files(paths: list[Path]) -> tuple[dict[str, str], dict[str, str]]:
    records: dict[str, str] = {}
    sources: dict[str, str] = {}
    if not paths:
        raise ValueError("At least one Tier-1 FASTA is required")
    for path in paths:
        _require_file(path, "Tier-1 FASTA")
        record_id: str | None = None
        chunks: list[str] = []

        def flush() -> None:
            nonlocal record_id, chunks
            if record_id is None:
                return
            sequence = "".join(chunks).replace(" ", "").upper().rstrip("*")
            if not sequence or not sequence.isascii() or not sequence.isalpha():
                raise ValueError(f"Invalid/empty Tier-1 FASTA sequence: {path}:{record_id}")
            if record_id in records:
                raise ValueError(f"Duplicate Tier-1 FASTA record ID: {record_id}")
            records[record_id] = sequence
            sources[record_id] = str(path)

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
                        raise ValueError(f"Sequence before first FASTA header at {path}:{line_number}")
                    chunks.append("".join(line.split()))
        flush()
    return records, sources


def _write_tsv(path: Path, rows: Iterable[dict[str, Any]], fields: Iterable[str]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_fasta(path: Path, rows: list[dict[str, Any]], sequences: dict[str, str]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            protein_id = str(row["protein_id"])
            member_id = str(row["source_member_id"])
            sequence = sequences[member_id]
            handle.write(
                f">{protein_id} source_member={member_id} "
                f"paired_representative={row['paired_representative_id']} "
                f"sha256={row['sequence_sha256']}\n"
            )
            for start in range(0, len(sequence), 80):
                handle.write(sequence[start : start + 80] + "\n")


def _write_checksums(directory: Path) -> None:
    names = (FASTA_NAME, INPUT_CHECKSUM_NAME, MANIFEST_NAME, SUMMARY_NAME)
    with (directory / CHECKSUM_NAME).open("x", encoding="utf-8") as handle:
        for name in sorted(names):
            handle.write(f"{file_sha256(directory / name)}  {name}\n")


def _verify_checksums(directory: Path) -> None:
    observed: set[str] = set()
    for line_number, raw in enumerate(
        (directory / CHECKSUM_NAME).read_text(encoding="utf-8").splitlines(), 1
    ):
        fields = raw.split(maxsplit=1)
        if len(fields) != 2:
            raise RuntimeError(f"Malformed checksum row {line_number}")
        expected, name = fields[0], fields[1].strip().lstrip("*")
        if Path(name).name != name or name in observed:
            raise RuntimeError(f"Unsafe or duplicate checksum target: {name}")
        if file_sha256(directory / name) != expected:
            raise RuntimeError(f"Checksum mismatch: {name}")
        observed.add(name)
    if observed != {FASTA_NAME, INPUT_CHECKSUM_NAME, MANIFEST_NAME, SUMMARY_NAME}:
        raise RuntimeError("Checksum target set mismatch")


def _validation_anchors(
    master_rows: list[dict[str, str]], representative_ids: set[str]
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in master_rows:
        source = row["source_dataset"].lower()
        if source not in {"hard_non_djr", "hard_negative", "hardnegative", "selected_hardneg"}:
            continue
        if row["split"].lower() != "validation":
            continue
        candidates = (
            row["source_cluster_id"],
            row["source_sequence_id"],
            row["protein_id"].removeprefix("HARD__"),
        )
        resolved = sorted({value for value in candidates if value in representative_ids})
        if len(resolved) != 1:
            raise ValueError(
                f"HardNeg Validation anchor does not resolve uniquely: "
                f"{row['protein_id']} -> {resolved}"
            )
        representative = resolved[0]
        if representative in result:
            raise ValueError(f"Duplicate HardNeg Validation anchor: {representative}")
        result[representative] = row
    return result


def build(
    *,
    recovery_status_path: Path,
    member_map_path: Path,
    master_manifest_path: Path,
    integrated_candidates_path: Path,
    tier1_fasta_paths: list[Path],
    output_dir: Path,
    expected_member_map_rows: int = EXPECTED_MEMBER_MAP_ROWS,
    expected_cluster_representatives: int = EXPECTED_CLUSTER_REPRESENTATIVES,
    expected_selected_hardneg_rows: int = EXPECTED_SELECTED_HARDNEG_ROWS,
    expected_validation_anchors: int = EXPECTED_VALIDATION_ANCHORS,
    expected_validation_members: int = EXPECTED_VALIDATION_MEMBERS,
    expected_validation_clusters_with_members: int = EXPECTED_VALIDATION_CLUSTERS_WITH_MEMBERS,
) -> dict[str, Any]:
    """Build and atomically publish the matched-member candidate inventory."""

    if os.path.lexists(output_dir):
        raise FileExistsError(f"Refusing to overwrite output directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    recovery = read_recovery_status(recovery_status_path)

    member_rows = read_tsv(
        member_map_path,
        ("family_id", "cluster_representative", "member", "member_sequence_sha256"),
        "recovered member map",
    )
    if len(member_rows) != expected_member_map_rows:
        raise ValueError(
            f"Recovered member-map row count mismatch: expected={expected_member_map_rows}, "
            f"observed={len(member_rows)}"
        )
    member_by_id = unique_index(member_rows, "member", "recovered member map")
    representative_ids = {row["cluster_representative"] for row in member_rows}
    if len(representative_ids) != expected_cluster_representatives:
        raise ValueError(
            "Recovered representative count mismatch: "
            f"expected={expected_cluster_representatives}, observed={len(representative_ids)}"
        )
    self_representatives = {
        row["member"] for row in member_rows if row["member"] == row["cluster_representative"]
    }
    if self_representatives != representative_ids:
        raise ValueError("Recovered member map lacks exactly one self row per representative")
    for row in member_rows:
        row["member_sequence_sha256"] = _valid_sha(
            row["member_sequence_sha256"], row["member"]
        )

    integrated_rows = read_tsv(
        integrated_candidates_path,
        ("target", "tier", "assigned_family", "sequence_sha256"),
        "integrated candidates",
    )
    integrated_by_id = unique_index(integrated_rows, "target", "integrated candidates")
    if not set(member_by_id).issubset(integrated_by_id):
        missing = sorted(set(member_by_id) - set(integrated_by_id))[:5]
        raise ValueError(
            f"Integrated candidates do not cover the legacy4 member map: missing={missing}"
        )
    # The integration table contains every strict candidate (including records
    # outside the Tier-1 cluster input).  Only IDs explicitly present in the
    # recovered legacy4 member map are in scope for this matched-member audit.
    for member_id in member_by_id:
        row = integrated_by_id[member_id]
        integrated_sha = _valid_sha(row["sequence_sha256"], member_id)
        if integrated_sha != member_by_id[member_id]["member_sequence_sha256"]:
            raise ValueError(f"Integrated/member-map sequence SHA mismatch: {member_id}")
        if row["assigned_family"] != member_by_id[member_id]["family_id"]:
            raise ValueError(f"Integrated/member-map family mismatch: {member_id}")

    master_rows = read_tsv(
        master_manifest_path,
        (
            "protein_id",
            "source_dataset",
            "source_cluster_id",
            "source_sequence_id",
            "global_component_id",
            "split",
        ),
        "V0 master manifest",
    )
    hard_rows = [row for row in master_rows if row["source_dataset"] == "hard_non_djr"]
    if len(hard_rows) != expected_selected_hardneg_rows:
        raise ValueError(
            f"Selected HardNeg master rows mismatch: expected={expected_selected_hardneg_rows}, "
            f"observed={len(hard_rows)}"
        )
    anchors = _validation_anchors(master_rows, representative_ids)
    if len(anchors) != expected_validation_anchors:
        raise ValueError(
            f"HardNeg Validation anchor mismatch: expected={expected_validation_anchors}, "
            f"observed={len(anchors)}"
        )

    candidate_source_rows = [
        row
        for row in member_rows
        if row["cluster_representative"] in anchors
        and row["member"] != row["cluster_representative"]
    ]
    candidate_source_rows.sort(key=lambda row: (row["cluster_representative"], row["member"]))
    clusters_with_members = {row["cluster_representative"] for row in candidate_source_rows}
    if len(candidate_source_rows) != expected_validation_members:
        raise ValueError(
            f"HardNeg Validation member count mismatch: expected={expected_validation_members}, "
            f"observed={len(candidate_source_rows)}"
        )
    if len(clusters_with_members) != expected_validation_clusters_with_members:
        raise ValueError(
            "HardNeg Validation non-singleton cluster count mismatch: "
            f"expected={expected_validation_clusters_with_members}, "
            f"observed={len(clusters_with_members)}"
        )

    sequences, sequence_sources = read_fasta_files(tier1_fasta_paths)
    if not set(member_by_id).issubset(sequences):
        missing = sorted(set(member_by_id) - set(sequences))[:5]
        raise ValueError(f"Tier-1 FASTAs do not cover the legacy4 member map: missing={missing}")
    for member_id in member_by_id:
        sequence = sequences[member_id]
        if sequence_sha256(sequence) != member_by_id[member_id]["member_sequence_sha256"]:
            raise ValueError(f"Tier-1 FASTA/member-map sequence SHA mismatch: {member_id}")

    manifest: list[dict[str, Any]] = []
    family_counts: Counter[str] = Counter()
    cluster_member_counts: Counter[str] = Counter()
    for index, source_row in enumerate(candidate_source_rows, 1):
        representative = source_row["cluster_representative"]
        member_id = source_row["member"]
        anchor = anchors[representative]
        integrated = integrated_by_id[member_id]
        protein_id = f"HNMM_V0_{index:06d}"
        family_counts[source_row["family_id"]] += 1
        cluster_member_counts[representative] += 1
        manifest.append(
            {
                "protein_id": protein_id,
                "source_member_id": member_id,
                "source_dataset": "hard_non_djr",
                "source_cluster_id": representative,
                "source_cluster_key": f"hard_non_djr::{representative}",
                "paired_representative_id": representative,
                "paired_representative_protein_id": anchor["protein_id"],
                "original_global_component_id": anchor["global_component_id"],
                "parent_split": "validation",
                "split": "validation_matched_member",
                "sequence_sha256": source_row["member_sequence_sha256"],
                "length_aa": len(sequences[member_id]),
                "head1_label": "non_djr",
                "head1_mask": "1",
                "head2_label": "",
                "head2_mask": "0",
                "head3_phylum_label": "",
                "head3_mask": "0",
                "score_head1": "1",
                "score_head2": "0",
                "h3_analysis_included": "0",
                "analysis_included": "0",
                "assigned_family": source_row["family_id"],
                "tier": integrated.get("tier", ""),
                "dataset_scope": integrated.get("dataset_scope", ""),
                "query": integrated.get("query", ""),
                "query_family": integrated.get("query_family", ""),
                "hmm_name": integrated.get("hmm_name", ""),
                "hmm_family": integrated.get("hmm_family", ""),
                "hmm_concordant": integrated.get("hmm_concordant", ""),
                "taxid": integrated.get("taxid", ""),
                "taxname": integrated.get("taxname", ""),
                "source_fasta_record_id": member_id,
                "source_reconstruction_status": EXPECTED_STATUS,
                "test_record": "0",
            }
        )

    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.building-", dir=output_dir.parent))
    published = False
    try:
        _write_tsv(stage / MANIFEST_NAME, manifest, MANIFEST_FIELDS)
        _write_fasta(stage / FASTA_NAME, manifest, sequences)
        input_rows = []
        input_specs = [
            ("recovery_status", recovery_status_path),
            ("member_map", member_map_path),
            ("master_manifest", master_manifest_path),
            ("integrated_candidates", integrated_candidates_path),
        ] + [("tier1_fasta", path) for path in sorted(tier1_fasta_paths)]
        for role, path in input_specs:
            input_rows.append(
                {
                    "role": role,
                    "path": str(path.resolve()),
                    "sha256": file_sha256(path),
                    "size_bytes": path.stat().st_size,
                }
            )
        _write_tsv(
            stage / INPUT_CHECKSUM_NAME,
            input_rows,
            ("role", "path", "sha256", "size_bytes"),
        )
        summary: dict[str, Any] = {
            "schema_version": 1,
            "analysis_id": ANALYSIS_ID,
            "project_version": "V0",
            "status": "candidate_inventory_complete_integrity_pending",
            "source_reconstruction_status": recovery["status"],
            "artifact_role": "auxiliary_post_freeze_hardnegative_validation_matched_members",
            "model_state": "frozen",
            "selection_feedback_permitted": False,
            "release_gate": False,
            "training_permitted": False,
            "calibration_fitting_permitted": False,
            "threshold_tuning_permitted": False,
            "test_artifact_access_permitted": False,
            "counts": {
                "recovered_member_map_rows": len(member_rows),
                "recovered_cluster_representatives": len(representative_ids),
                "selected_hardnegative_master_rows": len(hard_rows),
                "validation_anchors": len(anchors),
                "validation_clusters_with_nonrepresentative_members": len(clusters_with_members),
                "validation_singleton_clusters": len(anchors) - len(clusters_with_members),
                "candidate_nonrepresentative_members": len(manifest),
                "candidate_unique_sequence_sha256": len({row["sequence_sha256"] for row in manifest}),
                "integrated_candidate_rows_total": len(integrated_rows),
                "integrated_candidate_rows_outside_legacy4": len(integrated_by_id) - len(member_by_id),
                "tier1_fasta_records": len(sequences),
                "tier1_fasta_records_outside_legacy4": len(sequences) - len(member_by_id),
            },
            "candidate_family_counts": dict(sorted(family_counts.items())),
            "validation_cluster_member_count_range": {
                "minimum": min(cluster_member_counts.values()) if cluster_member_counts else 0,
                "maximum": max(cluster_member_counts.values()) if cluster_member_counts else 0,
            },
            "label_contract": {
                "head1": "non_djr (score; expected negative)",
                "head2": "not_applicable",
                "head3": "not_applicable",
            },
            "integrity": {
                "full_recovery_pass_required": True,
                "member_map_ids_subset_of_integrated_candidates": True,
                "member_map_ids_subset_of_tier1_fastas": True,
                "integrated_non_member_map_records_ignored": True,
                "sequence_sha256_verified_for_all_records": True,
                "positive_exclusion_complete": False,
                "all_node_integrity_complete": False,
                "eligible_for_scoring": False,
            },
            "interpretation": (
                "These are reconstructed non-representative members of frozen HardNeg "
                "Validation source clusters. They remain candidates until per-member exact, "
                "MMseqs2, HMM and Foldseek positive exclusion plus all-node integrity pass."
            ),
        }
        (stage / SUMMARY_NAME).write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _write_checksums(stage)
        _verify_checksums(stage)
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
    parser.add_argument("--recovery-status", required=True, type=Path)
    parser.add_argument("--member-map", required=True, type=Path)
    parser.add_argument("--master-manifest", required=True, type=Path)
    parser.add_argument("--integrated-candidates", required=True, type=Path)
    parser.add_argument("--tier1-fasta", action="append", default=[], type=Path)
    parser.add_argument(
        "--tier1-fasta-dir",
        action="append",
        default=[],
        type=Path,
        help="Directory searched non-recursively for tier1__*.faa files.",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-member-map-rows", type=int, default=EXPECTED_MEMBER_MAP_ROWS)
    parser.add_argument(
        "--expected-cluster-representatives", type=int, default=EXPECTED_CLUSTER_REPRESENTATIVES
    )
    parser.add_argument(
        "--expected-selected-hardneg-rows", type=int, default=EXPECTED_SELECTED_HARDNEG_ROWS
    )
    parser.add_argument(
        "--expected-validation-anchors", type=int, default=EXPECTED_VALIDATION_ANCHORS
    )
    parser.add_argument(
        "--expected-validation-members", type=int, default=EXPECTED_VALIDATION_MEMBERS
    )
    parser.add_argument(
        "--expected-validation-clusters-with-members",
        type=int,
        default=EXPECTED_VALIDATION_CLUSTERS_WITH_MEMBERS,
    )
    args = parser.parse_args()
    for directory in args.tier1_fasta_dir:
        if not directory.is_dir():
            parser.error(f"Tier-1 FASTA directory does not exist: {directory}")
        args.tier1_fasta.extend(sorted(directory.glob("tier1__*.faa")))
    # De-duplicate only exact repeated paths while preserving deterministic order.
    args.tier1_fasta = sorted({path.resolve() for path in args.tier1_fasta})
    if not args.tier1_fasta:
        parser.error("At least one --tier1-fasta or --tier1-fasta-dir is required")
    return args


def main() -> int:
    args = parse_args()
    summary = build(
        recovery_status_path=args.recovery_status,
        member_map_path=args.member_map,
        master_manifest_path=args.master_manifest,
        integrated_candidates_path=args.integrated_candidates,
        tier1_fasta_paths=args.tier1_fasta,
        output_dir=args.output_dir,
        expected_member_map_rows=args.expected_member_map_rows,
        expected_cluster_representatives=args.expected_cluster_representatives,
        expected_selected_hardneg_rows=args.expected_selected_hardneg_rows,
        expected_validation_anchors=args.expected_validation_anchors,
        expected_validation_members=args.expected_validation_members,
        expected_validation_clusters_with_members=args.expected_validation_clusters_with_members,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
