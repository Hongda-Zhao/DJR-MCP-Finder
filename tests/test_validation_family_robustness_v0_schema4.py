from __future__ import annotations

import importlib.util
import json
import csv
import hashlib
import builtins
import sys
from pathlib import Path

import numpy as np
import yaml

import djrmcp_finder.validation_family_robustness as robustness


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/validation_family_robustness_v0_schema4.yaml"
SCORER_PATH = ROOT / "scripts/score_validation_family_robustness_v0_schema4.py"
VALIDATOR_PATH = ROOT / "scripts/validate_validation_family_robustness_v0_schema4.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema4_boundary_and_source_head_matrix_are_fail_closed() -> None:
    scorer = _load("schema4_scorer_contract", SCORER_PATH)
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    scorer._validate_config(config)
    assert config["schema_version"] == 4
    assert config["selection_feedback_permitted"] is False
    assert config["release_gate"] is False
    assert config["model_state"] == "frozen"
    assert config["bootstrap_replicates"] == 10_000
    assert config["bootstrap_seed"] == 20260724
    assert scorer.APPLICABLE_HEADS == {
        "viral_vma_djr": ("head1", "head2", "head3_phylum"),
        "cellular_djr_none": ("head1", "head2"),
        "background_non_djr": ("head1",),
        "hard_non_djr": ("head1",),
    }
    assert scorer.PATH_ID == "full_expected_path"


def test_nested_bootstrap_is_fixed_seed_paired_and_three_level_weighted() -> None:
    scorer = _load("schema4_scorer_bootstrap", SCORER_PATH)
    rows = [
        {
            "dependence_block_id": "b1",
            "source_cluster_key": "s::c1",
            "representative_correct": 1,
            "member_correct": 1,
        },
        {
            "dependence_block_id": "b1",
            "source_cluster_key": "s::c1",
            "representative_correct": 1,
            "member_correct": 0,
        },
        {
            "dependence_block_id": "b1",
            "source_cluster_key": "s::c2",
            "representative_correct": 0,
            "member_correct": 0,
        },
        {
            "dependence_block_id": "b2",
            "source_cluster_key": "s::c3",
            "representative_correct": 1,
            "member_correct": 1,
        },
    ]
    first = scorer.nested_summary(rows, replicates=200, seed=17)
    second = scorer.nested_summary(rows, replicates=200, seed=17)
    assert first[0]["representative_value"] == 0.75
    assert first[0]["member_value"] == 0.625
    assert first[0]["n_source_clusters"] == 3
    assert first[0]["n_dependence_blocks"] == 2
    assert first[0]["clusters_all_members_correct"] == 1
    for left, right in zip(first[1:], second[1:]):
        np.testing.assert_array_equal(left, right)
    np.testing.assert_array_equal(first[3], first[2] - first[1])


def test_paths_include_only_metric_applicable_heads() -> None:
    scorer = _load("schema4_scorer_paths", SCORER_PATH)
    common = {
        "model_id": "esmc_6b",
        "protein_id": "v1",
        "source_dataset": "viral_vma_djr",
        "paired_representative_id": "vr",
        "source_cluster_id": "vc",
        "source_cluster_key": "viral_vma_djr::vc",
        "dependence_block_id": "vb",
        "member_predicted_label": "djr",
        "representative_predicted_label": "djr",
        "member_correct": 1,
        "representative_correct": 1,
        "metric_eligible": 1,
    }
    predictions = [
        {**common, "head": "head1", "truth_label": "djr"},
        {
            **common,
            "head": "head2",
            "truth_label": "viral_morphogenesis_associated",
            "member_predicted_label": "viral_morphogenesis_associated",
            "representative_predicted_label": "viral_morphogenesis_associated",
        },
        {
            **common,
            "head": "head3_phylum",
            "truth_label": "",
            "member_predicted_label": "Nucleocytoviricota",
            "representative_predicted_label": "Nucleocytoviricota",
            "member_correct": "",
            "representative_correct": "",
            "metric_eligible": 0,
        },
    ]
    path = scorer._path_rows(predictions)[0]
    assert path["expected_path"] == "djr>viral_morphogenesis_associated"
    assert path["n_applicable_heads"] == 2
    assert path["member_correct"] == 1


