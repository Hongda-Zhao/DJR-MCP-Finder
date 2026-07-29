"""Pinned, sequence-only ESM3-open adapter for the V0 embedding benchmark.

The official Biohub loader currently resolves its weight snapshot internally
without accepting a revision argument.  This adapter first resolves the exact
Hugging Face commit requested by the benchmark, then temporarily points the
official pretrained loader at that read-only snapshot.  The patch is scoped to
model construction, serialized with a lock, and always restored.

ESM3's public local inference API is single-protein.  ``embed_windows`` thus
accepts ``batch_size`` only to satisfy the common benchmark adapter interface;
it intentionally calls ``ESMProtein -> encode -> logits`` once per window.
"""

from __future__ import annotations

import json
import re
import threading
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Sequence

import numpy as np


_MODEL_REPO = "biohub/esm3-sm-open-v1"
_OFFICIAL_MODEL_NAME = "esm3-sm-open-v1"
_FULL_GIT_SHA = re.compile(r"[0-9a-f]{40}")
_DATA_ROOT_PATCH_LOCK = threading.Lock()


def _full_git_sha(value: Any, *, field: str) -> str:
    revision = str(value or "").lower()
    if _FULL_GIT_SHA.fullmatch(revision) is None:
        raise ValueError(f"{field} must be a full 40-character hexadecimal commit SHA")
    return revision


def _installed_vcs_revision(distribution_name: str) -> str:
    """Return the VCS commit recorded for a pinned direct-url installation."""

    try:
        raw = importlib_metadata.distribution(distribution_name).read_text("direct_url.json")
    except importlib_metadata.PackageNotFoundError as error:
        raise RuntimeError(
            f"Required distribution {distribution_name!r} is not installed"
        ) from error
    if not raw:
        raise RuntimeError(
            f"{distribution_name!r} lacks direct_url.json; install the preregistered git commit"
        )
    try:
        commit = json.loads(raw)["vcs_info"]["commit_id"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"{distribution_name!r} does not record an immutable VCS commit"
        ) from error
    return _full_git_sha(commit, field=f"installed {distribution_name} revision")


def _snapshot_revision(snapshot: Path) -> str:
    """Return the immutable revision encoded in an HF snapshot path."""

    if snapshot.parent.name != "snapshots":
        raise RuntimeError(
            "Hugging Face did not return an immutable snapshot directory: "
            f"expected .../snapshots/<commit>, observed {snapshot}"
        )
    return _full_git_sha(snapshot.name, field="resolved model revision")


def _tensor_numpy(value: Any) -> np.ndarray:
    """Detach an official torch tensor, while keeping tests torch-free."""

    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "float"):
        value = value.float()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value)


def _scalar_int(value: Any) -> int:
    array = _tensor_numpy(value)
    if array.size != 1:
        raise RuntimeError(f"Expected one token id, observed shape {array.shape}")
    return int(array.reshape(-1)[0])


