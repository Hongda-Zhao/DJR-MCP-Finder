from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from djrmcp_finder.stages import esm3_adapter as esm3_adapter_module
from djrmcp_finder.stages.esm3_adapter import Esm3Adapter


MODEL_REVISION = "47f0545b2b6daf26a93439a3cd610f4f7f3d5478"
ESM_CODE_REVISION = "67838dc8ac76f4145613e6cb36c5f3d758542f7c"
TRANSFORMERS_CODE_REVISION = "ef32577f55da19a4989cd7b22e004dc43a4998cb"


class _Parameter:
    def __init__(self, size: int) -> None:
        self.size = size

    def numel(self) -> int:
        return self.size


class _Protein:
    def __init__(self, *, sequence: str) -> None:
        self.sequence = sequence
        self.secondary_structure = None
        self.sasa = None
        self.function_annotations = None
        self.coordinates = None


class _LogitsConfig:
    def __init__(self, *, return_embeddings: bool = False) -> None:
        self.return_embeddings = return_embeddings


class _FakeModel:
    def __init__(self, *, malformed: str | None = None) -> None:
        self.encoder = SimpleNamespace(
            sequence_embed=SimpleNamespace(embedding_dim=3)
        )
        self.tokenizers = SimpleNamespace(
            sequence=SimpleNamespace(bos_token_id=0, eos_token_id=2)
        )
        self.malformed = malformed
        self.encoded_sequences: list[str] = []
        self.logits_calls: list[tuple[Any, _LogitsConfig]] = []
        self.eval_calls = 0

    def eval(self) -> "_FakeModel":
        self.eval_calls += 1
        return self

    def parameters(self) -> list[_Parameter]:
        return [_Parameter(7), _Parameter(11)]

    def encode(self, protein: _Protein) -> Any:
        assert protein.secondary_structure is None
        assert protein.sasa is None
        assert protein.function_annotations is None
        assert protein.coordinates is None
        self.encoded_sequences.append(protein.sequence)
        length = len(protein.sequence)
        token_count = length + 2 - (1 if self.malformed == "tokens_short" else 0)
        tokens = np.arange(token_count, dtype=np.int64)
        tokens[0] = 0
        tokens[-1] = 2
        if self.malformed == "wrong_bos":
            tokens[0] = 9
        return SimpleNamespace(sequence=tokens)

    def logits(self, encoded: Any, config: _LogitsConfig) -> Any:
        self.logits_calls.append((encoded, config))
        assert config.return_embeddings is True
        token_count = int(encoded.sequence.shape[0])
        if self.malformed == "embeddings_short":
            token_count -= 1
        rows = np.arange(token_count, dtype=np.float32)[:, None]
        embeddings = np.broadcast_to(rows, (token_count, 3)).copy()[None, :, :]
        return SimpleNamespace(embeddings=embeddings)


def _install_fake_sdk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *, malformed: str | None = None,
    resolved_revision: str = MODEL_REVISION,
) -> tuple[_FakeModel, dict[str, Any], Any]:
    model = _FakeModel(malformed=malformed)
    calls: dict[str, Any] = {"snapshots": [], "loader": []}
    original_data_root = object()

    monkeypatch.setattr(
        esm3_adapter_module,
        "_installed_vcs_revision",
        lambda name: ESM_CODE_REVISION if name == "esm" else TRANSFORMERS_CODE_REVISION,
    )

    hub = types.ModuleType("huggingface_hub")

    def snapshot_download(*, repo_id: str, revision: str) -> str:
        calls["snapshots"].append((repo_id, revision))
        path = tmp_path / "hub" / "snapshots" / resolved_revision
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    hub.snapshot_download = snapshot_download  # type: ignore[attr-defined]

    esm = types.ModuleType("esm")
    esm.__path__ = []  # type: ignore[attr-defined]
    pretrained = types.ModuleType("esm.pretrained")
    pretrained.data_root = original_data_root  # type: ignore[attr-defined]
    models = types.ModuleType("esm.models")
    models.__path__ = []  # type: ignore[attr-defined]
    esm3_module = types.ModuleType("esm.models.esm3")
    sdk = types.ModuleType("esm.sdk")
    sdk.__path__ = []  # type: ignore[attr-defined]
    api = types.ModuleType("esm.sdk.api")

    class _ESM3:
        @classmethod
        def from_pretrained(cls, *, model_name: str, device: Any) -> _FakeModel:
            pinned_root = pretrained.data_root("esm3")  # type: ignore[attr-defined,operator]
            calls["loader"].append((model_name, device, pinned_root))
            return model

    esm3_module.ESM3 = _ESM3  # type: ignore[attr-defined]
    api.ESMProtein = _Protein  # type: ignore[attr-defined]
    api.LogitsConfig = _LogitsConfig  # type: ignore[attr-defined]
    esm.pretrained = pretrained  # type: ignore[attr-defined]
    esm.models = models  # type: ignore[attr-defined]
    esm.sdk = sdk  # type: ignore[attr-defined]
    models.esm3 = esm3_module  # type: ignore[attr-defined]
    sdk.api = api  # type: ignore[attr-defined]

    for name, module in {
        "huggingface_hub": hub,
        "esm": esm,
        "esm.pretrained": pretrained,
        "esm.models": models,
        "esm.models.esm3": esm3_module,
        "esm.sdk": sdk,
        "esm.sdk.api": api,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return model, calls, original_data_root


def _settings(**updates: Any) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "model_name": "biohub/esm3-sm-open-v1",
        "model_revision": MODEL_REVISION,
        "esm_code_revision": ESM_CODE_REVISION,
        "transformers_code_revision": TRANSFORMERS_CODE_REVISION,
    }
    settings.update(updates)
    return settings


