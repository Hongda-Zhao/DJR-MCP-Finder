from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "postsplit_integrity_audit.py"
SPEC = importlib.util.spec_from_file_location("postsplit_integrity_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

MEMBERSHIP_FIELDS = (
    "node_id",
    "source_dataset",
    "source_cluster_id",
    "is_model_representative",
    "model_protein_id",
    "global_component_id",
    "split",
    "sequence_sha256",
)
MASTER_FIELDS = (
    "protein_id",
    "global_component_id",
    "split",
    "sequence_sha256",
)
QUARANTINE_FIELDS = (
    "protein_id",
    "source_dataset",
    "source_cluster_id",
    "global_component_id",
    "reason",
)


def _write_tsv(path: Path, rows: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(fields), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_fasta(path: Path, records: dict[str, str]) -> None:
    path.write_text(
        "".join(f">{record_id}\n{sequence}\n" for record_id, sequence in records.items()),
        encoding="utf-8",
    )


def _make_sources(tmp_path: Path, leak: str | None = None) -> dict[str, Path]:
    sequences = {
        "train_model": "ACDEFGHIKLMN",
        "train_member": "ACDEFGHIKLMP",
        "validation_model": "PQRSTVWYACDE",
        "test_model": "FGHIKLMNPQRS",
        "quarantine_model": "TVWYACDEFGHI",
        "quarantine_member": "LMNPQRSTVWYA",
    }
    if leak == "exact_sha":
        sequences["validation_model"] = sequences["train_model"]

    components = {
        "train_model": "component_train",
        "train_member": "component_train",
        "validation_model": (
            "component_train" if leak == "component" else "component_validation"
        ),
        "test_model": "component_test",
        # A quarantined model can share an active component; it must stay in the
        # all-node search FASTA even though it is absent from master_manifest.
        "quarantine_model": "component_train",
        "quarantine_member": "",
    }
    splits = {
        "train_model": "train",
        "train_member": "train",
        "validation_model": "validation",
        "test_model": "test",
        "quarantine_model": "train",
        "quarantine_member": "quarantine",
    }
    model_ids = {
        "train_model",
        "validation_model",
        "test_model",
        "quarantine_model",
    }

    membership_rows: list[dict[str, str]] = []
    for node_id, sequence in sequences.items():
        is_model = node_id in model_ids
        membership_rows.append(
            {
                "node_id": node_id,
                "source_dataset": "fixture",
                "source_cluster_id": components[node_id],
                "is_model_representative": "1" if is_model else "0",
                "model_protein_id": node_id if is_model else "",
                "global_component_id": components[node_id],
                "split": splits[node_id],
                "sequence_sha256": MODULE.sequence_sha256(sequence),
            }
        )

    master_rows = [
        {
            "protein_id": node_id,
            "global_component_id": components[node_id],
            "split": splits[node_id],
            "sequence_sha256": MODULE.sequence_sha256(sequences[node_id]),
        }
        for node_id in ("train_model", "validation_model", "test_model")
    ]
    quarantine_rows = [
        {
            "protein_id": "quarantine_model",
            "source_dataset": "fixture",
            "source_cluster_id": components["quarantine_model"],
            "global_component_id": components["quarantine_model"],
            "reason": "fixture_quarantine",
        }
    ]

    paths = {
        "master": tmp_path / "master_manifest.tsv",
        "quarantine": tmp_path / "quarantine_manifest.tsv",
        "membership": tmp_path / "global_component_membership.tsv",
        "component": tmp_path / "component_input.faa",
        "model": tmp_path / "model_representatives.faa",
        "member": tmp_path / "members.faa",
        "inputs": tmp_path / "audit_inputs",
    }
    _write_tsv(paths["master"], master_rows, MASTER_FIELDS)
    _write_tsv(paths["quarantine"], quarantine_rows, QUARANTINE_FIELDS)
    _write_tsv(paths["membership"], membership_rows, MEMBERSHIP_FIELDS)
    _write_fasta(paths["component"], sequences)
    _write_fasta(
        paths["model"],
        {node_id: sequences[node_id] for node_id in sequences if node_id in model_ids},
    )
    _write_fasta(paths["member"], {"train_member": sequences["train_member"]})
    return paths


def _prepare(paths: dict[str, Path]) -> dict[str, object]:
    return MODULE.prepare_audit(
        master_manifest_path=paths["master"],
        quarantine_manifest_path=paths["quarantine"],
        membership_path=paths["membership"],
        component_fasta_path=paths["component"],
        model_fasta_path=paths["model"],
        member_fasta_paths=[paths["member"]],
        output_dir=paths["inputs"],
    )


def _raw_paths(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "validation_vs_train": tmp_path / "validation_vs_train.raw.tsv",
        "test_vs_train": tmp_path / "test_vs_train.raw.tsv",
        "test_vs_validation": tmp_path / "test_vs_validation.raw.tsv",
    }
    for path in paths.values():
        path.write_text("", encoding="utf-8")
    return paths


def test_clean_prepare_and_empty_directional_searches_pass(tmp_path: Path) -> None:
    paths = _make_sources(tmp_path)
    preparation = _prepare(paths)
    assert preparation["status"] == "pass"
    assert preparation["counts"]["split_all_nodes"] == {
        "train": 3,
        "validation": 1,
        "test": 1,
    }
    assert preparation["counts"]["membership_quarantine_split_nodes"] == 1
    assert preparation["counts"]["quarantined_model_representatives"] == 1
    assert set(MODULE.read_fasta(paths["inputs"] / "train_all_nodes.faa")) == {
        "train_model",
        "train_member",
        "quarantine_model",
    }

    report_dir = tmp_path / "report"
    summary = MODULE.finalize_audit(
        preparation_dir=paths["inputs"],
        membership_path=paths["membership"],
        raw_paths=_raw_paths(tmp_path),
        output_dir=report_dir,
    )
    assert summary["status"] == "pass"
    assert summary["global_integrity"]["qualifying_edges"] == 0
    assert summary["preparation"]["directory"] == paths["inputs"].name
    assert summary["preparation"]["path_semantics"] == "relative_to_audit_release_root"
    assert not Path(summary["directions"]["validation_vs_train"]["raw_path"]).is_absolute()
    assert (report_dir / "SUMMARY.json").is_file()
    assert (report_dir / "CHECKSUMS.sha256").is_file()


def test_qualifying_edge_is_reported_and_cli_returns_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _make_sources(tmp_path)
    assert _prepare(paths)["status"] == "pass"
    raw = _raw_paths(tmp_path)
    raw["validation_vs_train"].write_text(
        "validation_model\ttrain_model\t35.0\t0.90\t0.80\t12\t1e-5\t42\n",
        encoding="utf-8",
    )
    report_dir = tmp_path / "report"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "finalize",
            "--preparation-dir",
            str(paths["inputs"]),
            "--membership",
            str(paths["membership"]),
            "--validation-vs-train",
            str(raw["validation_vs_train"]),
            "--test-vs-train",
            str(raw["test_vs_train"]),
            "--test-vs-validation",
            str(raw["test_vs_validation"]),
            "--output-dir",
            str(report_dir),
        ],
    )
    assert MODULE.main() == 2
    summary = json.loads((report_dir / "SUMMARY.json").read_text(encoding="utf-8"))
    assert summary["status"] == "fail"
    assert summary["global_integrity"]["qualifying_edges"] == 1
    report_rows = MODULE.read_tsv(
        report_dir / "validation_vs_train.tsv", MODULE.REPORT_FIELDS
    )
    assert len(report_rows) == 1
    assert report_rows[0]["qualifying"] == "1"


@pytest.mark.parametrize(
    ("leak", "expected_violation"),
    [
        ("component", "component_cross_split"),
        ("exact_sha", "exact_sha_cross_split"),
    ],
)
def test_cross_split_component_or_exact_sha_fails_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    leak: str,
    expected_violation: str,
) -> None:
    paths = _make_sources(tmp_path, leak=leak)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "prepare",
            "--master-manifest",
            str(paths["master"]),
            "--quarantine-manifest",
            str(paths["quarantine"]),
            "--membership",
            str(paths["membership"]),
            "--component-fasta",
            str(paths["component"]),
            "--model-fasta",
            str(paths["model"]),
            "--member-fasta",
            str(paths["member"]),
            "--output-dir",
            str(paths["inputs"]),
        ],
    )
    assert MODULE.main() == 2
    preparation = json.loads(
        (paths["inputs"] / "PREPARATION.json").read_text(encoding="utf-8")
    )
    assert preparation["status"] == "fail"
    assert preparation["counts"]["violations"][expected_violation] == 1
