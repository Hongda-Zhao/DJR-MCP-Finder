"""Resumable multi-backend embeddings for the V0 representation benchmark.

This module deliberately leaves the original ESM-2 V0 embedder untouched.  It
supports residue-level Hugging Face encoders and checkpoints whose native
SentenceTransformers pooling is part of the representation contract.
"""

from __future__ import annotations

import json
import platform
import re
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .embedding import (
    SequenceRecord,
    atomic_json,
    batched,
    load_records,
    sha256_file,
    sliding_windows,
    utc_now,
    write_index,
)


def _torch_dtype(torch: Any, precision: str) -> Any:
    if precision == "float16":
        return torch.float16
    if precision == "bfloat16":
        return torch.bfloat16
    if precision == "float32":
        return torch.float32
    raise ValueError(f"Unsupported compute precision: {precision}")


def _prepare_sequence(sequence: str, settings: dict[str, Any]) -> str:
    value = sequence
    if settings.get("replace_rare_with_x", False):
        value = re.sub(r"[UZOB]", "X", value)
    prefix = str(settings.get("sequence_prefix", ""))
    sequence_format = settings.get("sequence_format", "raw")
    if sequence_format == "raw":
        return prefix + value
    if sequence_format == "space_separated":
        spaced = " ".join(value)
        return f"{prefix} {spaced}" if prefix else spaced
    raise ValueError(f"Unsupported sequence_format: {sequence_format}")


def _require_pinned_revision(observed: str | None, requested: str, model_name: str) -> str:
    """Require an immutable 40-hex checkpoint revision and verify the loader result."""

    if not re.fullmatch(r"[0-9a-f]{40}", requested):
        raise RuntimeError(
            f"Benchmark model {model_name!r} is not pinned to a full commit SHA: {requested!r}"
        )
    if observed and observed != requested:
        raise RuntimeError(
            f"Resolved checkpoint differs from the preregistered revision for {model_name!r}: "
            f"observed={observed!r}, requested={requested!r}"
        )
    return observed or requested


def _hidden_state(output: Any) -> Any:
    if hasattr(output, "last_hidden_state") and output.last_hidden_state is not None:
        return output.last_hidden_state
    hidden_states = getattr(output, "hidden_states", None)
    if hidden_states:
        return hidden_states[-1]
    if hasattr(output, "encoder_last_hidden_state"):
        return output.encoder_last_hidden_state
    try:
        import torch

        if isinstance(output, torch.Tensor):
            return output
    except ModuleNotFoundError:
        pass
    if isinstance(output, (tuple, list)) and output:
        return output[0]
    raise RuntimeError(f"Cannot locate a residue hidden state in output type {type(output)!r}")


