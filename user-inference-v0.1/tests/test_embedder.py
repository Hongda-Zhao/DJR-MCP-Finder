from __future__ import annotations

import numpy as np
import pytest

from djrmcp_predict_v01 import embedder as module
from djrmcp_predict_v01.embedder import (
    FrozenTransformerEmbedder,
    sliding_windows,
    verify_transformers_distribution,
)


def test_sliding_windows_cover_tail_without_truncation() -> None:
    sequence = "ABCDEFGHIJK"

    windows = sliding_windows(sequence, residues=5, stride=3)

    assert windows == ["ABCDE", "DEFGH", "GHIJK"]
    assert windows[-1].endswith(sequence[-1])


def test_short_sequence_is_one_complete_window() -> None:
    assert sliding_windows("ACDE", residues=1022, stride=511) == ["ACDE"]


def test_esm2_worker_requires_exact_transformers_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "_installed_transformers_version", lambda: "5.14.1")

    observed = verify_transformers_distribution(
        {"backend": "transformer_residue", "transformers_version": "5.14.1"}
    )

    assert observed == {"version": "5.14.1", "source": "pypi"}


def test_esm2_worker_rejects_different_transformers_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "_installed_transformers_version", lambda: "4.57.6")

    with pytest.raises(RuntimeError, match="version differs"):
        verify_transformers_distribution(
            {"backend": "transformer_residue", "transformers_version": "5.14.1"}
        )


def test_runtime_metadata_cannot_accidentally_lazy_load_h3() -> None:
    instance = FrozenTransformerEmbedder(
        {
            "backend": "esmc_transformer",
            "model_name": "unused",
        }
    )

    with pytest.raises(RuntimeError, match="before model load"):
        instance.runtime_metadata()


def test_record_batching_matches_frozen_length_sorted_owner_recovery() -> None:
    instance = FrozenTransformerEmbedder(
        {
            "window_residues": 10,
            "stride": 5,
            "record_batch_size": 2,
            "classifier_input_quantization": "float16_roundtrip",
        }
    )
    instance._loaded = True
    instance.dimension = 2
    observed_batches: list[list[str]] = []

    def fake_embed(windows: list[str]) -> np.ndarray:
        observed_batches.append(list(windows))
        return np.asarray([[len(value), ord(value[0])] for value in windows], dtype=np.float32)

    instance._embed_windows = fake_embed  # type: ignore[method-assign]
    sequences = ["AAAA", "CC", "GGG"]

    vectors = instance.embed_sequences(sequences)

    assert observed_batches == [["CC", "GGG"], ["AAAA"]]
    assert vectors.tolist() == [[4.0, 65.0], [2.0, 67.0], [3.0, 71.0]]
