#!/usr/bin/env python3
"""Build the leakage-aware DJR-MCP-Finder V0 dataset using only stdlib Python."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import random
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


SPLITS = ("train", "validation", "test")
MODEL_FIELDS = (
    "protein_id",
    "source_dataset",
    "source_cluster_id",
    "source_sequence_id",
    "head1_label",
    "head1_mask",
    "head2_label",
    "head2_mask",
    "head3_phylum_label",
    "head3_operational_label",
    "head3_scope_mask",
    "head3_mask",
    "head3_known_mask",
    "head3_unknown_diagnostic_mask",
    "head3_status",
    "head3_unknown_reason",
    "ictv_class_metadata",
    "ictv_taxonomy_metadata",
    "taxonomy_authority_metadata",
    "literature_clade_metadata",
    "literature_assignment_rank_metadata",
    "literature_context_realm_metadata",
    "taxonomy_mapping_status_metadata",
    "evidence_tier",
    "family_metadata",
    "taxonomy_domain",
    "length_aa",
    "length_bin",
    "sequence_sha256",
    "selected_source",
    "structure_status",
    "legacy_positive_component_id",
    "source_fasta",
)
NODE_FIELDS = (
    "node_id",
    "source_dataset",
    "source_cluster_id",
    "source_sequence_id",
    "is_model_representative",
    "model_protein_id",
    "legacy_positive_component_id",
    "length_aa",
    "sequence_sha256",
)

# Project V0 is scientifically bound to the database data-curation V3 release.
# Keep this trust anchor in code as well as in configs/v0_dataset.json: otherwise
# changing the release label, expected count and hashes together would turn the
# supposedly frozen dataset contract into another self-consistent but stale run.
PROJECT_V0_POSITIVE_RELEASE = {
    "database_data_curation_version": "V3",
    "release_id": "v3_complete_20260722",
    "exact_sequence_representatives": 560,
    "source_sha256": {
        "fasta": "e7741d920af947ccfb8f0a3b54b245e10dd853eef1ef2425cc8f706579acb7c6",
        "manifest": "1c48926200d71299e0f2481247871d3879c511d893f9c5b02717686c52a570f0",
        "inventory": "3009ce3f1019c6b26c6b1da9fe9c4177b29dc226c329ea2c1557c51a7bfc8a3b",
        "release_validation": "ee3454d729ef55b50264ca77c072bfed7720730d0b99a8d756c7e8a88e323d69",
        "source_provenance": "c1291fd847358ad214485bb9a34b87184b25b0dd0154d0fc4f70691d7c19d59c",
    },
}
POSITIVE_SOURCE_KEYS = tuple(PROJECT_V0_POSITIVE_RELEASE["source_sha256"])


def die(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path) -> dict:
    with path.open() as handle:
        return json.load(handle)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, object]], fields: tuple[str, ...] | list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def read_fasta(path: Path) -> dict[str, str]:
    records: dict[str, str] = {}
    record_id: str | None = None
    chunks: list[str] = []
    with path.open() as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if record_id is not None:
                    if record_id in records:
                        die(f"Duplicate FASTA ID in {path}: {record_id}")
                    records[record_id] = "".join(chunks).upper()
                record_id = line[1:].split()[0]
                chunks = []
            else:
                if record_id is None:
                    die(f"Sequence before FASTA header in {path}")
                chunks.append(line)
    if record_id is not None:
        if record_id in records:
            die(f"Duplicate FASTA ID in {path}: {record_id}")
        records[record_id] = "".join(chunks).upper()
    return records


def write_fasta(path: Path, records: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for record_id, sequence in records:
            handle.write(f">{record_id}\n")
            for start in range(0, len(sequence), 80):
                handle.write(sequence[start : start + 80] + "\n")


def sequence_sha256(sequence: str) -> str:
    return hashlib.sha256(sequence.encode()).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_project_v0_dataset_contract(config: dict) -> dict:
    """Reject any dataset config that is not the frozen data-curation-V3/560 V0 contract."""

    required_root_values = {
        "version": "v0",
        "project_release": "project_v0",
        "upstream_database_release": PROJECT_V0_POSITIVE_RELEASE["release_id"],
        # Compatibility value frozen into configs/v0_dataset.json.  Its canonical
        # interpretation is data-curation V3 -> project V0, never project V3.
        "version_mapping": "database V3 -> project V0",
    }
    for field, expected in required_root_values.items():
        observed = config.get(field)
        if observed != expected:
            die(
                f"Project V0 dataset contract mismatch for {field}: "
                f"observed {observed!r}, expected {expected!r}"
            )

    expected_counts = config.get("expected_counts")
    if not isinstance(expected_counts, dict):
        die("Project V0 dataset contract requires expected_counts")
    expected_positive_count = PROJECT_V0_POSITIVE_RELEASE[
        "exact_sequence_representatives"
    ]
    observed_positive_count = expected_counts.get("viral_vma")
    if (
        type(observed_positive_count) is not int
        or observed_positive_count != expected_positive_count
    ):
        die(
            "Project V0 requires exactly 560 data-curation-V3 viral VMA "
            f"representatives; configured {observed_positive_count!r}"
        )

    contract = config.get("positive_release_contract")
    if not isinstance(contract, dict):
        die("Project V0 dataset config lacks positive_release_contract")
    for field in (
        "database_data_curation_version",
        "release_id",
        "exact_sequence_representatives",
    ):
        expected = PROJECT_V0_POSITIVE_RELEASE[field]
        observed = contract.get(field)
        if type(observed) is not type(expected) or observed != expected:
            die(
                f"Project V0 positive release contract mismatch for {field}: "
                f"observed {observed!r}, expected {expected!r}"
            )

    configured_hashes = contract.get("source_sha256")
    canonical_hashes = PROJECT_V0_POSITIVE_RELEASE["source_sha256"]
    if not isinstance(configured_hashes, dict):
        die("Project V0 positive release contract lacks source_sha256")
    if set(configured_hashes) != set(POSITIVE_SOURCE_KEYS):
        die(
            "Project V0 positive release contract source_sha256 must contain "
            f"exactly {', '.join(POSITIVE_SOURCE_KEYS)}"
        )
    for source_name in POSITIVE_SOURCE_KEYS:
        observed = configured_hashes.get(source_name)
        expected = canonical_hashes[source_name]
        if observed != expected:
            die(
                "Project V0 canonical positive source hash mismatch for "
                f"{source_name}: observed {observed!r}, expected {expected}"
            )

    sources = config.get("sources")
    if not isinstance(sources, dict) or not isinstance(sources.get("viral_vma"), dict):
        die("Project V0 dataset config lacks sources.viral_vma")
    viral_source = sources["viral_vma"]
    for source_name in POSITIVE_SOURCE_KEYS:
        configured_path = viral_source.get(source_name)
        if not isinstance(configured_path, str) or not configured_path.strip():
            die(f"Project V0 positive source path is missing for {source_name}")

    return {
        "database_data_curation_version": contract["database_data_curation_version"],
        "release_id": contract["release_id"],
        "exact_sequence_representatives": contract[
            "exact_sequence_representatives"
        ],
        "source_sha256": dict(configured_hashes),
    }


def validate_positive_source_identity(config: dict) -> dict:
    """Bind semantic V3 source roles to content hashes, independent of location."""

    contract = validate_project_v0_dataset_contract(config)
    source = config["sources"]["viral_vma"]
    observed_hashes: dict[str, str] = {}
    for source_name in POSITIVE_SOURCE_KEYS:
        path = Path(source[source_name])
        if not path.is_file():
            die(f"Missing Project V0 positive source file for {source_name}: {path}")
        observed = file_sha256(path)
        expected = contract["source_sha256"][source_name]
        if observed != expected:
            die(
                "Project V0 positive source content mismatch for "
                f"{source_name}: observed {observed}, expected {expected}"
            )
        observed_hashes[source_name] = observed
    return dict(contract, source_sha256=observed_hashes)


def validate_prepared_positive_source_identity(
    work_dir: Path, positive_contract: dict
) -> None:
    """Prevent finalize from consuming a work directory prepared from V2/558."""

    source_file_table = work_dir / "source_files.tsv"
    if not source_file_table.is_file():
        die(f"Prepared V0 source identity table is missing: {source_file_table}")
    rows = read_tsv(source_file_table)
    prepared_hashes = Counter(row.get("sha256", "") for row in rows)
    for source_name, expected in positive_contract["source_sha256"].items():
        if prepared_hashes[expected] != 1:
            die(
                "Prepared V0 work directory is not bound to the canonical V3 "
                f"{source_name}: expected SHA-256 {expected} exactly once"
            )


def canonical_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("_")
    if not token:
        die(f"Cannot construct canonical ID from {value!r}")
    return token


def length_bin(length: int) -> str:
    if length < 200:
        return "lt_200"
    if length < 350:
        return "200_349"
    if length < 500:
        return "350_499"
    if length < 700:
        return "500_699"
    if length <= 1022:
        return "700_1022"
    return "gt_1022"


def model_record(
    *,
    protein_id: str,
    source_dataset: str,
    source_cluster_id: str,
    source_sequence_id: str,
    sequence: str,
    head1_label: str,
    head2_label: str = "",
    head2_mask: str = "0",
    head3_label: str = "",
    head3_operational_label: str = "",
    head3_scope_mask: str = "0",
    head3_mask: str = "0",
    head3_known_mask: str = "0",
    head3_unknown_diagnostic_mask: str = "0",
    head3_status: str = "not_applicable",
    head3_unknown_reason: str = "",
    ictv_class: str = "",
    ictv_taxonomy: str = "",
    taxonomy_authority: str = "",
    literature_clade: str = "",
    literature_assignment_rank: str = "",
    literature_context_realm: str = "",
    taxonomy_mapping_status: str = "",
    evidence: str = "",
    family: str = "",
    taxonomy_domain: str = "",
    selected_source: str = "",
    structure_status: str = "",
    legacy_component: str = "",
    source_fasta: str = "",
) -> dict[str, str]:
    return {
        "protein_id": protein_id,
        "source_dataset": source_dataset,
        "source_cluster_id": source_cluster_id,
        "source_sequence_id": source_sequence_id,
        "head1_label": head1_label,
        "head1_mask": "1",
        "head2_label": head2_label,
        "head2_mask": head2_mask,
        "head3_phylum_label": head3_label,
        "head3_operational_label": head3_operational_label,
        "head3_scope_mask": head3_scope_mask,
        "head3_mask": head3_mask,
        "head3_known_mask": head3_known_mask,
        "head3_unknown_diagnostic_mask": head3_unknown_diagnostic_mask,
        "head3_status": head3_status,
        "head3_unknown_reason": head3_unknown_reason,
        "ictv_class_metadata": ictv_class,
        "ictv_taxonomy_metadata": ictv_taxonomy,
        "taxonomy_authority_metadata": taxonomy_authority,
        "literature_clade_metadata": literature_clade,
        "literature_assignment_rank_metadata": literature_assignment_rank,
        "literature_context_realm_metadata": literature_context_realm,
        "taxonomy_mapping_status_metadata": taxonomy_mapping_status,
        "evidence_tier": evidence,
        "family_metadata": family,
        "taxonomy_domain": taxonomy_domain,
        "length_aa": str(len(sequence)),
        "length_bin": length_bin(len(sequence)),
        "sequence_sha256": sequence_sha256(sequence),
        "selected_source": selected_source,
        "structure_status": structure_status,
        "legacy_positive_component_id": legacy_component,
        "source_fasta": source_fasta,
        "_sequence": sequence,
    }


def node_record(
    *,
    node_id: str,
    source_dataset: str,
    source_cluster_id: str,
    source_sequence_id: str,
    sequence: str,
    is_model: bool,
    model_protein_id: str = "",
    legacy_component: str = "",
) -> dict[str, str]:
    return {
        "node_id": node_id,
        "source_dataset": source_dataset,
        "source_cluster_id": source_cluster_id,
        "source_sequence_id": source_sequence_id,
        "is_model_representative": "1" if is_model else "0",
        "model_protein_id": model_protein_id,
        "legacy_positive_component_id": legacy_component,
        "length_aa": str(len(sequence)),
        "sequence_sha256": sequence_sha256(sequence),
        "_sequence": sequence,
    }


def source_paths(config: dict) -> list[Path]:
    paths: list[Path] = []
    for source in config["sources"].values():
        for value in source.values():
            paths.append(Path(value))
    return sorted(set(paths))


def first_nonempty(row: dict[str, str], *fields: str) -> str:
    for field in fields:
        value = row.get(field, "").strip()
        if value:
            return value
    return ""


def validate_positive_release(config: dict, source: dict) -> None:
    validation = load_json(Path(source["release_validation"]))
    if str(validation.get("status", "")).upper() != "PASS":
        die("Upstream V3 positive release validation is not PASS")
    observed = validation.get("counts", {}).get("unique_representative_proteins")
    expected = int(config["expected_counts"]["viral_vma"])
    if observed != expected:
        die(
            "Upstream V3 positive release count mismatch: "
            f"validation reports {observed}, expected {expected}"
        )


def positive_head3_fields(row: dict[str, str], config: dict) -> dict[str, str]:
    policy = config["head3"]
    phylum = first_nonempty(row, "primary_phylum", "phylum")
    authority = first_nonempty(
        row, "primary_taxonomy_authority_scope", "taxonomy_authority_scope"
    )
    known = set(policy["known_classes"])
    rare = set(policy["rare_formal_phyla_as_unknown"])
    unknown_label = policy["unknown_operational_label"]
    if phylum in known:
        return {
            "phylum": phylum,
            "operational_label": phylum,
            "known_mask": "1",
            "unknown_mask": "0",
            "status": "known_supervised",
            "unknown_reason": "",
        }
    if phylum in rare:
        return {
            "phylum": phylum,
            "operational_label": unknown_label,
            "known_mask": "0",
            "unknown_mask": "1",
            "status": "rare_formal_unknown_diagnostic",
            "unknown_reason": "rare_formal_phylum_mapped_to_operational_unknown",
        }
    if (
        not phylum
        and policy.get("allow_literature_unclassified_as_unknown")
        and authority == "literature_only_unclassified_not_ICTV_MSL41"
    ):
        return {
            "phylum": "",
            "operational_label": unknown_label,
            "known_mask": "0",
            "unknown_mask": "1",
            "status": "literature_unclassified_unknown_diagnostic",
            "unknown_reason": "no_formal_ICTV_MSL41_phylum",
        }
    taxonomy = first_nonempty(row, "taxonomies", "taxonomy")
    die(
        "Positive sequence has no permitted Head 3 mapping: "
        f"taxonomy={taxonomy!r}, phylum={phylum!r}, authority={authority!r}"
    )
    raise AssertionError("unreachable")


def prepare(config_path: Path, work_dir: Path) -> None:
    config = load_json(config_path)
    validate_project_v0_dataset_contract(config)
    if work_dir.exists() and any(work_dir.iterdir()):
        die(f"Refusing to reuse non-empty work directory: {work_dir}")
    work_dir.mkdir(parents=True, exist_ok=True)

    for path in source_paths(config):
        if not path.is_file():
            die(f"Missing source file: {path}")
    positive_source_contract = validate_positive_source_identity(config)

    model_rows: list[dict[str, str]] = []
    node_rows: list[dict[str, str]] = []

    # Viral morphogenesis-associated DJR proteins.
    source = config["sources"]["viral_vma"]
    validate_positive_release(config, source)
    positive_fasta_path = Path(source["fasta"])
    positive_fasta = read_fasta(positive_fasta_path)
    hash_to_positive: dict[str, tuple[str, str]] = {}
    for fasta_id, sequence in positive_fasta.items():
        digest = sequence_sha256(sequence)
        if digest in hash_to_positive:
            die(f"Positive unique FASTA contains an exact duplicate: {fasta_id}")
        hash_to_positive[digest] = (fasta_id, sequence)

    inventory = {row["official_cluster_id"]: row for row in read_tsv(Path(source["inventory"]))}
    positive_manifest = read_tsv(Path(source["manifest"]))
    expected_positive = int(config["expected_counts"]["viral_vma"])
    if len(positive_manifest) != expected_positive:
        die(
            f"Unexpected V3 positive manifest count: {len(positive_manifest)} "
            f"(expected {expected_positive})"
        )
    manifest_hashes = {row["sequence_sha256"] for row in positive_manifest}
    if manifest_hashes != set(hash_to_positive):
        die("V3 positive manifest and exact-sequence FASTA SHA sets differ")
    for row in positive_manifest:
        digest = row["sequence_sha256"]
        if digest not in hash_to_positive:
            die(f"Positive manifest sequence hash is absent from FASTA: {digest}")
        _, sequence = hash_to_positive[digest]
        primary_cluster = row["primary_official_cluster_id"]
        inventory_row = inventory.get(primary_cluster)
        if inventory_row is None:
            die(f"Positive primary cluster absent from inventory: {primary_cluster}")
        head3 = positive_head3_fields(row, config)
        source_sequence_id = first_nonempty(row, "primary_sequence_id", "sequence_id")
        if not source_sequence_id:
            die(f"Positive sequence lacks a source sequence ID: {digest}")
        protein_id = "VMA__" + canonical_token(row["sequence_entity_id"])
        legacy_component = inventory_row["global_analysis_component_id"]
        record = model_record(
            protein_id=protein_id,
            source_dataset="viral_vma_djr",
            source_cluster_id=primary_cluster,
            source_sequence_id=source_sequence_id,
            sequence=sequence,
            head1_label="djr",
            head2_label="viral_morphogenesis_associated",
            head2_mask="1",
            head3_label=head3["phylum"],
            head3_operational_label=head3["operational_label"],
            head3_scope_mask="1",
            head3_mask=head3["known_mask"],
            head3_known_mask=head3["known_mask"],
            head3_unknown_diagnostic_mask=head3["unknown_mask"],
            head3_status=head3["status"],
            head3_unknown_reason=head3["unknown_reason"],
            ictv_class=first_nonempty(row, "primary_class", "class"),
            ictv_taxonomy=first_nonempty(row, "taxonomies", "taxonomy"),
            taxonomy_authority=first_nonempty(
                row, "primary_taxonomy_authority_scope", "taxonomy_authority_scope"
            ),
            literature_clade=first_nonempty(
                row, "primary_literature_clade_label", "literature_clade_label"
            ),
            literature_assignment_rank=first_nonempty(
                row,
                "primary_literature_assignment_rank",
                "literature_assignment_rank",
            ),
            literature_context_realm=first_nonempty(
                row, "primary_literature_context_realm", "literature_context_realm"
            ),
            taxonomy_mapping_status=first_nonempty(
                row, "primary_taxonomy_mapping_status", "taxonomy_mapping_status"
            ),
            evidence=first_nonempty(row, "primary_evidence_class", "evidence_class"),
            family=first_nonempty(row, "groups", "group"),
            taxonomy_domain="Viruses",
            selected_source=first_nonempty(
                row, "primary_selected_source", "selected_source"
            ),
            structure_status=first_nonempty(
                row, "primary_structure_status", "structure_status"
            ),
            legacy_component=legacy_component,
            source_fasta=str(positive_fasta_path),
        )
        model_rows.append(record)
        node_rows.append(
            node_record(
                node_id=protein_id,
                source_dataset="viral_vma_djr",
                source_cluster_id=primary_cluster,
                source_sequence_id=source_sequence_id,
                sequence=sequence,
                is_model=True,
                model_protein_id=protein_id,
                legacy_component=legacy_component,
            )
        )

    # Cellular DJR proteins. All members are used for global component construction.
    source = config["sources"]["cellular_djr"]
    cellular_rep_path = Path(source["representative_fasta"])
    cellular_reps = read_fasta(cellular_rep_path)
    cellular_catalog = read_tsv(Path(source["catalog"]))
    cell_cluster_to_pid: dict[str, str] = {}
    cell_rep_to_cluster: dict[str, str] = {}
    cell_model_hash: dict[str, str] = {}
    for row in cellular_catalog:
        rep_id = row["representative_target"]
        sequence = cellular_reps.get(rep_id)
        if sequence is None:
            die(f"Cellular representative absent from FASTA: {rep_id}")
        cluster_id = row["cluster_id"]
        protein_id = "CELL__" + canonical_token(cluster_id)
        cell_cluster_to_pid[cluster_id] = protein_id
        cell_rep_to_cluster[rep_id] = cluster_id
        cell_model_hash[protein_id] = sequence_sha256(sequence)
        model_rows.append(
            model_record(
                protein_id=protein_id,
                source_dataset="cellular_djr_none",
                source_cluster_id=cluster_id,
                source_sequence_id=row["uniprot_accession"],
                sequence=sequence,
                head1_label="djr",
                head2_label="none",
                head2_mask="1",
                family=row["family_id"],
                taxonomy_domain=row["taxonomy_domain"],
                evidence=row["evidence_label"],
                selected_source=row["source_database"],
                structure_status=row["model_status"],
                source_fasta=str(cellular_rep_path),
            )
        )

    cellular_members = read_fasta(Path(source["member_fasta"]))
    seen_cell_model_nodes: set[str] = set()
    for index, row in enumerate(read_tsv(Path(source["membership"])), start=1):
        member_id = row["member_target"]
        sequence = cellular_members.get(member_id)
        if sequence is None:
            die(f"Cellular member absent from FASTA: {member_id}")
        cluster_id = row["cluster_id"]
        protein_id = cell_cluster_to_pid.get(cluster_id)
        if protein_id is None:
            die(f"Cellular member refers to unknown cluster: {cluster_id}")
        is_model = member_id == row["representative_target"]
        if is_model:
            node_id = protein_id
            seen_cell_model_nodes.add(protein_id)
            if sequence_sha256(sequence) != cell_model_hash[protein_id]:
                die(f"Cellular representative sequence mismatch: {cluster_id}")
        else:
            node_id = f"AUXCELL__{canonical_token(cluster_id)}__{index:07d}"
        node_rows.append(
            node_record(
                node_id=node_id,
                source_dataset="cellular_djr_none",
                source_cluster_id=cluster_id,
                source_sequence_id=row["member_uniprot_accession"],
                sequence=sequence,
                is_model=is_model,
                model_protein_id=protein_id if is_model else "",
            )
        )
    if seen_cell_model_nodes != set(cell_cluster_to_pid.values()):
        die("Not every cellular model representative appeared in the membership table")

    # Hard non-DJR representatives.
    source = config["sources"]["hard_non_djr"]
    hard_fasta_path = Path(source["fasta"])
    hard_fasta = read_fasta(hard_fasta_path)
    hard_metadata = {row["target"]: row for row in read_tsv(Path(source["metadata"]))}
    if set(hard_fasta) != set(hard_metadata):
        die("Hard-negative FASTA and metadata IDs differ")
    for target, sequence in hard_fasta.items():
        row = hard_metadata[target]
        protein_id = "HARD__" + canonical_token(target)
        model_rows.append(
            model_record(
                protein_id=protein_id,
                source_dataset="hard_non_djr",
                source_cluster_id=target,
                source_sequence_id=target,
                sequence=sequence,
                head1_label="non_djr",
                family=row["assigned_family"],
                taxonomy_domain=row.get("taxlineage", "").split(";")[1] if ";" in row.get("taxlineage", "") else "",
                evidence=row["tier"],
                selected_source="AlphaFoldDB_UniProt50",
                source_fasta=str(hard_fasta_path),
            )
        )
        node_rows.append(
            node_record(
                node_id=protein_id,
                source_dataset="hard_non_djr",
                source_cluster_id=target,
                source_sequence_id=target,
                sequence=sequence,
                is_model=True,
                model_protein_id=protein_id,
            )
        )

    # Background non-DJR proteins. Four selected members per source cluster are used
    # to reveal cross-dataset bridges, while only the representative enters the model.
    source = config["sources"]["background_non_djr"]
    background_rep_path = Path(source["representative_fasta"])
    background_reps = read_fasta(background_rep_path)
    background_clusters = read_tsv(Path(source["cluster_metadata"]))
    bg_cluster_to_pid: dict[str, str] = {}
    bg_rep_to_cluster: dict[str, str] = {}
    bg_model_hash: dict[str, str] = {}
    for row in background_clusters:
        rep_id = row["representative_id"]
        sequence = background_reps.get(rep_id)
        if sequence is None:
            die(f"Background representative absent from FASTA: {rep_id}")
        cluster_id = row["cluster_id"]
        protein_id = "BG__" + canonical_token(cluster_id)
        bg_cluster_to_pid[cluster_id] = protein_id
        bg_rep_to_cluster[rep_id] = cluster_id
        bg_model_hash[protein_id] = sequence_sha256(sequence)
        model_rows.append(
            model_record(
                protein_id=protein_id,
                source_dataset="background_non_djr",
                source_cluster_id=cluster_id,
                source_sequence_id=rep_id,
                sequence=sequence,
                head1_label="non_djr",
                family="background",
                taxonomy_domain=row["representative_superkingdom"],
                evidence="sequence_hmm_structure_exclusion_pass",
                selected_source="Swiss-Prot",
                source_fasta=str(background_rep_path),
            )
        )

    background_members = read_fasta(Path(source["member_fasta"]))
    seen_bg_model_nodes: set[str] = set()
    for index, row in enumerate(read_tsv(Path(source["sequence_metadata"])), start=1):
        sequence_id = row["sequence_id"]
        sequence = background_members.get(sequence_id)
        if sequence is None:
            die(f"Background member absent from FASTA: {sequence_id}")
        cluster_id = row["cluster_id"]
        protein_id = bg_cluster_to_pid.get(cluster_id)
        if protein_id is None:
            die(f"Background member refers to unknown cluster: {cluster_id}")
        is_model = sequence_id == row["cluster_representative_id"]
        if is_model:
            node_id = protein_id
            seen_bg_model_nodes.add(protein_id)
            if sequence_sha256(sequence) != bg_model_hash[protein_id]:
                die(f"Background representative sequence mismatch: {cluster_id}")
        else:
            node_id = f"AUXBG__{canonical_token(cluster_id)}__{index:07d}"
        node_rows.append(
            node_record(
                node_id=node_id,
                source_dataset="background_non_djr",
                source_cluster_id=cluster_id,
                source_sequence_id=sequence_id,
                sequence=sequence,
                is_model=is_model,
                model_protein_id=protein_id if is_model else "",
            )
        )
    if seen_bg_model_nodes != set(bg_cluster_to_pid.values()):
        die("Not every background representative appeared in the sequence metadata")

    model_ids = [row["protein_id"] for row in model_rows]
    node_ids = [row["node_id"] for row in node_rows]
    viral_rows = [row for row in model_rows if row["source_dataset"] == "viral_vma_djr"]
    observed_v3_counts = {
        "viral_vma": len(viral_rows),
        "viral_vma_formal_phylum": sum(bool(row["head3_phylum_label"]) for row in viral_rows),
        "head3_known": sum(row["head3_known_mask"] == "1" for row in viral_rows),
        "head3_unknown_diagnostic": sum(
            row["head3_unknown_diagnostic_mask"] == "1" for row in viral_rows
        ),
    }
    for key, observed in observed_v3_counts.items():
        expected = int(config["expected_counts"][key])
        if observed != expected:
            die(f"Unexpected {key} count: {observed} (expected {expected})")
    if len(model_ids) != len(set(model_ids)):
        die("Canonical model protein IDs are not unique")
    if len(node_ids) != len(set(node_ids)):
        die("Canonical component node IDs are not unique")
    if set(model_ids) - set(node_ids):
        die("Some model representatives are absent from the component graph")
    expected_models = int(config["expected_counts"]["model_representatives"])
    expected_nodes = int(config["expected_counts"]["component_graph_nodes"])
    if len(model_rows) != expected_models:
        die(
            f"Unexpected V0 representative count: {len(model_rows)} "
            f"(expected {expected_models})"
        )
    if len(node_rows) != expected_nodes:
        die(
            f"Unexpected V0 component-node count: {len(node_rows)} "
            f"(expected {expected_nodes})"
        )

    write_tsv(work_dir / "model_records_pre_split.tsv", model_rows, MODEL_FIELDS)
    write_tsv(work_dir / "component_nodes.tsv", node_rows, NODE_FIELDS)
    write_fasta(
        work_dir / "model_representatives.faa",
        [(row["protein_id"], row["_sequence"]) for row in model_rows],
    )
    write_fasta(
        work_dir / "component_input.faa",
        [(row["node_id"], row["_sequence"]) for row in node_rows],
    )

    source_file_rows = [
        {
            "path": str(path),
            "bytes": str(path.stat().st_size),
            "sha256": file_sha256(path),
        }
        for path in source_paths(config)
    ]
    write_tsv(work_dir / "source_files.tsv", source_file_rows, ("path", "bytes", "sha256"))
    summary = {
        "version": config["version"],
        "project_release": config["project_release"],
        "upstream_database_release": config["upstream_database_release"],
        "version_mapping": config["version_mapping"],
        "positive_release_contract": positive_source_contract,
        "model_representatives": len(model_rows),
        "component_graph_nodes": len(node_rows),
        "source_counts": dict(Counter(row["source_dataset"] for row in model_rows)),
        "phylum_counts": dict(
            Counter(
                row["head3_phylum_label"] or "<UNCLASSIFIED>"
                for row in model_rows
                if row["head3_scope_mask"] == "1"
            )
        ),
        "head3_operational_counts": dict(
            Counter(
                row["head3_operational_label"]
                for row in model_rows
                if row["head3_scope_mask"] == "1"
            )
        ),
        "head3_status_counts": dict(
            Counter(
                row["head3_status"]
                for row in model_rows
                if row["head3_scope_mask"] == "1"
            )
        ),
        "v3_contract_counts": observed_v3_counts,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    (work_dir / "prepare_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


class UnionFind:
    def __init__(self, items: list[str]) -> None:
        self.parent = {item: item for item in items}
        self.rank = {item: 0 for item in items}

    def find(self, item: str) -> str:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        if self.rank[root_left] < self.rank[root_right]:
            root_left, root_right = root_right, root_left
        self.parent[root_right] = root_left
        if self.rank[root_left] == self.rank[root_right]:
            self.rank[root_left] += 1


def feature_weight(feature: str) -> float:
    if feature == "all":
        return 1.0
    prefix = feature.split("=", 1)[0]
    return {
        "source": 10.0,
        "h1": 6.0,
        "h2": 8.0,
        "h3": 15.0,
        "evidence": 5.0,
        "cell_family": 3.0,
        "hard_family": 1.0,
        "background_domain": 2.0,
        "source_length": 1.0,
    }.get(prefix, 1.0)


def record_features(row: dict[str, str]) -> list[str]:
    features = [
        "all",
        f"source={row['source_dataset']}",
        f"h1={row['head1_label']}",
        f"source_length={row['source_dataset']}::{row['length_bin']}",
    ]
    if row["head2_mask"] == "1":
        features.append(f"h2={row['head2_label']}")
    if row["head3_scope_mask"] == "1":
        features.append(f"h3={row['head3_operational_label']}")
        features.append(f"evidence={row['evidence_tier']}")
    if row["source_dataset"] == "cellular_djr_none":
        features.append(f"cell_family={row['family_metadata']}")
    elif row["source_dataset"] == "hard_non_djr":
        features.append(f"hard_family={row['family_metadata']}")
    elif row["source_dataset"] == "background_non_djr":
        features.append(f"background_domain={row['taxonomy_domain']}")
    return features


def deterministic_tie(seed: int, *values: str) -> str:
    return hashlib.sha256((str(seed) + "|" + "|".join(values)).encode()).hexdigest()


def split_groups(
    groups: dict[str, list[dict[str, str]]], fractions: dict[str, float], seed: int
) -> dict[str, str]:
    totals: Counter[str] = Counter()
    group_features: dict[str, Counter[str]] = {}
    for group_id, rows in groups.items():
        counts: Counter[str] = Counter()
        for row in rows:
            counts.update(record_features(row))
        group_features[group_id] = counts
        totals.update(counts)

    eligible = {
        key
        for key, total in totals.items()
        if total >= 5 or key == "all" or key.startswith(("source=", "h1=", "h2=", "h3="))
    }
    targets = {
        split: {key: totals[key] * fractions[split] for key in eligible} for split in SPLITS
    }
    current = {split: Counter() for split in SPLITS}

    def rarity(group_id: str) -> float:
        return sum(
            feature_weight(key) * count / max(totals[key], 1)
            for key, count in group_features[group_id].items()
            if key in eligible
        )

    ordered = sorted(
        groups,
        key=lambda group_id: (
            -rarity(group_id),
            -len(groups[group_id]),
            deterministic_tie(seed, group_id),
        ),
    )

    assignment: dict[str, str] = {}
    for group_id in ordered:
        counts = group_features[group_id]
        candidates: list[tuple[float, str, str]] = []
        for split in SPLITS:
            delta = 0.0
            for key, count in counts.items():
                if key not in eligible:
                    continue
                target = targets[split][key]
                before = current[split][key]
                after = before + count
                delta += feature_weight(key) * (
                    (after - target) ** 2 - (before - target) ** 2
                ) / max(target, 1.0)
            candidates.append((delta, deterministic_tie(seed, group_id, split), split))
        _, _, chosen = min(candidates)
        assignment[group_id] = chosen
        current[chosen].update(counts)

    # Local moves reduce residual deviation without ever splitting a component.
    move_order = sorted(groups, key=lambda group_id: deterministic_tie(seed + 1, group_id))
    for _ in range(5):
        moved = False
        for group_id in move_order:
            counts = group_features[group_id]
            old_split = assignment[group_id]
            best_delta = 0.0
            best_split = old_split
            for new_split in SPLITS:
                if new_split == old_split:
                    continue
                delta = 0.0
                for key, count in counts.items():
                    if key not in eligible:
                        continue
                    weight = feature_weight(key)
                    old_target = targets[old_split][key]
                    old_before = current[old_split][key]
                    old_after = old_before - count
                    new_target = targets[new_split][key]
                    new_before = current[new_split][key]
                    new_after = new_before + count
                    delta += weight * (
                        (old_after - old_target) ** 2 - (old_before - old_target) ** 2
                    ) / max(old_target, 1.0)
                    delta += weight * (
                        (new_after - new_target) ** 2 - (new_before - new_target) ** 2
                    ) / max(new_target, 1.0)
                if delta < best_delta - 1e-9:
                    best_delta = delta
                    best_split = new_split
            if best_split != old_split:
                current[old_split].subtract(counts)
                current[best_split].update(counts)
                assignment[group_id] = best_split
                moved = True
        if not moved:
            break
    return assignment


def nested_counts(rows: list[dict[str, str]], field: str, *, mask: str | None = None) -> dict:
    result: dict[str, dict[str, int]] = {}
    for split in SPLITS:
        selected = [row for row in rows if row["split"] == split]
        if mask is not None:
            selected = [row for row in selected if row[mask] == "1"]
        result[split] = dict(Counter(row[field] or "<EMPTY>" for row in selected).most_common())
    return result


def finalize(
    config_path: Path,
    work_dir: Path,
    cluster_tsv: Path,
    search_tsv: Path,
    output_dir: Path,
) -> None:
    config = load_json(config_path)
    if output_dir.exists():
        die(f"Refusing to overwrite existing output directory: {output_dir}")
    positive_source_contract = validate_positive_source_identity(config)
    validate_prepared_positive_source_identity(work_dir, positive_source_contract)
    if not cluster_tsv.is_file():
        die(f"Missing MMseqs cluster TSV: {cluster_tsv}")
    if not search_tsv.is_file():
        die(f"Missing MMseqs full-search TSV: {search_tsv}")

    model_rows = read_tsv(work_dir / "model_records_pre_split.tsv")
    model_sequences = read_fasta(work_dir / "model_representatives.faa")
    node_rows = read_tsv(work_dir / "component_nodes.tsv")
    nodes = {row["node_id"]: row for row in node_rows}
    uf = UnionFind(list(nodes))

    first_source_cluster: dict[tuple[str, str], str] = {}
    first_hash: dict[str, str] = {}
    first_legacy_component: dict[str, str] = {}
    for row in node_rows:
        node_id = row["node_id"]
        source_key = (row["source_dataset"], row["source_cluster_id"])
        if source_key in first_source_cluster:
            uf.union(node_id, first_source_cluster[source_key])
        else:
            first_source_cluster[source_key] = node_id
        digest = row["sequence_sha256"]
        if digest in first_hash:
            uf.union(node_id, first_hash[digest])
        else:
            first_hash[digest] = node_id
        legacy = row["legacy_positive_component_id"]
        if legacy:
            if legacy in first_legacy_component:
                uf.union(node_id, first_legacy_component[legacy])
            else:
                first_legacy_component[legacy] = node_id

    mmseqs_pair_counts: dict[str, int] = {}
    for edge_kind, edge_path in (
        ("easy_cluster", cluster_tsv),
        ("full_all_vs_all_search", search_tsv),
    ):
        pair_count = 0
        with edge_path.open(newline="") as handle:
            for values in csv.reader(handle, delimiter="\t"):
                if len(values) < 2:
                    continue
                left, right = values[0], values[1]
                if left not in nodes or right not in nodes:
                    die(
                        f"MMseqs {edge_kind} TSV contains an unknown node: "
                        f"{left}, {right}"
                    )
                uf.union(left, right)
                pair_count += 1
        if pair_count == 0:
            die(f"MMseqs {edge_kind} TSV is empty")
        mmseqs_pair_counts[edge_kind] = pair_count

    root_to_nodes: defaultdict[str, list[str]] = defaultdict(list)
    for node_id in nodes:
        root_to_nodes[uf.find(node_id)].append(node_id)

    model_by_id = {row["protein_id"]: row for row in model_rows}
    root_to_models: defaultdict[str, list[str]] = defaultdict(list)
    for row in node_rows:
        if row["is_model_representative"] == "1":
            root_to_models[uf.find(row["node_id"])].append(row["model_protein_id"])

    root_to_component: dict[str, str] = {}
    for root, protein_ids in root_to_models.items():
        stable_key = "\n".join(sorted(set(protein_ids)))
        root_to_component[root] = "V0GC_" + hashlib.sha256(stable_key.encode()).hexdigest()[:16]

    component_to_models: defaultdict[str, list[str]] = defaultdict(list)
    for root, protein_ids in root_to_models.items():
        component_to_models[root_to_component[root]].extend(sorted(set(protein_ids)))

    quarantine_rows: list[dict[str, str]] = []
    quarantined_ids: set[str] = set()
    mixed_h1_components: list[str] = []
    for component_id, protein_ids in component_to_models.items():
        labels = {model_by_id[protein_id]["head1_label"] for protein_id in protein_ids}
        if labels == {"djr", "non_djr"}:
            mixed_h1_components.append(component_id)
            for protein_id in protein_ids:
                row = model_by_id[protein_id]
                if row["head1_label"] == "non_djr":
                    quarantined_ids.add(protein_id)
                    quarantine_rows.append(
                        {
                            "protein_id": protein_id,
                            "source_dataset": row["source_dataset"],
                            "source_cluster_id": row["source_cluster_id"],
                            "global_component_id": component_id,
                            "reason": "global_component_contains_djr_and_non_djr",
                        }
                    )

    active_rows: list[dict[str, str]] = []
    for row in model_rows:
        if row["protein_id"] in quarantined_ids:
            continue
        root = uf.find(row["protein_id"])
        row["global_component_id"] = root_to_component[root]
        row["split"] = ""
        active_rows.append(row)

    groups: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in active_rows:
        groups[row["global_component_id"]].append(row)
    assignment = split_groups(groups, config["split_fractions"], int(config["seed"]))
    for row in active_rows:
        row["split"] = assignment[row["global_component_id"]]

    split_order = {name: index for index, name in enumerate(SPLITS)}
    active_rows.sort(key=lambda row: (split_order[row["split"]], row["source_dataset"], row["protein_id"]))
    output_dir.mkdir(parents=True)

    final_fields = (
        "protein_id",
        "source_dataset",
        "source_cluster_id",
        "source_sequence_id",
        "global_component_id",
        "split",
        "head1_label",
        "head1_mask",
        "head2_label",
        "head2_mask",
        "head3_phylum_label",
        "head3_operational_label",
        "head3_scope_mask",
        "head3_mask",
        "head3_known_mask",
        "head3_unknown_diagnostic_mask",
        "head3_status",
        "head3_unknown_reason",
        "ictv_class_metadata",
        "ictv_taxonomy_metadata",
        "taxonomy_authority_metadata",
        "literature_clade_metadata",
        "literature_assignment_rank_metadata",
        "literature_context_realm_metadata",
        "taxonomy_mapping_status_metadata",
        "evidence_tier",
        "family_metadata",
        "taxonomy_domain",
        "length_aa",
        "length_bin",
        "sequence_sha256",
        "selected_source",
        "structure_status",
        "legacy_positive_component_id",
        "source_fasta",
    )
    write_tsv(output_dir / "master_manifest.tsv", active_rows, final_fields)
    write_tsv(
        output_dir / "quarantine_manifest.tsv",
        sorted(quarantine_rows, key=lambda row: row["protein_id"]),
        ("protein_id", "source_dataset", "source_cluster_id", "global_component_id", "reason"),
    )

    for split in SPLITS:
        split_rows = [row for row in active_rows if row["split"] == split]
        write_tsv(output_dir / "splits" / f"{split}.tsv", split_rows, final_fields)
        write_fasta(
            output_dir / "splits" / f"{split}.faa",
            [(row["protein_id"], model_sequences[row["protein_id"]]) for row in split_rows],
        )
        for head, mask_field, label_field in (
            ("head1", "head1_mask", "head1_label"),
            ("head2", "head2_mask", "head2_label"),
            ("head3_phylum", "head3_known_mask", "head3_operational_label"),
            (
                "head3_unknown_diagnostic",
                "head3_unknown_diagnostic_mask",
                "head3_operational_label",
            ),
        ):
            head_rows = [row for row in split_rows if row[mask_field] == "1"]
            head_export_rows = [dict(row, target_label=row[label_field]) for row in head_rows]
            head_fields = ("target_label",) + final_fields
            write_tsv(output_dir / "heads" / head / f"{split}.tsv", head_export_rows, head_fields)
            write_fasta(
                output_dir / "heads" / head / f"{split}.faa",
                [(row["protein_id"], model_sequences[row["protein_id"]]) for row in head_rows],
            )

    component_membership_rows: list[dict[str, str]] = []
    node_split_by_id: dict[str, str] = {}
    active_split_by_component = {
        row["global_component_id"]: row["split"] for row in active_rows
    }
    for row in node_rows:
        root = uf.find(row["node_id"])
        component_id = root_to_component.get(root, "")
        node_split = active_split_by_component.get(component_id, "quarantine")
        node_split_by_id[row["node_id"]] = node_split
        component_membership_rows.append(
            {
                "node_id": row["node_id"],
                "source_dataset": row["source_dataset"],
                "source_cluster_id": row["source_cluster_id"],
                "is_model_representative": row["is_model_representative"],
                "model_protein_id": row["model_protein_id"],
                "global_component_id": component_id,
                "split": node_split,
                "sequence_sha256": row["sequence_sha256"],
            }
        )
    write_tsv(
        output_dir / "global_component_membership.tsv",
        component_membership_rows,
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

    residual_full_search_cross_split_edges = 0
    with search_tsv.open(newline="") as handle:
        for values in csv.reader(handle, delimiter="\t"):
            if len(values) < 2:
                continue
            left_split = node_split_by_id[values[0]]
            right_split = node_split_by_id[values[1]]
            if left_split in SPLITS and right_split in SPLITS and left_split != right_split:
                residual_full_search_cross_split_edges += 1

    summary = {
        "version": config["version"],
        "project_release": config["project_release"],
        "upstream_database_release": config["upstream_database_release"],
        "version_mapping": config["version_mapping"],
        "positive_release_contract": positive_source_contract,
        "seed": config["seed"],
        "requested_split_fractions": config["split_fractions"],
        "input_model_representatives": len(model_rows),
        "active_model_representatives": len(active_rows),
        "quarantined_model_representatives": len(quarantine_rows),
        "component_graph_nodes": len(node_rows),
        "global_components_with_model_representatives": len(groups),
        "mixed_head1_components_before_quarantine": len(mixed_h1_components),
        "mmseqs_edge_rows": mmseqs_pair_counts,
        "residual_full_search_cross_split_edges": residual_full_search_cross_split_edges,
        "counts_by_source": nested_counts(active_rows, "source_dataset"),
        "counts_by_head1": nested_counts(active_rows, "head1_label", mask="head1_mask"),
        "counts_by_head2": nested_counts(active_rows, "head2_label", mask="head2_mask"),
        "counts_by_head3_phylum": nested_counts(
            active_rows, "head3_phylum_label", mask="head3_scope_mask"
        ),
        "counts_by_head3_operational_label": nested_counts(
            active_rows, "head3_operational_label", mask="head3_scope_mask"
        ),
        "counts_by_head3_known": nested_counts(
            active_rows, "head3_operational_label", mask="head3_known_mask"
        ),
        "counts_by_head3_unknown_diagnostic": nested_counts(
            active_rows, "head3_status", mask="head3_unknown_diagnostic_mask"
        ),
        "counts_by_positive_evidence": nested_counts(
            active_rows, "evidence_tier", mask="head3_scope_mask"
        ),
        "counts_by_length_bin": nested_counts(active_rows, "length_bin"),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "split_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    component_splits: defaultdict[str, set[str]] = defaultdict(set)
    hash_splits: defaultdict[str, set[str]] = defaultdict(set)
    active_component_labels: defaultdict[str, set[str]] = defaultdict(set)
    for row in active_rows:
        component_splits[row["global_component_id"]].add(row["split"])
        hash_splits[row["sequence_sha256"]].add(row["split"])
        active_component_labels[row["global_component_id"]].add(row["head1_label"])
    known_phyla = set(config["head3"]["known_classes"])
    observed_known = {
        row["head3_operational_label"]
        for row in active_rows
        if row["head3_known_mask"] == "1"
    }
    active_viral_rows = [
        row for row in active_rows if row["source_dataset"] == "viral_vma_djr"
    ]
    expected_models = int(config["expected_counts"]["model_representatives"])
    expected_nodes = int(config["expected_counts"]["component_graph_nodes"])
    checks = [
        ("expected_input_representatives", len(model_rows) == expected_models, len(model_rows)),
        ("expected_component_graph_nodes", len(node_rows) == expected_nodes, len(node_rows)),
        (
            "expected_active_viral_vma",
            len(active_viral_rows) == int(config["expected_counts"]["viral_vma"]),
            len(active_viral_rows),
        ),
        (
            "expected_active_head3_known",
            sum(row["head3_known_mask"] == "1" for row in active_viral_rows)
            == int(config["expected_counts"]["head3_known"]),
            sum(row["head3_known_mask"] == "1" for row in active_viral_rows),
        ),
        (
            "expected_active_head3_unknown_diagnostic",
            sum(
                row["head3_unknown_diagnostic_mask"] == "1"
                for row in active_viral_rows
            )
            == int(config["expected_counts"]["head3_unknown_diagnostic"]),
            sum(
                row["head3_unknown_diagnostic_mask"] == "1"
                for row in active_viral_rows
            ),
        ),
        ("all_active_records_have_one_split", all(row["split"] in SPLITS for row in active_rows), len(active_rows)),
        ("no_global_component_crosses_splits", all(len(value) == 1 for value in component_splits.values()), len(component_splits)),
        ("no_exact_sequence_crosses_splits", all(len(value) == 1 for value in hash_splits.values()), len(hash_splits)),
        ("no_active_head1_mixed_components", all(len(value) == 1 for value in active_component_labels.values()), len(active_component_labels)),
        (
            "no_full_search_edge_crosses_splits",
            residual_full_search_cross_split_edges == 0,
            residual_full_search_cross_split_edges,
        ),
        ("head2_mask_scope", all((row["head2_mask"] == "1") == (row["head1_label"] == "djr") for row in active_rows), "checked"),
        (
            "head3_scope_mask_scope",
            all(
                (row["head3_scope_mask"] == "1")
                == (row["source_dataset"] == "viral_vma_djr")
                for row in active_rows
            ),
            "checked",
        ),
        (
            "head3_mask_matches_known_mask",
            all(row["head3_mask"] == row["head3_known_mask"] for row in active_rows),
            "checked",
        ),
        ("expected_head3_known_classes", observed_known == known_phyla, sorted(observed_known)),
        (
            "head3_known_unknown_masks_partition_scope",
            all(
                (int(row["head3_known_mask"]) + int(row["head3_unknown_diagnostic_mask"]))
                == int(row["head3_scope_mask"])
                for row in active_rows
            ),
            "checked",
        ),
        (
            "head3_unknown_has_operational_label",
            all(
                row["head3_operational_label"] == config["head3"]["unknown_operational_label"]
                for row in active_rows
                if row["head3_unknown_diagnostic_mask"] == "1"
            ),
            "checked",
        ),
        ("all_splits_nonempty", all(any(row["split"] == split for row in active_rows) for split in SPLITS), "checked"),
    ]
    validation = {
        "status": "pass" if all(item[1] for item in checks) else "fail",
        "checks": [
            {"check": name, "pass": passed, "observed": observed}
            for name, passed, observed in checks
        ],
    }
    (output_dir / "validation_report.json").write_text(
        json.dumps(validation, indent=2, sort_keys=True) + "\n"
    )
    if validation["status"] != "pass":
        die("V0 validation failed; inspect validation_report.json")

    shutil.copy2(config_path, output_dir / "v0_dataset.json")
    shutil.copy2(work_dir / "source_files.tsv", output_dir / "source_files.tsv")
    metadata = {
        "version": config["version"],
        "project_release": config["project_release"],
        "upstream_database_release": config["upstream_database_release"],
        "version_mapping": config["version_mapping"],
        "positive_release_contract": positive_source_contract,
        "schema_version": config["schema_version"],
        "seed": config["seed"],
        "python": sys.version,
        "platform": platform.platform(),
        "hostname": platform.node(),
        "mmseqs_cluster_tsv": str(cluster_tsv),
        "mmseqs_full_search_tsv": str(search_tsv),
        "mmseqs_edge_rows": mmseqs_pair_counts,
        "mmseqs_parameters": config["mmseqs"],
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "build_metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")

    readme = f"""# DJR-MCP-Finder V0 model-ready dataset