class TransformerResidueAdapter:
    pooling_contract = "residue_mean_then_window_mean"

    def __init__(self, settings: dict[str, Any], device: Any) -> None:
        library_import = settings.get("library_import")
        if library_import:
            import importlib

            importlib.import_module(str(library_import))
        import torch
        import transformers
        from transformers import AutoModel, AutoModelForMaskedLM, AutoTokenizer, T5EncoderModel

        self.settings = settings
        self.device = device
        self.torch = torch
        self.transformers_version = transformers.__version__
        precision = settings["precision"]
        dtype = _torch_dtype(torch, precision) if device.type == "cuda" else torch.float32
        common = {
            "revision": settings["model_revision"],
            "trust_remote_code": bool(settings.get("trust_remote_code", False)),
        }
        tokenizer_loader = settings.get("tokenizer_loader", "auto")
        if tokenizer_loader == "auto":
            self.tokenizer = AutoTokenizer.from_pretrained(settings["model_name"], **common)
        elif tokenizer_loader == "t5":
            from transformers import T5Tokenizer

            self.tokenizer = T5Tokenizer.from_pretrained(settings["model_name"], **common)
        else:
            raise ValueError(f"Unsupported tokenizer_loader: {tokenizer_loader}")

        model_kwargs = {**common, "torch_dtype": dtype}
        loader = settings.get("model_loader", "auto")
        if loader == "auto":
            self.model = AutoModel.from_pretrained(settings["model_name"], **model_kwargs)
        elif loader == "masked_lm":
            self.model = AutoModelForMaskedLM.from_pretrained(
                settings["model_name"], **model_kwargs
            )
        elif loader == "t5_encoder":
            self.model = T5EncoderModel.from_pretrained(settings["model_name"], **model_kwargs)
        else:
            raise ValueError(f"Unsupported model_loader: {loader}")
        self.model.to(device)
        self.model.eval()
        config = self.model.config
        self.embedding_dim = int(
            getattr(config, "hidden_size", getattr(config, "d_model", 0))
        )
        if self.embedding_dim <= 0:
            raise RuntimeError("Model config does not expose hidden_size or d_model")
        self.resolved_revision = _require_pinned_revision(
            getattr(config, "_commit_hash", None),
            str(settings["model_revision"]),
            str(settings["model_name"]),
        )
        self.parameter_count = int(sum(parameter.numel() for parameter in self.model.parameters()))

    def _tokenize(self, windows: Sequence[str]) -> tuple[dict[str, Any], Any]:
        prepared = [_prepare_sequence(window, self.settings) for window in windows]
        tokenized = self.tokenizer(
            prepared,
            return_tensors="pt",
            padding=True,
            add_special_tokens=True,
            return_special_tokens_mask=True,
            truncation=False,
        )
        special_tokens_mask = tokenized.pop("special_tokens_mask")
        if "attention_mask" not in tokenized:
            tokenized["attention_mask"] = (tokenized["input_ids"] != self.tokenizer.pad_token_id)
        content_mask = (
            tokenized["attention_mask"].to(dtype=self.torch.bool)
            & ~special_tokens_mask.to(dtype=self.torch.bool)
        )
        prefix_tokens = int(self.settings.get("prefix_token_count", 0))
        observed_before_prefix_exclusion = content_mask.sum(dim=1)
        expected_before_prefix_exclusion = self.torch.tensor(
            [len(window) + prefix_tokens for window in windows]
        )
        if not self.torch.equal(
            observed_before_prefix_exclusion.cpu(), expected_before_prefix_exclusion
        ):
            raise RuntimeError(
                "Tokenizer is not one-token-per-residue under this adapter: "
                f"observed={observed_before_prefix_exclusion.cpu().tolist()}, "
                f"expected={expected_before_prefix_exclusion.tolist()}"
            )
        if prefix_tokens:
            for row in range(content_mask.shape[0]):
                prefix_positions = self.torch.nonzero(
                    content_mask[row], as_tuple=False
                ).flatten()[:prefix_tokens]
                special_tokens_mask[row, prefix_positions] = 1
        residue_counts = (
            tokenized["attention_mask"].to(dtype=self.torch.bool)
            & ~special_tokens_mask.to(dtype=self.torch.bool)
        ).sum(dim=1)
        expected = self.torch.tensor([len(window) for window in windows])
        if not self.torch.equal(residue_counts.cpu(), expected):
            raise RuntimeError(
                "Tokenizer is not one-token-per-residue under this adapter: "
                f"observed={residue_counts.cpu().tolist()}, expected={expected.tolist()}"
            )
        return tokenized, special_tokens_mask

    def embed_windows(self, windows: Sequence[str], batch_size: int) -> np.ndarray:
        vectors: list[np.ndarray] = []
        precision = self.settings["precision"]
        use_autocast = self.device.type == "cuda" and precision in {"float16", "bfloat16"}
        autocast_dtype = _torch_dtype(self.torch, precision)
        for indices in batched(list(range(len(windows))), batch_size):
            selected = [windows[index] for index in indices]
            tokenized, special_tokens_mask = self._tokenize(selected)
            attention_mask = tokenized["attention_mask"]
            tokenized = {key: value.to(self.device) for key, value in tokenized.items()}
            with self.torch.inference_mode():
                with self.torch.autocast(
                    device_type=self.device.type,
                    dtype=autocast_dtype,
                    enabled=use_autocast,
                ):
                    if self.settings.get("model_loader") == "masked_lm":
                        output = self.model(
                            **tokenized, output_hidden_states=True, return_dict=True
                        )
                    else:
                        output = self.model(**tokenized)
            states = _hidden_state(output).float()
            residue_mask = (
                attention_mask.to(dtype=self.torch.bool)
                & ~special_tokens_mask.to(dtype=self.torch.bool)
            ).to(self.device)
            denominator = residue_mask.sum(dim=1, keepdim=True).clamp_min(1)
            pooled = (states * residue_mask.unsqueeze(-1)).sum(dim=1) / denominator
            vectors.append(pooled.cpu().numpy())
        return np.concatenate(vectors, axis=0).astype(np.float32, copy=False)


