#!/usr/bin/env python3
"""Shared fail-closed utilities for the internal cross-fitted benchmark."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Iterable, Sequence


TASKS = {
    "h1_djr": {"reference": "djr", "eligible": "all", "label": "is_djr"},
    "h2_vma_conditional": {
        "reference": "vma",
        "eligible": "djr",
        "label": "is_vma",
    },
    "vma_end_to_end": {
        "reference": "vma",
        "eligible": "all",
        "label": "is_vma",
    },
}


def cyclic_fold_roles(
    evaluation_fold: int, fold_count: int = 5, calibration_offset: int = 1
) -> tuple[int, list[int]]:
    if not 1 <= evaluation_fold <= fold_count or fold_count < 3:
        raise ValueError("Invalid cyclic fold design")
    calibration_fold = ((evaluation_fold - 1 + calibration_offset) % fold_count) + 1
    if calibration_fold == evaluation_fold:
        raise ValueError("Calibration and evaluation folds must differ")
    fit_folds = sorted(set(range(1, fold_count + 1)) - {evaluation_fold, calibration_fold})
    return calibration_fold, fit_folds


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_lines(values: Iterable[str]) -> str:
    payload = "".join(f"{value}\n" for value in values).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"TSV has no header: {path}")
        return list(reader)


def write_tsv(path: Path, rows: Sequence[dict], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(fieldnames), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})
    os.replace(temporary, path)


def read_fasta(path: Path) -> dict[str, str]:
    records: dict[str, str] = {}
    current: str | None = None
    parts: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current is not None:
                    records[current] = "".join(parts)
                current = line[1:].split()[0]
                if not current or current in records:
                    raise ValueError(f"Invalid/duplicate FASTA ID at {path}:{line_number}")
                parts = []
            else:
                if current is None:
                    raise ValueError(f"Sequence before header at {path}:{line_number}")
                parts.append(line.upper())
    if current is not None:
        records[current] = "".join(parts)
    if not records or any(not value for value in records.values()):
        raise ValueError(f"Empty FASTA or sequence: {path}")
    return records


def write_fasta(path: Path, rows: Sequence[dict[str, str]], sequences: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            protein_id = row["protein_id"]
            sequence = sequences[protein_id]
            handle.write(f">{protein_id}\n")
            for start in range(0, len(sequence), 80):
                handle.write(sequence[start : start + 80] + "\n")
    os.replace(temporary, path)


def sanitize_identifier(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return value.strip("_") or "unknown"


def profile_group(row: dict[str, str]) -> str:
    if row["source_dataset"] == "viral_vma_djr":
        cluster = row.get("source_cluster_id", "")
        group = re.sub(r"_C[0-9]+(?:_.*)?$", "", cluster)
        return "viral__" + sanitize_identifier(group or cluster)
    if row["source_dataset"] == "cellular_djr_none":
        family = row.get("family_metadata", "") or row.get("source_cluster_id", "")
        return "cellular__" + sanitize_identifier(family)
    raise ValueError(f"Profile group requested for non-DJR row {row['protein_id']}")


def load_config(config_path: Path) -> tuple[dict, Path, Path]:
    config = read_json(config_path.resolve())
    project_root = Path(config["project_root"]).resolve()
    benchmark_root = (project_root / config["benchmark_root"]).resolve()
    if not benchmark_root.is_relative_to(project_root):
        raise ValueError("benchmark_root escapes project_root")
    return config, project_root, benchmark_root


def resolved_input(config: dict, project_root: Path, key: str) -> Path:
    return (project_root / config["inputs"][key]).resolve()


def score_text(value: float) -> str:
    if math.isnan(value):
        return "NA"
    if value == -math.inf:
        return "-inf"
    if value == math.inf:
        return "inf"
    return f"{value:.17g}"


def parse_score(value: str) -> float:
    if value == "NA" or not value:
        return math.nan
    return float(value)


def run_checked(
    args: Sequence[str],
    *,
    cwd: Path,
    log_path: Path,
    stdout_path: Path | None = None,
    env: dict[str, str] | None = None,
) -> float:
    """Run one tool without a shell and preserve stdout/stderr plus wall time."""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log_handle:
        log_handle.write("COMMAND\t" + json.dumps(list(args)) + "\n")
        log_handle.flush()
        if stdout_path is None:
            completed = subprocess.run(
                list(args), cwd=cwd, stdout=log_handle, stderr=subprocess.STDOUT, env=env
            )
        else:
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            with stdout_path.open("w", encoding="utf-8") as stdout_handle:
                completed = subprocess.run(
                    list(args),
                    cwd=cwd,
                    stdout=stdout_handle,
                    stderr=log_handle,
                    env=env,
                )
        elapsed = time.monotonic() - started
        log_handle.write(f"\nRETURN_CODE\t{completed.returncode}\nWALL_SECONDS\t{elapsed:.6f}\n")
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed ({completed.returncode}): {args}; see {log_path}")
    return elapsed


def executable_sha256(config: dict, key: str) -> str:
    path = Path(config["tools"][key])
    if not path.is_file() or not os.access(path, os.X_OK):
        raise FileNotFoundError(f"Missing executable for {key}: {path}")
    return sha256_file(path)
