from __future__ import annotations

import numpy as np
import pytest

from djrmcp_finder.stages.benchmark_embedding import SentenceTransformerAdapter


class _NoTruncationTokenizer:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, sequences, **kwargs):
        self.calls.append(kwargs)
        assert kwargs["add_special_tokens"] is True
        assert kwargs["padding"] is False
        assert kwargs["truncation"] is False
        assert kwargs["return_attention_mask"] is False
        return {"input_ids": [[0, *range(len(sequence)), 2] for sequence in sequences]}


class _FirstModule:
    def __init__(self, tokenizer: _NoTruncationTokenizer) -> None:
        self.tokenizer = tokenizer


class _FakeSentenceTransformer:
    max_seq_length = 512

    def __init__(self, tokenizer: _NoTruncationTokenizer) -> None:
        self.first_module = _FirstModule(tokenizer)
        self.encoded: list[str] = []

    def __getitem__(self, index: int):
        assert index == 0
        return self.first_module

    def encode(self, prepared, **kwargs):
        self.encoded.extend(prepared)
        return np.zeros((len(prepared), 3), dtype=np.float32)


def _adapter() -> tuple[SentenceTransformerAdapter, _NoTruncationTokenizer]:
    tokenizer = _NoTruncationTokenizer()
    adapter = SentenceTransformerAdapter.__new__(SentenceTransformerAdapter)
    adapter.settings = {"sequence_format": "raw", "native_model_max_tokens": 512}
    adapter.model = _FakeSentenceTransformer(tokenizer)
    return adapter, tokenizer


def test_untruncated_native_tokenizer_accepts_510_residues() -> None:
    adapter, tokenizer = _adapter()
    observed = adapter.embed_windows(["A" * 510], batch_size=1)

    assert observed.shape == (1, 3)
    assert tokenizer.calls == [
        {
            "add_special_tokens": True,
            "padding": False,
            "truncation": False,
            "return_attention_mask": False,
        }
    ]


@pytest.mark.parametrize("residue_count", [511, 1022, 2906])
def test_untruncated_native_tokenizer_rejects_over_limit_windows(residue_count: int) -> None:
    adapter, _ = _adapter()

    with pytest.raises(RuntimeError, match="would truncate untruncated token lengths"):
        adapter.embed_windows(["A" * residue_count], batch_size=1)


def test_checkpoint_native_limit_must_match_frozen_config() -> None:
    adapter, _ = _adapter()
    adapter.settings["native_model_max_tokens"] = 1024

    with pytest.raises(RuntimeError, match="native max-token contract differs"):
        adapter.embed_windows(["A"], batch_size=1)
