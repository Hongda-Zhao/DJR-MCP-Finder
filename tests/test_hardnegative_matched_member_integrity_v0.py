from __future__ import annotations

import csv
import hashlib
import importlib.util
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDER = _load("build_hardnegative_matched_member_inputs_v0")
FINALIZER = _load("finalize_hardnegative_matched_member_integrity_v0")


SEQUENCES = {
    "R1": "MAACCDDEEFFG",
    "M1": "MGGHHIIKKLLM",
    "M2": "MNPPQQRRSSTV",
    "R2": "MVVWWYYAACCD",
    "R3": "MEEFGLMNPKQR",
}
EXTRA_SEQUENCE = "MSTVWYACDEFG"


def _sha(sequence: str) -> str:
    return hashlib.sha256(sequence.encode("ascii")).hexdigest()


def _write_tsv(path: Path, rows: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _write_fasta(path: Path, records: dict[str, str]) -> None:
    path.write_text(
        "".join(f">{record_id}\n{sequence}\n" for record_id, sequence in records.items()),
        encoding="utf-8",
    )


def _builder_fixture(tmp_path: Path) -> Path:
    status = tmp_path / "FINAL_RECOVERY_STATUS.tsv"
    status.write_text("status\tFULL_OPERATIONAL_RECOVERY_PASS\n", encoding="utf-8")
    member_map = tmp_path / "member_map.tsv"
    map_rows = [
        {"family_id": "wd40", "cluster_representative": rep, "member": member, "member_sequence_sha256": _sha(SEQUENCES[member])}
        for rep, member in (("R1", "R1"), ("R1", "M1"), ("R1", "M2"), ("R2", "R2"), ("R3", "R3"))
    ]
    _write_tsv(
        member_map,
        map_rows,
        ("family_id", "cluster_representative", "member", "member_sequence_sha256"),
    )
    integrated = tmp_path / "integrated.tsv"
    integrated_rows = [
        {
            "target": member,
            "tier": "tier1_structure_supported",
            "assigned_family": "wd40",
            "sequence_sha256": _sha(sequence),
            "dataset_scope": "head1_non_djr_hard_negative",
        }
        for member, sequence in SEQUENCES.items()
    ]
    integrated_rows.append(
        {
            "target": "BATCH6_EXTRA",
            "tier": "tier1_structure_supported",
            "assigned_family": "wd40",
            "sequence_sha256": _sha(EXTRA_SEQUENCE),
            "dataset_scope": "head1_non_djr_hard_negative",
        }
    )
    _write_tsv(
        integrated,
        integrated_rows,
        ("target", "tier", "assigned_family", "sequence_sha256", "dataset_scope"),
    )
    master = tmp_path / "master.tsv"
    master_rows = []
    for index, (rep, split) in enumerate((("R1", "validation"), ("R2", "validation"), ("R3", "train")), 1):
        master_rows.append(
            {
                "protein_id": f"HARD__{rep}",
                "source_dataset": "hard_non_djr",
                "source_cluster_id": rep,
                "source_sequence_id": rep,
                "global_component_id": f"V0GC_{index}",
                "split": split,
            }
        )
    _write_tsv(
        master,
        master_rows,
        ("protein_id", "source_dataset", "source_cluster_id", "source_sequence_id", "global_component_id", "split"),
    )
    fasta = tmp_path / "tier1__wd40.faa"
    _write_fasta(fasta, {**SEQUENCES, "BATCH6_EXTRA": EXTRA_SEQUENCE})
    output = tmp_path / "candidates"
    summary = BUILDER.build(
        recovery_status_path=status,
        member_map_path=member_map,
        master_manifest_path=master,
        integrated_candidates_path=integrated,
        tier1_fasta_paths=[fasta],
        output_dir=output,
        expected_member_map_rows=5,
        expected_cluster_representatives=3,
        expected_selected_hardneg_rows=3,
        expected_validation_anchors=2,
        expected_validation_members=2,
        expected_validation_clusters_with_members=1,
    )
    assert summary["counts"]["candidate_nonrepresentative_members"] == 2
    assert summary["counts"]["integrated_candidate_rows_outside_legacy4"] == 1
    assert summary["counts"]["tier1_fasta_records_outside_legacy4"] == 1
    return output


def _run_metadata(path: Path) -> None:
    values = {
        "status": "complete",
        "analysis_id": FINALIZER.ANALYSIS_ID,
        "mmseqs_version": "18-8cc5c",
        "hmmer_version": "HMMER 3.4",
        "foldseek_version": "10-941cd33",
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
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")


def _edge(query: str, target: str, identity: float) -> str:
    return f"{query}\t{target}\t{identity}\t0.9\t0.9\t12\t1e-8\t80\n"


def test_build_and_finalize_individual_exclusion_and_ordinary_homology(tmp_path: Path) -> None:
    candidates = _builder_fixture(tmp_path)
    rows = _read_tsv(candidates / "candidate_manifest.tsv")
    by_member = {row["source_member_id"]: row["protein_id"] for row in rows}
    assert set(by_member) == {"M1", "M2"}

    all_sequences = {
        "train_exact": SEQUENCES["M1"],
        "train_related": "MACDEFGHIKLM",
        "validation_anchor": "MCDEFGHIKLMN",
    }
    membership = tmp_path / "membership.tsv"
    _write_tsv(
        membership,
        [
            {
                "node_id": node,
                "global_component_id": f"GC_{node}",
                "split": "validation" if node == "validation_anchor" else "train",
                "sequence_sha256": _sha(sequence),
            }
            for node, sequence in all_sequences.items()
        ],
        ("node_id", "global_component_id", "split", "sequence_sha256"),
    )
    all_fasta = tmp_path / "all.faa"
    _write_fasta(all_fasta, all_sequences)
    positives = tmp_path / "positives.faa"
    _write_fasta(positives, {"POS1": "MQRSTVWYACDE"})
    positive_mmseqs = tmp_path / "positive_mmseqs.tsv"
    positive_mmseqs.write_text("", encoding="utf-8")
    cellular_hmm = tmp_path / "cellular.domtbl"
    viral_hmm = tmp_path / "viral.domtbl"
    cellular_hmm.write_text("", encoding="utf-8")
    viral_hmm.write_text("", encoding="utf-8")
    foldseek = tmp_path / "foldseek.tsv"
    foldseek.write_text("", encoding="utf-8")
    all_edges = tmp_path / "candidate_vs_all.tsv"
    all_edges.write_text(
        _edge(by_member["M1"], "train_exact", 100.0)
        + _edge(by_member["M2"], "train_related", 45.0),
        encoding="utf-8",
    )
    candidate_edges = tmp_path / "candidate_vs_candidate.tsv"
    candidate_edges.write_text(_edge(by_member["M1"], by_member["M2"], 40.0), encoding="utf-8")
    metadata = tmp_path / "RUN_METADATA.txt"
    _run_metadata(metadata)

    output = tmp_path / "integrity"
    summary = FINALIZER.finalize(
        candidate_manifest_path=candidates / "candidate_manifest.tsv",
        candidate_fasta_path=candidates / "candidate_sequences.faa",
        candidate_checksums_path=candidates / "CHECKSUMS.sha256",
        positive_fasta_path=positives,
        positive_mmseqs_path=positive_mmseqs,
        positive_hmm_paths=[cellular_hmm, viral_hmm],
        positive_foldseek_path=foldseek,
        all_node_membership_path=membership,
        all_node_fasta_path=all_fasta,
        candidate_vs_all_nodes_path=all_edges,
        candidate_vs_candidate_path=candidate_edges,
        run_metadata_path=metadata,
        output_dir=output,
        expected_candidates=2,
        expected_all_nodes=3,
    )
    assert summary["counts"]["legal_members"] == 1
    assert summary["counts"]["excluded_members"] == 1
    legal = _read_tsv(output / "legal/member_manifest.tsv")
    assert legal[0]["source_member_id"] == "M2"
    assert legal[0]["split"] == "robustness_validation"
    assert legal[0]["analysis_included"] == "1"
    assert legal[0]["score_head1"] == "1"
    assert legal[0]["score_head2"] == "0"
    assert legal[0]["h3_analysis_included"] == "0"
    assert legal[0]["test_record"] == "0"
    assert legal[0]["paired_representative_protein_id"] == "HARD__R1"
    assert legal[0]["train_relationship_stratum"] == "30_<50"
    excluded = _read_tsv(output / "legal/excluded_entities.tsv")
    assert excluded[0]["source_member_id"] == "M1"
    assert "all_node_exact_sequence_overlap" in excluded[0]["exclusion_reasons"]
    assert (output / "legal/CHECKSUMS.sha256").is_file()
    for raw in (output / "legal/CHECKSUMS.sha256").read_text().splitlines():
        expected, name = raw.split(maxsplit=1)
        assert hashlib.sha256((output / "legal" / name.strip()).read_bytes()).hexdigest() == expected