def test_hardnegative_rows_use_master_protein_id_and_emit_h1_only() -> None:
    scorer = _load("schema4_scorer_hard", SCORER_PATH)
    rows = [
        {
            "protein_id": "member",
            "source_dataset": "hard_non_djr",
            "source_cluster_id": "raw-rep",
            "source_cluster_key": "hard_non_djr::raw-rep",
            "paired_representative_id": "raw-rep",
            "paired_representative_protein_id": "HARD__0001",
            "dependence_block_id": "block",
            "train_relationship_stratum": "none",
            "score_head1": "1",
            "score_head2": "0",
            "h3_analysis_included": "0",
            "test_record": "0",
        }
    ]
    run = {
        "member": {
            "threshold": 0.5,
            "probability": {"member": 0.1},
            "raw_score": {"member": -1.0},
        },
        "representative": {
            "threshold": 0.5,
            "probability": {"HARD__0001": 0.2},
            "raw_score": {"HARD__0001": -0.5},
        },
    }
    output = scorer._hardnegative_prediction_rows(
        rows, {model: run for model in scorer.MODELS}
    )
    assert len(output) == 2
    assert {row["head"] for row in output} == {"head1"}
    assert {row["paired_representative_id"] for row in output} == {"raw-rep"}
    assert {row["paired_representative_protein_id"] for row in output} == {
        "HARD__0001"
    }


def test_validation_representative_subset_satisfies_embedding_loader_invariants(
    tmp_path: Path,
) -> None:
    scorer = _load("schema4_scorer_subset", SCORER_PATH)
    master = tmp_path / "master.tsv"
    master_rows = [
        {"protein_id": "HARD__V", "sequence_sha256": "v" * 64, "split": "validation"},
        {"protein_id": "HARD__T", "sequence_sha256": "t" * 64, "split": "test"},
    ]
    with master.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(master_rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(master_rows)
    source = tmp_path / "source"
    source.mkdir()
    index_rows = [
        {**row, "embedding_row": index} for index, row in enumerate(master_rows)
    ]
    with (source / "index.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(index_rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(index_rows)
    np.save(source / "embeddings.float16.npy", np.asarray([[1, 2], [3, 4]], dtype=np.float16))
    np.save(source / "completed.npy", np.ones(2, dtype=bool))
    (source / "metadata.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "manifest_sha256": hashlib.sha256(master.read_bytes()).hexdigest(),
                "dtype": "float16",
                "embedding_dimension": 2,
                "records": 2,
            }
        ),
        encoding="utf-8",
    )
    artifacts = ("completed.npy", "embeddings.float16.npy", "index.tsv", "metadata.json")
    (source / "CHECKSUMS.sha256").write_text(
        "".join(
            f"{hashlib.sha256((source / name).read_bytes()).hexdigest()}  {name}\n"
            for name in artifacts
        ),
        encoding="utf-8",
    )
    benchmark = tmp_path / "benchmark.yaml"
    benchmark.write_text(
        yaml.safe_dump(
                {
                    "project": {"name": "fixture", "version": "fixture"},
                    "benchmark": {"common": {}, "models": {"esm2_650m": {}}},
                    "paths": {
                        "benchmark_embedding_root": str(tmp_path / "unused"),
                        "benchmark_result_root": str(tmp_path / "results"),
                        "benchmark_embedding_overrides": {"esm2_650m": str(source)},
                    },
                    "known_mcps": {},
                    "dataset": {},
                    "embedding": {},
                    "classifier": {},
                }
        ),
        encoding="utf-8",
    )
    subset = tmp_path / "subset"
    subset_manifest = scorer._write_subset_embedding_bundle(
        {"benchmark_config": str(benchmark), "master_manifest": str(master)},
        "esm2_650m",
        ["HARD__V"],
        subset,
    )
    # The repository requires Python >=3.10.  The local Rosetta scientific
    # runtime used in CI here is 3.9, so supply only zip(strict=...) compatibility
    # while exercising the real checksum/manifest loader implementation.
    if sys.version_info < (3, 10):
        robustness.zip = lambda *items, strict=False: builtins.zip(*items)
    rows, vectors, metadata, verified = robustness._load_embedding(
        subset_manifest, subset
    )
    assert [row["protein_id"] for row in rows] == ["HARD__V"]
    np.testing.assert_array_equal(vectors, np.asarray([[1, 2]], dtype=np.float16))
    assert metadata["records"] == 1
    assert set(verified) == set(artifacts)


def test_validator_is_independent_and_declares_all_required_gates() -> None:
    text = VALIDATOR_PATH.read_text(encoding="utf-8")
    assert "score_validation_family_robustness_v0_schema4" not in text
    for phrase in (
        "schema3_three_source_per_record_continuity",
        "hardnegative_h2_h3_prediction_count_zero",
        "fixed_seed_nested_bootstrap_recomputed",
        "h3_endpoints_separated_and_small_n_explicit",
    ):
        assert phrase in text
    assert "family_member_predictions.tsv" in text
    assert "complete_four_source" in text
