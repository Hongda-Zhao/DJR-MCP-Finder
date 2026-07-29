from __future__ import annotations

import json
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from djrmcp_finder.stages import esmc_adapter as esmc_adapter_module
from djrmcp_finder.stages.esmc_adapter import EsmcAdapter


TRANSFORMERS_CODE_REVISION = "ef32577f55da19a4989cd7b22e004dc43a4998cb"
MODEL_REVISIONS = {
    "Biohub/ESMC-300M": "a59b831785f907e96e6a246b1d142bfb76df31ee",
    "Biohub/ESMC-600M": "a7e82012c83126b9eedb055fea9fa84b6c02f094",
    "Biohub/ESMC-6B": "45b0fa5d7fb06faefbd5e3b89bdcef35d564e79a",
}


class _Tensor:
    def __init__(self, values: Any) -> None:
        self.values = np.asarray(values)

    @property
    def shape(self) -> tuple[int, ...]:
        return self.values.shape

    def to(self, *args: Any, dtype: Any = None, **kwargs: Any) -> "_Tensor":
        requested_dtype = dtype
        if requested_dtype is None and args and args[0] is np.bool_:
            requested_dtype = args[0]
        if requested_dtype is np.bool_:
            return _Tensor(self.values.astype(bool))
        return self

    def sum(self, dim: int | None = None, keepdim: bool = False) -> "_Tensor":
        return _Tensor(self.values.sum(axis=dim, keepdims=keepdim))

    def unsqueeze(self, dim: int) -> "_Tensor":
        return _Tensor(np.expand_dims(self.values, axis=dim))

    def clamp_min(self, value: float) -> "_Tensor":
        return _Tensor(np.maximum(self.values, value))

    def float(self) -> "_Tensor":
        return _Tensor(self.values.astype(np.float32))

    def cpu(self) -> "_Tensor":
        return self

    def numpy(self) -> np.ndarray:
        return self.values

    def __and__(self, other: "_Tensor") -> "_Tensor":
        return _Tensor(self.values & other.values)

    def __invert__(self) -> "_Tensor":
        return _Tensor(~self.values)

    def __mul__(self, other: "_Tensor") -> "_Tensor":
        return _Tensor(self.values * other.values)

    def __truediv__(self, other: "_Tensor") -> "_Tensor":
        return _Tensor(self.values / other.values)


class _FakeTorch:
    bool = np.bool_
    bfloat16 = np.float32

    @staticmethod
    def tensor(values: Any) -> _Tensor:
        return _Tensor(values)

    @staticmethod
    def equal(left: _Tensor, right: _Tensor) -> bool:
        return np.array_equal(left.values, right.values)

    @staticmethod
    def inference_mode() -> Any:
        return nullcontext()

    @staticmethod
    def autocast(**kwargs: Any) -> Any:
        return nullcontext()


class _VariableLengthTokenizer:
    pad_token_id = 1

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, sequences: list[str], **kwargs: Any) -> dict[str, _Tensor]:
        self.calls.append(sequences)
        assert kwargs["truncation"] is False
        assert kwargs["padding"] is True
        assert kwargs["return_special_tokens_mask"] is True
        assert sequences == ["ACD", "G"]
        return {
            "input_ids": _Tensor([[0, 10, 11, 12, 2], [0, 13, 2, 1, 1]]),
            "attention_mask": _Tensor([[1, 1, 1, 1, 1], [1, 1, 1, 0, 0]]),
            "special_tokens_mask": _Tensor([[1, 0, 0, 0, 1], [1, 0, 1, 1, 1]]),
        }


class _VariableLengthModel:
    def __call__(self, **kwargs: Any) -> Any:
        assert kwargs["output_hidden_states"] is True
        assert kwargs["return_dict"] is True
        # BOS/EOS are deliberately large, and the short row's PAD positions are
        # 999. Correct pooling must return residue-only means 3 and 7.
        scalar_states = np.asarray(
            [[100, 1, 3, 5, 200], [100, 7, 200, 999, 999]],
            dtype=np.float32,
        )
        states = _Tensor(np.repeat(scalar_states[:, :, None], 2, axis=2))
        return SimpleNamespace(hidden_states=[states])


def _settings(model_name: str = "Biohub/ESMC-300M", **updates: Any) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "model_name": model_name,
        "model_revision": MODEL_REVISIONS[model_name],
        "model_loader": "masked_lm",
        "transformers_code_revision": TRANSFORMERS_CODE_REVISION,
    }
    settings.update(updates)
    return settings