def test_adapter_pins_snapshot_restores_loader_and_pools_residues(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model, calls, original_data_root = _install_fake_sdk(monkeypatch, tmp_path)
    device = SimpleNamespace(type="cuda")

    adapter = Esm3Adapter(_settings(), device)
    vectors = adapter.embed_windows(["AC", "G"], batch_size=64)

    assert calls["snapshots"] == [
        ("biohub/esm3-sm-open-v1", MODEL_REVISION)
    ]
    assert calls["loader"] == [
        (
            "esm3-sm-open-v1",
            device,
            tmp_path / "hub" / "snapshots" / MODEL_REVISION,
        )
    ]
    assert sys.modules["esm.pretrained"].data_root is original_data_root
    assert model.encoded_sequences == ["AC", "G"]
    assert len(model.logits_calls) == 2
    assert model.eval_calls == 1
    np.testing.assert_allclose(vectors, [[1.5, 1.5, 1.5], [1.0, 1.0, 1.0]])
    assert vectors.dtype == np.float32
    assert vectors.shape == (2, 3)
    assert adapter.pooling_contract == "residue_mean_then_window_mean"
    assert adapter.embedding_dim == 3
    assert adapter.resolved_revision == MODEL_REVISION
    assert adapter.esm_code_revision == ESM_CODE_REVISION
    assert adapter.transformers_code_revision == TRANSFORMERS_CODE_REVISION
    assert adapter.parameter_count == 18
    assert adapter.transformers_version is None


@pytest.mark.parametrize(
    ("malformed", "message"),
    [
        ("tokens_short", "token length indicates truncation"),
        ("wrong_bos", "expected BOS"),
        ("embeddings_short", "embedding shape indicates truncation"),
    ],
)
def test_adapter_fails_closed_on_token_or_embedding_contract_violation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    malformed: str,
    message: str,
) -> None:
    _install_fake_sdk(monkeypatch, tmp_path, malformed=malformed)
    adapter = Esm3Adapter(_settings(), SimpleNamespace(type="cpu"))
    with pytest.raises(RuntimeError, match=message):
        adapter.embed_windows(["ACD"], batch_size=1)


def test_adapter_rejects_moving_or_mismatched_revisions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_sdk(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="model_revision must be a full"):
        Esm3Adapter(_settings(model_revision="main"), SimpleNamespace(type="cpu"))
    with pytest.raises(ValueError, match="esm_code_revision must be a full"):
        Esm3Adapter(_settings(esm_code_revision="67838dc8"), SimpleNamespace(type="cpu"))
    with pytest.raises(ValueError, match="transformers_code_revision must be a full"):
        Esm3Adapter(
            _settings(transformers_code_revision="ef32577f"),
            SimpleNamespace(type="cpu"),
        )

    _install_fake_sdk(monkeypatch, tmp_path, resolved_revision="a" * 40)
    with pytest.raises(RuntimeError, match="differs from the requested"):
        Esm3Adapter(_settings(), SimpleNamespace(type="cpu"))


def test_adapter_rejects_installed_code_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_sdk(monkeypatch, tmp_path)
    monkeypatch.setattr(
        esm3_adapter_module,
        "_installed_vcs_revision",
        lambda name: "a" * 40 if name == "esm" else TRANSFORMERS_CODE_REVISION,
    )
    with pytest.raises(RuntimeError, match="Installed ESM code differs"):
        Esm3Adapter(_settings(), SimpleNamespace(type="cpu"))


def test_adapter_validates_empty_input_and_common_batch_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_sdk(monkeypatch, tmp_path)
    adapter = Esm3Adapter(_settings(), SimpleNamespace(type="cpu"))

    empty = adapter.embed_windows([], batch_size=1)
    assert empty.shape == (0, adapter.embedding_dim)
    assert empty.dtype == np.float32
    with pytest.raises(ValueError, match="batch_size must be positive"):
        adapter.embed_windows(["A"], batch_size=0)
    with pytest.raises(ValueError, match="non-empty"):
        adapter.embed_windows([""], batch_size=1)
