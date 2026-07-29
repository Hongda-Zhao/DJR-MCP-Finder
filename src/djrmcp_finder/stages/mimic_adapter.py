"""Pinned MIMIC 1.0 adapter for the V0 representation benchmark.

MIMIC's downstream single-vector contract concatenates its five ordered
register tokens with a mean-pooled relevant track.  With the sequence-only
protein input used here, that relevant track is the amino-acid track, giving
``(5 + 1) * 1536 = 9216`` features per window.
"""

from __future__ import annotations

import json
from importlib import metadata as importlib_metadata
from typing import Any, Sequence

import numpy as np


MIMIC_CODE_REVISION = "15f5ef3050ea471b4c00e3f7d2be05165ff3dce8"
MIMIC_CHECKPOINT_VERSION = "1.0"
MIMIC_CHECKPOINT_REVISION = "40bb974c1b66598168117f2b561e158e769a4a8b"
MIMIC_ENCODER_DIM = 1536
MIMIC_REGISTER_COUNT = 5


def _installed_vcs_revision(distribution_name: str) -> str:
    """Return the immutable VCS commit recorded by a direct-url installation."""

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
    return str(commit)


def _as_numpy(value: Any, *, floating: bool) -> np.ndarray:
    """Copy a MIMIC tensor to NumPy without assuming it is already on CPU."""

    if hasattr(value, "detach"):
        value = value.detach()
    # Cast on the torch side because NumPy cannot represent torch.bfloat16.
    if floating and hasattr(value, "float"):
        value = value.float()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value, dtype=np.float32 if floating else np.int64)


