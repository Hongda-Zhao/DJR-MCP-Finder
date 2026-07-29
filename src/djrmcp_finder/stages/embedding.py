"""Frozen ESM-2 embedding generation for the V0 model dataset.

The writer is deliberately resumable.  Rows are keyed by the sequence SHA256 from
the frozen manifest and are marked complete only after their vector has been
flushed to disk.  The frozen dataset itself is never modified.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import numpy as np


@dataclass(frozen=True)
class SequenceRecord:
    """One row of the frozen manifest paired with its amino-acid sequence."""

    row: int
    protein_id: str
    sequence_sha256: str
    split: str
    sequence: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def read_fasta(path: Path) -> dict[str, str]:
    records: dict[str, str] = {}
    current_id: str | None = None
    chunks: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current_id is not None:
                    if current_id in records:
                        raise ValueError(f"Duplicate FASTA id: {current_id}")
                    records[current_id] = "".join(chunks).upper()
                current_id = line[1:].split()[0]
                if not current_id:
                    raise ValueError(f"Empty FASTA id at {path}:{line_number}")
                chunks = []
            else:
                if current_id is None:
                    raise ValueError(f"Sequence before first FASTA header at {path}:{line_number}")
                chunks.append("".join(line.split()))
    if current_id is not None:
        if current_id in records:
            raise ValueError(f"Duplicate FASTA id: {current_id}")
        records[current_id] = "".join(chunks).upper()
    if not records:
        raise ValueError(f"No FASTA records found in {path}")
    return records


def load_records(manifest_path: Path, fasta_path: Path) -> list[SequenceRecord]:
    sequences = read_fasta(fasta_path)
    required = {"protein_id", "sequence_sha256", "split", "length_aa"}
    records: list[SequenceRecord] = []
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = set(reader.fieldnames or [])
        missing = required - fields
        if missing:
            raise ValueError(f"{manifest_path} is missing columns: {sorted(missing)}")
        for row_number, row in enumerate(reader):
            protein_id = row["protein_id"].strip()
            if protein_id not in sequences:
                raise ValueError(f"Manifest protein missing from FASTA: {protein_id}")
            sequence = sequences.pop(protein_id)
            expected_length = int(row["length_aa"])
            if len(sequence) != expected_length:
                raise ValueError(
                    f"Length mismatch for {protein_id}: manifest={expected_length}, fasta={len(sequence)}"
                )
            observed_hash = hashlib.sha256(sequence.encode("ascii")).hexdigest()
            expected_hash = row["sequence_sha256"].strip()
            if observed_hash != expected_hash:
                raise ValueError(
                    f"Sequence SHA256 mismatch for {protein_id}: "
                    f"manifest={expected_hash}, observed={observed_hash}"
                )
            records.append(
                SequenceRecord(
                    row=row_number,
                    protein_id=protein_id,
                    sequence_sha256=expected_hash,
                    split=row["split"].strip(),
                    sequence=sequence,
                )
            )
    if sequences:
        examples = ", ".join(sorted(sequences)[:5])
        raise ValueError(f"FASTA contains {len(sequences)} ids absent from manifest, e.g. {examples}")
    if not records:
        raise ValueError(f"No records found in {manifest_path}")
    return records


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


def batched(values: Sequence[int], batch_size: int) -> Iterator[Sequence[int]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    for start in range(0, len(values), batch_size):
        yield values[start : start + batch_size]


def _pool_residues(last_hidden_state: Any, lengths: Sequence[int]) -> Any:
    """Mean-pool residues only, excluding BOS/EOS and padding tokens."""

    import torch

    pooled = []
    for index, length in enumerate(lengths):
        residue_states = last_hidden_state[index, 1 : length + 1, :]
        if residue_states.shape[0] != length:
            raise RuntimeError(
                f"Tokenizer/model output has {residue_states.shape[0]} residues; expected {length}"
            )
        pooled.append(residue_states.float().mean(dim=0))
    return torch.stack(pooled, dim=0)


def _embed_record_batch(
    records: Sequence[SequenceRecord],
    tokenizer: Any,
    model: Any,
    device: Any,
    precision: str,
    window_residues: int,
    stride: int,
    protein_pooling: str,
) -> np.ndarray:
    import torch

    windows: list[str] = []
    owners: list[int] = []
    for owner, record in enumerate(records):
        record_windows = sliding_windows(record.sequence, window_residues, stride)
        windows.extend(record_windows)
        owners.extend([owner] * len(record_windows))

    tokenized = tokenizer(windows, return_tensors="pt", padding=True, add_special_tokens=True)
    input_ids = tokenized["input_ids"]
    maximum_expected = window_residues + 2
    if input_ids.shape[1] > maximum_expected:
        raise RuntimeError(
            f"Tokenized length {input_ids.shape[1]} exceeds expected {maximum_expected}; "
            "silent truncation is forbidden"
        )
    tokenized = {key: value.to(device) for key, value in tokenized.items()}
    lengths = [len(window) for window in windows]

    use_autocast = device.type == "cuda" and precision in {"float16", "bfloat16"}
    autocast_dtype = torch.float16 if precision == "float16" else torch.bfloat16
    with torch.inference_mode():
        with torch.autocast(
            device_type=device.type,
            dtype=autocast_dtype,
            enabled=use_autocast,
        ):
            output = model(**tokenized)
        window_vectors = _pool_residues(output.last_hidden_state, lengths)

    protein_vectors = []
    for owner in range(len(records)):
        positions = [index for index, value in enumerate(owners) if value == owner]
        selected = window_vectors[positions]
        if protein_pooling == "mean":
            vector = selected.mean(dim=0)
        elif protein_pooling == "max":
            vector = selected.max(dim=0).values
        else:
            raise ValueError(f"Unsupported protein_pooling: {protein_pooling}")
        protein_vectors.append(vector.cpu().numpy())
    return np.stack(protein_vectors).astype(np.float32, copy=False)


def write_index(path: Path, records: Iterable[SequenceRecord]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["embedding_row", "protein_id", "sequence_sha256", "split", "length_aa"])
        for record in records:
            writer.writerow(
                [record.row, record.protein_id, record.sequence_sha256, record.split, len(record.sequence)]
            )


def _load_existing_metadata(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def run(config: dict[str, Any], *, device_override: str | None = None, limit: int | None = None) -> dict[str, Any]:
    """Generate or resume the frozen V0 ESM-2 embedding matrix."""

    try:
        import torch
        import transformers
        from transformers import AutoModel, AutoTokenizer
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Embedding requires torch and transformers; install the project with "
            + "`python -m pip install -e '.[embedding]'`"
        ) from exc

    paths = config["paths"]
    settings = config["embedding"]
    manifest_path = Path(paths["v0_manifest"])
    fasta_path = Path(paths["v0_fasta"])
    output_dir = Path(paths["embedding_output"])
    output_dir.mkdir(parents=True, exist_ok=True)

    records = load_records(manifest_path, fasta_path)
    manifest_sha256 = sha256_file(manifest_path)
    fasta_sha256 = sha256_file(fasta_path)
    index_path = output_dir / "index.tsv"
    vectors_path = output_dir / "embeddings.float16.npy"
    completed_path = output_dir / "completed.npy"
    metadata_path = output_dir / "metadata.json"
    progress_path = output_dir / "progress.json"

    expected_contract = {
        "schema_version": 1,
        "model_name": settings["model_name"],
        "requested_model_revision": settings["model_revision"],
        "pooling": "residue_mean_then_window_" + settings["protein_pooling"],
        "window_residues": int(settings["window_residues"]),
        "stride": int(settings["stride"]),
        "dtype": settings["output_dtype"],
        "record_count": len(records),
        "manifest_sha256": manifest_sha256,
        "fasta_sha256": fasta_sha256,
    }
    existing = _load_existing_metadata(metadata_path)
    if existing is not None:
        for key, expected in expected_contract.items():
            if existing.get(key) != expected:
                raise RuntimeError(
                    f"Existing embedding contract differs for {key}: "
                    f"existing={existing.get(key)!r}, requested={expected!r}. "
                    "Use a new versioned output directory."
                )
        if existing.get("status") == "complete":
            if not vectors_path.is_file() or not index_path.is_file():
                raise RuntimeError("Complete metadata exists but embedding artifacts are missing")
            return existing
    else:
        if any(path.exists() for path in (vectors_path, completed_path, index_path)):
            raise RuntimeError(
                f"Untracked files already exist in {output_dir}; refusing to overwrite them"
            )
        write_index(index_path, records)

    device_name = device_override or settings.get("device", "auto")
    if device_name == "auto":
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(device_name)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")

    tokenizer = AutoTokenizer.from_pretrained(
        settings["model_name"], revision=settings["model_revision"]
    )
    model = AutoModel.from_pretrained(
        settings["model_name"],
        revision=settings["model_revision"],
        torch_dtype=(torch.float16 if device.type == "cuda" else torch.float32),
    )
    model.to(device)
    model.eval()
    embedding_dim = int(model.config.hidden_size)
    resolved_revision = getattr(model.config, "_commit_hash", None)

    if vectors_path.exists():
        vectors = np.lib.format.open_memmap(vectors_path, mode="r+")
        completed = np.lib.format.open_memmap(completed_path, mode="r+")
        if vectors.shape != (len(records), embedding_dim):
            raise RuntimeError(f"Existing vector shape is {vectors.shape}; expected {(len(records), embedding_dim)}")
        if completed.shape != (len(records),):
            raise RuntimeError(f"Existing completion shape is {completed.shape}; expected {(len(records),)}")
    else:
        vectors = np.lib.format.open_memmap(
            vectors_path,
            mode="w+",
            dtype=np.dtype(settings["output_dtype"]),
            shape=(len(records), embedding_dim),
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
        "resolved_model_revision": resolved_revision,
        "embedding_dimension": embedding_dim,
        "batch_size": int(settings["batch_size"]),
        "compute_precision": settings["precision"],
        "device": str(device),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "cuda_runtime": torch.version.cuda,
        "gpu": (torch.cuda.get_device_name(device) if device.type == "cuda" else None),
        "long_sequence_policy": "overlapping_windows_no_truncation",
        "special_token_policy": "exclude_BOS_EOS_and_padding_from_residue_pooling",
    }
    atomic_json(metadata_path, metadata)

    pending = np.flatnonzero(~np.asarray(completed, dtype=bool)).tolist()
    pending.sort(key=lambda index: len(records[index].sequence))
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        pending = pending[:limit]

    for batch_number, row_indices in enumerate(
        batched(pending, int(settings["batch_size"])), start=1
    ):
        batch_records = [records[index] for index in row_indices]
        batch_vectors = _embed_record_batch(
            batch_records,
            tokenizer,
            model,
            device,
            settings["precision"],
            int(settings["window_residues"]),
            int(settings["stride"]),
            settings["protein_pooling"],
        )
        vectors[row_indices, :] = batch_vectors.astype(vectors.dtype, copy=False)
        vectors.flush()
        completed[row_indices] = True
        completed.flush()
        if batch_number == 1 or batch_number % 25 == 0:
            atomic_json(
                progress_path,
                {
                    "updated_utc": utc_now(),
                    "completed": int(np.asarray(completed).sum()),
                    "total": len(records),
                    "last_batch_rows": list(row_indices),
                },
            )

    completed_count = int(np.asarray(completed).sum())
    metadata["updated_utc"] = utc_now()
    metadata["completed_records"] = completed_count
    if completed_count == len(records):
        metadata["status"] = "complete"
        metadata["completed_utc"] = utc_now()
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
        checksum_path = output_dir / "CHECKSUMS.sha256"
        checksum_path.write_text(
            "".join(f"{digest}  {name}\n" for name, digest in sorted(checksums.items())),
            encoding="utf-8",
        )
    else:
        metadata["status"] = "partial"
        atomic_json(metadata_path, metadata)
    return metadata
