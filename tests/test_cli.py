from __future__ import annotations

import json
from pathlib import Path

import pytest

from djrmcp_finder import cli


ROOT = Path(__file__).resolve().parents[1]


def test_plan_lists_only_active_data_curation_v3_project_v0_boundaries(capsys) -> None:
    assert cli.main(["plan"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["project_release"] == "V0"
    assert payload["source_dataset_version"] == "data-curation V3"
    assert payload["version_mapping"] == "data-curation V3 -> project V0"

    entrypoints = [row["entrypoint"] for row in payload["boundaries"]]
    assert len(entrypoints) == len(set(entrypoints))
    assert "scripts/score_validation_family_robustness_v0_schema4.py" in entrypoints
    for entrypoint in entrypoints:
        if entrypoint.startswith(("pbs/", "scripts/")):
            assert (ROOT / entrypoint).is_file(), entrypoint
    retired = {
        "pbs/03_embed.pbs",
        "pbs/04_train_classifier.pbs",
        "scripts/run_workstation_embed_v0.sh",
        "scripts/run_model_benchmark_v1_projection.pbs",
        "scripts/score_validation_family_robustness_v0.py",
    }
    assert retired.isdisjoint(entrypoints)


@pytest.mark.parametrize("retired_command", ["embed", "train", "test"])
def test_cli_does_not_expose_retired_or_direct_test_commands(retired_command: str) -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([retired_command])


def test_benchmark_embed_requires_explicit_model() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["benchmark-embed"])


def test_benchmark_embed_expands_registry_model_and_runs_benchmark_embedder(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "benchmark.yaml"
    base_config = {"base": True}
    expanded_config = {"expanded": "esm2_650m"}
    observed: dict[str, object] = {}

    def fake_load(path: Path):
        observed["config_path"] = path
        return base_config

    def fake_expand(config, model_id: str):
        observed["expand"] = (config, model_id)
        return expanded_config

    def fake_run(config, *, device_override, limit):
        observed["run"] = (config, device_override, limit)
        return {"status": "complete", "model_id": "esm2_650m"}

    monkeypatch.setattr(cli, "load_config", fake_load)
    monkeypatch.setattr(cli, "expand_benchmark_model", fake_expand)
    monkeypatch.setattr(cli, "_run_benchmark_embedding", fake_run)

    assert (
        cli.main(
            [
                "benchmark-embed",
                "--config",
                str(config_path),
                "--model",
                "esm2_650m",
                "--device",
                "cuda:1",
                "--limit",
                "2",
            ]
        )
        == 0
    )
    assert observed == {
        "config_path": config_path,
        "expand": (base_config, "esm2_650m"),
        "run": (expanded_config, "cuda:1", 2),
    }
    assert json.loads(capsys.readouterr().out)["status"] == "complete"
