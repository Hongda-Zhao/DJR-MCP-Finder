from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_model_benchmark_metric_revision_1.py"
SPEC = importlib.util.spec_from_file_location("validate_metric_revision_1", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def _selection_row(
    model_id: str,
    score: float,
    *,
    validation_h1: float = 0.90,
    fpr: float = 0.10,
) -> dict:
    return {
        "model_id": model_id,
        "composite_score": score,
        "composite_fold_scores": [score] * 5,
        "validation": {"head1": validation_h1, "head2": 0.90, "head3": 0.90},
        "validation_h1_fpr_at_95pct_recall": fpr,
        "permissive_license": True,
        "speed_tie_break_eligible": False,
        "gpu_seconds_per_sequence": None,
        "timing_comparability_key": {},
    }


def test_independent_selection_applies_gate_paired_one_se_and_fpr_tie_break() -> None:
    rows = [
        _selection_row("esm2_650m", 0.90),
        _selection_row("raw_best_but_gate_fail", 0.92, validation_h1=0.88),
        _selection_row("candidate_high", 0.91, fpr=0.10),
        _selection_row("candidate_tie", 0.91, fpr=0.05),
    ]

    result = VALIDATOR._compute_selection(rows)

    assert result["raw_cv_best_model_id"] == "raw_best_but_gate_fail"
    assert result["highest_selectable_cv_model_id"] == "candidate_high"
    assert result["models"]["raw_best_but_gate_fail"]["selectable"] is False
    assert result["models"]["candidate_tie"]["paired_delta_se_vs_best_selectable_cv"] == 0
    assert result["selected_model_id"] == "candidate_tie"


def test_test_named_input_is_rejected_before_file_access(tmp_path: Path) -> None:
    forbidden = tmp_path / "frozen_test_metrics.json"
    with pytest.raises(RuntimeError, match="Refusing to read Test-like input"):
        VALIDATOR._read_json(forbidden)


def test_validator_output_is_exclusive_and_never_overwritten(tmp_path: Path) -> None:
    output = tmp_path / "validation.json"
    VALIDATOR._exclusive_json(output, {"status": "pass"})
    assert json.loads(output.read_text(encoding="utf-8")) == {"status": "pass"}
    with pytest.raises(FileExistsError):
        VALIDATOR._exclusive_json(output, {"status": "changed"})
    assert json.loads(output.read_text(encoding="utf-8")) == {"status": "pass"}
