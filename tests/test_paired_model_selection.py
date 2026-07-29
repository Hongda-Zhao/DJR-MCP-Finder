from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from djrmcp_finder.cv_folds import (
    build_fold_assignment,
    freeze_cv_fold_map,
    load_frozen_cv_fold_map,
)
from djrmcp_finder.stages.classifier import TEST_SELECTED_INPUT_FILES, _cross_validate


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "summarize_model_benchmark", SCRIPTS / "summarize_model_benchmark.py"
)
assert SPEC is not None and SPEC.loader is not None
SUMMARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUMMARY)


def _manifest_rows() -> list[dict[str, str]]:
    templates = (
        ("non", "non_djr", "", ""),
        ("djr", "djr", "none", ""),
        (
            "nucleo",
            "djr",
            "viral_morphogenesis_associated",
            "Nucleocytoviricota",
        ),
        (
            "preplasmi",
            "djr",
            "viral_morphogenesis_associated",
            "Preplasmiviricota",
        ),
        (
            "rare",
            "djr",
            "viral_morphogenesis_associated",
            "unknown/other",
        ),
    )
    rows = []
    for label, head1, head2, head3 in templates:
        for index in range(10):
            rows.append(
                {
                    "protein_id": f"{label}_{index}",
                    "split": "train",
                    "global_component_id": f"component::{label}_{index}",
                    "head1_label": head1,
                    "head2_label": head2,
                    "head3_operational_label": head3,
                }
            )
    rows.append(
        {
            "protein_id": "validation_only",
            "split": "validation",
            "global_component_id": "component::validation",
            "head1_label": "non_djr",
            "head2_label": "",
            "head3_operational_label": "",
        }
    )
    return rows


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    fields = list(rows[0])
    path.write_text(
        "\t".join(fields)
        + "\n"
        + "".join("\t".join(row[field] for field in fields) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_one_frozen_fold_map_covers_train_components_and_is_reused(tmp_path: Path) -> None:
    manifest = tmp_path / "master_manifest.tsv"
    _write_manifest(manifest, _manifest_rows())
    config = {
        "project": {"seed": 17},
        "paths": {
            "v0_manifest": str(manifest),
            "benchmark_cv_fold_map": str(tmp_path / "folds.tsv"),
            "benchmark_cv_fold_metadata": str(tmp_path / "folds.json"),
        },
        "classifier": {"cross_validation_folds": 5},
    }
    created = freeze_cv_fold_map(config)
    assert created["status"] == "frozen_now"
    attestation, assignment = load_frozen_cv_fold_map(config)
    assert len(assignment) == 50
    assert set(assignment.values()) == {1, 2, 3, 4, 5}
    assert "component::validation" not in assignment
    reused = freeze_cv_fold_map(config, reuse_if_valid=True)
    assert reused["status"] == "already_frozen_and_valid"
    assert reused["fold_map_sha256"] == attestation["fold_map_sha256"]


def test_fold_builder_is_deterministic_and_component_exclusive() -> None:
    rows = _manifest_rows()
    first, _ = build_fold_assignment(rows, folds=5, seed=23)
    second, _ = build_fold_assignment(list(reversed(rows)), folds=5, seed=23)
    assert first == second
    assert len(first) == len(set(first))


@pytest.mark.parametrize("head_name", ["head1", "head2", "head3_phylum"])
def test_all_heads_consume_explicit_fold_ids_instead_of_resplitting(
    head_name: str,
) -> None:
    groups = np.asarray([f"g{index}" for index in range(10)])
    assignment = {group: index % 5 + 1 for index, group in enumerate(groups)}
    y = np.asarray([index // 5 for index in range(10)], dtype=np.int64)
    x = np.column_stack([y, np.arange(10)]).astype(np.float32)
    metadata = [
        {
            "source_dataset": "viral_vma_djr" if label else "hard_non_djr",
            "family_metadata": "synthetic",
        }
        for label in y
    ]
    settings = {
        "cross_validation_folds": 5,
        "head1_alpha_grid": [1e-4],
        "head1_epochs": 2,
        "head1_negative_ratio": 3,
        "logistic_c_grid": [1.0],
        "logistic_max_iter": 100,
    }
    _, report = _cross_validate(
        head_name, x, y, groups, metadata, settings, 11, assignment
    )
    assert report["splitter"] == "FrozenGlobalComponentFoldMap"
    assert report["fold_ids"] == [1, 2, 3, 4, 5]
    assert [row["heldout_global_component_count"] for row in report["fold_diagnostics"]] == [
        2,
        2,
        2,
        2,
        2,
    ]
    with pytest.raises(RuntimeError, match=f"lacks {head_name} Train components"):
        _cross_validate(
            head_name, x, y, groups, metadata, settings, 11, {"g0": 1}
        )


def _selection_row(
    model_id: str,
    folds: list[float],
    *,
    fpr: float,
    seconds: float = 1.0,
    permissive: bool = True,
    timing_key: dict | None = None,
) -> dict:
    if timing_key is None:
        timing_key = {
            "definition": "accumulated_inference_seconds_excluding_model_load",
            "host": "workstation",
            "gpu": "gpu",
            "device": "cuda",
            "python": "3.12",
            "platform": "linux",
            "torch": "2.13",
            "transformers": "5.14",
            "cuda_runtime": "13.0",
        }
    return {
        "model_id": model_id,
        "composite_fold_scores": folds,
        "composite_score": sum(folds) / len(folds),
        "val_head1_average_precision": 0.9,
        "val_head2_macro_f1": 0.9,
        "val_head3_macro_f1": 0.9,
        "val_head1_fpr_at_95pct_recall": fpr,
        "gpu_seconds_per_sequence": seconds,
        "permissive_license": permissive,
        "speed_tie_break_eligible": True,
        "timing_comparability_key": timing_key,
    }


def test_one_se_set_uses_paired_fold_delta_not_independent_se_pooling() -> None:
    best = [0.80, 0.90, 1.00, 0.90, 0.80]
    constant_gap = [value - 0.01 for value in best]
    rows = [_selection_row("esm2_650m", best, fpr=0.2)]
    rows.append(_selection_row("candidate_constant_gap", constant_gap, fpr=0.1))
    for index in range(12):
        rows.append(
            _selection_row(
                f"candidate_{index:02d}",
                [value - 0.05 - index / 1000 for value in best],
                fpr=0.3,
            )
        )
    assert len(rows) == 14

    _, reference, selected = SUMMARY._apply_development_selection(rows)
    candidate = next(row for row in rows if row["model_id"] == "candidate_constant_gap")
    assert reference["model_id"] == "esm2_650m"
    assert candidate["paired_fold_deltas_vs_best_selectable_cv"] == pytest.approx(
        [0.01] * 5
    )
    assert candidate["paired_delta_se_vs_best_selectable_cv"] == pytest.approx(0.0)
    assert candidate["within_one_paired_se"] is False
    independent_pooled_se = math.sqrt(
        SUMMARY._se(best) ** 2 + SUMMARY._se(constant_gap) ** 2
    )
    assert independent_pooled_se > candidate["difference_from_best_selectable_cv"]
    assert selected["model_id"] == "esm2_650m"


def test_fold_lineage_does_not_break_selected_test_evidence_schema() -> None:
    assert SUMMARY.SELECTED_INPUT_NAMES == set(TEST_SELECTED_INPUT_FILES)
    assert {"cv_fold_map", "cv_fold_metadata"}.isdisjoint(
        SUMMARY.SELECTED_INPUT_NAMES
    )


def test_speed_is_skipped_for_mixed_timing_definitions_then_license_wins() -> None:
    folds = [0.90, 0.91, 0.89, 0.90, 0.90]
    baseline = _selection_row(
        "esm2_650m", folds, fpr=0.1, seconds=100.0, permissive=True
    )
    wall_time_key = dict(baseline["timing_comparability_key"])
    wall_time_key["definition"] = "metadata_timestamp_wall_time"
    candidate = _selection_row(
        "candidate",
        folds,
        fpr=0.1,
        seconds=0.01,
        permissive=False,
        timing_key=wall_time_key,
    )

    _, _, selected = SUMMARY._apply_development_selection([baseline, candidate])

    assert selected["model_id"] == "esm2_650m"
    assert baseline["speed_tie_break_status"] == "skipped_incomparable_same_fpr_group"
    assert candidate["speed_tie_break_status"] == "skipped_incomparable_same_fpr_group"


def test_speed_is_used_only_for_same_fpr_and_same_comparability_key() -> None:
    folds = [0.90, 0.91, 0.89, 0.90, 0.90]
    slower = _selection_row(
        "esm2_650m", folds, fpr=0.1, seconds=2.0, permissive=True
    )
    faster = _selection_row(
        "candidate", folds, fpr=0.1, seconds=1.0, permissive=False
    )

    _, _, selected = SUMMARY._apply_development_selection([slower, faster])

    assert selected["model_id"] == "candidate"
    assert faster["speed_tie_break_status"] == "used_comparable_same_fpr_group"
