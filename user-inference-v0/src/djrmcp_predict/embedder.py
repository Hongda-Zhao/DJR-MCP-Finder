"""Frozen ESM-C 6B embedding contract for user-provided proteins."""

from __future__ import annotations

import json
import re
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Sequence

import numpy as np


_FULL_GIT_SHA = re.compile(r"[0-9a-f]{40}")


def sliding_windows(sequence: str, residues: int, stride: int) -> list[str]:
    if residues <= 0 or stride <= 0:
        raise ValueError("Window residues and stride must be positive")
    if len(sequence) <= residues:
        return [sequence]
    starts = list(range(0, len(sequence) - residues + 1, stride))
    final_start = len(sequence) - residues
    if starts[-1] != final_start:
        starts.append(final_start)
    return [sequence[start : start + residues] for start in starts]


def _batches(values: Sequence[str], batch_size: int) -> list[Sequence[str]]:
    if batch_size <= 0:
        raise ValueError("Batch size must be positive")
    return [values[start : start + batch_size] for start in range(0, len(values), batch_size)]


def _full_git_sha(value: Any, field: str) -> str:
    revision = str(value or "").lower()
    if _FULL_GIT_SHA.fullmatch(revision) is None:
        raise ValueError(f"{field} must be a full 40-character git SHA")
    return revision


def verify_transformers_distribution(expected_repo: str, expected_revision: str) -> dict[str, str]:
    """Require the preregistered Biohub Transformers direct-url installation."""

    expected_revision = _full_git_sha(expected_revision, "transformers_code_revision")
    try:
        distribution = importlib_metadata.distribution("transformers")
    except importlib_metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            "ESM-C inference dependencies are not installed; install with "
            "`python -m pip install -e '.[inference]'`"
        ) from exc
    raw = distribution.read_text("direct_url.json")
    if not raw:
        raise RuntimeError(
            "The installed Transformers distribution has no direct_url.json; "
            "the frozen Biohub git revision is required"
        )
    try:
        payload = json.loads(raw)
        observed_repo = str(payload["url"]).rstrip("/")
        observed_revision = _full_git_sha(
            payload["vcs_info"]["commit_id"], "installed Transformers revision"
        )
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Transformers direct_url.json lacks an immutable git revision") from exc
    if observed_repo.lower() != expected_repo.rstrip("/").lower():
        raise RuntimeError(
            f"Installed Transformers repository differs: expected={expected_repo}, "
            f"observed={observed_repo}"
        )
    if observed_revision != expected_revision:
        raise RuntimeError(
            f"Installed Transformers revision differs: expected={expected_revision}, "
            f"observed={observed_revision}"
        )
    return {"repository": observed_repo, "revision": observed_revision}


def _hidden_state(output: Any) -> Any:
    if getattr(output, "last_hidden_state", None) is not None:
        return output.last_hidden_state
    hidden_states = getattr(output, "hidden_states", None)
    if hidden_states:
        return hidden_states[-1]
    if isinstance(output, (tuple, list)) and output:
        return output[0]
    raise RuntimeError(f"Cannot locate residue hidden states in {type(output)!r}")


def _embedding_dimension(config: Any) -> int:
    """Read the standard HF or Biohub ESM-C hidden-width field."""

    for field in ("hidden_size", "d_model"):
        value = getattr(config, field, None)
        if value is not None and int(value) > 0:
            return int(value)
    return 0


