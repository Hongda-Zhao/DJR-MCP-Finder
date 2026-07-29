"""Frozen mixed-encoder embedding contracts used by isolated workers."""

from __future__ import annotations

import json
import platform
import re
import sys
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Iterator, Sequence

import numpy as np


_FULL_GIT_SHA = re.compile(r"[0-9a-f]{40}")


def sliding_windows(sequence: str, residues: int, stride: int) -> list[str]:
    """Cover a protein without truncation under the frozen overlap contract."""

    if residues <= 0 or stride <= 0:
        raise ValueError("Window residues and stride must be positive")
    if len(sequence) <= residues:
        return [sequence]
    starts = list(range(0, len(sequence) - residues + 1, stride))
    final_start = len(sequence) - residues
    if starts[-1] != final_start:
        starts.append(final_start)
    return [sequence[start : start + residues] for start in starts]


def _batches(values: Sequence[str], batch_size: int) -> Iterator[Sequence[str]]:
    if batch_size <= 0:
        raise ValueError("Batch size must be positive")
    for start in range(0, len(values), batch_size):
        yield values[start : start + batch_size]


def _full_git_sha(value: Any, field: str) -> str:
    revision = str(value or "").lower()
    if _FULL_GIT_SHA.fullmatch(revision) is None:
        raise ValueError(f"{field} must be a full 40-character git SHA")
    return revision


def _installed_transformers_version() -> str:
    try:
        return importlib_metadata.version("transformers")
    except importlib_metadata.PackageNotFoundError as exc:
        raise RuntimeError("The worker's frozen Transformers distribution is missing") from exc


def verify_transformers_distribution(settings: dict[str, Any]) -> dict[str, str]:
    """Fail closed if a worker is using the wrong Transformers implementation."""

    backend = str(settings["backend"])
    observed_version = _installed_transformers_version()
    if backend == "transformer_residue":
        expected_version = str(settings["transformers_version"])
        if observed_version != expected_version:
            raise RuntimeError(
                "Installed Transformers version differs for ESM-2: "
                f"expected={expected_version}, observed={observed_version}"
            )
        return {"version": observed_version, "source": "pypi"}

    if backend != "esmc_transformer":
        raise ValueError(f"Unsupported encoder backend: {backend}")
    expected_repo = str(settings["transformers_repository"]).rstrip("/")
    expected_revision = _full_git_sha(
        settings["transformers_code_revision"], "transformers_code_revision"
    )
    distribution = importlib_metadata.distribution("transformers")
    raw = distribution.read_text("direct_url.json")
    if not raw:
        raise RuntimeError(
            "The ESM-C worker lacks Transformers direct_url.json; the frozen Biohub "
            "git revision is required"
        )
    try:
        payload = json.loads(raw)
        observed_repo = str(payload["url"]).rstrip("/")
        observed_revision = _full_git_sha(
            payload["vcs_info"]["commit_id"], "installed Transformers revision"
        )
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Transformers direct_url.json lacks an immutable git revision") from exc
    if observed_repo.lower() != expected_repo.lower():
        raise RuntimeError(
            f"Installed Transformers repository differs: expected={expected_repo}, "
            f"observed={observed_repo}"
        )
    if observed_revision != expected_revision:
        raise RuntimeError(
            f"Installed Transformers revision differs: expected={expected_revision}, "
            f"observed={observed_revision}"
        )
    expected_version = str(settings["transformers_version"])
    if observed_version != expected_version:
        raise RuntimeError(
            "Installed Biohub Transformers version differs: "
            f"expected={expected_version}, observed={observed_version}"
        )
    return {
        "version": observed_version,
        "source": "git",
        "repository": observed_repo,
        "revision": observed_revision,
    }


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
    for field in ("hidden_size", "d_model"):
        value = getattr(config, field, None)
        if value is not None and int(value) > 0:
            return int(value)
    return 0