class Esm3Adapter:
    """Extract final ESM3-open residue embeddings under a pinned contract."""

    pooling_contract = "residue_mean_then_window_mean"
    transformers_version = None

    def __init__(self, settings: dict[str, Any], device: Any) -> None:
        from huggingface_hub import snapshot_download

        model_name = str(settings.get("model_name", ""))
        if model_name.lower() != _MODEL_REPO:
            raise ValueError(
                f"Esm3Adapter only supports the official {_MODEL_REPO!r} checkpoint; "
                f"observed {model_name!r}"
            )
        requested_revision = _full_git_sha(
            settings.get("model_revision"), field="model_revision"
        )
        self.esm_code_revision = _full_git_sha(
            settings.get("esm_code_revision"), field="esm_code_revision"
        )
        self.transformers_code_revision = _full_git_sha(
            settings.get("transformers_code_revision"),
            field="transformers_code_revision",
        )
        installed_esm_revision = _installed_vcs_revision("esm")
        installed_transformers_revision = _installed_vcs_revision("transformers")
        if installed_esm_revision != self.esm_code_revision:
            raise RuntimeError(
                "Installed ESM code differs from the preregistered commit: "
                f"installed={installed_esm_revision}, required={self.esm_code_revision}"
            )
        if installed_transformers_revision != self.transformers_code_revision:
            raise RuntimeError(
                "Installed Biohub Transformers code differs from the preregistered commit: "
                f"installed={installed_transformers_revision}, "
                f"required={self.transformers_code_revision}"
            )
        self.settings = settings
        self.device = device

        snapshot = Path(
            snapshot_download(repo_id=_MODEL_REPO, revision=requested_revision)
        )
        resolved_revision = _snapshot_revision(snapshot)
        if resolved_revision != requested_revision:
            raise RuntimeError(
                "Resolved ESM3 model revision differs from the requested revision: "
                f"requested={requested_revision}, resolved={resolved_revision}"
            )

        # Import only after the immutable snapshot has been resolved.  The official
        # builder looks up ``data_root`` in esm.pretrained at call time.
        import esm.pretrained as esm_pretrained
        from esm.models.esm3 import ESM3
        from esm.sdk.api import ESMProtein, LogitsConfig

        def pinned_data_root(model: str) -> Path:
            if not str(model).startswith("esm3"):
                raise RuntimeError(
                    f"Unexpected non-ESM3 asset request while loading ESM3: {model!r}"
                )
            return snapshot

        with _DATA_ROOT_PATCH_LOCK:
            original_data_root = esm_pretrained.data_root
            esm_pretrained.data_root = pinned_data_root
            try:
                model = ESM3.from_pretrained(
                    model_name=_OFFICIAL_MODEL_NAME, device=device
                )
            finally:
                esm_pretrained.data_root = original_data_root

        self.model = model.eval()
        self._protein_type = ESMProtein
        self._logits_config_type = LogitsConfig
        self.resolved_revision = resolved_revision
        self.installed_esm_code_revision = installed_esm_revision
        self.installed_transformers_code_revision = installed_transformers_revision
        self.parameter_count = int(
            sum(int(parameter.numel()) for parameter in self.model.parameters())
        )

        sequence_embedding = getattr(
            getattr(self.model, "encoder", None), "sequence_embed", None
        )
        self.embedding_dim = int(getattr(sequence_embedding, "embedding_dim", 0))
        if self.embedding_dim <= 0:
            raise RuntimeError(
                "Official ESM3 model does not expose encoder.sequence_embed.embedding_dim"
            )

        sequence_tokenizer = getattr(
            getattr(self.model, "tokenizers", None), "sequence", None
        )
        self._bos_token_id = getattr(sequence_tokenizer, "bos_token_id", None)
        self._eos_token_id = getattr(sequence_tokenizer, "eos_token_id", None)
        if self._bos_token_id is None or self._eos_token_id is None:
            raise RuntimeError("Official ESM3 sequence tokenizer does not expose BOS/EOS ids")
        self._bos_token_id = int(self._bos_token_id)
        self._eos_token_id = int(self._eos_token_id)

    def _embed_one(self, window: str) -> np.ndarray:
        if not isinstance(window, str) or not window:
            raise ValueError("ESM3 windows must be non-empty amino-acid strings")

        # Supplying only sequence makes the inference contract explicit: no
        # structure, secondary-structure, SASA, or function track is conditioned on.
        encoded = self.model.encode(self._protein_type(sequence=window))
        sequence_tokens = getattr(encoded, "sequence", None)
        if sequence_tokens is None:
            raise RuntimeError("ESM3 encode() did not return sequence tokens")
        token_shape = tuple(int(size) for size in sequence_tokens.shape)
        expected_tokens = len(window) + 2
        if token_shape != (expected_tokens,):
            raise RuntimeError(
                "ESM3 sequence token length indicates truncation or an invalid encoding: "
                f"observed={token_shape}, expected={(expected_tokens,)}"
            )
        if _scalar_int(sequence_tokens[0]) != self._bos_token_id:
            raise RuntimeError("ESM3 encoded sequence does not begin with the expected BOS token")
        if _scalar_int(sequence_tokens[-1]) != self._eos_token_id:
            raise RuntimeError("ESM3 encoded sequence does not end with the expected EOS token")

        output = self.model.logits(
            encoded, self._logits_config_type(return_embeddings=True)
        )
        embeddings = getattr(output, "embeddings", None)
        if embeddings is None:
            raise RuntimeError("ESM3 logits() did not return requested embeddings")
        embedding_shape = tuple(int(size) for size in embeddings.shape)
        expected_shape = (1, expected_tokens, self.embedding_dim)
        if embedding_shape != expected_shape:
            raise RuntimeError(
                "ESM3 embedding shape indicates truncation or an invalid output: "
                f"observed={embedding_shape}, expected={expected_shape}"
            )

        # The official output retains the encoded BOS/EOS positions.  Exclude
        # exactly those two positions, then mean-pool all and only the residues.
        residue_embeddings = _tensor_numpy(embeddings)[0, 1:-1, :]
        if residue_embeddings.shape != (len(window), self.embedding_dim):
            raise RuntimeError(
                "ESM3 residue embedding length differs from the input sequence: "
                f"observed={residue_embeddings.shape}, "
                f"expected={(len(window), self.embedding_dim)}"
            )
        return residue_embeddings.mean(axis=0, dtype=np.float32).astype(
            np.float32, copy=False
        )

    def embed_windows(self, windows: Sequence[str], batch_size: int) -> np.ndarray:
        """Embed windows sequentially using ESM3's official single-input API."""

        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if not windows:
            return np.empty((0, self.embedding_dim), dtype=np.float32)
        # Deliberately do not construct a fake batch: encode/logits are called once
        # per window because that is the official local ESM3 inference interface.
        vectors = [self._embed_one(window) for window in windows]
        return np.stack(vectors, axis=0).astype(np.float32, copy=False)
