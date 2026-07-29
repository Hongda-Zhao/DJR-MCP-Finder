from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from djrmcp_finder.stages import mimic_adapter as mimic_adapter_module
from djrmcp_finder.stages.mimic_adapter import (
    MIMIC_CHECKPOINT_REVISION,
    MIMIC_CODE_REVISION,
    MimicAdapter,
)


HIDDEN = 1536
REGISTER_ID = 701
AA_ID = 211


class FakeParameter:
    def __init__(self, size: int) -> None:
        self.size = size

    def numel(self) -> int:
        return self.size


class FakeDevice:
    type = "cpu"

    def __str__(self) -> str:
        return "cpu"


class FakeTensor:
    """Exercise the detach/float/cpu path without installing torch."""

    def __init__(self, value: np.ndarray) -> None:
        self.value = value

    def detach(self):
        return self

    def float(self):
        self.value = self.value.astype(np.float32)
        return self

    def cpu(self):
        return self

    def numpy(self) -> np.ndarray:
        return self.value


class FakeMimicModel:
    def __init__(self) -> None:
        self.encoder = types.SimpleNamespace(dim=HIDDEN)
        self.num_register_tokens = 5
        self.register_token_id = REGISTER_ID
        self.mod_group_lookup = {"tok_aa_seq": AA_ID}
        self.responses: list[dict[str, FakeTensor]] = []
        self.inputs: list[list[dict[str, str]]] = []
        self.eval_called = False

    def _lookup_mod(self, name: str) -> str:
        assert name == "aa_seq"
        return "tok_aa_seq"

    def parameters(self):
        return [FakeParameter(7), FakeParameter(11)]

    def eval(self):
        self.eval_called = True
        return self

    def input(self, batch):
        self.inputs.append(batch)

    def embed(self):
        return self.responses.pop(0)


def install_fake_modules(monkeypatch, model: FakeMimicModel):
    calls = []

    def load_pretrained(*, version, device, hf_repo, revision):
        calls.append(
            {
                "version": version,
                "device": device,
                "hf_repo": hf_repo,
                "revision": revision,
            }
        )
        return model

    monkeypatch.setattr(
        mimic_adapter_module,
        "_installed_vcs_revision",
        lambda distribution_name: MIMIC_CODE_REVISION,
    )
    monkeypatch.setitem(
        sys.modules, "mimic", types.SimpleNamespace(load_pretrained=load_pretrained)
    )
    monkeypatch.setitem(sys.modules, "transformers", types.SimpleNamespace(__version__="9.8.7"))
    return calls


def settings(**overrides):
    return {
        "mimic_code_revision": MIMIC_CODE_REVISION,
        "model_name": "polymathic-ai/MIMIC",
        "model_revision": MIMIC_CHECKPOINT_REVISION,
        **overrides,
    }


def representation(rows: list[tuple[list[float], list[float], int]]):
    """Build rows as (five register values, aa token values, padding count)."""

    width = max(5 + len(aa_values) + padding for _, aa_values, padding in rows)
    full = np.full((len(rows), width, HIDDEN), 999.0, dtype=np.float16)
    mod_ids = np.full((len(rows), width), -1, dtype=np.int16)
    for row, (register_values, aa_values, _) in enumerate(rows):
        assert len(register_values) == 5
        for index, value in enumerate(register_values):
            full[row, index] = value
            mod_ids[row, index] = REGISTER_ID
        for offset, value in enumerate(aa_values, start=5):
            full[row, offset] = value
            mod_ids[row, offset] = AA_ID
    return {"full": FakeTensor(full), "mod_ids": FakeTensor(mod_ids)}


def test_official_loader_pin_and_metadata(monkeypatch):
    model = FakeMimicModel()
    calls = install_fake_modules(monkeypatch, model)

    adapter = MimicAdapter(settings(), FakeDevice())

    assert calls == [
        {
            "version": "1.0",
            "device": "cpu",
            "hf_repo": "polymathic-ai/MIMIC",
            "revision": MIMIC_CHECKPOINT_REVISION,
        }
    ]
    assert adapter.checkpoint_version == "1.0"
    assert adapter.checkpoint_revision == MIMIC_CHECKPOINT_REVISION
    assert adapter.mimic_code_revision == MIMIC_CODE_REVISION