def _mock_common_adapter(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, Any]]:
    calls: list[tuple[Any, Any]] = []

    def fake_init(self: Any, settings: dict[str, Any], device: Any) -> None:
        calls.append((settings, device))
        self.settings = settings
        self.device = device
        self.embedding_dim = 960
        self.parameter_count = 332_997_184
        self.resolved_revision = settings["model_revision"]

    monkeypatch.setattr(
        esmc_adapter_module.TransformerResidueAdapter,
        "__init__",
        fake_init,
    )
    monkeypatch.setattr(
        esmc_adapter_module,
        "_installed_vcs_revision",
        lambda name: TRANSFORMERS_CODE_REVISION,
    )
    return calls


@pytest.mark.parametrize("model_name", tuple(MODEL_REVISIONS))
def test_adapter_checks_fork_then_delegates_to_common_residue_adapter(
    monkeypatch: pytest.MonkeyPatch, model_name: str
) -> None:
    calls = _mock_common_adapter(monkeypatch)
    settings = _settings(model_name)
    device = SimpleNamespace(type="cuda")

    adapter = EsmcAdapter(settings, device)

    assert calls == [(settings, device)]
    assert adapter.transformers_code_revision == TRANSFORMERS_CODE_REVISION
    assert adapter.installed_transformers_code_revision == TRANSFORMERS_CODE_REVISION
    assert adapter.resolved_revision == MODEL_REVISIONS[model_name]
    assert adapter.pooling_contract == "residue_mean_then_window_mean"


def test_adapter_rejects_unsupported_checkpoint_or_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _mock_common_adapter(monkeypatch)

    unsupported = _settings()
    unsupported["model_name"] = "biohub/esmc-300m-2024-12"
    with pytest.raises(ValueError, match="frozen official Biohub checkpoints"):
        EsmcAdapter(
            unsupported,
            SimpleNamespace(type="cpu"),
        )
    with pytest.raises(ValueError, match="model_loader='masked_lm'"):
        EsmcAdapter(
            _settings(model_loader="auto"),
            SimpleNamespace(type="cpu"),
        )
    assert calls == []


def test_adapter_rejects_moving_or_mismatched_transformers_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_common_adapter(monkeypatch)
    with pytest.raises(ValueError, match="must be a full 40-character"):
        EsmcAdapter(
            _settings(transformers_code_revision="main"),
            SimpleNamespace(type="cpu"),
        )

    monkeypatch.setattr(
        esmc_adapter_module,
        "_installed_vcs_revision",
        lambda name: "a" * 40,
    )
    with pytest.raises(RuntimeError, match="differs from the preregistered commit"):
        EsmcAdapter(_settings(), SimpleNamespace(type="cpu"))


def test_inherited_batch_pooling_excludes_bos_eos_and_variable_padding() -> None:
    adapter = object.__new__(EsmcAdapter)
    adapter.settings = {
        "precision": "bfloat16",
        "model_loader": "masked_lm",
        "prefix_token_count": 0,
    }
    adapter.device = SimpleNamespace(type="cpu")
    adapter.torch = _FakeTorch
    adapter.tokenizer = _VariableLengthTokenizer()
    adapter.model = _VariableLengthModel()
    adapter.embedding_dim = 2

    vectors = adapter.embed_windows(["ACD", "G"], batch_size=2)

    np.testing.assert_allclose(vectors, [[3.0, 3.0], [7.0, 7.0]])
    assert vectors.dtype == np.float32
    assert adapter.tokenizer.calls == [["ACD", "G"]]


def test_direct_url_parser_requires_an_immutable_vcs_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    distribution = SimpleNamespace(
        read_text=lambda name: json.dumps(
            {"vcs_info": {"commit_id": TRANSFORMERS_CODE_REVISION}}
        )
    )
    monkeypatch.setattr(
        esmc_adapter_module.importlib_metadata,
        "distribution",
        lambda name: distribution,
    )
    assert (
        esmc_adapter_module._installed_vcs_revision("transformers")
        == TRANSFORMERS_CODE_REVISION
    )

    distribution.read_text = lambda name: json.dumps({"url": "https://example.invalid"})
    with pytest.raises(RuntimeError, match="does not record an immutable VCS commit"):
        esmc_adapter_module._installed_vcs_revision("transformers")