class EsmcEmbedder:
    """Load the pinned ESM-C checkpoint and reproduce the frozen pooling contract."""

    def __init__(
        self,
        settings: dict[str, Any],
        *,
        device: str = "auto",
        cache_dir: str | Path | None = None,
        local_files_only: bool = False,
    ) -> None:
        self.settings = dict(settings)
        self.requested_device = device
        self.cache_dir = str(cache_dir) if cache_dir is not None else None
        self.local_files_only = bool(local_files_only)
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        transformers_install = verify_transformers_distribution(
            str(self.settings["transformers_repository"]),
            str(self.settings["transformers_code_revision"]),
        )
        try:
            import torch
            import transformers
            from transformers import AutoModelForMaskedLM, AutoTokenizer
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "ESM-C inference dependencies are missing; install the `inference` extra"
            ) from exc

        if self.requested_device == "auto":
            if not torch.cuda.is_available():
                raise RuntimeError(
                    "No CUDA GPU is available. ESM-C 6B requires about 15 GB GPU memory; "
                    "use `--device cpu` only if you explicitly accept an unvalidated, slow CPU run."
                )
            device_name = "cuda"
        else:
            device_name = self.requested_device
        device = torch.device(device_name)
        if device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
        if device.type not in {"cuda", "cpu"}:
            raise ValueError(f"Unsupported device: {device}")

        requested_revision = _full_git_sha(
            self.settings["model_revision"], "ESM-C model revision"
        )
        common = {
            "revision": requested_revision,
            "trust_remote_code": False,
            "cache_dir": self.cache_dir,
            "local_files_only": self.local_files_only,
        }
        tokenizer = AutoTokenizer.from_pretrained(self.settings["model_name"], **common)
        dtype = torch.bfloat16 if device.type == "cuda" else torch.float32
        model = AutoModelForMaskedLM.from_pretrained(
            self.settings["model_name"], torch_dtype=dtype, **common
        )
        model.to(device)
        model.eval()

        observed_revision = getattr(model.config, "_commit_hash", None)
        if observed_revision and str(observed_revision).lower() != requested_revision:
            raise RuntimeError(
                f"Resolved ESM-C revision differs: requested={requested_revision}, "
                f"observed={observed_revision}"
            )
        dimension = _embedding_dimension(model.config)
        if dimension != int(self.settings["dimension"]):
            raise RuntimeError(
                f"ESM-C embedding dimension differs: expected={self.settings['dimension']}, "
                f"observed={dimension}"
            )

        self.torch = torch
        self.transformers = transformers
        self.transformers_install = transformers_install
        self.tokenizer = tokenizer
        self.model = model
        self.device = device
        self.dimension = dimension
        self.resolved_revision = requested_revision
        self.parameter_count = int(sum(parameter.numel() for parameter in model.parameters()))
        self._loaded = True

    def _embed_windows(self, windows: Sequence[str]) -> np.ndarray:
        vectors: list[np.ndarray] = []
        batch_size = int(self.settings.get("window_batch_size", 1))
        for selected in _batches(list(windows), batch_size):
            tokenized = self.tokenizer(
                list(selected),
                return_tensors="pt",
                padding=True,
                add_special_tokens=True,
                return_special_tokens_mask=True,
                truncation=False,
            )
            special_tokens_mask = tokenized.pop("special_tokens_mask")
            if "attention_mask" not in tokenized:
                tokenized["attention_mask"] = (
                    tokenized["input_ids"] != self.tokenizer.pad_token_id
                )
            attention_mask = tokenized["attention_mask"]
            content_mask = attention_mask.to(dtype=self.torch.bool) & ~special_tokens_mask.to(
                dtype=self.torch.bool
            )
            observed = content_mask.sum(dim=1).cpu().tolist()
            expected = [len(window) for window in selected]
            if observed != expected:
                raise RuntimeError(
                    "Tokenizer is not one-token-per-residue under the frozen contract: "
                    f"observed={observed}, expected={expected}"
                )

            model_inputs = {key: value.to(self.device) for key, value in tokenized.items()}
            use_autocast = self.device.type == "cuda"
            with self.torch.inference_mode():
                with self.torch.autocast(
                    device_type=self.device.type,
                    dtype=self.torch.bfloat16,
                    enabled=use_autocast,
                ):
                    output = self.model(
                        **model_inputs, output_hidden_states=True, return_dict=True
                    )
            states = _hidden_state(output).float()
            residue_mask = (
                attention_mask.to(dtype=self.torch.bool)
                & ~special_tokens_mask.to(dtype=self.torch.bool)
            ).to(self.device)
            denominator = residue_mask.sum(dim=1, keepdim=True).clamp_min(1)
            pooled = (states * residue_mask.unsqueeze(-1)).sum(dim=1) / denominator
            vectors.append(pooled.cpu().numpy())
        return np.concatenate(vectors, axis=0).astype(np.float32, copy=False)

    def embed_sequences(self, sequences: Sequence[str]) -> np.ndarray:
        if not sequences:
            raise ValueError("No sequences were supplied for embedding")
        self._load()
        output: list[np.ndarray] = []
        residues = int(self.settings["window_residues"])
        stride = int(self.settings["stride"])
        for sequence in sequences:
            windows = sliding_windows(sequence, residues, stride)
            window_vectors = self._embed_windows(windows)
            protein_vector = window_vectors.mean(axis=0, dtype=np.float32)
            if self.settings.get("classifier_input_quantization") != "float16_roundtrip":
                raise RuntimeError("Unsupported classifier input quantization contract")
            # Training and calibration consumed float16-stored vectors cast back to float32.
            protein_vector = protein_vector.astype(np.float16).astype(np.float32)
            output.append(protein_vector)
        return np.stack(output).astype(np.float32, copy=False)

    def runtime_metadata(self) -> dict[str, Any]:
        self._load()
        gpu = None
        peak_memory = None
        if self.device.type == "cuda":
            gpu = self.torch.cuda.get_device_name(self.device)
            peak_memory = int(self.torch.cuda.max_memory_allocated(self.device))
        return {
            "device": str(self.device),
            "gpu": gpu,
            "peak_gpu_memory_bytes": peak_memory,
            "parameter_count": self.parameter_count,
            "torch": self.torch.__version__,
            "transformers": self.transformers.__version__,
            "transformers_install": self.transformers_install,
            "resolved_model_revision": self.resolved_revision,
        }