def test_register_plus_aa_mean_pooling_is_ordered_and_9216d(monkeypatch):
    model = FakeMimicModel()
    calls = install_fake_modules(monkeypatch, model)
    model.responses.append(
        representation(
            [
                ([1, 2, 3, 4, 5], [10, 20, 30], 2),
                ([11, 12, 13, 14, 15], [40, 60], 3),
            ]
        )
    )

    adapter = MimicAdapter(settings(), "cpu")
    result = adapter.embed_windows(["ACD", "WY"], batch_size=2)

    expected_first = np.concatenate(
        [np.full(HIDDEN, value, dtype=np.float32) for value in [1, 2, 3, 4, 5, 20]]
    )
    expected_second = np.concatenate(
        [np.full(HIDDEN, value, dtype=np.float32) for value in [11, 12, 13, 14, 15, 50]]
    )
    np.testing.assert_array_equal(result, np.stack([expected_first, expected_second]))
    assert result.shape == (2, 9216)
    assert result.dtype == np.float32
    assert adapter.embedding_dim == 9216
    assert adapter.parameter_count == 18
    assert adapter.transformers_version == "9.8.7"
    assert adapter.resolved_revision == (
        "checkpoint:40bb974c1b66598168117f2b561e158e769a4a8b|"
        "code:15f5ef3050ea471b4c00e3f7d2be05165ff3dce8"
    )
    assert adapter.pooling_contract == (
        "five_ordered_registers_flattened_plus_aa_mean_then_window_mean"
    )
    assert calls == [
        {
            "version": "1.0",
            "device": "cpu",
            "hf_repo": "polymathic-ai/MIMIC",
            "revision": MIMIC_CHECKPOINT_REVISION,
        }
    ]
    assert model.eval_called
    assert model.inputs == [[{"aa_seq": "ACD"}, {"aa_seq": "WY"}]]


def test_rejects_possible_silent_truncation(monkeypatch):
    model = FakeMimicModel()
    install_fake_modules(monkeypatch, model)
    model.responses.append(representation([([1, 2, 3, 4, 5], [10, 20], 1)]))
    adapter = MimicAdapter(settings(), "cpu")

    with pytest.raises(RuntimeError, match="possible silent truncation"):
        adapter.embed_windows(["ACD"], batch_size=1)


def test_rejects_changed_register_positions(monkeypatch):
    model = FakeMimicModel()
    install_fake_modules(monkeypatch, model)
    output = representation([([1, 2, 3, 4, 5], [10], 1)])
    output["mod_ids"].value[0, 4:6] = [AA_ID, REGISTER_ID]
    model.responses.append(output)
    adapter = MimicAdapter(settings(), "cpu")

    with pytest.raises(RuntimeError, match="register-token order changed"):
        adapter.embed_windows(["A"], batch_size=1)


def test_rejects_non_aa_track_in_sequence_only_output(monkeypatch):
    model = FakeMimicModel()
    install_fake_modules(monkeypatch, model)
    output = representation([([1, 2, 3, 4, 5], [10], 1)])
    output["mod_ids"].value[0, -1] = 999
    model.responses.append(output)
    adapter = MimicAdapter(settings(), "cpu")

    with pytest.raises(RuntimeError, match="non-aa track ids"):
        adapter.embed_windows(["A"], batch_size=1)


@pytest.mark.parametrize("revision", [None, "main", "15f5ef3"])
def test_requires_exact_code_pin(monkeypatch, revision):
    model = FakeMimicModel()
    calls = install_fake_modules(monkeypatch, model)

    with pytest.raises(ValueError, match="pinned code revision"):
        MimicAdapter(settings(mimic_code_revision=revision), "cpu")
    assert calls == []


def test_rejects_non_v1_checkpoint_before_loading(monkeypatch):
    model = FakeMimicModel()
    calls = install_fake_modules(monkeypatch, model)

    with pytest.raises(ValueError, match="frozen to MIMIC checkpoint v1.0"):
        MimicAdapter(settings(mimic_checkpoint_version="2.0"), "cpu")
    assert calls == []


def test_rejects_non_pinned_checkpoint_revision(monkeypatch):
    model = FakeMimicModel()
    calls = install_fake_modules(monkeypatch, model)

    with pytest.raises(ValueError, match="immutable MIMIC v1.0 checkpoint commit"):
        MimicAdapter(settings(model_revision="main"), "cpu")
    assert calls == []


def test_rejects_installed_code_revision_mismatch(monkeypatch):
    model = FakeMimicModel()
    calls = install_fake_modules(monkeypatch, model)
    monkeypatch.setattr(
        mimic_adapter_module, "_installed_vcs_revision", lambda distribution_name: "wrong"
    )

    with pytest.raises(RuntimeError, match="Installed MIMIC code differs"):
        MimicAdapter(settings(), "cpu")
    assert calls == []


def test_empty_input_has_stable_shape(monkeypatch):
    model = FakeMimicModel()
    install_fake_modules(monkeypatch, model)
    adapter = MimicAdapter(settings(), "cpu")

    result = adapter.embed_windows([], batch_size=1)

    assert result.shape == (0, 9216)
    assert result.dtype == np.float32