class FrozenTransformerEmbedder:
    """Reproduce one frozen encoder's residue/window pooling and quantization."""

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
        transformers_install = verify_transformers_distribution(self.settings)
        try:
            import torch
            import transformers
            from transformers import AutoModel, AutoModelForMaskedLM, AutoTokenizer
        except ModuleNotFoundError as exc:
            raise RuntimeError("Frozen inference dependencies are missing in this worker") from exc
        if np.__version__ != "2.5.1":
            raise RuntimeError(
                f"NumPy version differs: expected=2.5.1, observed={np.__version__}"
            )
        torch_base_version = str(torch.__version__).split("+", maxsplit=1)[0]
        if torch_base_version != "2.13.0":
            raise RuntimeError(
                f"PyTorch version differs: expected=2.13.0, observed={torch.__version__}"
            )

        if self.requested_device == "auto":
            if not torch.cuda.is_available():
                raise RuntimeError(
                    "No CUDA GPU is available. Use --device cpu only if you explicitly "
                    "accept a slow, unvalidated CPU run."
                )
            device_name = "cuda"
        else:
            device_name = self.requested_device
        device = torch.device(device_name)
        if device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
        if device.type not in {"cuda", "cpu"}:
            raise ValueError(f"Unsupported device: {device}")
        if device.type == "cuda" and torch.version.cuda != "13.0":
            raise RuntimeError(
                f"CUDA runtime differs: expected=13.0, observed={torch.version.cuda}"
            )
        if (
            device.type == "cuda"
            and self.settings["compute_precision"] == "bfloat16"
            and not torch.cuda.is_bf16_supported()
        ):
            raise RuntimeError("The selected CUDA GPU does not support native bfloat16")

        requested_revision = _full_git_sha(
            self.settings["model_revision"], "model revision"
        )
        common = {
            "revision": requested_revision,
            "trust_remote_code": False,
            "cache_dir": self.cache_dir,
            "local_files_only": self.local_files_only,
        }
        tokenizer = AutoTokenizer.from_pretrained(self.settings["model_name"], **common)
        precision = str(self.settings["compute_precision"])
        if device.type == "cpu":
            dtype = torch.float32
        elif precision == "float16":
            dtype = torch.float16
        elif precision == "bfloat16":
            dtype = torch.bfloat16
        else:
            raise ValueError(f"Unsupported compute precision: {precision}")
        loader = (
            AutoModel
            if self.settings["backend"] == "transformer_residue"
            else AutoModelForMaskedLM
        )
        model = loader.from_pretrained(
            self.settings["model_name"], torch_dtype=dtype, **common
        )
        model.to(device)
        model.eval()

        observed_revision = getattr(model.config, "_commit_hash", None)
        if not observed_revision:
            raise RuntimeError("Loaded model config does not expose its resolved commit hash")
        if str(observed_revision).lower() != requested_revision:
            raise RuntimeError(
                f"Resolved model revision differs: requested={requested_revision}, "
                f"observed={observed_revision}"
            )
        dimension = _embedding_dimension(model.config)
        if dimension != int(self.settings["dimension"]):
            raise RuntimeError(
                f"Embedding dimension differs: expected={self.settings['dimension']}, "
                f"observed={dimension}"
            )

        self.torch = torch
        self.transformers = transformers
        self.transformers_install = transformers_install
        self.tokenizer = tokenizer
        self.model = model
        self.device = device
        self.dtype = dtype
        self.dimension = dimension
        self.resolved_revision = requested_revision
        self.parameter_count = int(sum(parameter.numel() for parameter in model.parameters()))
        self._loaded = True

    def _embed_windows(self, windows: Sequence[str]) -> np.ndarray:
        vectors: list[np.ndarray] = []
        batch_size = int(self.settings["window_batch_size"])
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
            with self.torch.inference_mode():
                with self.torch.autocast(
                    device_type=self.device.type,
                    dtype=self.dtype,
                    enabled=self.device.type == "cuda",
                ):
                    if self.settings.get("model_loader") == "masked_lm":
                        output = self.model(
                            **model_inputs, output_hidden_states=True, return_dict=True
                        )
                    else:
                        output = self.model(**model_inputs)
            states = _hidden_state(output).float()
            residue_mask = content_mask.to(self.device)
            denominator = residue_mask.sum(dim=1, keepdim=True).clamp_min(1)
            pooled = (states * residue_mask.unsqueeze(-1)).sum(dim=1) / denominator
            vectors.append(pooled.cpu().numpy())
        return np.concatenate(vectors, axis=0).astype(np.float32, copy=False)

    def embed_sequences(self, sequences: Sequence[str]) -> np.ndarray:
        if not sequences:
            raise ValueError("No sequences were supplied for embedding")
        self._load()
        output = np.empty((len(sequences), self.dimension), dtype=np.float32)
        residues = int(self.settings["window_residues"])
        stride = int(self.settings["stride"])
        record_batch_size = int(self.settings["record_batch_size"])
        pending = sorted(range(len(sequences)), key=lambda index: len(sequences[index]))
        for row_indices in _batches(pending, record_batch_size):
            windows: list[str] = []
            owners: list[int] = []
            for owner, row_index in enumerate(row_indices):
                selected = sliding_windows(sequences[row_index], residues, stride)
                windows.extend(selected)
                owners.extend([owner] * len(selected))
            window_vectors = self._embed_windows(windows)
            if window_vectors.shape != (len(windows), self.dimension):
                raise RuntimeError(
                    f"Encoder returned {window_vectors.shape}; "
                    f"expected {(len(windows), self.dimension)}"
                )
            owner_array = np.asarray(owners)
            for owner, row_index in enumerate(row_indices):
                protein_vector = window_vectors[owner_array == owner].mean(axis=0)
                if self.settings["classifier_input_quantization"] != "float16_roundtrip":
                    raise RuntimeError("Unsupported classifier input quantization contract")
                output[row_index] = protein_vector.astype(np.float16).astype(np.float32)
        return output

    def runtime_metadata(self) -> dict[str, Any]:
        """Return metadata only after a worker deliberately loaded this model."""

        if not self._loaded:
            raise RuntimeError("runtime_metadata called before model load")
        gpu = None
        peak_memory = None
        if self.device.type == "cuda":
            gpu = self.torch.cuda.get_device_name(self.device)
            peak_memory = int(self.torch.cuda.max_memory_allocated(self.device))
        return {
            "loaded": True,
            "device": str(self.device),
            "gpu": gpu,
            "compute_precision": self.settings["compute_precision"],
            "model_name": self.settings["model_name"],
            "backend": self.settings["backend"],
            "record_batch_size": int(self.settings["record_batch_size"]),
            "window_batch_size": int(self.settings["window_batch_size"]),
            "window_residues": int(self.settings["window_residues"]),
            "stride": int(self.settings["stride"]),
            "pooling": self.settings["pooling"],
            "peak_gpu_memory_bytes": peak_memory,
            "parameter_count": self.parameter_count,
            "python": sys.version.split()[0],
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "torch": self.torch.__version__,
            "cuda_runtime": self.torch.version.cuda,
            "transformers": self.transformers.__version__,
            "transformers_install": self.transformers_install,
            "resolved_model_revision": self.resolved_revision,
        }
