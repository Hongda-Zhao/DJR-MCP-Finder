from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SRC = ROOT / "src"
RESULTS = ROOT / "results" / "model_benchmark_v0"
os.environ.setdefault("MPLCONFIGDIR", "/tmp/djrmcp-matplotlib-test-cache")
pytest.importorskip("matplotlib", reason="figure extra is not installed")
pytest.importorskip("PIL", reason="figure extra is not installed")
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PLOT_V0 = _load_script("plot_model_benchmark")


def _formal_inputs():
    config_path = ROOT / "configs" / "model_benchmark_v0.yaml"
    config = PLOT_V0.load_config(config_path)
    summary = json.loads((RESULTS / "model_comparison.json").read_text(encoding="utf-8"))
    with (RESULTS / "model_comparison.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    with (RESULTS / "fold_scores.tsv").open(encoding="utf-8", newline="") as handle:
        folds = list(csv.DictReader(handle, delimiter="\t"))
    return config_path, config, summary, rows, folds


def test_formal_inputs_pass_exact_14_model_contract() -> None:
    config_path, config, summary, rows, folds = _formal_inputs()
    model_ids, baseline = PLOT_V0._validate_benchmark_inputs(
        config, config_path, summary, rows, folds
    )
    assert len(model_ids) == 14
    assert model_ids == list(config["benchmark"]["models"])
    assert baseline == "esm2_650m"


def test_checksum_manifest_is_exact_and_detects_tamper(tmp_path: Path) -> None:
    comparison = tmp_path / "model_comparison.tsv"
    summary = tmp_path / "model_comparison.json"
    folds = tmp_path / "fold_scores.tsv"
    manifest = tmp_path / "COMPARISON_CHECKSUMS.sha256"
    for source, target in (
        (RESULTS / comparison.name, comparison),
        (RESULTS / summary.name, summary),
        (RESULTS / folds.name, folds),
        (RESULTS / manifest.name, manifest),
    ):
        target.write_bytes(source.read_bytes())
    PLOT_V0._verify_comparison_checksums(
        manifest, comparison=comparison, summary=summary, fold_scores=folds
    )
    comparison.write_text(comparison.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Checksum mismatch"):
        PLOT_V0._verify_comparison_checksums(
            manifest, comparison=comparison, summary=summary, fold_scores=folds
        )


def test_json_tsv_metric_drift_is_rejected() -> None:
    config_path, config, summary, rows, folds = _formal_inputs()
    altered = deepcopy(summary)
    altered["models"][0]["composite_score"] += 0.001
    with pytest.raises(RuntimeError, match="JSON/TSV mismatch"):
        PLOT_V0._validate_benchmark_inputs(config, config_path, altered, rows, folds)


def test_fold_arithmetic_drift_is_rejected() -> None:
    config_path, config, summary, rows, folds = _formal_inputs()
    altered = deepcopy(folds)
    altered[0]["score"] = str(float(altered[0]["score"]) + 0.01)
    with pytest.raises(RuntimeError, match="Fold/summary mean mismatch|Composite fold mismatch"):
        PLOT_V0._validate_benchmark_inputs(config, config_path, summary, rows, altered)


def test_peak_memory_is_na_without_source_attestation() -> None:
    _, _, summary, _, _ = _formal_inputs()
    usable, reason = PLOT_V0._peak_memory_contract(summary)
    assert usable is False
    assert reason.startswith("NA:")


def test_atomic_publish_refuses_existing_output(tmp_path: Path) -> None:
    destination = tmp_path / "already-there"
    destination.mkdir()
    args = argparse.Namespace(output_dir=destination)
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        PLOT_V0._atomic_publish(args)
    assert not (tmp_path / ".already-there.publish.lock").exists()


def test_plot_source_has_no_embedded_registry_model_ids() -> None:
    config = yaml.safe_load((ROOT / "configs" / "model_benchmark_v0.yaml").read_text(encoding="utf-8"))
    source = (SCRIPTS / "plot_model_benchmark.py").read_text(encoding="utf-8")
    assert all(model_id not in source for model_id in config["benchmark"]["models"])
    assert "len(rows) != 11" not in source
