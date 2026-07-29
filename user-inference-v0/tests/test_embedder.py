import json
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from djrmcp_predict import embedder as embedder_module
from djrmcp_predict.embedder import (
    EsmcEmbedder,
    _embedding_dimension,
    sliding_windows,
    verify_transformers_distribution,
)


def test_short_sequence_has_one_window() -> None:
    assert sliding_windows("ABCDE", 10, 5) == ["ABCDE"]


def test_final_window_reaches_sequence_end() -> None:
    windows = sliding_windows("ABCDEFGHIJK", 6, 4)
    assert windows == ["ABCDEF", "EFGHIJ", "FGHIJK"]
    assert windows[-1].endswith("K")


def test_embedding_dimension_accepts_standard_and_biohub_config_fields() -> None:
    assert _embedding_dimension(SimpleNamespace(hidden_size=2560)) == 2560
    assert _embedding_dimension(SimpleNamespace(hidden_size=None, d_model=2560)) == 2560
    assert _embedding_dimension(SimpleNamespace()) == 0


@pytest.mark.parametrize("residues,stride", [(0, 1), (1, 0), (-1, 1)])
def test_invalid_window_settings_fail(residues: int, stride: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        sliding_windows("ABCDE", residues, stride)


class _Tensor:
    def __init__(self, values: Any) -> None:
        self.values = np.asarray(values)

    @property
    def shape(self):
        return self.values.shape

    def to(self, *args: Any, dtype: Any = None, **kwargs: Any):
        if dtype is np.bool_:
            return _Tensor(self.values.astype(bool))
        return self

    def sum(self, dim=None, keepdim=False):
        return _Tensor(self.values.sum(axis=dim, keepdims=keepdim))

    def unsqueeze(self, dim):
        return _Tensor(np.expand_dims(self.values, axis=dim))

    def clamp_min(self, value):
        return _Tensor(np.maximum(self.values, value))

    def float(self):
        return _Tensor(self.values.astype(np.float32))

    def cpu(self):
        return self

    def numpy(self):
        return self.values

    def tolist(self):
        return self.values.tolist()

    def __and__(self, other):
        return _Tensor(self.values & other.values)

    def __invert__(self):
        return _Tensor(~self.values)

    def __mul__(self, other):
        return _Tensor(self.values * other.values)

    def __truediv__(self, other):
        return _Tensor(self.values / other.values)


class _FakeTorch:
    bool = np.bool_
    bfloat16 = np.float32

    @staticmethod
    def inference_mode():
        return nullcontext()

    @staticmethod
    def autocast(**kwargs):
        return nullcontext()


class _Tokenizer:
    pad_token_id = 1

    def __call__(self, sequences, **kwargs):
        assert sequences == ["ACD", "G"]
        assert kwargs["truncation"] is False
        return {
            "input_ids": _Tensor([[0, 10, 11, 12, 2], [0, 13, 2, 1, 1]]),
            "attention_mask": _Tensor([[1, 1, 1, 1, 1], [1, 1, 1, 0, 0]]),
            "special_tokens_mask": _Tensor([[1, 0, 0, 0, 1], [1, 0, 1, 1, 1]]),
        }


class _Model:
    def __call__(self, **kwargs):
        scalar = np.asarray(
            [[100, 1, 3, 5, 200], [100, 7, 200, 999, 999]], dtype=np.float32
        )
        states = _Tensor(np.repeat(scalar[:, :, None], 2, axis=2))
        return SimpleNamespace(hidden_states=[states])


def test_residue_pooling_excludes_special_tokens_and_padding() -> None:
    embedder = object.__new__(EsmcEmbedder)
    embedder.settings = {"window_batch_size": 2}
    embedder.torch = _FakeTorch
    embedder.tokenizer = _Tokenizer()
    embedder.model = _Model()
    embedder.device = SimpleNamespace(type="cpu")
    vectors = embedder._embed_windows(["ACD", "G"])
    np.testing.assert_array_equal(vectors, [[3.0, 3.0], [7.0, 7.0]])


def test_protein_window_mean_and_float16_roundtrip() -> None:
    embedder = object.__new__(EsmcEmbedder)
    embedder._loaded = True
    embedder.settings = {
        "window_residues": 6,
        "stride": 4,
        "classifier_input_quantization": "float16_roundtrip",
    }
    embedder._embed_windows = lambda windows: np.asarray(
        [[0.1, 1.0], [0.2, 2.0], [0.3, 3.0]], dtype=np.float32
    )
    vectors = embedder.embed_sequences(["ABCDEFGHIJK"])
    expected = np.asarray([[0.2, 2.0]], dtype=np.float16).astype(np.float32)
    np.testing.assert_array_equal(vectors, expected)


def test_transformers_direct_url_is_pinned(monkeypatch) -> None:
    revision = "a" * 40
    repository = "https://github.com/Biohub/transformers.git"
    distribution = SimpleNamespace(
        read_text=lambda name: json.dumps(
            {"url": repository, "vcs_info": {"commit_id": revision}}
        )
    )
    monkeypatch.setattr(
        embedder_module.importlib_metadata, "distribution", lambda name: distribution
    )
    assert verify_transformers_distribution(repository, revision)["revision"] == revision
    with pytest.raises(RuntimeError, match="repository differs"):
        verify_transformers_distribution("https://example.test/other.git", revision)