class SentenceTransformerAdapter:
    pooling_contract = "checkpoint_native_then_window_mean"

    def __init__(self, settings: dict[str, Any], device: Any) -> None:
        import sentence_transformers
        import torch
        import transformers
        from sentence_transformers import SentenceTransformer

        model_path = settings["model_name"]
        repo_subfolder = settings.get("repo_subfolder")
        snapshot_revision = None
        if repo_subfolder:
            from huggingface_hub import snapshot_download

            snapshot = snapshot_download(
                repo_id=settings["model_name"],
                revision=settings["model_revision"],
                allow_patterns=[f"{repo_subfolder}/*"],
            )
            model_path = str(Path(snapshot) / repo_subfolder)
            snapshot_revision = Path(snapshot).name

        self.settings = settings
        self.device = device
        self.torch = torch
        self.transformers_version = transformers.__version__
        self.sentence_transformers_version = sentence_transformers.__version__
        self.model = SentenceTransformer(
            model_path,
            revision=(None if repo_subfolder else settings["model_revision"]),
            device=str(device),
            trust_remote_code=bool(settings.get("trust_remote_code", False)),
            model_kwargs={"torch_dtype": _torch_dtype(torch, settings["precision"])},
        )
        self.model.eval()
        self.embedding_dim = int(self.model.get_sentence_embedding_dimension())
        first_module = self.model[0]
        auto_model = getattr(first_module, "auto_model", None)
        config = getattr(auto_model, "config", None)
        self.resolved_revision = _require_pinned_revision(
            snapshot_revision or getattr(config, "_commit_hash", None),
            str(settings["model_revision"]),
            str(settings["model_name"]),
        )
        self.parameter_count = int(sum(parameter.numel() for parameter in self.model.parameters()))

    def embed_windows(self, windows: Sequence[str], batch_size: int) -> np.ndarray:
        prepared = [_prepare_sequence(window, self.settings) for window in windows]
        # SentenceTransformer.tokenize() already applies the checkpoint's
        # truncation policy.  Count tokens with the underlying tokenizer and
        # truncation explicitly disabled before calling model.encode().
        first_module = self.model[0]
        tokenizer = getattr(first_module, "tokenizer", None)
        if tokenizer is None:
            raise RuntimeError("SentenceTransformer first module exposes no tokenizer")
        tokenized = tokenizer(
            prepared,
            add_special_tokens=True,
            padding=False,
            truncation=False,
            return_attention_mask=False,
        )
        input_ids = tokenized["input_ids"]
        if hasattr(input_ids, "tolist"):
            input_ids = input_ids.tolist()
        if input_ids and isinstance(input_ids[0], int):
            input_ids = [input_ids]
        token_lengths = [len(row) for row in input_ids]
        maximum = int(getattr(self.model, "max_seq_length", 0))
        if maximum <= 0:
            raise RuntimeError("SentenceTransformer has no finite max_seq_length")
        declared_maximum = self.settings.get("native_model_max_tokens")
        if declared_maximum is not None and maximum != int(declared_maximum):
            raise RuntimeError(
                "SentenceTransformer native max-token contract differs: "
                f"checkpoint={maximum}, configured={declared_maximum}"
            )
        if len(token_lengths) != len(prepared):
            raise RuntimeError("Underlying tokenizer returned the wrong batch cardinality")
        over_limit = [length for length in token_lengths if length > maximum]
        if over_limit:
            raise RuntimeError(
                "SentenceTransformer would truncate untruncated token lengths "
                f"{over_limit} to {maximum}"
            )
        result = self.model.encode(
            prepared,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=False,
        )
        return np.asarray(result, dtype=np.float32)


def _load_adapter(settings: dict[str, Any], device: Any) -> Any:
    backend = settings.get("backend", "transformer_residue")
    if backend == "transformer_residue":
        return TransformerResidueAdapter(settings, device)
    if backend == "sentence_transformer":
        return SentenceTransformerAdapter(settings, device)
    if backend == "mimic":
        from .mimic_adapter import MimicAdapter

        return MimicAdapter(settings, device)
    if backend == "esmc_transformer":
        from .esmc_adapter import EsmcAdapter

        return EsmcAdapter(settings, device)
    if backend == "esm3":
        from .esm3_adapter import Esm3Adapter

        return Esm3Adapter(settings, device)
    raise ValueError(f"Unsupported benchmark embedding backend: {backend}")


def _pooling_contract(settings: dict[str, Any]) -> str:
    backend = settings.get("backend", "transformer_residue")
    if backend == "sentence_transformer":
        return "checkpoint_native_then_window_mean"
    if backend == "mimic":
        return "five_ordered_registers_flattened_plus_aa_mean_then_window_mean"
    if backend == "esmc_transformer":
        return "residue_mean_then_window_mean"
    if backend == "esm3":
        return "residue_mean_then_window_mean"
    return "residue_mean_then_window_mean"


