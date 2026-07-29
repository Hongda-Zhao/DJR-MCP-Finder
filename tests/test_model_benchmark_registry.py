from __future__ import annotations

import re
from pathlib import Path

import yaml

from djrmcp_finder.stages.benchmark_embedding import (
    _pooling_contract,
    _prepare_sequence,
    _special_token_policy,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "model_benchmark_v0.yaml"
EXPECTED_MODELS = (
    "esm2_150m",
    "esm2_650m",
    "esm2_3b",
    "esmc_300m",
    "esmc_600m",
    "esmc_6b",
    "prott5_xl",
    "ankh3_large",
    "amplify_350m",
    "protsent_150m",
    "protrek_650m",
    "prostt5",
    "mimic_1b",
    "esm3_open_1_4b",
)


def _config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def test_registry_is_the_frozen_14_model_project_v0_scope() -> None:
    config = _config()
    models = config["benchmark"]["models"]

    assert tuple(models) == EXPECTED_MODELS
    assert len(models) == 14
    assert config["project"]["version"] == (
        "project-v0-model-benchmark__source-database-v3-560"
    )
    assert all(
        re.fullmatch(r"[0-9a-f]{40}", str(spec.get("model_revision", "")))
        for spec in models.values()
    )


def test_custom_backends_and_code_are_immutably_pinned() -> None:
    models = _config()["benchmark"]["models"]

    expected_esmc = {
        "esmc_300m": (
            "Biohub/ESMC-300M",
            "a59b831785f907e96e6a246b1d142bfb76df31ee",
        ),
        "esmc_600m": (
            "Biohub/ESMC-600M",
            "a7e82012c83126b9eedb055fea9fa84b6c02f094",
        ),
        "esmc_6b": (
            "Biohub/ESMC-6B",
            "45b0fa5d7fb06faefbd5e3b89bdcef35d564e79a",
        ),
    }
    for model_id, (repo, revision) in expected_esmc.items():
        esmc = models[model_id]
        assert esmc["backend"] == "esmc_transformer"
        assert esmc["model_loader"] == "masked_lm"
        assert esmc["model_name"] == repo
        assert esmc["model_revision"] == revision
        assert re.fullmatch(r"[0-9a-f]{40}", esmc["transformers_code_revision"])
        assert _pooling_contract(esmc) == "residue_mean_then_window_mean"
        assert _special_token_policy(esmc) == (
            "bos_eos_and_padding_excluded; sequence_only_residues_mean_pooled"
        )

    mimic = models["mimic_1b"]
    assert mimic["backend"] == "mimic"
    assert mimic["mimic_checkpoint_version"] == "1.0"
    assert re.fullmatch(r"[0-9a-f]{40}", mimic["mimic_code_revision"])
    assert _pooling_contract(mimic) == (
        "five_ordered_registers_flattened_plus_aa_mean_then_window_mean"
    )

    esm3 = models["esm3_open_1_4b"]
    assert esm3["backend"] == "esm3"
    assert re.fullmatch(r"[0-9a-f]{40}", esm3["esm_code_revision"])
    assert re.fullmatch(r"[0-9a-f]{40}", esm3["transformers_code_revision"])
    assert _pooling_contract(esm3) == "residue_mean_then_window_mean"


def test_prostt5_sequence_contract_keeps_one_prefix_and_one_token_per_residue() -> None:
    settings = _config()["benchmark"]["models"]["prostt5"]

    assert settings["prefix_token_count"] == 1
    assert _prepare_sequence("AUZOB", settings) == "<AA2fold> A X X X X"


def test_protsent_respects_pinned_native_512_token_limit() -> None:
    config = _config()
    common = config["benchmark"]["common"]
    settings = {**common, **config["benchmark"]["models"]["protsent_150m"]}

    assert settings["native_model_max_tokens"] == 512
    assert settings["window_residues"] == 510
    assert settings["stride"] == 255


def test_protrek_pins_native_sentence_transformer_limit() -> None:
    config = _config()
    common = config["benchmark"]["common"]
    settings = {**common, **config["benchmark"]["models"]["protrek_650m"]}

    assert settings["native_model_max_tokens"] == 1026
    assert settings["window_residues"] == 1022
    assert settings["stride"] == 511
