#!/usr/bin/env python3
"""Independent post-split sequence-integrity audit for the V0 dataset.

The audit has two deliberately separate phases:

* ``prepare`` reconstructs all-node train/validation/test FASTAs from the
  finalized manifest and membership tables, while independently checking the
  component and exact-sequence split barriers.
* ``finalize`` re-reads the membership contract and evaluates three directional
  MMseqs2 searches.  It fails closed on any qualifying similarity edge, exact
  SHA duplicate, component overlap, self-ID collision, or direction mismatch.

MMseqs2 itself is run by ``pbs/05_postsplit_integrity_audit.pbs`` so this module
remains unit-testable without an MMseqs2 installation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


ACTIVE_SPLITS = ("train", "validation", "test")
DIRECTIONS = (
    ("validation_vs_train", "validation", "train"),
    ("test_vs_train", "test", "train"),
    ("test_vs_validation", "test", "validation"),
)
MMSEQS_FIELDS = (
    "query",
    "target",
    "pident",
    "qcov",
    "tcov",
    "alnlen",
    "evalue",
    "bits",
)
REPORT_FIELDS = (
    "query_id",
    "target_id",
    "pident_raw",
    "identity_fraction",
    "qcov_raw",
    "qcov_fraction",
    "tcov_raw",
    "tcov_fraction",
    "alignment_length",
    "evalue",
    "bit_score",
    "query_split",
    "target_split",
    "query_component_id",
    "target_component_id",
    "query_sha256",
    "target_sha256",
    "self_id",
    "exact_sha",
    "same_component",
    "qualifying",
    "violation_reasons",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def sequence_sha256(sequence: str) -> str:
    return hashlib.sha256(sequence.encode()).hexdigest()


def read_tsv(path: Path, required_fields: Iterable[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"TSV has no header: {path}")
        missing = sorted(set(required_fields) - set(reader.fieldnames))
        if missing:
            raise ValueError(f"TSV {path} is missing fields: {missing}")
        return list(reader)


def index_unique(
    rows: list[dict[str, str]], key: str, *, label: str
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row_number, row in enumerate(rows, start=2):
        value = row[key].strip()
        if not value:
            raise ValueError(f"Empty {key} in {label} at data row {row_number}")
        if value in result:
            raise ValueError(f"Duplicate {key} in {label}: {value}")
        result[value] = row
    return result


def read_fasta(path: Path) -> dict[str, str]:
    records: dict[str, str] = {}
    record_id: str | None = None
    chunks: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if record_id is not None:
                    if record_id in records:
                        raise ValueError(f"Duplicate FASTA ID in {path}: {record_id}")
                    records[record_id] = "".join(chunks).upper()
                record_id = line[1:].split()[0]
                if not record_id:
                    raise ValueError(f"Empty FASTA ID at {path}:{line_number}")
                chunks = []
            else:
                if record_id is None:
                    raise ValueError(f"Sequence before first FASTA header at {path}:{line_number}")
                chunks.append("".join(line.split()))
    if record_id is not None:
        if record_id in records:
            raise ValueError(f"Duplicate FASTA ID in {path}: {record_id}")
        records[record_id] = "".join(chunks).upper()
    return records


def write_fasta(path: Path, records: Iterable[tuple[str, str]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record_id, sequence in records:
            handle.write(f">{record_id}\n")
            for start in range(0, len(sequence), 80):
                handle.write(sequence[start : start + 80] + "\n")


def write_tsv(path: Path, rows: Iterable[dict[str, object]], fields: Iterable[str]) -> None:
    field_list = list(fields)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=field_list, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in field_list})


def write_checksums(directory: Path) -> None:
    targets = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.name != "CHECKSUMS.sha256"
    )
    text = "".join(f"{file_sha256(path)}  {path.name}\n" for path in targets)
    (directory / "CHECKSUMS.sha256").write_text(text, encoding="utf-8")


def verify_checksums(directory: Path) -> None:
    checksum_path = directory / "CHECKSUMS.sha256"
    if not checksum_path.is_file():
        raise ValueError(f"Missing checksum manifest: {checksum_path}")
    with checksum_path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.rstrip("\n")
            if not line:
                continue
            try:
                expected, relative = line.split("  ", 1)
            except ValueError as error:
                raise ValueError(
                    f"Malformed checksum line at {checksum_path}:{line_number}"
                ) from error
            target = directory / relative
            if not target.is_file():
                raise ValueError(f"Checksummed preparation file is absent: {target}")
            observed = file_sha256(target)
            if observed != expected:
                raise ValueError(
                    f"Preparation checksum mismatch for {target}: {observed} != {expected}"
                )


def split_key_violations(
    membership_rows: list[dict[str, str]], field: str, violation_type: str
) -> list[dict[str, object]]:
    by_key: defaultdict[str, defaultdict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in membership_rows:
        split = row["split"].strip()
        if split not in ACTIVE_SPLITS:
            continue
        key = row[field].strip()
        if not key:
            raise ValueError(f"Active node {row['node_id']} has an empty {field}")
        by_key[key][split].append(row["node_id"])

    violations: list[dict[str, object]] = []
    for key, split_nodes in sorted(by_key.items()):
        if len(split_nodes) < 2:
            continue
        nodes = sorted(node for values in split_nodes.values() for node in values)
        violations.append(
            {
                "violation_type": violation_type,
                "key": key,
                "splits": ",".join(sorted(split_nodes)),
                "node_count": len(nodes),
                "node_ids": ",".join(nodes),
            }
        )
    return violations


def cross_split_violations(
    membership_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    return split_key_violations(
        membership_rows, "global_component_id", "component_cross_split"
    ) + split_key_violations(
        membership_rows, "sequence_sha256", "exact_sha_cross_split"
    )


def _source_record(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def prepare_audit(
    *,
    master_manifest_path: Path,
    quarantine_manifest_path: Path,
    membership_path: Path,
    component_fasta_path: Path,
    model_fasta_path: Path,
    member_fasta_paths: list[Path],
    output_dir: Path,
) -> dict[str, object]:
    """Validate finalized inputs and materialize all-node split FASTAs."""

    temporary = output_dir.with_name(output_dir.name + ".building")
    if output_dir.exists() or temporary.exists():
        raise FileExistsError(f"Refusing to overwrite integrity-audit inputs: {output_dir}")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.mkdir()

    master_rows = read_tsv(
        master_manifest_path,
        ("protein_id", "global_component_id", "split", "sequence_sha256"),
    )
    master_by_id = index_unique(master_rows, "protein_id", label="master manifest")
    quarantine_rows = read_tsv(
        quarantine_manifest_path,
        ("protein_id", "global_component_id", "reason"),
    )
    quarantine_by_id = index_unique(
        quarantine_rows, "protein_id", label="quarantine manifest"
    )
    overlap = sorted(set(master_by_id) & set(quarantine_by_id))[:5]
    if overlap:
        raise ValueError(f"Protein IDs occur in both master and quarantine manifests: {overlap}")
    membership_rows = read_tsv(
        membership_path,
        (
            "node_id",
            "source_dataset",
            "source_cluster_id",
            "is_model_representative",
            "model_protein_id",
            "global_component_id",
            "split",
            "sequence_sha256",
        ),
    )
    membership_by_id = index_unique(
        membership_rows, "node_id", label="component membership"
    )
    component_sequences = read_fasta(component_fasta_path)
    model_sequences = read_fasta(model_fasta_path)
    member_sources = [(path, read_fasta(path)) for path in member_fasta_paths]

    membership_ids = set(membership_by_id)
    if set(component_sequences) != membership_ids:
        missing = sorted(membership_ids - set(component_sequences))[:5]
        extra = sorted(set(component_sequences) - membership_ids)[:5]
        raise ValueError(
            "component_input FASTA IDs differ from membership IDs; "
            f"missing={missing}, extra={extra}"
        )

    model_node_ids: set[str] = set()
    for node_id, row in membership_by_id.items():
        marker = row["is_model_representative"].strip()
        if marker not in {"0", "1"}:
            raise ValueError(f"Invalid is_model_representative for {node_id}: {marker!r}")
        split = row["split"].strip()
        if split not in {*ACTIVE_SPLITS, "quarantine"}:
            raise ValueError(f"Unexpected split for {node_id}: {split!r}")
        observed_sha = sequence_sha256(component_sequences[node_id])
        if observed_sha != row["sequence_sha256"].strip():
            raise ValueError(f"Membership sequence SHA mismatch for node {node_id}")
        if marker == "1":
            model_id = row["model_protein_id"].strip()
            if model_id != node_id:
                raise ValueError(
                    f"Model node {node_id} has inconsistent model_protein_id {model_id!r}"
                )
            model_node_ids.add(node_id)

    if set(model_sequences) != model_node_ids:
        missing = sorted(model_node_ids - set(model_sequences))[:5]
        extra = sorted(set(model_sequences) - model_node_ids)[:5]
        raise ValueError(
            "Model FASTA IDs differ from model representatives in membership; "
            f"missing={missing}, extra={extra}"
        )
    for model_id, sequence in model_sequences.items():
        if sequence != component_sequences[model_id]:
            raise ValueError(f"Model/component FASTA sequence mismatch for {model_id}")

    for path, member_sequences in member_sources:
        unknown = sorted(set(member_sequences) - membership_ids)[:5]
        if unknown:
            raise ValueError(f"Member FASTA {path} has IDs absent from membership: {unknown}")
        for node_id, sequence in member_sequences.items():
            if sequence != component_sequences[node_id]:
                raise ValueError(f"Member/component FASTA sequence mismatch for {node_id}")

    expected_model_ids = set(master_by_id) | set(quarantine_by_id)
    if expected_model_ids != model_node_ids:
        missing = sorted(model_node_ids - expected_model_ids)[:5]
        extra = sorted(expected_model_ids - model_node_ids)[:5]
        raise ValueError(
            "Master plus quarantine manifest IDs differ from model membership; "
            f"missing={missing}, extra={extra}"
        )
    for protein_id, master_row in master_by_id.items():
        membership_row = membership_by_id[protein_id]
        if master_row["split"].strip() not in ACTIVE_SPLITS:
            raise ValueError(
                f"Master manifest protein {protein_id} has non-active split "
                f"{master_row['split']!r}"
            )
        for field in ("split", "global_component_id", "sequence_sha256"):
            if master_row[field].strip() != membership_row[field].strip():
                raise ValueError(f"Master/membership {field} mismatch for {protein_id}")
        if master_row["sequence_sha256"].strip() != sequence_sha256(
            model_sequences[protein_id]
        ):
            raise ValueError(f"Master/model FASTA sequence SHA mismatch for {protein_id}")
    for protein_id, quarantine_row in quarantine_by_id.items():
        membership_row = membership_by_id[protein_id]
        if (
            quarantine_row["global_component_id"].strip()
            != membership_row["global_component_id"].strip()
        ):
            raise ValueError(
                f"Quarantine/membership global_component_id mismatch for {protein_id}"
            )

    split_nodes: dict[str, list[str]] = {split: [] for split in ACTIVE_SPLITS}
    quarantine_split_count = 0
    inventory_rows: list[dict[str, object]] = []
    for node_id, row in membership_by_id.items():
        split = row["split"].strip()
        if split == "quarantine":
            quarantine_split_count += 1
            continue
        split_nodes[split].append(node_id)
        inventory_rows.append(
            {
                "node_id": node_id,
                "split": split,
                "global_component_id": row["global_component_id"],
                "sequence_sha256": row["sequence_sha256"],
                "is_model_representative": row["is_model_representative"],
                "model_protein_id": row["model_protein_id"],
                "source_dataset": row["source_dataset"],
                "source_cluster_id": row["source_cluster_id"],
            }
        )

    for split, node_ids in split_nodes.items():
        node_ids.sort()
        write_fasta(
            temporary / f"{split}_all_nodes.faa",
            ((node_id, component_sequences[node_id]) for node_id in node_ids),
        )

    inventory_fields = (
        "node_id",
        "split",
        "global_component_id",
        "sequence_sha256",
        "is_model_representative",
        "model_protein_id",
        "source_dataset",
        "source_cluster_id",
    )
    write_tsv(
        temporary / "node_inventory.tsv",
        sorted(inventory_rows, key=lambda row: (str(row["split"]), str(row["node_id"]))),
        inventory_fields,
    )

    violations = cross_split_violations(membership_rows)
    write_tsv(
        temporary / "preflight_violations.tsv",
        violations,
        ("violation_type", "key", "splits", "node_count", "node_ids"),
    )
    violation_counts = Counter(str(row["violation_type"]) for row in violations)
    split_model_counts = Counter(
        row["split"].strip()
        for row in membership_rows
        if row["split"].strip() in ACTIVE_SPLITS
        and row["is_model_representative"].strip() == "1"
    )
    split_component_counts = {
        split: len(
            {
                row["global_component_id"].strip()
                for row in membership_rows
                if row["split"].strip() == split
            }
        )
        for split in ACTIVE_SPLITS
    }
    source_files = {
        "master_manifest": _source_record(master_manifest_path),
        "quarantine_manifest": _source_record(quarantine_manifest_path),
        "membership": _source_record(membership_path),
        "component_fasta": _source_record(component_fasta_path),
        "model_fasta": _source_record(model_fasta_path),
        "member_fastas": [_source_record(path) for path in member_fasta_paths],
    }
    summary: dict[str, object] = {
        "audit_schema_version": 1,
        "phase": "prepare",
        "status": "pass" if not violations else "fail",
        "source_files": source_files,
        "counts": {
            "master_manifest_rows": len(master_rows),
            "quarantined_model_representatives": len(quarantine_rows),
            "membership_rows": len(membership_rows),
            "component_fasta_records": len(component_sequences),
            "model_fasta_records": len(model_sequences),
            "component_member_records": len(component_sequences) - len(model_sequences),
            "member_fasta_records": {
                str(path): len(records) for path, records in member_sources
            },
            "split_all_nodes": {split: len(split_nodes[split]) for split in ACTIVE_SPLITS},
            "split_model_representatives": {
                split: split_model_counts[split] for split in ACTIVE_SPLITS
            },
            "split_components": split_component_counts,
            "membership_quarantine_split_nodes": quarantine_split_count,
            "violations": dict(sorted(violation_counts.items())),
        },
        "policies": {
            "active_splits": list(ACTIVE_SPLITS),
            "quarantined_models": (
                "validated through quarantine_manifest and retained whenever their component "
                "belongs to an active split"
            ),
            "quarantine_split": (
                "membership rows explicitly assigned split=quarantine are validated against "
                "source files but excluded from search FASTAs"
            ),
            "exact_sequence": "same sequence_sha256 may not occur in multiple active splits",
            "component": "same global_component_id may not occur in multiple active splits",
            "self": "directional searches are cross-split; query_id == target_id is invalid",
        },
    }
    (temporary / "PREPARATION.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_checksums(temporary)
    os.replace(temporary, output_dir)
    return summary


def metric_fraction(raw: str, *, field: str, source: Path, line_number: int) -> float:
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(
            f"Invalid {field} at {source}:{line_number}: {raw!r}"
        ) from error
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"Invalid {field} at {source}:{line_number}: {raw!r}")
    if value <= 1.0:
        return value
    if value <= 100.0:
        return value / 100.0
    raise ValueError(f"Out-of-range {field} at {source}:{line_number}: {raw!r}")


def audit_direction(
    *,
    raw_path: Path,
    report_path: Path,
    query_split: str,
    target_split: str,
    membership: dict[str, dict[str, str]],
    min_identity: float,
    min_qcov: float,
    min_tcov: float,
) -> dict[str, object]:
    counters: Counter[str] = Counter()
    with raw_path.open(encoding="utf-8", newline="") as raw_handle, report_path.open(
        "w", encoding="utf-8", newline=""
    ) as report_handle:
        writer = csv.DictWriter(
            report_handle,
            fieldnames=list(REPORT_FIELDS),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for line_number, raw in enumerate(raw_handle, start=1):
            line = raw.rstrip("\r\n")
            if not line:
                continue
            values = line.split("\t")
            if len(values) != len(MMSEQS_FIELDS):
                raise ValueError(
                    f"Expected {len(MMSEQS_FIELDS)} MMseqs fields at "
                    f"{raw_path}:{line_number}, observed {len(values)}"
                )
            hit = dict(zip(MMSEQS_FIELDS, values))
            counters["raw_rows"] += 1
            identity = metric_fraction(
                hit["pident"], field="pident", source=raw_path, line_number=line_number
            )
            qcov = metric_fraction(
                hit["qcov"], field="qcov", source=raw_path, line_number=line_number
            )
            tcov = metric_fraction(
                hit["tcov"], field="tcov", source=raw_path, line_number=line_number
            )
            qualifying = (
                identity >= min_identity and qcov >= min_qcov and tcov >= min_tcov
            )
            if qualifying:
                counters["qualifying_edges"] += 1
            else:
                counters["nonqualifying_rows"] += 1

            query = membership.get(hit["query"])
            target = membership.get(hit["target"])
            reasons: list[str] = []
            if query is None or target is None:
                counters["unknown_node_rows"] += 1
                reasons.append("unknown_node")
            observed_query_split = query["split"].strip() if query else ""
            observed_target_split = target["split"].strip() if target else ""
            if (
                observed_query_split != query_split
                or observed_target_split != target_split
            ):
                counters["direction_mismatch_rows"] += 1
                reasons.append("direction_mismatch")

            self_id = hit["query"] == hit["target"]
            exact_sha = bool(
                query
                and target
                and query["sequence_sha256"].strip()
                == target["sequence_sha256"].strip()
            )
            same_component = bool(
                query
                and target
                and query["global_component_id"].strip()
                and query["global_component_id"].strip()
                == target["global_component_id"].strip()
            )
            if self_id:
                counters["self_id_rows"] += 1
                reasons.append("self_id_collision")
            if exact_sha:
                counters["exact_sha_rows"] += 1
                reasons.append("exact_sha_cross_split")
            if same_component:
                counters["same_component_rows"] += 1
                reasons.append("component_cross_split")
            if qualifying:
                reasons.append("qualifying_similarity_edge")

            if reasons:
                counters["reported_rows"] += 1
                writer.writerow(
                    {
                        "query_id": hit["query"],
                        "target_id": hit["target"],
                        "pident_raw": hit["pident"],
                        "identity_fraction": f"{identity:.8f}",
                        "qcov_raw": hit["qcov"],
                        "qcov_fraction": f"{qcov:.8f}",
                        "tcov_raw": hit["tcov"],
                        "tcov_fraction": f"{tcov:.8f}",
                        "alignment_length": hit["alnlen"],
                        "evalue": hit["evalue"],
                        "bit_score": hit["bits"],
                        "query_split": observed_query_split,
                        "target_split": observed_target_split,
                        "query_component_id": (
                            query["global_component_id"].strip() if query else ""
                        ),
                        "target_component_id": (
                            target["global_component_id"].strip() if target else ""
                        ),
                        "query_sha256": query["sequence_sha256"].strip() if query else "",
                        "target_sha256": (
                            target["sequence_sha256"].strip() if target else ""
                        ),
                        "self_id": int(self_id),
                        "exact_sha": int(exact_sha),
                        "same_component": int(same_component),
                        "qualifying": int(qualifying),
                        "violation_reasons": ",".join(dict.fromkeys(reasons)),
                    }
                )

    query_nodes = sum(
        row["split"].strip() == query_split for row in membership.values()
    )
    target_nodes = sum(
        row["split"].strip() == target_split for row in membership.values()
    )
    return {
        "query_split": query_split,
        "target_split": target_split,
        "query_nodes": query_nodes,
        "target_nodes": target_nodes,
        "raw_path": str(Path(raw_path.parent.name) / raw_path.name),
        "raw_sha256": file_sha256(raw_path),
        "report_path": report_path.name,
        **{
            key: counters[key]
            for key in (
                "raw_rows",
                "nonqualifying_rows",
                "qualifying_edges",
                "reported_rows",
                "unknown_node_rows",
                "direction_mismatch_rows",
                "self_id_rows",
                "exact_sha_rows",
                "same_component_rows",
            )
        },
    }


def finalize_audit(
    *,
    preparation_dir: Path,
    membership_path: Path,
    raw_paths: dict[str, Path],
    output_dir: Path,
    min_identity: float = 0.30,
    min_qcov: float = 0.80,
    min_tcov: float = 0.80,
) -> dict[str, object]:
    """Evaluate directional MMseqs output and emit a fail-closed report."""

    for name, value in (
        ("min_identity", min_identity),
        ("min_qcov", min_qcov),
        ("min_tcov", min_tcov),
    ):
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be a fraction in [0, 1]")

    temporary = output_dir.with_name(output_dir.name + ".building")
    if output_dir.exists() or temporary.exists():
        raise FileExistsError(f"Refusing to overwrite integrity-audit report: {output_dir}")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.mkdir()

    verify_checksums(preparation_dir)
    preparation_path = preparation_dir / "PREPARATION.json"
    preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    if preparation.get("status") != "pass":
        raise ValueError("Preparation phase did not pass; MMseqs results cannot be finalized")
    expected_membership_sha = preparation["source_files"]["membership"]["sha256"]
    if file_sha256(membership_path) != expected_membership_sha:
        raise ValueError("Membership changed after audit FASTAs were prepared")

    membership_rows = read_tsv(
        membership_path,
        (
            "node_id",
            "global_component_id",
            "split",
            "sequence_sha256",
            "is_model_representative",
            "model_protein_id",
            "source_dataset",
            "source_cluster_id",
        ),
    )
    membership = index_unique(membership_rows, "node_id", label="component membership")
    global_violations = cross_split_violations(membership_rows)

    for split in ACTIVE_SPLITS:
        split_fasta = read_fasta(preparation_dir / f"{split}_all_nodes.faa")
        expected_ids = {
            node_id
            for node_id, row in membership.items()
            if row["split"].strip() == split
        }
        if set(split_fasta) != expected_ids:
            raise ValueError(f"Prepared {split} FASTA IDs no longer match membership")
        for node_id, sequence in split_fasta.items():
            if sequence_sha256(sequence) != membership[node_id]["sequence_sha256"].strip():
                raise ValueError(f"Prepared {split} FASTA SHA mismatch for {node_id}")

    expected_raw_names = {name for name, _, _ in DIRECTIONS}
    if set(raw_paths) != expected_raw_names:
        raise ValueError(
            f"Raw direction keys must be {sorted(expected_raw_names)}, got {sorted(raw_paths)}"
        )

    direction_summaries: dict[str, dict[str, object]] = {}
    for name, query_split, target_split in DIRECTIONS:
        raw_path = raw_paths[name]
        if not raw_path.is_file():
            raise FileNotFoundError(f"Missing directional MMseqs TSV: {raw_path}")
        direction_summaries[name] = audit_direction(
            raw_path=raw_path,
            report_path=temporary / f"{name}.tsv",
            query_split=query_split,
            target_split=target_split,
            membership=membership,
            min_identity=min_identity,
            min_qcov=min_qcov,
            min_tcov=min_tcov,
        )

    total_qualifying = sum(
        int(summary["qualifying_edges"]) for summary in direction_summaries.values()
    )
    total_direction_mismatch = sum(
        int(summary["direction_mismatch_rows"])
        for summary in direction_summaries.values()
    )
    total_unknown = sum(
        int(summary["unknown_node_rows"]) for summary in direction_summaries.values()
    )
    total_self = sum(
        int(summary["self_id_rows"]) for summary in direction_summaries.values()
    )
    total_exact_hits = sum(
        int(summary["exact_sha_rows"]) for summary in direction_summaries.values()
    )
    total_component_hits = sum(
        int(summary["same_component_rows"]) for summary in direction_summaries.values()
    )
    global_violation_counts = Counter(
        str(row["violation_type"]) for row in global_violations
    )
    failure_reasons: list[str] = []
    if total_qualifying:
        failure_reasons.append("qualifying_cross_split_similarity_edges")
    if global_violation_counts["exact_sha_cross_split"] or total_exact_hits:
        failure_reasons.append("exact_sha_cross_split")
    if global_violation_counts["component_cross_split"] or total_component_hits:
        failure_reasons.append("component_cross_split")
    if total_self:
        failure_reasons.append("self_id_collision")
    if total_direction_mismatch:
        failure_reasons.append("direction_mismatch")
    if total_unknown:
        failure_reasons.append("unknown_node")

    summary = {
        "audit_schema_version": 1,
        "phase": "finalize",
        "status": "pass" if not failure_reasons else "fail",
        "failure_reasons": failure_reasons,
        "mmseqs_contract": {
            "required_release": "18-8cc5c",
            "searches": [
                {
                    "name": name,
                    "query_split": query_split,
                    "target_split": target_split,
                }
                for name, query_split, target_split in DIRECTIONS
            ],
            "min_seq_id": min_identity,
            "min_query_coverage": min_qcov,
            "min_target_coverage": min_tcov,
            "cov_mode": 0,
            "sensitivity": 7.5,
            "max_seqs": 50000,
            "format_output": ",".join(MMSEQS_FIELDS),
        },
        "directionality_policy": {
            "only": [
                "validation->train",
                "test->train",
                "test->validation",
            ],
            "reverse_searches": (
                "not executed; each unordered split pair is audited once in the specified "
                "orientation, with qcov and tcov evaluated separately"
            ),
            "self_hits": "invalid because every search is between disjoint split ID sets",
            "exact_hits": "independently rejected by sequence SHA before and after search",
        },
        "preparation": {
            "directory": preparation_dir.name,
            "path_semantics": "relative_to_audit_release_root",
            "preparation_sha256": file_sha256(preparation_path),
            "membership_path": str(membership_path),
            "membership_sha256": file_sha256(membership_path),
        },
        "global_integrity": {
            "component_cross_split_keys": global_violation_counts[
                "component_cross_split"
            ],
            "exact_sha_cross_split_keys": global_violation_counts[
                "exact_sha_cross_split"
            ],
            "qualifying_edges": total_qualifying,
            "self_id_rows": total_self,
            "direction_mismatch_rows": total_direction_mismatch,
            "unknown_node_rows": total_unknown,
            "exact_sha_hit_rows": total_exact_hits,
            "same_component_hit_rows": total_component_hits,
        },
        "directions": direction_summaries,
    }
    (temporary / "SUMMARY.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_checksums(temporary)
    os.replace(temporary, output_dir)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Build and validate all-node split FASTAs")
    prepare.add_argument(
        "--master-manifest",
        type=Path,
        default=Path("data/processed/v0/master_manifest.tsv"),
    )
    prepare.add_argument(
        "--membership",
        type=Path,
        default=Path("data/processed/v0/global_component_membership.tsv"),
    )
    prepare.add_argument(
        "--quarantine-manifest",
        type=Path,
        default=Path("data/processed/v0/quarantine_manifest.tsv"),
    )
    prepare.add_argument(
        "--component-fasta",
        type=Path,
        default=Path("data/interim/v0/component_input.faa"),
    )
    prepare.add_argument(
        "--model-fasta",
        type=Path,
        default=Path("data/interim/v0/model_representatives.faa"),
    )
    prepare.add_argument(
        "--member-fasta",
        type=Path,
        action="append",
        default=[],
        help="Optional source member FASTA to reconcile against component_input (repeatable)",
    )
    prepare.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/postsplit_integrity_v0/inputs"),
    )

    finalize = subparsers.add_parser("finalize", help="Validate directional MMseqs TSVs")
    finalize.add_argument(
        "--preparation-dir",
        type=Path,
        default=Path("results/postsplit_integrity_v0/inputs"),
    )
    finalize.add_argument(
        "--membership",
        type=Path,
        default=Path("data/processed/v0/global_component_membership.tsv"),
    )
    finalize.add_argument("--validation-vs-train", type=Path, required=True)
    finalize.add_argument("--test-vs-train", type=Path, required=True)
    finalize.add_argument("--test-vs-validation", type=Path, required=True)
    finalize.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/postsplit_integrity_v0/report"),
    )
    finalize.add_argument("--min-seq-id", type=float, default=0.30)
    finalize.add_argument("--min-qcov", type=float, default=0.80)
    finalize.add_argument("--min-tcov", type=float, default=0.80)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "prepare":
        summary = prepare_audit(
            master_manifest_path=args.master_manifest,
            quarantine_manifest_path=args.quarantine_manifest,
            membership_path=args.membership,
            component_fasta_path=args.component_fasta,
            model_fasta_path=args.model_fasta,
            member_fasta_paths=args.member_fasta,
            output_dir=args.output_dir,
        )
    else:
        summary = finalize_audit(
            preparation_dir=args.preparation_dir,
            membership_path=args.membership,
            raw_paths={
                "validation_vs_train": args.validation_vs_train,
                "test_vs_train": args.test_vs_train,
                "test_vs_validation": args.test_vs_validation,
            },
            output_dir=args.output_dir,
            min_identity=args.min_seq_id,
            min_qcov=args.min_qcov,
            min_tcov=args.min_tcov,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