def _special_token_policy(settings: dict[str, Any]) -> str:
    backend = settings.get("backend", "transformer_residue")
    if backend == "sentence_transformer":
        return "checkpoint_native_pooling"
    if backend == "mimic":
        return "five_ordered_registers_preserved; padding_excluded_from_aa_mean"
    if backend == "esmc_transformer":
        return "bos_eos_and_padding_excluded; sequence_only_residues_mean_pooled"
    if backend == "esm3":
        return "bos_and_eos_excluded; sequence_only_residues_mean_pooled"
    return "special_and_padding_tokens_excluded_by_tokenizer_mask"


def _embed_record_batch(
    records: Sequence[SequenceRecord], adapter: Any, settings: dict[str, Any]
) -> np.ndarray:
    windows: list[str] = []
    owners: list[int] = []
    for owner, record in enumerate(records):
        selected = sliding_windows(
            record.sequence, int(settings["window_residues"]), int(settings["stride"])
        )
        windows.extend(selected)
        owners.extend([owner] * len(selected))
    window_vectors = adapter.embed_windows(windows, int(settings["window_batch_size"]))
    if window_vectors.shape != (len(windows), adapter.embedding_dim):
        raise RuntimeError(
            f"Adapter returned {window_vectors.shape}; "
            f"expected {(len(windows), adapter.embedding_dim)}"
        )
    protein_vectors = []
    owner_array = np.asarray(owners)
    for owner in range(len(records)):
        protein_vectors.append(window_vectors[owner_array == owner].mean(axis=0))
    return np.stack(protein_vectors).astype(np.float32, copy=False)


