from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from djrmcp_finder.benchmark_config import expand_benchmark_model
from djrmcp_finder.config import load_config


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "configs" / "model_benchmark_v0.yaml"
REVISION = ROOT / "configs" / "model_benchmark_v0_metric_revision_1.yaml"


def test_metric_revision_overlay_pins_base_and_versioned_result_root() -> None:
    config = load_config(REVISION)
    assert config["config_lineage"]["base_sha256"] == hashlib.sha256(
        BASE.read_bytes()
    ).hexdigest()
    assert config["project"]["metric_revision_id"] == "raw-score-stable-calibration-v1"
    assert config["project"]["test_evaluation_permitted"] is False
    assert config["classifier"]["binary_ranking_score"] == "raw_decision_function"
    assert config["classifier"]["temperature_objective"] == "stable_label_smoothed_logit_nll"
    assert config["classifier"]["temperature_label_smoothing"] == 0.001

    expanded = expand_benchmark_model(config, "esm2_650m")
    assert expanded["paths"]["embedding_output"] == (
        "data/processed/embeddings/v0_benchmark_esm2_650m"
    )
    assert expanded["paths"]["result_output"] == (
        "results/model_benchmark_v0_metric_revision_1/esm2_650m"
    )
    archived = expand_benchmark_model(config, "esmc_6b")
    assert archived["paths"]["embedding_output"].endswith(
        "/05_archived_paths/data/processed/embeddings/v0_benchmark_esmc_6b"
    )


def test_metric_revision_overlay_fails_if_base_hash_drifts(tmp_path: Path) -> None:
    base = tmp_path / "base.yaml"
    base.write_text(
        "project: {}\npaths: {}\nknown_mcps: {}\ndataset: {}\nembedding: {}\nclassifier: {}\n",
        encoding="utf-8",
    )
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(
        "extends: base.yaml\nextends_sha256: " + "0" * 64 + "\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        load_config(overlay)