class MimicAdapter:
    """Embed amino-acid windows with the official MIMIC 1.0 checkpoint."""

    pooling_contract = "five_ordered_registers_flattened_plus_aa_mean_then_window_mean"

    def __init__(self, settings: dict[str, Any], device: Any) -> None:
        requested_code_revision = settings.get("mimic_code_revision")
        if requested_code_revision != MIMIC_CODE_REVISION:
            raise ValueError(
                "MIMIC must be installed from the benchmark's pinned code revision: "
                f"requested={requested_code_revision!r}, required={MIMIC_CODE_REVISION!r}"
            )
        installed_code_revision = _installed_vcs_revision("mimic")
        if installed_code_revision != MIMIC_CODE_REVISION:
            raise RuntimeError(
                "Installed MIMIC code differs from the preregistered commit: "
                f"installed={installed_code_revision!r}, required={MIMIC_CODE_REVISION!r}"
            )
        requested_checkpoint = str(settings.get("mimic_checkpoint_version", "1.0"))
        if requested_checkpoint.removeprefix("v") != MIMIC_CHECKPOINT_VERSION:
            raise ValueError(
                "This adapter is frozen to MIMIC checkpoint v1.0: "
                f"requested={requested_checkpoint!r}"
            )
        requested_revision = str(settings.get("model_revision", ""))
        if requested_revision != MIMIC_CHECKPOINT_REVISION:
            raise ValueError(
                "This adapter requires the immutable MIMIC v1.0 checkpoint commit: "
                f"requested={requested_revision!r}, required={MIMIC_CHECKPOINT_REVISION!r}"
            )

        import mimic
        import transformers

        self.settings = settings
        self.device = device
        self.mimic_code_revision = MIMIC_CODE_REVISION
        self.installed_mimic_code_revision = installed_code_revision
        self.checkpoint_version = MIMIC_CHECKPOINT_VERSION
        self.checkpoint_revision = MIMIC_CHECKPOINT_REVISION
        self.resolved_revision = (
            f"checkpoint:{requested_revision}|code:{installed_code_revision}"
        )
        self.transformers_version = transformers.__version__

        # Keep the released loader as the only checkpoint construction path.
        self.model = mimic.load_pretrained(
            version="1.0",
            device=str(device),
            hf_repo=str(settings["model_name"]),
            revision=requested_revision,
        )
        self.model.eval()

        encoder_dim = int(getattr(getattr(self.model, "encoder", None), "dim", 0))
        if encoder_dim != MIMIC_ENCODER_DIM:
            raise RuntimeError(
                "Unexpected MIMIC 1.0 encoder dimension: "
                f"observed={encoder_dim}, expected={MIMIC_ENCODER_DIM}"
            )
        register_count = int(getattr(self.model, "num_register_tokens", 0))
        if register_count != MIMIC_REGISTER_COUNT:
            raise RuntimeError(
                "Unexpected MIMIC 1.0 register-token count: "
                f"observed={register_count}, expected={MIMIC_REGISTER_COUNT}"
            )
        try:
            aa_modality = self.model._lookup_mod("aa_seq")
            self.aa_group_id = int(self.model.mod_group_lookup[aa_modality])
            self.register_token_id = int(self.model.register_token_id)
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise RuntimeError(
                "Pinned MIMIC API does not expose the aa_seq/register mod_ids contract"
            ) from error
        if self.aa_group_id in {-1, self.register_token_id}:
            raise RuntimeError("MIMIC aa_seq, register, and padding mod_ids are not distinct")

        self.encoder_dim = encoder_dim
        self.embedding_dim = (register_count + 1) * encoder_dim
        self.parameter_count = int(
            sum(parameter.numel() for parameter in self.model.parameters())
        )

    def _pool_batch(self, windows: Sequence[str], representations: Any) -> np.ndarray:
        if not isinstance(representations, dict):
            raise RuntimeError("MIMIC embed() did not return a dictionary")
        if "full" not in representations or "mod_ids" not in representations:
            raise RuntimeError("MIMIC embed() must return both 'full' and 'mod_ids'")

        states = _as_numpy(representations["full"], floating=True)
        mod_ids = _as_numpy(representations["mod_ids"], floating=False)
        batch_size = len(windows)
        if states.ndim != 3 or states.shape[0] != batch_size:
            raise RuntimeError(
                "Unexpected MIMIC full representation shape: "
                f"observed={states.shape}, expected=({batch_size}, N, {self.encoder_dim})"
            )
        if states.shape[2] != self.encoder_dim:
            raise RuntimeError(
                "Unexpected MIMIC hidden dimension: "
                f"observed={states.shape[2]}, expected={self.encoder_dim}"
            )
        if mod_ids.shape != states.shape[:2]:
            raise RuntimeError(
                "MIMIC mod_ids do not align with full representations: "
                f"full={states.shape}, mod_ids={mod_ids.shape}"
            )

        vectors: list[np.ndarray] = []
        expected_register_positions = np.arange(MIMIC_REGISTER_COUNT)
        for row, window in enumerate(windows):
            row_ids = mod_ids[row]
            register_positions = np.flatnonzero(row_ids == self.register_token_id)
            if not np.array_equal(register_positions, expected_register_positions):
                raise RuntimeError(
                    "MIMIC register-token order changed: "
                    f"observed_positions={register_positions.tolist()}, "
                    f"expected_positions={expected_register_positions.tolist()}"
                )

            unexpected_ids = np.unique(
                row_ids[
                    (row_ids != -1)
                    & (row_ids != self.register_token_id)
                    & (row_ids != self.aa_group_id)
                ]
            )
            if unexpected_ids.size:
                raise RuntimeError(
                    "MIMIC sequence-only embedding returned non-aa track ids: "
                    f"{unexpected_ids.tolist()}"
                )

            aa_positions = np.flatnonzero(row_ids == self.aa_group_id)
            if aa_positions.size != len(window):
                raise RuntimeError(
                    "MIMIC amino-acid token count differs from residue count; "
                    "possible silent truncation: "
                    f"row={row}, observed_tokens={aa_positions.size}, "
                    f"expected_residues={len(window)}"
                )

            ordered_registers = states[row, register_positions].reshape(-1)
            aa_mean = states[row, aa_positions].mean(axis=0, dtype=np.float32)
            vector = np.concatenate((ordered_registers, aa_mean)).astype(
                np.float32, copy=False
            )
            if vector.shape != (self.embedding_dim,):
                raise RuntimeError(
                    f"MIMIC pooling returned {vector.shape}; expected {(self.embedding_dim,)}"
                )
            vectors.append(vector)
        return np.stack(vectors).astype(np.float32, copy=False)

    def embed_windows(self, windows: Sequence[str], batch_size: int) -> np.ndarray:
        """Return one 9216-d float32 vector per amino-acid window."""

        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if not windows:
            return np.empty((0, self.embedding_dim), dtype=np.float32)
        for index, window in enumerate(windows):
            if not isinstance(window, str) or not window:
                raise ValueError(f"MIMIC window {index} must be a non-empty amino-acid string")

        pooled_batches: list[np.ndarray] = []
        for start in range(0, len(windows), batch_size):
            selected = list(windows[start : start + batch_size])
            # The only provided modality is the raw amino-acid sequence.
            self.model.input([{"aa_seq": sequence} for sequence in selected])
            pooled_batches.append(self._pool_batch(selected, self.model.embed()))
        return np.concatenate(pooled_batches, axis=0).astype(np.float32, copy=False)