This directory was generated from immutable source datasets by
`scripts/build_v0_dataset.sh`.

- Active representatives: **{len(active_rows)}**
- Quarantined representatives: **{len(quarantine_rows)}**
- Global components: **{len(groups)}**
- Split policy: component-aware 60/20/20
- Head 1: `djr` / `non_djr`
- Head 2: `viral_morphogenesis_associated` / `none`, masked outside true DJR
- Head 3 named outputs: `Nucleocytoviricota` / `Preplasmiviricota`
- Head 3 operational unknown: `Produgelaviricota` plus literature-only
  unclassified viral VMA DJR are held out from known-class training and evaluated
  as `unknown/other` diagnostics.
- Upstream mapping: `{config['version_mapping']}`
- Component closure: easy-cluster seed graph plus sensitive all-vs-all MMseqs2
  search edges before split assignment.

Use `master_manifest.tsv` as the source of truth. The files under `heads/`
are convenience exports and must not be re-split. `test` is frozen after this
build and must not be used for model selection or calibration.
"""
    (output_dir / "README.md").write_text(readme)

    checksum_rows: list[str] = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "CHECKSUMS.sha256":
            checksum_rows.append(f"{file_sha256(path)}  {path.relative_to(output_dir)}")
    (output_dir / "CHECKSUMS.sha256").write_text("\n".join(checksum_rows) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--config", required=True, type=Path)
    prepare_parser.add_argument("--work-dir", required=True, type=Path)
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--config", required=True, type=Path)
    finalize_parser.add_argument("--work-dir", required=True, type=Path)
    finalize_parser.add_argument("--cluster-tsv", required=True, type=Path)
    finalize_parser.add_argument("--search-tsv", required=True, type=Path)
    finalize_parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "prepare":
        prepare(args.config, args.work_dir)
    else:
        finalize(
            args.config,
            args.work_dir,
            args.cluster_tsv,
            args.search_tsv,
            args.output_dir,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