def _existing_metadata(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _validate_resume_revision(
    existing: dict[str, Any] | None, current_revision: str | None
) -> None:
    if existing is None:
        return
    existing_revision = existing.get("resolved_model_revision")
    if not existing_revision or existing_revision != current_revision:
        raise RuntimeError(
            "Refusing to resume embedding across resolved model revisions: "
            f"existing={existing_revision!r}, current={current_revision!r}"
        )


def run(
    config: dict[str, Any], *, device_override: str | None = None, limit: int | None = None
) -> dict[str, Any]:
    """Generate or resume one versioned candidate embedding matrix."""

    import torch
    import transformers

    paths = config["paths"]
    settings = config["embedding"]
    manifest_path = Path(paths["v0_manifest"])
    fasta_path = Path(paths["v0_fasta"])
    output_dir = Path(paths["embedding_output"])
    output_dir.mkdir(parents=True, exist_ok=True)
    records = load_records(manifest_path, fasta_path)

    expected_contract = {
        "schema_version": 3,
        "benchmark_model_id": settings["benchmark_model_id"],
        "model_name": settings["model_name"],
        "requested_model_revision": settings["model_revision"],
        "backend": settings.get("backend", "transformer_residue"),
        "pooling": _pooling_contract(settings),
        "window_residues": int(settings["window_residues"]),
        "stride": int(settings["stride"]),
        "dtype": settings["output_dtype"],
        "record_count": len(records),
        "manifest_sha256": sha256_file(manifest_path),
        "fasta_sha256": sha256_file(fasta_path),
        "adapter_options": {
            key: settings[key]
            for key in (
                "model_loader",
                "tokenizer_loader",
                "sequence_format",
                "sequence_prefix",
                "replace_rare_with_x",
                "trust_remote_code",
                "repo_subfolder",
                "library_import",
                "prefix_token_count",
                "native_model_max_tokens",
                "mimic_checkpoint_version",
                "mimic_code_revision",
                "esm_code_revision",
                "transformers_code_revision",
            )
            if key in settings
        },
    }
    metadata_path = output_dir / "metadata.json"
    progress_path = output_dir / "progress.json"
    vectors_path = output_dir / "embeddings.float16.npy"
    completed_path = output_dir / "completed.npy"
    index_path = output_dir / "index.tsv"
    existing = _existing_metadata(metadata_path)
    if existing is not None:
        for key, expected in expected_contract.items():
            observed = existing.get(key)
            if key == "adapter_options":
                observed = {
                    option: value for option, value in (observed or {}).items() if value is not None
                }
                expected = {
                    option: value for option, value in expected.items() if value is not None
                }
            if observed != expected:
                raise RuntimeError(
                    f"Existing embedding contract differs for {key}: "
                    f"existing={observed!r}, requested={expected!r}"
                )
        if existing.get("status") == "complete":
            return existing
    elif any(path.exists() for path in (vectors_path, completed_path, index_path)):
        raise RuntimeError(f"Untracked files already exist in {output_dir}")
    else:
        write_index(index_path, records)

    device_name = device_override or settings.get("device", "auto")
    if device_name == "auto":
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(device_name)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)

    load_started = time.perf_counter()
    adapter = _load_adapter(settings, device)
    model_load_seconds = time.perf_counter() - load_started
    _validate_resume_revision(existing, adapter.resolved_revision)

    if vectors_path.exists():
        vectors = np.lib.format.open_memmap(vectors_path, mode="r+")
        completed = np.lib.format.open_memmap(completed_path, mode="r+")
        if vectors.shape != (len(records), adapter.embedding_dim):
            raise RuntimeError(
                f"Existing vector shape {vectors.shape}; "
                f"expected {(len(records), adapter.embedding_dim)}"
            )
    else:
        vectors = np.lib.format.open_memmap(
            vectors_path,
            mode="w+",
            dtype=np.dtype(settings["output_dtype"]),
            shape=(len(records), adapter.embedding_dim),
        )
        completed = np.lib.format.open_memmap(
            completed_path, mode="w+", dtype=np.bool_, shape=(len(records),)
        )
        completed[:] = False
        completed.flush()

    metadata: dict[str, Any] = {
        **expected_contract,
        "status": "running",
        "created_utc": (existing or {}).get("created_utc", utc_now()),
        "updated_utc": utc_now(),
        "resolved_model_revision": adapter.resolved_revision,
        "embedding_dimension": adapter.embedding_dim,
        "parameter_count": adapter.parameter_count,
        "record_batch_size": int(settings["record_batch_size"]),
        "window_batch_size": int(settings["window_batch_size"]),
        "compute_precision": settings["precision"],
        "device": str(device),
        "python": sys.version.split()[0],
        "host": platform.node(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "sentence_transformers": getattr(adapter, "sentence_transformers_version", None),
        "cuda_runtime": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        "long_sequence_policy": "overlapping_windows_no_truncation",
        "special_token_policy": _special_token_policy(settings),
        "model_load_seconds_current_run": model_load_seconds,
        "accumulated_embedding_seconds": float(
            (existing or {}).get("accumulated_embedding_seconds", 0.0)
        ),
    }
    atomic_json(metadata_path, metadata)

    pending = np.flatnonzero(~np.asarray(completed, dtype=bool)).tolist()
    pending.sort(key=lambda index: len(records[index].sequence))
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        pending = pending[:limit]

    embed_started = time.perf_counter()
    for batch_number, row_indices in enumerate(
        batched(pending, int(settings["record_batch_size"])), start=1
    ):
        selected_records = [records[index] for index in row_indices]
        batch_vectors = _embed_record_batch(selected_records, adapter, settings)
        vectors[row_indices, :] = batch_vectors.astype(vectors.dtype, copy=False)
        vectors.flush()
        completed[row_indices] = True
        completed.flush()
        if batch_number == 1 or batch_number % 25 == 0:
            current_seconds = time.perf_counter() - embed_started
            atomic_json(
                progress_path,
                {
                    "updated_utc": utc_now(),
                    "completed": int(np.asarray(completed).sum()),
                    "total": len(records),
                    "embedding_seconds_current_run": current_seconds,
                    "last_batch_rows": list(row_indices),
                },
            )

    current_seconds = time.perf_counter() - embed_started
    metadata["accumulated_embedding_seconds"] += current_seconds
    completed_count = int(np.asarray(completed).sum())
    metadata["completed_records"] = completed_count
    metadata["updated_utc"] = utc_now()
    if device.type == "cuda":
        metadata["peak_gpu_memory_bytes"] = int(torch.cuda.max_memory_allocated(device))
    if completed_count == len(records):
        metadata["status"] = "complete"
        metadata["completed_utc"] = utc_now()
        metadata["records_per_second"] = (
            len(records) / metadata["accumulated_embedding_seconds"]
            if metadata["accumulated_embedding_seconds"] > 0
            else None
        )
        metadata["artifacts"] = {
            "embeddings": vectors_path.name,
            "index": index_path.name,
            "completion_bitmap": completed_path.name,
        }
        atomic_json(metadata_path, metadata)
        checksums = {
            path.name: sha256_file(path)
            for path in (vectors_path, index_path, completed_path, metadata_path)
        }
        (output_dir / "CHECKSUMS.sha256").write_text(
            "".join(f"{digest}  {name}\n" for name, digest in sorted(checksums.items())),
            encoding="utf-8",
        )
    else:
        metadata["status"] = "partial"
        atomic_json(metadata_path, metadata)
    return metadata
