#!/usr/bin/env python3
"""Run receipt-bound cyclic BLAST/DIAMOND/MMseqs/HMMER/PSI-BLAST baselines."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import math
import os
import shutil
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from common import (
    atomic_json,
    cyclic_fold_roles,
    executable_sha256,
    load_config,
    read_fasta,
    read_json,
    read_tsv,
    resolved_input,
    run_checked,
    sanitize_identifier,
    score_text,
    sha256_file,
    sha256_lines,
    write_fasta,
    write_tsv,
)


PSI_METHOD = "psiblast_longest_seed_positiveDB_3iter"
CLASSICAL_METHODS = (
    "blastp",
    "diamond_ultra",
    "mmseqs_s7.5",
    "hmmer_component",
    "hmmer_family",
    PSI_METHOD,
)

SCORE_FIELDS = [
    "protein_id",
    "evaluation_fold",
    "source_fold",
    "role",
    "task",
    "method",
    "score",
    "status",
]
REFERENCE_CONTRACT_FIELDS = [
    "method",
    "evaluation_fold",
    "calibration_fold",
    "reference_kind",
    "expected_record_count",
    "observed_record_count",
    "expected_id_set_sha256",
    "observed_id_set_sha256",
    "reference_fasta_sha256",
    "reference_manifest_sha256",
    "exact_equal",
    "receipt_kind",
    "receipt_status",
]
PROFILE_MEMBER_FIELDS = [
    "evaluation_fold",
    "reference_kind",
    "method",
    "profile_id",
    "group_key",
    "member_id",
    "member_component",
    "member_fold",
    "singleton_profile",
]
INCLUSION_FIELDS = [
    "evaluation_fold",
    "reference_kind",
    "method",
    "profile_id",
    "iteration",
    "subject_id",
    "best_evalue",
    "passes_threshold_in_iteration",
]
SEED_FIELDS = [
    "evaluation_fold",
    "reference_kind",
    "method",
    "profile_id",
    "group_key",
    "seed_id",
    "seed_component",
    "seed_fold",
    "seed_length_aa",
    "reference_record_count",
    "reference_id_set_sha256",
]
ARTIFACT_FIELDS = [
    "evaluation_fold",
    "reference_kind",
    "method",
    "profile_id",
    "artifact_kind",
    "artifact_path",
    "artifact_sha256",
    "receipt_path",
    "receipt_sha256",
    "receipt_status",
]
RAW_RECEIPT_FIELDS = [
    "evaluation_fold",
    "reference_kind",
    "method",
    "stage",
    "artifact_path",
    "artifact_sha256",
    "receipt_path",
    "receipt_sha256",
    "receipt_status",
    "status",
    "argv_json",
    "input_sha256",
    "tool_sha256",
    "argv_sha256",
    "output_path",
    "output_sha256",
]
RUNTIME_FIELDS = [
    "method",
    "evaluation_fold",
    "reference_kind",
    "stage",
    "wall_seconds",
    "status",
    "receipt_path",
]

TABLE_SPECS = {
    "scores": ("scores.fold_{fold}.tsv", SCORE_FIELDS),
    "reference_contract": (
        "classical_reference_contract.fold_{fold}.tsv",
        REFERENCE_CONTRACT_FIELDS,
    ),
    "profile_members": ("profile_members.fold_{fold}.tsv", PROFILE_MEMBER_FIELDS),
    "profile_inclusion": (
        "profile_inclusion_ledger.fold_{fold}.tsv",
        INCLUSION_FIELDS,
    ),
    "psiblast_seeds": ("psiblast_seed_ledger.fold_{fold}.tsv", SEED_FIELDS),
    "profile_artifacts": (
        "profile_artifact_registry.fold_{fold}.tsv",
        ARTIFACT_FIELDS,
    ),
    "raw_receipts": ("raw_receipt_ledger.fold_{fold}.tsv", RAW_RECEIPT_FIELDS),
    "runtime": ("runtime.fold_{fold}.tsv", RUNTIME_FIELDS),
}

MERGED_TABLES = {
    "scores": "work/scores/classical_scores.tsv",
    "reference_contract": "work/classical_reference_contract.tsv",
    "profile_members": "work/profile_members.tsv",
    "profile_inclusion": "work/profile_inclusion_ledger.tsv",
    "psiblast_seeds": "work/psiblast_seed_ledger.tsv",
    "profile_artifacts": "work/profile_artifact_registry.tsv",
    "raw_receipts": "work/raw_receipt_ledger.tsv",
    "runtime": "work/runtime_resources.tsv",
}

_TOOL_SHA_CACHE: dict[str, str] = {}
_PATH_SHA_CACHE: dict[tuple[str, int, int, int], str] = {}


@dataclass(frozen=True)
class StageResult:
    seconds: float
    status: str
    receipt_path: Path
    artifact_path: Path


def tool(config: dict, name: str) -> str:
    path = Path(config["tools"][name])
    if not path.is_file() or not os.access(path, os.X_OK):
        raise FileNotFoundError(f"Required tool is unavailable: {name} -> {path}")
    return str(path)


def search_evalue_text(config: dict) -> str:
    value = float(config["parameters"]["search_evalue"])
    if value != 1000.0:
        raise RuntimeError(f"Frozen classical search E-value must be 1000, observed {value}")
    return f"{value:g}"


def tool_sha(config: dict, name: str) -> str:
    path = tool(config, name)
    if path not in _TOOL_SHA_CACHE:
        _TOOL_SHA_CACHE[path] = executable_sha256(config, name)
    return _TOOL_SHA_CACHE[path]


def stable_sha(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def relative_path(path: Path, benchmark_root: Path) -> str:
    resolved = path.resolve()
    root = benchmark_root.resolve()
    if not resolved.is_relative_to(root):
        raise RuntimeError(f"Artifact escapes benchmark root: {path}")
    return str(resolved.relative_to(root))


def path_sha(path: Path) -> str:
    if path.is_file():
        stat = path.stat()
        key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size, 0)
        if key not in _PATH_SHA_CACHE:
            _PATH_SHA_CACHE[key] = sha256_file(path)
        return _PATH_SHA_CACHE[key]
    if path.is_dir():
        stat = path.stat()
        files = [item for item in sorted(path.rglob("*")) if item.is_file()]
        metadata_sha = stable_sha(
            [
                (str(item.relative_to(path)), item.stat().st_mtime_ns, item.stat().st_size)
                for item in files
            ]
        )
        key = (str(path.resolve()), stat.st_mtime_ns, len(files), int(metadata_sha[:16], 16))
        if key in _PATH_SHA_CACHE:
            return _PATH_SHA_CACHE[key]
        entries = [
            (str(item.relative_to(path)), sha256_file(item))
            for item in files
        ]
        _PATH_SHA_CACHE[key] = stable_sha(entries)
        return _PATH_SHA_CACHE[key]
    raise FileNotFoundError(path)


def clean_exact_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def promote_directory(building: Path, final: Path) -> None:
    """Atomically swap a completed same-filesystem directory into place."""

    previous = final.with_name(final.name + ".previous")
    if previous.exists() and not final.exists():
        os.replace(previous, final)
    elif previous.exists():
        clean_exact_path(previous)
    if final.exists():
        os.replace(final, previous)
    try:
        os.replace(building, final)
    except BaseException:
        if previous.exists() and not final.exists():
            os.replace(previous, final)
        raise
    if previous.exists():
        clean_exact_path(previous)


def input_details(paths: Sequence[Path], benchmark_root: Path) -> dict[str, str]:
    details: dict[str, str] = {}
    for path in sorted({item.resolve() for item in paths}, key=str):
        label = relative_path(path, benchmark_root)
        details[label] = path_sha(path)
    return details


def receipt_binding(
    config: dict,
    benchmark_root: Path,
    evaluation_fold: int,
    reference: str,
    method: str,
    stage: str,
    argvs: Sequence[Sequence[str]],
    inputs: Sequence[Path],
    tool_names: Sequence[str],
) -> dict:
    input_map = input_details(inputs, benchmark_root)
    executable_map = {
        name: {"path": tool(config, name), "sha256": tool_sha(config, name)}
        for name in sorted(set(tool_names))
    }
    normalized_argv = [list(args) for args in argvs]
    return {
        "design_id": config["design_id"],
        "evaluation_fold": evaluation_fold,
        "reference_kind": reference,
        "method": method,
        "stage": stage,
        "argv": normalized_argv,
        "argv_sha256": stable_sha(normalized_argv),
        "inputs": input_map,
        "input_sha256": stable_sha(input_map),
        "tools": executable_map,
        "tool_sha256": stable_sha(executable_map),
    }


def receipt_is_valid(
    receipt_path: Path,
    benchmark_root: Path,
    binding: dict,
    artifact_path: Path,
) -> bool:
    if not receipt_path.is_file() or not artifact_path.is_file():
        return False
    try:
        receipt = read_json(receipt_path)
        for field in (
            "design_id",
            "evaluation_fold",
            "reference_kind",
            "method",
            "stage",
            "argv_sha256",
            "input_sha256",
            "tool_sha256",
        ):
            if receipt.get(field) != binding[field]:
                return False
        if receipt.get("status") != "PASS":
            return False
        original_seconds = float(receipt.get("wall_seconds", -1.0))
        if not math.isfinite(original_seconds) or original_seconds < 0:
            return False
        artifact_rel = relative_path(artifact_path, benchmark_root)
        artifact_digest = sha256_file(artifact_path)
        if receipt.get("artifact_path") != artifact_rel:
            return False
        if receipt.get("artifact_sha256") != artifact_digest:
            return False
        if receipt.get("output_sha256") != artifact_digest:
            return False
        outputs = receipt.get("outputs")
        if not isinstance(outputs, dict) or artifact_rel not in outputs:
            return False
        for relpath, expected in outputs.items():
            output = (benchmark_root / relpath).resolve()
            if not output.is_relative_to(benchmark_root.resolve()) or not output.is_file():
                return False
            if sha256_file(output) != expected:
                return False
        return True
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def directory_matches_receipt(
    directory: Path, receipt_path: Path, benchmark_root: Path
) -> bool:
    """Reject unregistered files that could alter a database-prefix lookup."""

    try:
        receipt = read_json(receipt_path)
        outputs = receipt.get("outputs")
        if not isinstance(outputs, dict):
            return False
        expected = {
            (benchmark_root / relative).resolve()
            for relative in outputs
            if (benchmark_root / relative).resolve().is_relative_to(directory.resolve())
        }
        observed = {path.resolve() for path in directory.rglob("*") if path.is_file()}
        return bool(expected) and observed == expected
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def publish_receipt(
    receipt_path: Path,
    benchmark_root: Path,
    binding: dict,
    artifact_path: Path,
    outputs: Sequence[Path],
    wall_seconds: float,
) -> None:
    output_map = {
        relative_path(path, benchmark_root): sha256_file(path)
        for path in sorted(set(outputs), key=str)
    }
    artifact_digest = sha256_file(artifact_path)
    artifact_rel = relative_path(artifact_path, benchmark_root)
    if artifact_rel not in output_map:
        raise RuntimeError(f"Primary artifact omitted from receipt outputs: {artifact_path}")
    atomic_json(
        receipt_path,
        {
            **binding,
            "status": "PASS",
            "artifact_path": artifact_rel,
            "artifact_sha256": artifact_digest,
            "output_sha256": artifact_digest,
            "outputs": output_map,
            "wall_seconds": wall_seconds,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )


def receipt_ledger_row(
    result: StageResult,
    benchmark_root: Path,
    evaluation_fold: int,
    reference: str,
    method: str,
    stage: str,
) -> dict[str, str]:
    receipt = read_json(result.receipt_path)
    artifact_digest = sha256_file(result.artifact_path)
    if receipt.get("status") != "PASS" or receipt.get("artifact_sha256") != artifact_digest:
        raise RuntimeError(f"Receipt/artifact mismatch: {result.receipt_path}")
    return {
        "evaluation_fold": str(evaluation_fold),
        "reference_kind": reference,
        "method": method,
        "stage": stage,
        "artifact_path": relative_path(result.artifact_path, benchmark_root),
        "artifact_sha256": artifact_digest,
        "receipt_path": relative_path(result.receipt_path, benchmark_root),
        "receipt_sha256": sha256_file(result.receipt_path),
        "receipt_status": "PASS",
        "status": "PASS",
        "argv_json": json.dumps(receipt["argv"], separators=(",", ":"), ensure_ascii=True),
        "input_sha256": receipt["input_sha256"],
        "tool_sha256": receipt["tool_sha256"],
        "argv_sha256": receipt["argv_sha256"],
        "output_path": relative_path(result.artifact_path, benchmark_root),
        "output_sha256": artifact_digest,
    }


def runtime_row(
    method: str,
    evaluation_fold: int,
    reference: str,
    stage: str,
    result: StageResult,
    benchmark_root: Path,
) -> dict[str, str]:
    return {
        "method": method,
        "evaluation_fold": str(evaluation_fold),
        "reference_kind": reference,
        "stage": stage,
        "wall_seconds": f"{result.seconds:.6f}",
        "status": result.status,
        "receipt_path": relative_path(result.receipt_path, benchmark_root),
    }


def run_logged(
    args: Sequence[str],
    *,
    cwd: Path,
    log_path: Path,
    stdout_path: Path | None = None,
) -> float:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_log = log_path.with_name(log_path.name + ".building")
    clean_exact_path(temporary_log)
    try:
        seconds = run_checked(
            args,
            cwd=cwd,
            log_path=temporary_log,
            stdout_path=stdout_path,
        )
    except BaseException:
        if temporary_log.is_file():
            os.replace(temporary_log, log_path)
        raise
    os.replace(temporary_log, log_path)
    return seconds


def run_file_stage(
    *,
    config: dict,
    benchmark_root: Path,
    evaluation_fold: int,
    reference: str,
    method: str,
    stage: str,
    final_output: Path,
    args_for_temporary: Sequence[str],
    inputs: Sequence[Path],
    tool_names: Sequence[str],
    log_path: Path,
    validate: Callable[[Path], object],
    stdout_output: bool = False,
    before_run: Callable[[], None] | None = None,
) -> StageResult:
    temporary = final_output.with_name(final_output.name + ".building")
    receipt_path = final_output.with_name(final_output.name + ".receipt.json")
    args = list(args_for_temporary)
    binding = receipt_binding(
        config,
        benchmark_root,
        evaluation_fold,
        reference,
        method,
        stage,
        [args],
        inputs,
        tool_names,
    )
    if receipt_is_valid(receipt_path, benchmark_root, binding, final_output):
        try:
            validate(final_output)
        except (OSError, RuntimeError, ValueError, ET.ParseError):
            pass
        else:
            receipt = read_json(receipt_path)
            seconds = float(receipt.get("wall_seconds", 0.0))
            if not math.isfinite(seconds) or seconds < 0:
                raise RuntimeError(f"Invalid original runtime in receipt: {receipt_path}")
            return StageResult(seconds, "reused", receipt_path, final_output)

    final_output.parent.mkdir(parents=True, exist_ok=True)
    clean_exact_path(temporary)
    if before_run is not None:
        before_run()
    seconds = run_logged(
        args,
        cwd=final_output.parent,
        log_path=log_path,
        stdout_path=temporary if stdout_output else None,
    )
    if not temporary.is_file():
        raise RuntimeError(f"External stage did not create output: {temporary}")
    validate(temporary)
    os.replace(temporary, final_output)
    publish_receipt(
        receipt_path,
        benchmark_root,
        binding,
        final_output,
        [final_output, log_path],
        seconds,
    )
    return StageResult(seconds, "ok", receipt_path, final_output)


def parse_exact_ids(path: Path, expected_ids: set[str]) -> set[str]:
    observed: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            identifier = raw.strip()
            if not identifier:
                continue
            if any(character.isspace() for character in identifier):
                raise ValueError(f"Malformed database ID at {path}:{line_number}")
            observed.append(identifier)
    if len(observed) != len(set(observed)):
        raise ValueError(f"Duplicate IDs recovered from database: {path}")
    observed_set = set(observed)
    if observed_set != expected_ids:
        missing = sorted(expected_ids - observed_set)[:5]
        extra = sorted(observed_set - expected_ids)[:5]
        raise RuntimeError(f"Database ID mismatch at {path}; missing={missing}, extra={extra}")
    return observed_set


def ensure_blast_database(
    config: dict,
    benchmark_root: Path,
    evaluation_fold: int,
    reference: str,
    method: str,
    stage: str,
    fasta: Path,
    expected_ids: set[str],
    final_dir: Path,
    log_stem: str,
) -> tuple[Path, set[str], StageResult]:
    final_ids = final_dir / "verified_ids.txt"
    final_prefix = final_dir / "reference"
    receipt_path = final_dir.with_name(final_dir.name + ".receipt.json")
    building = final_dir.with_name(final_dir.name + ".building")
    building_prefix = building / "reference"
    building_ids = building / "verified_ids.txt"
    make_args = [
        tool(config, "makeblastdb"),
        "-in",
        str(fasta),
        "-dbtype",
        "prot",
        "-parse_seqids",
        "-out",
        str(building_prefix),
    ]
    inspect_args = [
        tool(config, "blastdbcmd"),
        "-db",
        str(building_prefix),
        "-entry",
        "all",
        "-outfmt",
        "%a",
        "-out",
        str(building_ids),
    ]
    binding = receipt_binding(
        config,
        benchmark_root,
        evaluation_fold,
        reference,
        method,
        stage,
        [make_args, inspect_args],
        [fasta],
        ["makeblastdb", "blastdbcmd"],
    )
    if receipt_is_valid(
        receipt_path, benchmark_root, binding, final_ids
    ) and directory_matches_receipt(final_dir, receipt_path, benchmark_root):
        try:
            observed = parse_exact_ids(final_ids, expected_ids)
            db_files = [
                path for path in final_dir.glob("reference.*") if path.is_file() and path.stat().st_size > 0
            ]
            if len(db_files) < 3:
                raise RuntimeError(f"Incomplete BLAST database: {final_dir}")
        except (OSError, RuntimeError, ValueError):
            pass
        else:
            seconds = float(read_json(receipt_path)["wall_seconds"])
            return final_prefix, observed, StageResult(seconds, "reused", receipt_path, final_ids)

    clean_exact_path(building)
    building.mkdir(parents=True)
    make_log = benchmark_root / "logs" / f"{log_stem}.makeblastdb.log"
    inspect_log = benchmark_root / "logs" / f"{log_stem}.blastdbcmd.log"
    seconds = run_logged(make_args, cwd=building, log_path=make_log)
    seconds += run_logged(inspect_args, cwd=building, log_path=inspect_log)
    observed = parse_exact_ids(building_ids, expected_ids)
    db_files = [
        path for path in building.glob("reference.*") if path.is_file() and path.stat().st_size > 0
    ]
    if len(db_files) < 3:
        raise RuntimeError(f"makeblastdb created an incomplete database: {building}")
    promote_directory(building, final_dir)
    publish_receipt(
        receipt_path,
        benchmark_root,
        binding,
        final_ids,
        [*sorted(final_dir.iterdir()), make_log, inspect_log],
        seconds,
    )
    return final_prefix, observed, StageResult(seconds, "ok", receipt_path, final_ids)


def ensure_diamond_database(
    config: dict,
    benchmark_root: Path,
    evaluation_fold: int,
    reference: str,
    method: str,
    fasta: Path,
    expected_ids: set[str],
    final_dir: Path,
    log_stem: str,
) -> tuple[Path, set[str], StageResult]:
    final_db = final_dir / "reference.dmnd"
    final_recovered = final_dir / "verified_sequences.faa"
    receipt_path = final_dir.with_name(final_dir.name + ".receipt.json")
    building = final_dir.with_name(final_dir.name + ".building")
    building_prefix = building / "reference"
    building_db = building / "reference.dmnd"
    building_recovered = building / "verified_sequences.faa"
    make_args = [
        tool(config, "diamond"),
        "makedb",
        "--in",
        str(fasta),
        "--db",
        str(building_prefix),
    ]
    inspect_args = [
        tool(config, "diamond"),
        "getseq",
        "--db",
        str(building_db),
        "--out",
        str(building_recovered),
    ]
    binding = receipt_binding(
        config,
        benchmark_root,
        evaluation_fold,
        reference,
        method,
        "diamond_db",
        [make_args, inspect_args],
        [fasta],
        ["diamond"],
    )

    def validate_recovered(path: Path) -> set[str]:
        observed = set(read_fasta(path))
        if observed != expected_ids or len(observed) != len(expected_ids):
            raise RuntimeError(f"DIAMOND getseq ID mismatch: {path}")
        return observed

    if receipt_is_valid(
        receipt_path, benchmark_root, binding, final_db
    ) and directory_matches_receipt(final_dir, receipt_path, benchmark_root):
        try:
            observed = validate_recovered(final_recovered)
            if final_db.stat().st_size <= 0:
                raise RuntimeError(f"Empty DIAMOND database: {final_db}")
        except (OSError, RuntimeError, ValueError):
            pass
        else:
            seconds = float(read_json(receipt_path)["wall_seconds"])
            return final_db, observed, StageResult(seconds, "reused", receipt_path, final_db)

    clean_exact_path(building)
    building.mkdir(parents=True)
    make_log = benchmark_root / "logs" / f"{log_stem}.diamond_makedb.log"
    inspect_log = benchmark_root / "logs" / f"{log_stem}.diamond_getseq.log"
    seconds = run_logged(make_args, cwd=building, log_path=make_log)
    seconds += run_logged(inspect_args, cwd=building, log_path=inspect_log)
    if not building_db.is_file() or building_db.stat().st_size <= 0:
        raise RuntimeError(f"DIAMOND makedb did not produce a nonempty database: {building_db}")
    observed = validate_recovered(building_recovered)
    promote_directory(building, final_dir)
    publish_receipt(
        receipt_path,
        benchmark_root,
        binding,
        final_db,
        [final_db, final_recovered, make_log, inspect_log],
        seconds,
    )
    return final_db, observed, StageResult(seconds, "ok", receipt_path, final_db)


def parse_pairwise_hits(
    path: Path,
    query_ids: set[str],
    reference_ids: set[str],
) -> dict[str, float]:
    best = {protein_id: -math.inf for protein_id in query_ids}
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip() or raw.startswith("#"):
                continue
            fields = raw.rstrip("\n").split("\t")
            if len(fields) != 6:
                raise ValueError(f"Malformed six-column hit at {path}:{line_number}")
            query, subject = fields[:2]
            if query not in query_ids:
                raise ValueError(f"Unknown query ID at {path}:{line_number}: {query}")
            if subject not in reference_ids:
                raise ValueError(f"Unknown subject ID at {path}:{line_number}: {subject}")
            numbers = [float(value) for value in fields[2:]]
            if any(not math.isfinite(value) for value in numbers):
                raise ValueError(f"Non-finite hit field at {path}:{line_number}")
            if numbers[1] < 0.0:
                raise ValueError(f"Negative E-value at {path}:{line_number}")
            best[query] = max(best[query], numbers[0])
    return best


def reference_contract_row(
    method: str,
    evaluation_fold: int,
    reference: str,
    expected_ids: set[str],
    observed_ids: set[str],
    reference_fasta: Path,
    reference_manifest: Path,
    receipt_kind: str,
) -> dict[str, str]:
    expected_sha = sha256_lines(sorted(expected_ids))
    observed_sha = sha256_lines(sorted(observed_ids))
    exact = expected_ids == observed_ids and len(expected_ids) == len(observed_ids)
    if not exact:
        raise RuntimeError(f"Reference ID contract failed for {method} fold {evaluation_fold} {reference}")
    return {
        "method": method,
        "evaluation_fold": str(evaluation_fold),
        "calibration_fold": str(cyclic_fold_roles(evaluation_fold)[0]),
        "reference_kind": reference,
        "expected_record_count": str(len(expected_ids)),
        "observed_record_count": str(len(observed_ids)),
        "expected_id_set_sha256": expected_sha,
        "observed_id_set_sha256": observed_sha,
        "reference_fasta_sha256": sha256_file(reference_fasta),
        "reference_manifest_sha256": sha256_file(reference_manifest),
        "exact_equal": "1",
        "receipt_kind": receipt_kind,
        "receipt_status": "PASS",
    }


def run_pairwise(
    config: dict,
    benchmark_root: Path,
    evaluation_fold: int,
    reference: str,
    query_fasta: Path,
    reference_fasta: Path,
    reference_manifest: Path,
    query_ids: set[str],
    reference_ids: set[str],
) -> tuple[
    dict[str, dict[str, float]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    work = benchmark_root / f"work/classical/fold_{evaluation_fold}/{reference}/pairwise"
    logs = benchmark_root / "logs"
    work.mkdir(parents=True, exist_ok=True)
    threads = str(int(config["parameters"]["threads"]))
    evalue = search_evalue_text(config)
    all_reference_count = str(len(reference_ids))
    results: dict[str, dict[str, float]] = {}
    runtimes: list[dict[str, str]] = []
    raw_receipts: list[dict[str, str]] = []
    contracts: list[dict[str, str]] = []

    blast_prefix, observed, db_result = ensure_blast_database(
        config,
        benchmark_root,
        evaluation_fold,
        reference,
        "blastp",
        "blast_db",
        reference_fasta,
        reference_ids,
        work / "blast_db",
        f"fold_{evaluation_fold}.{reference}.blastp",
    )
    runtimes.append(runtime_row("blastp", evaluation_fold, reference, "blast_db", db_result, benchmark_root))
    raw_receipts.append(
        receipt_ledger_row(db_result, benchmark_root, evaluation_fold, reference, "blastp", "blast_db")
    )
    contracts.append(
        reference_contract_row(
            "blastp", evaluation_fold, reference, reference_ids, observed,
            reference_fasta, reference_manifest, "blast_database",
        )
    )
    blast_hits = work / "blastp.hits.tsv"
    blast_temporary = blast_hits.with_name(blast_hits.name + ".building")
    blast_args = [
        tool(config, "blastp"),
        "-query",
        str(query_fasta),
        "-db",
        str(blast_prefix),
        "-seg",
        "yes",
        "-comp_based_stats",
        "2",
        "-evalue",
        evalue,
        "-max_target_seqs",
        all_reference_count,
        "-max_hsps",
        "1",
        "-num_threads",
        threads,
        "-outfmt",
        "6 qseqid sseqid bitscore evalue pident qcovs",
        "-out",
        str(blast_temporary),
    ]
    blast_result = run_file_stage(
        config=config,
        benchmark_root=benchmark_root,
        evaluation_fold=evaluation_fold,
        reference=reference,
        method="blastp",
        stage="search_hits",
        final_output=blast_hits,
        args_for_temporary=blast_args,
        inputs=[query_fasta, reference_fasta, work / "blast_db"],
        tool_names=["blastp"],
        log_path=logs / f"fold_{evaluation_fold}.{reference}.blastp.search.log",
        validate=lambda path: parse_pairwise_hits(path, query_ids, reference_ids),
    )
    results["blastp"] = parse_pairwise_hits(blast_hits, query_ids, reference_ids)
    runtimes.append(runtime_row("blastp", evaluation_fold, reference, "search_hits", blast_result, benchmark_root))
    raw_receipts.append(
        receipt_ledger_row(blast_result, benchmark_root, evaluation_fold, reference, "blastp", "search_hits")
    )

    diamond_db, observed, db_result = ensure_diamond_database(
        config,
        benchmark_root,
        evaluation_fold,
        reference,
        "diamond_ultra",
        reference_fasta,
        reference_ids,
        work / "diamond_db",
        f"fold_{evaluation_fold}.{reference}.diamond",
    )
    runtimes.append(
        runtime_row("diamond_ultra", evaluation_fold, reference, "diamond_db", db_result, benchmark_root)
    )
    raw_receipts.append(
        receipt_ledger_row(
            db_result, benchmark_root, evaluation_fold, reference, "diamond_ultra", "diamond_db"
        )
    )
    contracts.append(
        reference_contract_row(
            "diamond_ultra", evaluation_fold, reference, reference_ids, observed,
            reference_fasta, reference_manifest, "diamond_database",
        )
    )
    diamond_hits = work / "diamond.hits.tsv"
    diamond_temporary = diamond_hits.with_name(diamond_hits.name + ".building")
    diamond_args = [
        tool(config, "diamond"),
        "blastp",
        "--ultra-sensitive",
        "--query",
        str(query_fasta),
        "--db",
        str(diamond_db),
        "--out",
        str(diamond_temporary),
        "--outfmt",
        "6",
        "qseqid",
        "sseqid",
        "bitscore",
        "evalue",
        "pident",
        "qcovhsp",
        "--evalue",
        evalue,
        "--max-target-seqs",
        all_reference_count,
        "--threads",
        threads,
    ]
    diamond_result = run_file_stage(
        config=config,
        benchmark_root=benchmark_root,
        evaluation_fold=evaluation_fold,
        reference=reference,
        method="diamond_ultra",
        stage="search_hits",
        final_output=diamond_hits,
        args_for_temporary=diamond_args,
        inputs=[query_fasta, reference_fasta, work / "diamond_db"],
        tool_names=["diamond"],
        log_path=logs / f"fold_{evaluation_fold}.{reference}.diamond.search.log",
        validate=lambda path: parse_pairwise_hits(path, query_ids, reference_ids),
    )
    results["diamond_ultra"] = parse_pairwise_hits(diamond_hits, query_ids, reference_ids)
    runtimes.append(
        runtime_row("diamond_ultra", evaluation_fold, reference, "search_hits", diamond_result, benchmark_root)
    )
    raw_receipts.append(
        receipt_ledger_row(
            diamond_result, benchmark_root, evaluation_fold, reference, "diamond_ultra", "search_hits"
        )
    )

    contracts.append(
        reference_contract_row(
            "mmseqs_s7.5", evaluation_fold, reference, reference_ids, set(read_fasta(reference_fasta)),
            reference_fasta, reference_manifest, "direct_reference_fasta",
        )
    )
    mmseqs_hits = work / "mmseqs.hits.tsv"
    mmseqs_temporary = mmseqs_hits.with_name(mmseqs_hits.name + ".building")
    mmseqs_tmp = work / "mmseqs_tmp"
    mmseqs_args = [
        tool(config, "mmseqs"),
        "easy-search",
        str(query_fasta),
        str(reference_fasta),
        str(mmseqs_temporary),
        str(mmseqs_tmp),
        "-s",
        str(config["parameters"]["mmseqs_sensitivity"]),
        "--num-iterations",
        "1",
        "--max-seqs",
        str(int(config["parameters"]["mmseqs_max_seqs"])),
        "-e",
        evalue,
        "--threads",
        threads,
        "--format-output",
        "query,target,bits,evalue,pident,qcov",
    ]
    mmseqs_result = run_file_stage(
        config=config,
        benchmark_root=benchmark_root,
        evaluation_fold=evaluation_fold,
        reference=reference,
        method="mmseqs_s7.5",
        stage="search_hits",
        final_output=mmseqs_hits,
        args_for_temporary=mmseqs_args,
        inputs=[query_fasta, reference_fasta],
        tool_names=["mmseqs"],
        log_path=logs / f"fold_{evaluation_fold}.{reference}.mmseqs.search.log",
        validate=lambda path: parse_pairwise_hits(path, query_ids, reference_ids),
        before_run=lambda: clean_exact_path(mmseqs_tmp),
    )
    clean_exact_path(mmseqs_tmp)
    results["mmseqs_s7.5"] = parse_pairwise_hits(mmseqs_hits, query_ids, reference_ids)
    runtimes.append(
        runtime_row("mmseqs_s7.5", evaluation_fold, reference, "search_hits", mmseqs_result, benchmark_root)
    )
    raw_receipts.append(
        receipt_ledger_row(
            mmseqs_result, benchmark_root, evaluation_fold, reference, "mmseqs_s7.5", "search_hits"
        )
    )
    return results, contracts, raw_receipts, runtimes


def profile_id(mode: str, group: str) -> str:
    digest = hashlib.sha256(group.encode("utf-8")).hexdigest()[:12]
    return sanitize_identifier(f"{mode}_{group}")[:80] + "__" + digest


def validate_alignment(path: Path, expected_ids: set[str]) -> None:
    sequences = read_fasta(path)
    if set(sequences) != expected_ids or len(sequences) != len(expected_ids):
        raise RuntimeError(f"Alignment ID mismatch: {path}")
    aligned_lengths = {len(sequence) for sequence in sequences.values()}
    if len(aligned_lengths) != 1:
        raise RuntimeError(f"Alignment has inconsistent row lengths: {path}")


def hmm_names(path: Path) -> list[str]:
    names: list[str] = []
    terminators = 0
    first_nonempty = ""
    with path.open(encoding="utf-8", errors="strict") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if line and not first_nonempty:
                first_nonempty = line
            if line.startswith("NAME"):
                fields = line.split(maxsplit=1)
                if len(fields) != 2 or not fields[1].strip():
                    raise ValueError(f"Malformed HMM NAME line: {path}")
                names.append(fields[1].strip())
            elif line.strip() == "//":
                terminators += 1
    if not first_nonempty.startswith("HMMER3/") or not names or terminators != len(names):
        raise ValueError(f"Malformed or incomplete HMM artifact: {path}")
    if len(names) != len(set(names)):
        raise ValueError(f"Duplicate HMM NAME values: {path}")
    return names


def validate_single_hmm(path: Path, expected_name: str) -> None:
    if hmm_names(path) != [expected_name]:
        raise RuntimeError(f"HMM NAME mismatch for {expected_name}: {path}")


def validate_hmm_library(path: Path, expected_names: set[str]) -> set[str]:
    observed = set(hmm_names(path))
    if observed != expected_names or len(observed) != len(expected_names):
        raise RuntimeError(f"HMM library profile-set mismatch: {path}")
    for suffix in (".h3f", ".h3i", ".h3m", ".h3p"):
        index = Path(str(path) + suffix)
        if not index.is_file() or index.stat().st_size <= 0:
            raise RuntimeError(f"Missing/empty hmmpress index: {index}")
    return observed


def artifact_registry_row(
    result: StageResult,
    benchmark_root: Path,
    evaluation_fold: int,
    reference: str,
    method: str,
    profile: str,
    artifact_kind: str,
) -> dict[str, str]:
    receipt = read_json(result.receipt_path)
    digest = sha256_file(result.artifact_path)
    if receipt.get("status") != "PASS" or receipt.get("artifact_sha256") != digest:
        raise RuntimeError(f"Invalid registered artifact receipt: {result.receipt_path}")
    return {
        "evaluation_fold": str(evaluation_fold),
        "reference_kind": reference,
        "method": method,
        "profile_id": profile,
        "artifact_kind": artifact_kind,
        "artifact_path": relative_path(result.artifact_path, benchmark_root),
        "artifact_sha256": digest,
        "receipt_path": relative_path(result.receipt_path, benchmark_root),
        "receipt_sha256": sha256_file(result.receipt_path),
        "receipt_status": "PASS",
    }


def ensure_hmm_library(
    config: dict,
    benchmark_root: Path,
    evaluation_fold: int,
    reference: str,
    method: str,
    profile_paths: Sequence[Path],
    expected_names: set[str],
    work: Path,
) -> tuple[Path, StageResult]:
    final_dir = work / "library"
    final_library = final_dir / "library.hmm"
    receipt_path = final_dir.with_name(final_dir.name + ".receipt.json")
    building = final_dir.with_name(final_dir.name + ".building")
    building_library = building / "library.hmm"
    args = [tool(config, "hmmpress"), "-f", str(building_library)]
    binding = receipt_binding(
        config,
        benchmark_root,
        evaluation_fold,
        reference,
        method,
        "library_hmmpress",
        [args],
        list(profile_paths),
        ["hmmpress"],
    )
    if receipt_is_valid(
        receipt_path, benchmark_root, binding, final_library
    ) and directory_matches_receipt(final_dir, receipt_path, benchmark_root):
        try:
            validate_hmm_library(final_library, expected_names)
        except (OSError, RuntimeError, ValueError):
            pass
        else:
            seconds = float(read_json(receipt_path)["wall_seconds"])
            return final_library, StageResult(seconds, "reused", receipt_path, final_library)

    clean_exact_path(building)
    building.mkdir(parents=True)
    with building_library.open("wb") as output:
        for path in profile_paths:
            output.write(path.read_bytes())
    if set(hmm_names(building_library)) != expected_names:
        raise RuntimeError(f"Concatenated HMM library mismatch: {building_library}")
    log_path = benchmark_root / "logs" / f"fold_{evaluation_fold}.{reference}.{method}.hmmpress.log"
    seconds = run_logged(args, cwd=building, log_path=log_path)
    validate_hmm_library(building_library, expected_names)
    promote_directory(building, final_dir)
    publish_receipt(
        receipt_path,
        benchmark_root,
        binding,
        final_library,
        [*sorted(final_dir.iterdir()), log_path],
        seconds,
    )
    return final_library, StageResult(seconds, "ok", receipt_path, final_library)


def parse_hmmscan_hits(
    path: Path,
    query_ids: set[str],
    profile_names: set[str],
) -> dict[str, float]:
    best = {protein_id: -math.inf for protein_id in query_ids}
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip() or raw.startswith("#"):
                continue
            fields = raw.split()
            if len(fields) < 18:
                raise ValueError(f"Malformed hmmscan tblout at {path}:{line_number}")
            target, query = fields[0], fields[2]
            if target not in profile_names:
                raise ValueError(f"Unknown HMM target at {path}:{line_number}: {target}")
            if query not in query_ids:
                raise ValueError(f"Unknown hmmscan query at {path}:{line_number}: {query}")
            score = float(fields[5])
            evalue = float(fields[4])
            if not math.isfinite(score) or not math.isfinite(evalue) or evalue < 0.0:
                raise ValueError(f"Invalid hmmscan score at {path}:{line_number}")
            best[query] = max(best[query], score)
    return best


def run_hmmer(
    config: dict,
    benchmark_root: Path,
    evaluation_fold: int,
    reference: str,
    query_fasta: Path,
    reference_fasta: Path,
    reference_manifest: Path,
    reference_rows: list[dict[str, str]],
    query_ids: set[str],
    mode: str,
) -> tuple[
    dict[str, float],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    dict[str, str],
]:
    method = f"hmmer_{mode}"
    work = benchmark_root / f"work/classical/fold_{evaluation_fold}/{reference}/{method}"
    logs = benchmark_root / "logs"
    work.mkdir(parents=True, exist_ok=True)
    reference_sequences = read_fasta(reference_fasta)
    reference_ids = set(reference_sequences)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in reference_rows:
        group = row["global_component_id"] if mode == "component" else row["profile_group"]
        if not group:
            raise RuntimeError(f"Empty {mode} profile group for {row['protein_id']}")
        grouped[group].append(row)
    if not grouped:
        raise RuntimeError(f"No HMM profile groups for fold {evaluation_fold} {reference} {mode}")

    membership: list[dict[str, str]] = []
    registry: list[dict[str, str]] = []
    raw_receipts: list[dict[str, str]] = []
    runtimes: list[dict[str, str]] = []
    profile_paths: list[Path] = []
    expected_profile_names: set[str] = set()
    for group in sorted(grouped):
        members = sorted(grouped[group], key=lambda row: row["protein_id"])
        identifier = profile_id(mode, group)
        if identifier in expected_profile_names:
            raise RuntimeError(f"HMM profile identifier collision: {identifier}")
        expected_profile_names.add(identifier)
        profile_root = work / "profiles" / identifier
        profile_root.mkdir(parents=True, exist_ok=True)
        members_fasta = profile_root / "members.faa"
        alignment = profile_root / "alignment.faa"
        hmm_path = profile_root / "profile.hmm"
        write_fasta(members_fasta, members, reference_sequences)
        member_ids = {row["protein_id"] for row in members}

        if len(members) == 1:
            write_fasta(alignment, members, reference_sequences)
            validate_alignment(alignment, member_ids)
        else:
            alignment_temporary = alignment.with_name(alignment.name + ".building")
            mafft_args = [
                tool(config, "mafft"),
                "--auto",
                "--thread",
                "1",
                str(members_fasta),
            ]
            alignment_result = run_file_stage(
                config=config,
                benchmark_root=benchmark_root,
                evaluation_fold=evaluation_fold,
                reference=reference,
                method=method,
                stage=f"profile_alignment:{identifier}",
                final_output=alignment,
                args_for_temporary=mafft_args,
                inputs=[members_fasta],
                tool_names=["mafft"],
                log_path=logs
                / f"fold_{evaluation_fold}.{reference}.{method}.{identifier}.mafft.log",
                validate=lambda path, ids=member_ids: validate_alignment(path, ids),
                stdout_output=True,
            )
            # MAFFT writes stdout, so its argv intentionally has no output argument.
            if str(alignment_temporary) in mafft_args:
                raise AssertionError("Unexpected MAFFT output argument")
            raw_receipts.append(
                receipt_ledger_row(
                    alignment_result,
                    benchmark_root,
                    evaluation_fold,
                    reference,
                    method,
                    f"profile_alignment:{identifier}",
                )
            )
            runtimes.append(
                runtime_row(
                    method,
                    evaluation_fold,
                    reference,
                    f"profile_alignment:{identifier}",
                    alignment_result,
                    benchmark_root,
                )
            )

        hmm_temporary = hmm_path.with_name(hmm_path.name + ".building")
        hmmbuild_args = [
            tool(config, "hmmbuild"),
            "--amino",
            "-n",
            identifier,
            str(hmm_temporary),
            str(alignment),
        ]
        hmm_result = run_file_stage(
            config=config,
            benchmark_root=benchmark_root,
            evaluation_fold=evaluation_fold,
            reference=reference,
            method=method,
            stage=f"profile_hmmbuild:{identifier}",
            final_output=hmm_path,
            args_for_temporary=hmmbuild_args,
            inputs=[alignment, members_fasta],
            tool_names=["hmmbuild"],
            log_path=logs
            / f"fold_{evaluation_fold}.{reference}.{method}.{identifier}.hmmbuild.log",
            validate=lambda path, name=identifier: validate_single_hmm(path, name),
        )
        profile_paths.append(hmm_path)
        raw_receipts.append(
            receipt_ledger_row(
                hmm_result,
                benchmark_root,
                evaluation_fold,
                reference,
                method,
                f"profile_hmmbuild:{identifier}",
            )
        )
        runtimes.append(
            runtime_row(
                method,
                evaluation_fold,
                reference,
                f"profile_hmmbuild:{identifier}",
                hmm_result,
                benchmark_root,
            )
        )
        registry.append(
            artifact_registry_row(
                hmm_result,
                benchmark_root,
                evaluation_fold,
                reference,
                method,
                identifier,
                "hmm_profile",
            )
        )
        for row in members:
            if row["protein_id"] not in reference_ids:
                raise RuntimeError(f"HMM member outside reference: {row['protein_id']}")
            membership.append(
                {
                    "evaluation_fold": str(evaluation_fold),
                    "reference_kind": reference,
                    "method": method,
                    "profile_id": identifier,
                    "group_key": group,
                    "member_id": row["protein_id"],
                    "member_component": row["global_component_id"],
                    "member_fold": row["fold"],
                    "singleton_profile": "1" if len(members) == 1 else "0",
                }
            )

    library, library_result = ensure_hmm_library(
        config,
        benchmark_root,
        evaluation_fold,
        reference,
        method,
        profile_paths,
        expected_profile_names,
        work,
    )
    membership_ids = [row["member_id"] for row in membership]
    if len(membership_ids) != len(reference_ids) or set(membership_ids) != reference_ids:
        raise RuntimeError(
            f"HMM profile membership does not partition the reference: "
            f"fold {evaluation_fold} {reference} {method}"
        )
    raw_receipts.append(
        receipt_ledger_row(
            library_result,
            benchmark_root,
            evaluation_fold,
            reference,
            method,
            "library_hmmpress",
        )
    )
    runtimes.append(
        runtime_row(
            method,
            evaluation_fold,
            reference,
            "library_hmmpress",
            library_result,
            benchmark_root,
        )
    )
    registry.append(
        artifact_registry_row(
            library_result,
            benchmark_root,
            evaluation_fold,
            reference,
            method,
            "__library__",
            "hmm_library",
        )
    )

    hits = work / "hmmscan.tblout"
    hits_temporary = hits.with_name(hits.name + ".building")
    hmmscan_args = [
        tool(config, "hmmscan"),
        "--max",
        "--cpu",
        str(int(config["parameters"]["threads"])),
        "--noali",
        "-E",
        search_evalue_text(config),
        "--domE",
        search_evalue_text(config),
        "--tblout",
        str(hits_temporary),
        str(library),
        str(query_fasta),
    ]
    scan_result = run_file_stage(
        config=config,
        benchmark_root=benchmark_root,
        evaluation_fold=evaluation_fold,
        reference=reference,
        method=method,
        stage="hmmscan_hits",
        final_output=hits,
        args_for_temporary=hmmscan_args,
        inputs=[query_fasta, library, library.parent],
        tool_names=["hmmscan"],
        log_path=logs / f"fold_{evaluation_fold}.{reference}.{method}.hmmscan.log",
        validate=lambda path: parse_hmmscan_hits(path, query_ids, expected_profile_names),
    )
    best = parse_hmmscan_hits(hits, query_ids, expected_profile_names)
    raw_receipts.append(
        receipt_ledger_row(
            scan_result,
            benchmark_root,
            evaluation_fold,
            reference,
            method,
            "hmmscan_hits",
        )
    )
    runtimes.append(
        runtime_row(
            method,
            evaluation_fold,
            reference,
            "hmmscan_hits",
            scan_result,
            benchmark_root,
        )
    )
    contract = reference_contract_row(
        method,
        evaluation_fold,
        reference,
        reference_ids,
        set(reference_sequences),
        reference_fasta,
        reference_manifest,
        "hmm_library",
    )
    return best, membership, registry, raw_receipts, runtimes, contract


def resolve_xml_subject(hit: ET.Element, reference_ids: set[str], path: Path) -> str:
    raw_candidates = [
        hit.findtext("Hit_accession", default=""),
        hit.findtext("Hit_def", default=""),
        hit.findtext("Hit_id", default=""),
    ]
    candidates: set[str] = set()
    for raw in raw_candidates:
        token = raw.strip().split()[0] if raw.strip() else ""
        if not token:
            continue
        candidates.add(token)
        if token.startswith("lcl|"):
            candidates.add(token[4:])
        if "|" in token:
            parts = [part for part in token.split("|") if part]
            candidates.update(parts)
    matches = candidates & reference_ids
    if len(matches) != 1:
        raise RuntimeError(
            f"PSI-BLAST XML subject does not resolve uniquely inside reference at {path}: "
            f"raw={raw_candidates!r}, matches={sorted(matches)!r}"
        )
    return next(iter(matches))


def parse_psiblast_xml(
    path: Path,
    seed_id: str,
    profile: str,
    reference_ids: set[str],
    inclusion_evalue: float,
    iteration_cap: int,
    evaluation_fold: int,
    reference: str,
) -> list[dict[str, str]]:
    root = ET.parse(path).getroot()
    query_definition = root.findtext("BlastOutput_query-def", default="").strip()
    if not query_definition or query_definition.split()[0] != seed_id:
        raise RuntimeError(f"PSI-BLAST XML top-level query is not seed {seed_id}: {path}")
    iterations = root.findall(".//Iteration")
    if not iterations:
        raise RuntimeError(f"PSI-BLAST XML contains no iterations: {path}")
    seen_iterations: set[int] = set()
    rows: list[dict[str, str]] = []
    for iteration in iterations:
        raw_number = iteration.findtext("Iteration_iter-num", default="").strip()
        try:
            iteration_number = int(raw_number)
        except ValueError as error:
            raise RuntimeError(f"Invalid PSI-BLAST iteration number in {path}: {raw_number!r}") from error
        if not 1 <= iteration_number <= iteration_cap or iteration_number in seen_iterations:
            raise RuntimeError(f"PSI-BLAST iteration outside frozen contract in {path}: {iteration_number}")
        seen_iterations.add(iteration_number)
        iteration_query = iteration.findtext("Iteration_query-def", default="").strip()
        if not iteration_query or iteration_query.split()[0] != seed_id:
            raise RuntimeError(
                f"PSI-BLAST iteration {iteration_number} query is not seed {seed_id}: {path}"
            )
        for hit in iteration.findall("./Iteration_hits/Hit"):
            subject = resolve_xml_subject(hit, reference_ids, path)
            evalues: list[float] = []
            for value in hit.findall("./Hit_hsps/Hsp/Hsp_evalue"):
                if value.text is None:
                    continue
                number = float(value.text)
                if not math.isfinite(number) or number < 0.0:
                    raise RuntimeError(f"Invalid PSI-BLAST XML E-value in {path}")
                evalues.append(number)
            if not evalues:
                raise RuntimeError(f"PSI-BLAST XML hit without HSP E-value in {path}")
            best_evalue = min(evalues)
            rows.append(
                {
                    "evaluation_fold": str(evaluation_fold),
                    "reference_kind": reference,
                    "method": PSI_METHOD,
                    "profile_id": profile,
                    "iteration": str(iteration_number),
                    "subject_id": subject,
                    "best_evalue": f"{best_evalue:.17g}",
                    "passes_threshold_in_iteration": "1"
                    if best_evalue <= inclusion_evalue
                    else "0",
                }
            )
    return rows


def validate_pssm(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(f"Missing/empty PSI-BLAST PSSM: {path}")


def ensure_psiblast_enrichment(
    config: dict,
    benchmark_root: Path,
    evaluation_fold: int,
    reference: str,
    profile: str,
    seed_id: str,
    seed_fasta: Path,
    reference_fasta: Path,
    reference_db_dir: Path,
    reference_db_prefix: Path,
    reference_ids: set[str],
    profile_root: Path,
) -> tuple[StageResult, list[dict[str, str]]]:
    final_dir = profile_root / "enrichment"
    final_pssm = final_dir / "profile.pssm"
    final_xml = final_dir / "enrichment.xml"
    receipt_path = final_dir.with_name(final_dir.name + ".receipt.json")
    building = final_dir.with_name(final_dir.name + ".building")
    building_pssm = building / "profile.pssm"
    building_xml = building / "enrichment.xml"
    iterations = int(config["parameters"]["psiblast_iterations"])
    inclusion = float(config["parameters"]["psiblast_inclusion_evalue"])
    args = [
        tool(config, "psiblast"),
        "-query",
        str(seed_fasta),
        "-db",
        str(reference_db_prefix),
        "-num_iterations",
        str(iterations),
        "-inclusion_ethresh",
        str(inclusion),
        "-evalue",
        search_evalue_text(config),
        "-max_target_seqs",
        str(len(reference_ids)),
        "-num_threads",
        "1",
        "-outfmt",
        "5",
        "-out_pssm",
        str(building_pssm),
        "-save_pssm_after_last_round",
        "-out",
        str(building_xml),
    ]
    binding = receipt_binding(
        config,
        benchmark_root,
        evaluation_fold,
        reference,
        PSI_METHOD,
        f"profile_enrichment:{profile}",
        [args],
        [seed_fasta, reference_fasta, reference_db_dir],
        ["psiblast"],
    )
    if receipt_is_valid(
        receipt_path, benchmark_root, binding, final_pssm
    ) and directory_matches_receipt(final_dir, receipt_path, benchmark_root):
        try:
            validate_pssm(final_pssm)
            ledger = parse_psiblast_xml(
                final_xml,
                seed_id,
                profile,
                reference_ids,
                inclusion,
                iterations,
                evaluation_fold,
                reference,
            )
        except (OSError, RuntimeError, ValueError, ET.ParseError):
            pass
        else:
            seconds = float(read_json(receipt_path)["wall_seconds"])
            return StageResult(seconds, "reused", receipt_path, final_pssm), ledger

    clean_exact_path(building)
    building.mkdir(parents=True)
    log_path = (
        benchmark_root
        / "logs"
        / f"fold_{evaluation_fold}.{reference}.{PSI_METHOD}.{profile}.enrich.log"
    )
    seconds = run_logged(args, cwd=building, log_path=log_path)
    validate_pssm(building_pssm)
    ledger = parse_psiblast_xml(
        building_xml,
        seed_id,
        profile,
        reference_ids,
        inclusion,
        iterations,
        evaluation_fold,
        reference,
    )
    promote_directory(building, final_dir)
    publish_receipt(
        receipt_path,
        benchmark_root,
        binding,
        final_pssm,
        [final_pssm, final_xml, log_path],
        seconds,
    )
    return StageResult(seconds, "ok", receipt_path, final_pssm), ledger


def parse_psiblast_scan(path: Path, query_ids: set[str]) -> dict[str, float]:
    best = {protein_id: -math.inf for protein_id in query_ids}
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip() or raw.startswith("#"):
                continue
            fields = raw.rstrip("\n").split("\t")
            if len(fields) != 3:
                raise ValueError(f"Malformed PSI-BLAST scan row at {path}:{line_number}")
            query, raw_score, raw_evalue = fields
            if query not in query_ids:
                raise ValueError(f"Unknown PSI-BLAST scan subject at {path}:{line_number}: {query}")
            score = float(raw_score)
            evalue = float(raw_evalue)
            if not math.isfinite(score) or not math.isfinite(evalue) or evalue < 0.0:
                raise ValueError(f"Invalid PSI-BLAST scan score at {path}:{line_number}")
            best[query] = max(best[query], score)
    return best


def run_psiblast(
    config: dict,
    benchmark_root: Path,
    evaluation_fold: int,
    reference: str,
    query_fasta: Path,
    reference_fasta: Path,
    reference_manifest: Path,
    reference_rows: list[dict[str, str]],
    query_ids: set[str],
) -> tuple[
    dict[str, float],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    dict[str, str],
]:
    work = benchmark_root / f"work/classical/fold_{evaluation_fold}/{reference}/{PSI_METHOD}"
    work.mkdir(parents=True, exist_ok=True)
    reference_sequences = read_fasta(reference_fasta)
    reference_ids = set(reference_sequences)
    reference_db_dir = work / "reference_db"
    reference_prefix, observed_ids, reference_db_result = ensure_blast_database(
        config,
        benchmark_root,
        evaluation_fold,
        reference,
        PSI_METHOD,
        "reference_db",
        reference_fasta,
        reference_ids,
        reference_db_dir,
        f"fold_{evaluation_fold}.{reference}.{PSI_METHOD}.reference",
    )
    query_db_dir = work / "query_db"
    query_prefix, observed_query_ids, query_db_result = ensure_blast_database(
        config,
        benchmark_root,
        evaluation_fold,
        reference,
        PSI_METHOD,
        "query_db",
        query_fasta,
        query_ids,
        query_db_dir,
        f"fold_{evaluation_fold}.{reference}.{PSI_METHOD}.query",
    )
    if observed_query_ids != query_ids:
        raise RuntimeError(f"PSI-BLAST query database ID mismatch in fold {evaluation_fold}")
    raw_receipts = [
        receipt_ledger_row(
            reference_db_result,
            benchmark_root,
            evaluation_fold,
            reference,
            PSI_METHOD,
            "reference_db",
        ),
        receipt_ledger_row(
            query_db_result,
            benchmark_root,
            evaluation_fold,
            reference,
            PSI_METHOD,
            "query_db",
        ),
    ]
    runtimes = [
        runtime_row(
            PSI_METHOD,
            evaluation_fold,
            reference,
            "reference_db",
            reference_db_result,
            benchmark_root,
        ),
        runtime_row(
            PSI_METHOD,
            evaluation_fold,
            reference,
            "query_db",
            query_db_result,
            benchmark_root,
        ),
    ]

    components: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in reference_rows:
        components[row["global_component_id"]].append(row)
    seeds: list[tuple[str, str, dict[str, str]]] = []
    seed_ledger: list[dict[str, str]] = []
    reference_id_sha = sha256_lines(sorted(reference_ids))
    for component in sorted(components):
        members = components[component]
        seed = sorted(
            members,
            key=lambda row: (-int(row["length_aa"]), row["protein_id"]),
        )[0]
        if len(reference_sequences[seed["protein_id"]]) != int(seed["length_aa"]):
            raise RuntimeError(f"Frozen seed length mismatch: {seed['protein_id']}")
        identifier = profile_id("psi", component)
        seeds.append((identifier, component, seed))
        seed_ledger.append(
            {
                "evaluation_fold": str(evaluation_fold),
                "reference_kind": reference,
                "method": PSI_METHOD,
                "profile_id": identifier,
                "group_key": component,
                "seed_id": seed["protein_id"],
                "seed_component": seed["global_component_id"],
                "seed_fold": seed["fold"],
                "seed_length_aa": seed["length_aa"],
                "reference_record_count": str(len(reference_ids)),
                "reference_id_set_sha256": reference_id_sha,
            }
        )

    def worker(
        item: tuple[str, str, dict[str, str]],
    ) -> tuple[
        str,
        dict[str, float],
        list[dict[str, str]],
        list[dict[str, str]],
        list[dict[str, str]],
        dict[str, str],
    ]:
        identifier, _component, seed = item
        profile_root = work / "profiles" / identifier
        profile_root.mkdir(parents=True, exist_ok=True)
        seed_fasta = profile_root / "seed.faa"
        write_fasta(seed_fasta, [seed], reference_sequences)
        enrichment_result, ledger_rows = ensure_psiblast_enrichment(
            config,
            benchmark_root,
            evaluation_fold,
            reference,
            identifier,
            seed["protein_id"],
            seed_fasta,
            reference_fasta,
            reference_db_dir,
            reference_prefix,
            reference_ids,
            profile_root,
        )
        pssm = enrichment_result.artifact_path
        hits = profile_root / "query_hits.tsv"
        hits_temporary = hits.with_name(hits.name + ".building")
        scan_args = [
            tool(config, "psiblast"),
            "-in_pssm",
            str(pssm),
            "-db",
            str(query_prefix),
            "-num_iterations",
            "1",
            "-evalue",
            search_evalue_text(config),
            "-max_target_seqs",
            str(len(query_ids)),
            "-max_hsps",
            "1",
            "-num_threads",
            "1",
            "-outfmt",
            "6 sseqid bitscore evalue",
            "-out",
            str(hits_temporary),
        ]
        scan_result = run_file_stage(
            config=config,
            benchmark_root=benchmark_root,
            evaluation_fold=evaluation_fold,
            reference=reference,
            method=PSI_METHOD,
            stage=f"scan_hits:{identifier}",
            final_output=hits,
            args_for_temporary=scan_args,
            inputs=[pssm, query_fasta, query_db_dir],
            tool_names=["psiblast"],
            log_path=benchmark_root
            / "logs"
            / f"fold_{evaluation_fold}.{reference}.{PSI_METHOD}.{identifier}.scan.log",
            validate=lambda path: parse_psiblast_scan(path, query_ids),
        )
        profile_best = parse_psiblast_scan(hits, query_ids)
        worker_raw = [
            receipt_ledger_row(
                enrichment_result,
                benchmark_root,
                evaluation_fold,
                reference,
                PSI_METHOD,
                f"profile_enrichment:{identifier}",
            ),
            receipt_ledger_row(
                scan_result,
                benchmark_root,
                evaluation_fold,
                reference,
                PSI_METHOD,
                f"scan_hits:{identifier}",
            ),
        ]
        worker_runtime = [
            runtime_row(
                PSI_METHOD,
                evaluation_fold,
                reference,
                f"profile_enrichment:{identifier}",
                enrichment_result,
                benchmark_root,
            ),
            runtime_row(
                PSI_METHOD,
                evaluation_fold,
                reference,
                f"scan_hits:{identifier}",
                scan_result,
                benchmark_root,
            ),
        ]
        artifact = artifact_registry_row(
            enrichment_result,
            benchmark_root,
            evaluation_fold,
            reference,
            PSI_METHOD,
            identifier,
            "pssm",
        )
        return identifier, profile_best, ledger_rows, worker_raw, worker_runtime, artifact

    best = {protein_id: -math.inf for protein_id in query_ids}
    inclusion_ledger: list[dict[str, str]] = []
    artifacts: list[dict[str, str]] = []
    worker_count = min(int(config["parameters"]["threads"]), max(1, len(seeds)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(worker, item) for item in seeds]
        for future in concurrent.futures.as_completed(futures):
            _identifier, profile_best, ledger_rows, worker_raw, worker_runtime, artifact = future.result()
            for protein_id, value in profile_best.items():
                best[protein_id] = max(best[protein_id], value)
            inclusion_ledger.extend(ledger_rows)
            raw_receipts.extend(worker_raw)
            runtimes.extend(worker_runtime)
            artifacts.append(artifact)

    contract = reference_contract_row(
        PSI_METHOD,
        evaluation_fold,
        reference,
        reference_ids,
        observed_ids,
        reference_fasta,
        reference_manifest,
        "blast_database",
    )
    return best, seed_ledger, inclusion_ledger, artifacts, raw_receipts, runtimes, contract


def append_task_scores(
    destination: list[dict[str, str]],
    method: str,
    evaluation_fold: int,
    reference: str,
    query_rows: list[dict[str, str]],
    scores: dict[str, float],
) -> None:
    query_ids = {row["protein_id"] for row in query_rows}
    if set(scores) != query_ids:
        raise RuntimeError(f"Incomplete score key set for {method} fold {evaluation_fold} {reference}")
    for row in query_rows:
        value = scores[row["protein_id"]]
        common = {
            "protein_id": row["protein_id"],
            "evaluation_fold": str(evaluation_fold),
            "source_fold": row["fold"],
            "role": row["benchmark_role"],
            "method": method,
            "score": score_text(value),
            "status": "no_hit" if value == -math.inf else "ok",
        }
        if reference == "djr":
            destination.append({**common, "task": "h1_djr"})
        else:
            if row["is_djr"] == "1":
                destination.append({**common, "task": "h2_vma_conditional"})
            destination.append({**common, "task": "vma_end_to_end"})


def read_tsv_strict(path: Path, expected_fields: Sequence[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != list(expected_fields):
            raise RuntimeError(
                f"TSV schema mismatch at {path}: {reader.fieldnames!r} != {list(expected_fields)!r}"
            )
        return list(reader)


def is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def validate_raw_receipt_rows(
    rows: Sequence[dict[str, str]],
    config: dict,
    benchmark_root: Path,
    evaluation_fold: int,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    if not rows:
        raise RuntimeError(f"Empty raw receipt ledger for fold {evaluation_fold}")
    artifact_map: dict[str, str] = {}
    receipt_map: dict[str, str] = {}
    external_output_map: dict[str, str] = {}
    seen_keys: set[tuple[str, str, str, str]] = set()
    for row in rows:
        key = (
            row["method"],
            row["reference_kind"],
            row["stage"],
            row["artifact_path"],
        )
        if key in seen_keys:
            raise RuntimeError(f"Duplicate raw receipt row in fold {evaluation_fold}: {key}")
        seen_keys.add(key)
        if row["evaluation_fold"] != str(evaluation_fold):
            raise RuntimeError(f"Raw receipt fold mismatch: {row}")
        if row["method"] not in CLASSICAL_METHODS or row["reference_kind"] not in {"djr", "vma"}:
            raise RuntimeError(f"Unknown method/reference in raw receipt: {row}")
        if row["receipt_status"] != "PASS" or row["status"] != "PASS":
            raise RuntimeError(f"Non-PASS raw receipt row: {row}")
        for field in (
            "artifact_sha256",
            "receipt_sha256",
            "input_sha256",
            "tool_sha256",
            "argv_sha256",
            "output_sha256",
        ):
            if not is_sha256(row[field]):
                raise RuntimeError(f"Invalid {field} in raw receipt row: {row}")
        if row["artifact_path"] != row["output_path"]:
            raise RuntimeError(f"Raw artifact/output path alias mismatch: {row}")
        if row["artifact_sha256"] != row["output_sha256"]:
            raise RuntimeError(f"Raw artifact/output SHA alias mismatch: {row}")
        artifact = (benchmark_root / row["artifact_path"]).resolve()
        receipt_path = (benchmark_root / row["receipt_path"]).resolve()
        if not artifact.is_relative_to(benchmark_root.resolve()) or not artifact.is_file():
            raise RuntimeError(f"Missing/escaped raw artifact: {artifact}")
        if not receipt_path.is_relative_to(benchmark_root.resolve()) or not receipt_path.is_file():
            raise RuntimeError(f"Missing/escaped receipt: {receipt_path}")
        if sha256_file(artifact) != row["artifact_sha256"]:
            raise RuntimeError(f"Raw artifact checksum mismatch: {artifact}")
        if sha256_file(receipt_path) != row["receipt_sha256"]:
            raise RuntimeError(f"Raw receipt checksum mismatch: {receipt_path}")
        receipt = read_json(receipt_path)
        if (
            receipt.get("status") != "PASS"
            or receipt.get("design_id") != config["design_id"]
            or receipt.get("evaluation_fold") != evaluation_fold
            or receipt.get("method") != row["method"]
            or receipt.get("reference_kind") != row["reference_kind"]
            or receipt.get("stage") != row["stage"]
            or receipt.get("artifact_path") != row["artifact_path"]
            or receipt.get("artifact_sha256") != row["artifact_sha256"]
            or receipt.get("output_sha256") != row["output_sha256"]
        ):
            raise RuntimeError(f"Raw receipt semantic mismatch: {receipt_path}")
        for field in ("input_sha256", "tool_sha256", "argv_sha256"):
            if receipt.get(field) != row[field]:
                raise RuntimeError(f"Receipt {field} mismatch: {receipt_path}")
        if stable_sha(receipt.get("argv")) != receipt.get("argv_sha256"):
            raise RuntimeError(f"Receipt argv digest mismatch: {receipt_path}")
        if json.loads(row["argv_json"]) != receipt.get("argv"):
            raise RuntimeError(f"Ledger argv JSON mismatch: {receipt_path}")
        receipt_inputs = receipt.get("inputs")
        if not isinstance(receipt_inputs, dict) or stable_sha(receipt_inputs) != receipt.get("input_sha256"):
            raise RuntimeError(f"Receipt input digest mismatch: {receipt_path}")
        for relpath, expected in receipt_inputs.items():
            input_path = (benchmark_root / relpath).resolve()
            if not input_path.is_relative_to(benchmark_root.resolve()) or path_sha(input_path) != expected:
                raise RuntimeError(f"Receipt input changed: {relpath}")
        receipt_tools = receipt.get("tools")
        if not isinstance(receipt_tools, dict) or stable_sha(receipt_tools) != receipt.get("tool_sha256"):
            raise RuntimeError(f"Receipt tool digest mismatch: {receipt_path}")
        for name, description in receipt_tools.items():
            if name not in config["tools"] or description.get("path") != tool(config, name):
                raise RuntimeError(f"Receipt tool path mismatch: {receipt_path}")
            if description.get("sha256") != tool_sha(config, name):
                raise RuntimeError(f"Receipt tool executable changed: {receipt_path}")
        outputs = receipt.get("outputs")
        if not isinstance(outputs, dict) or row["artifact_path"] not in outputs:
            raise RuntimeError(f"Receipt output map is malformed: {receipt_path}")
        for relpath, expected in outputs.items():
            output = (benchmark_root / relpath).resolve()
            if not output.is_relative_to(benchmark_root.resolve()) or not output.is_file():
                raise RuntimeError(f"Receipt output missing/escaped: {relpath}")
            if sha256_file(output) != expected:
                raise RuntimeError(f"Receipt output checksum changed: {relpath}")
            if relpath in external_output_map and external_output_map[relpath] != expected:
                raise RuntimeError(f"Conflicting receipt output checksums: {relpath}")
            external_output_map[relpath] = expected
        artifact_map[row["artifact_path"]] = row["artifact_sha256"]
        receipt_map[row["receipt_path"]] = row["receipt_sha256"]
    return (
        dict(sorted(artifact_map.items())),
        dict(sorted(receipt_map.items())),
        dict(sorted(external_output_map.items())),
    )


def validate_raw_coverage(
    rows: Sequence[dict[str, str]],
    evaluation_fold: int,
    profile_members: Sequence[dict[str, str]],
    psiblast_seeds: Sequence[dict[str, str]],
) -> None:
    stages: dict[tuple[str, str], list[str]] = defaultdict(list)
    artifacts: dict[tuple[str, str, str], str] = {}
    for row in rows:
        stages[(row["method"], row["reference_kind"])].append(row["stage"].lower())
        artifacts[(row["method"], row["reference_kind"], row["stage"])] = row["artifact_path"]
    for method in CLASSICAL_METHODS:
        for reference in ("djr", "vma"):
            observed = stages[(method, reference)]
            if not observed:
                raise RuntimeError(f"No raw receipts for fold {evaluation_fold} {reference} {method}")
            joined = " ".join(observed)
            if method in {"blastp", "diamond_ultra"} and "db" not in joined:
                raise RuntimeError(f"Missing database receipt for {method} fold {evaluation_fold} {reference}")
            if method in {"blastp", "diamond_ultra", "mmseqs_s7.5"} and not any(
                token in joined for token in ("search", "hit")
            ):
                raise RuntimeError(f"Missing pairwise search receipt for {method} fold {evaluation_fold}")
            if method.startswith("hmmer_") and not (
                "profile" in joined and "library" in joined and ("scan" in joined or "hit" in joined)
            ):
                raise RuntimeError(f"Incomplete HMM receipt coverage for fold {evaluation_fold} {reference}")
            if method == PSI_METHOD and not (
                "db" in joined
                and ("enrich" in joined or "profile" in joined)
                and ("scan" in joined or "hit" in joined)
            ):
                raise RuntimeError(f"Incomplete PSI receipt coverage for fold {evaluation_fold} {reference}")
    expected_blast = (
        f"work/classical/fold_{evaluation_fold}/djr/pairwise/blastp.hits.tsv",
        f"work/classical/fold_{evaluation_fold}/vma/pairwise/blastp.hits.tsv",
    )
    blast_paths = {
        row["artifact_path"]
        for row in rows
        if row["method"] == "blastp" and row["stage"] == "search_hits"
    }
    if blast_paths != set(expected_blast):
        raise RuntimeError(f"BLAST raw path contract failed in fold {evaluation_fold}: {blast_paths}")

    expected_stages: set[tuple[str, str, str]] = set()
    for reference in ("djr", "vma"):
        expected_stages.update(
            {
                ("blastp", reference, "blast_db"),
                ("blastp", reference, "search_hits"),
                ("diamond_ultra", reference, "diamond_db"),
                ("diamond_ultra", reference, "search_hits"),
                ("mmseqs_s7.5", reference, "search_hits"),
                (PSI_METHOD, reference, "reference_db"),
                (PSI_METHOD, reference, "query_db"),
            }
        )
        for method in ("hmmer_component", "hmmer_family"):
            members = [
                row
                for row in profile_members
                if row["method"] == method and row["reference_kind"] == reference
            ]
            by_profile = Counter(row["profile_id"] for row in members)
            if not by_profile:
                raise RuntimeError(
                    f"No HMM profiles for raw coverage: fold {evaluation_fold} {reference} {method}"
                )
            expected_stages.add((method, reference, "library_hmmpress"))
            expected_stages.add((method, reference, "hmmscan_hits"))
            for profile, member_count in by_profile.items():
                expected_stages.add((method, reference, f"profile_hmmbuild:{profile}"))
                if member_count > 1:
                    expected_stages.add((method, reference, f"profile_alignment:{profile}"))
        seeds = [
            row
            for row in psiblast_seeds
            if row["reference_kind"] == reference and row["method"] == PSI_METHOD
        ]
        if not seeds:
            raise RuntimeError(
                f"No PSI seeds for raw coverage: fold {evaluation_fold} {reference}"
            )
        for seed in seeds:
            profile = seed["profile_id"]
            expected_stages.add((PSI_METHOD, reference, f"profile_enrichment:{profile}"))
            expected_stages.add((PSI_METHOD, reference, f"scan_hits:{profile}"))
    observed_stages = {
        (row["method"], row["reference_kind"], row["stage"]) for row in rows
    }
    if len(observed_stages) != len(rows) or observed_stages != expected_stages:
        raise RuntimeError(
            f"Raw receipt stage-set mismatch in fold {evaluation_fold}; "
            f"missing={sorted(expected_stages - observed_stages)[:5]} "
            f"extra={sorted(observed_stages - expected_stages)[:5]}"
        )


def validate_prepared_input_attestation(
    config: dict,
    project_root: Path,
    benchmark_root: Path,
    attestation: dict,
) -> None:
    expected_derived = {"cohort.tsv", "reference_attestation.tsv"}
    for fold in range(1, 6):
        expected_derived.update(
            {
                f"fold_{fold}/query_evaluation.tsv",
                f"fold_{fold}/query_evaluation.faa",
                f"fold_{fold}/query_calibration.tsv",
                f"fold_{fold}/query_calibration.faa",
                f"fold_{fold}/query_combined.tsv",
                f"fold_{fold}/query_combined.faa",
                f"fold_{fold}/reference_djr.tsv",
                f"fold_{fold}/reference_djr.faa",
                f"fold_{fold}/reference_vma.tsv",
                f"fold_{fold}/reference_vma.faa",
            }
        )
    declared = attestation.get("derived_output_sha256")
    if not isinstance(declared, dict) or set(declared) != expected_derived:
        raise RuntimeError("Prepared-input derived artifact map is incomplete or has extras")
    input_root = (benchmark_root / "inputs").resolve()
    for relative, expected in declared.items():
        path = (input_root / relative).resolve()
        if (
            not path.is_relative_to(input_root)
            or not path.is_file()
            or not is_sha256(expected)
            or sha256_file(path) != expected
        ):
            raise RuntimeError(f"Prepared-input artifact checksum mismatch: {relative}")

    declared_sources = attestation.get("input_sha256")
    expected_sources = {
        key: sha256_file(resolved_input(config, project_root, key))
        for key in config["inputs"]
    }
    if declared_sources != expected_sources:
        raise RuntimeError("Prepared-input source checksum map is stale or incomplete")
    for key, expected in config["expected_sha256"].items():
        if expected_sources.get(key) != expected:
            raise RuntimeError(f"Frozen source checksum mismatch: {key}")


def validate_query_and_reference_inputs(
    config: dict,
    benchmark_root: Path,
    evaluation_fold: int,
) -> tuple[
    list[dict[str, str]],
    Path,
    dict[str, tuple[list[dict[str, str]], Path, Path]],
    int,
    list[int],
]:
    fold_root = benchmark_root / f"inputs/fold_{evaluation_fold}"
    cohort = read_tsv(benchmark_root / "inputs/cohort.tsv")
    cohort_by_id = {row["protein_id"]: row for row in cohort}
    if not cohort or len(cohort_by_id) != len(cohort):
        raise RuntimeError("Prepared cohort is empty or has duplicate protein IDs")
    if any(row["is_vma"] == "1" and row["is_djr"] != "1" for row in cohort):
        raise RuntimeError("Prepared cohort violates VMA subset-of-DJR")
    query_manifest = fold_root / "query_combined.tsv"
    query_fasta = fold_root / "query_combined.faa"
    query_rows = read_tsv(query_manifest)
    query_sequences = read_fasta(query_fasta)
    query_ids = [row["protein_id"] for row in query_rows]
    if not query_rows or len(query_ids) != len(set(query_ids)) or set(query_ids) != set(query_sequences):
        raise RuntimeError(f"Combined query manifest/FASTA ID contract failed in fold {evaluation_fold}")
    roles = {row.get("benchmark_role", "") for row in query_rows}
    if roles != {"calibration", "evaluation"}:
        raise RuntimeError(f"Combined query roles malformed in fold {evaluation_fold}: {roles}")
    fold_count = int(config["parameters"]["folds"])
    calibration_fold, fit_folds = cyclic_fold_roles(
        evaluation_fold,
        fold_count,
        int(config["parameters"]["calibration_fold_offset"]),
    )
    if len(fit_folds) != int(config["parameters"]["fit_fold_count"]):
        raise RuntimeError(f"Fit-fold count mismatch in cycle {evaluation_fold}")
    expected_query_ids = {
        row["protein_id"]
        for row in cohort
        if int(row["fold"]) in {evaluation_fold, calibration_fold}
    }
    if set(query_ids) != expected_query_ids:
        raise RuntimeError(f"Combined query is not the exact cyclic cohort subset in fold {evaluation_fold}")
    for row in query_rows:
        cohort_row = cohort_by_id.get(row["protein_id"])
        if cohort_row is None or any(row.get(field) != value for field, value in cohort_row.items()):
            raise RuntimeError(f"Combined query metadata differs from cohort: {row['protein_id']}")
        sequence = query_sequences[row["protein_id"]]
        if (
            len(sequence) != int(row["length_aa"])
            or hashlib.sha256(sequence.encode("ascii")).hexdigest() != row["sequence_sha256"]
        ):
            raise RuntimeError(f"Combined query sequence checksum/length mismatch: {row['protein_id']}")
        expected_role = "evaluation" if int(row["fold"]) == evaluation_fold else "calibration"
        if row["benchmark_role"] != expected_role:
            raise RuntimeError(f"Query role/source fold mismatch in cycle {evaluation_fold}: {row}")
        if row["benchmark_role"] == "calibration" and int(row["fold"]) != calibration_fold:
            raise RuntimeError(f"Wrong calibration fold in cycle {evaluation_fold}: {row}")
    if not any(row["benchmark_role"] == "evaluation" for row in query_rows):
        raise RuntimeError(f"Empty evaluation role in cycle {evaluation_fold}")
    if not any(row["benchmark_role"] == "calibration" for row in query_rows):
        raise RuntimeError(f"Empty calibration role in cycle {evaluation_fold}")

    query_components = {row["global_component_id"] for row in query_rows}
    references: dict[str, tuple[list[dict[str, str]], Path, Path]] = {}
    for reference, label in (("djr", "is_djr"), ("vma", "is_vma")):
        manifest = fold_root / f"reference_{reference}.tsv"
        fasta = fold_root / f"reference_{reference}.faa"
        rows = read_tsv(manifest)
        sequences = read_fasta(fasta)
        ids = [row["protein_id"] for row in rows]
        if not rows or len(ids) != len(set(ids)) or set(ids) != set(sequences):
            raise RuntimeError(f"Reference manifest/FASTA ID contract failed: fold {evaluation_fold} {reference}")
        if any(row[label] != "1" for row in rows):
            raise RuntimeError(f"Negative row entered positive reference: fold {evaluation_fold} {reference}")
        expected_rows = [
            row
            for row in cohort
            if int(row["fold"]) in fit_folds and row[label] == "1"
        ]
        if rows != expected_rows:
            raise RuntimeError(f"Reference is not the exact fit-positive cohort: fold {evaluation_fold} {reference}")
        for row in rows:
            sequence = sequences[row["protein_id"]]
            if (
                len(sequence) != int(row["length_aa"])
                or hashlib.sha256(sequence.encode("ascii")).hexdigest()
                != row["sequence_sha256"]
            ):
                raise RuntimeError(
                    f"Reference sequence checksum/length mismatch: fold {evaluation_fold} {row['protein_id']}"
                )
        if {int(row["fold"]) for row in rows} - set(fit_folds):
            raise RuntimeError(f"Non-fit fold entered reference: fold {evaluation_fold} {reference}")
        if query_components & {row["global_component_id"] for row in rows}:
            raise RuntimeError(f"Query/reference component leakage: fold {evaluation_fold} {reference}")
        references[reference] = (rows, fasta, manifest)
    return query_rows, query_fasta, references, calibration_fold, fit_folds


def expected_fold_table_paths(benchmark_root: Path, evaluation_fold: int) -> dict[str, Path]:
    classical_root = benchmark_root / "work/classical"
    return {
        key: classical_root / filename.format(fold=evaluation_fold)
        for key, (filename, _fields) in TABLE_SPECS.items()
    }


def validate_score_matrix(
    rows: Sequence[dict[str, str]],
    query_rows: Sequence[dict[str, str]],
    evaluation_fold: int,
) -> None:
    query_by_id = {row["protein_id"]: row for row in query_rows}
    expected_counts = {
        "h1_djr": len(query_rows),
        "h2_vma_conditional": sum(row["is_djr"] == "1" for row in query_rows),
        "vma_end_to_end": len(query_rows),
    }
    expected_keys: set[tuple[str, str, str, str, str]] = set()
    for method in CLASSICAL_METHODS:
        for source in query_rows:
            common = (
                method,
                str(evaluation_fold),
                source["benchmark_role"],
                source["protein_id"],
            )
            expected_keys.add((common[0], "h1_djr", *common[1:]))
            expected_keys.add((common[0], "vma_end_to_end", *common[1:]))
            if source["is_djr"] == "1":
                expected_keys.add((common[0], "h2_vma_conditional", *common[1:]))
    counts: Counter[tuple[str, str]] = Counter()
    seen: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        key = (
            row["method"],
            row["task"],
            row["evaluation_fold"],
            row["role"],
            row["protein_id"],
        )
        if key in seen:
            raise RuntimeError(f"Duplicate score row: {key}")
        seen.add(key)
        if key not in expected_keys:
            raise RuntimeError(f"Unexpected score key outside the frozen matrix: {key}")
        if row["evaluation_fold"] != str(evaluation_fold) or row["protein_id"] not in query_by_id:
            raise RuntimeError(f"Score provenance mismatch in fold {evaluation_fold}: {row}")
        source = query_by_id[row["protein_id"]]
        if row["source_fold"] != source["fold"] or row["role"] != source["benchmark_role"]:
            raise RuntimeError(f"Score role/source-fold mismatch: {row}")
        if row["status"] not in {"ok", "no_hit"}:
            raise RuntimeError(f"Invalid score status: {row}")
        if row["status"] == "no_hit" and row["score"] != "-inf":
            raise RuntimeError(f"no_hit score is not -inf: {row}")
        if row["status"] == "ok" and not math.isfinite(float(row["score"])):
            raise RuntimeError(f"Non-finite successful score: {row}")
        counts[(row["method"], row["task"])] += 1
    for method in CLASSICAL_METHODS:
        for task, expected in expected_counts.items():
            if counts[(method, task)] != expected:
                raise RuntimeError(
                    f"Incomplete score matrix fold {evaluation_fold} {method} {task}: "
                    f"{counts[(method, task)]} != {expected}"
                )
    if seen != expected_keys:
        raise RuntimeError(
            f"Score key-set mismatch in fold {evaluation_fold}; "
            f"missing={sorted(expected_keys - seen)[:5]} extra={sorted(seen - expected_keys)[:5]}"
        )


def fold_input_paths(
    config_path: Path,
    benchmark_root: Path,
    evaluation_fold: int,
) -> list[Path]:
    fold_root = benchmark_root / f"inputs/fold_{evaluation_fold}"
    return [
        config_path.resolve(),
        benchmark_root / "inputs/input_attestation.json",
        fold_root / "query_combined.tsv",
        fold_root / "query_combined.faa",
        fold_root / "reference_djr.tsv",
        fold_root / "reference_djr.faa",
        fold_root / "reference_vma.tsv",
        fold_root / "reference_vma.faa",
    ]


def validate_fold_attestation(
    config: dict,
    config_path: Path,
    benchmark_root: Path,
    evaluation_fold: int,
) -> dict:
    attestation_path = benchmark_root / f"work/classical/fold_attestation.fold_{evaluation_fold}.json"
    attestation = read_json(attestation_path)
    if (
        attestation.get("status") != "PASS"
        or attestation.get("design_id") != config["design_id"]
        or attestation.get("evaluation_fold") != evaluation_fold
        or attestation.get("validation_prediction_rows") != 0
        or attestation.get("test_prediction_rows") != 0
    ):
        raise RuntimeError(f"Invalid classical fold attestation: {attestation_path}")
    if attestation.get("config_sha256") != sha256_file(config_path.resolve()):
        raise RuntimeError(f"Classical fold config changed: {attestation_path}")
    if attestation.get("run_classical_script_sha256") != sha256_file(Path(__file__).resolve()):
        raise RuntimeError(f"Classical runner script changed: {attestation_path}")
    common_script = Path(__file__).resolve().with_name("common.py")
    if attestation.get("common_script_sha256") != sha256_file(common_script):
        raise RuntimeError(f"Classical common script changed: {attestation_path}")
    input_attestation = benchmark_root / "inputs/input_attestation.json"
    if attestation.get("input_attestation_sha256") != sha256_file(input_attestation):
        raise RuntimeError(f"Input attestation changed: {attestation_path}")
    expected_inputs = input_details(
        fold_input_paths(config_path, benchmark_root, evaluation_fold), benchmark_root
    )
    if attestation.get("input_sha256") != expected_inputs:
        raise RuntimeError(f"Classical fold inputs changed: {attestation_path}")
    expected_tools = {name: tool_sha(config, name) for name in sorted(config["tools"])}
    if attestation.get("tool_sha256") != expected_tools:
        raise RuntimeError(f"Classical fold tools changed: {attestation_path}")

    table_paths = expected_fold_table_paths(benchmark_root, evaluation_fold)
    expected_output_map = {
        relative_path(path, benchmark_root): sha256_file(path) for path in table_paths.values()
    }
    if attestation.get("output_sha256") != dict(sorted(expected_output_map.items())):
        raise RuntimeError(f"Classical fold table output changed: {attestation_path}")
    raw_rows = read_tsv_strict(table_paths["raw_receipts"], RAW_RECEIPT_FIELDS)
    profile_member_rows = read_tsv_strict(
        table_paths["profile_members"], PROFILE_MEMBER_FIELDS
    )
    seed_rows = read_tsv_strict(table_paths["psiblast_seeds"], SEED_FIELDS)
    artifacts, receipts, external_outputs = validate_raw_receipt_rows(
        raw_rows, config, benchmark_root, evaluation_fold
    )
    validate_raw_coverage(
        raw_rows, evaluation_fold, profile_member_rows, seed_rows
    )
    if attestation.get("raw_artifact_sha256") != artifacts:
        raise RuntimeError(f"Classical raw artifact map changed: {attestation_path}")
    if attestation.get("raw_receipt_sha256") != receipts:
        raise RuntimeError(f"Classical raw receipt map changed: {attestation_path}")
    if attestation.get("external_output_sha256") != external_outputs:
        raise RuntimeError(f"Classical external output map changed: {attestation_path}")
    return attestation


def fold_is_complete(
    config: dict,
    config_path: Path,
    benchmark_root: Path,
    evaluation_fold: int,
) -> bool:
    try:
        validate_fold_attestation(config, config_path, benchmark_root, evaluation_fold)
    except (FileNotFoundError, KeyError, OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return True


def run_fold(
    config: dict,
    config_path: Path,
    benchmark_root: Path,
    evaluation_fold: int,
) -> None:
    if fold_is_complete(config, config_path, benchmark_root, evaluation_fold):
        print(f"REUSE receipt-validated classical cycle {evaluation_fold}")
        return
    query_rows, query_fasta, references, calibration_fold, fit_folds = (
        validate_query_and_reference_inputs(config, benchmark_root, evaluation_fold)
    )
    query_ids = {row["protein_id"] for row in query_rows}
    all_scores: list[dict[str, str]] = []
    contracts: list[dict[str, str]] = []
    membership: list[dict[str, str]] = []
    inclusion: list[dict[str, str]] = []
    seeds: list[dict[str, str]] = []
    artifacts: list[dict[str, str]] = []
    raw_receipts: list[dict[str, str]] = []
    runtimes: list[dict[str, str]] = []

    for reference in ("djr", "vma"):
        reference_rows, reference_fasta, reference_manifest = references[reference]
        reference_ids = {row["protein_id"] for row in reference_rows}
        pairwise, pair_contracts, pair_raw, pair_runtime = run_pairwise(
            config,
            benchmark_root,
            evaluation_fold,
            reference,
            query_fasta,
            reference_fasta,
            reference_manifest,
            query_ids,
            reference_ids,
        )
        contracts.extend(pair_contracts)
        raw_receipts.extend(pair_raw)
        runtimes.extend(pair_runtime)
        for method, scores in pairwise.items():
            append_task_scores(all_scores, method, evaluation_fold, reference, query_rows, scores)

        for mode in ("component", "family"):
            scores, members, registry, hmm_raw, hmm_runtime, contract = run_hmmer(
                config,
                benchmark_root,
                evaluation_fold,
                reference,
                query_fasta,
                reference_fasta,
                reference_manifest,
                reference_rows,
                query_ids,
                mode,
            )
            append_task_scores(
                all_scores, f"hmmer_{mode}", evaluation_fold, reference, query_rows, scores
            )
            membership.extend(members)
            artifacts.extend(registry)
            raw_receipts.extend(hmm_raw)
            runtimes.extend(hmm_runtime)
            contracts.append(contract)

        (
            psi_scores,
            psi_seeds,
            psi_inclusion,
            psi_artifacts,
            psi_raw,
            psi_runtime,
            psi_contract,
        ) = run_psiblast(
            config,
            benchmark_root,
            evaluation_fold,
            reference,
            query_fasta,
            reference_fasta,
            reference_manifest,
            reference_rows,
            query_ids,
        )
        append_task_scores(
            all_scores, PSI_METHOD, evaluation_fold, reference, query_rows, psi_scores
        )
        seeds.extend(psi_seeds)
        inclusion.extend(psi_inclusion)
        artifacts.extend(psi_artifacts)
        raw_receipts.extend(psi_raw)
        runtimes.extend(psi_runtime)
        contracts.append(psi_contract)

    expected_contract_keys = {
        (method, reference) for method in CLASSICAL_METHODS for reference in ("djr", "vma")
    }
    observed_contract_keys = {(row["method"], row["reference_kind"]) for row in contracts}
    if len(contracts) != len(expected_contract_keys) or observed_contract_keys != expected_contract_keys:
        raise RuntimeError(f"Incomplete/duplicate method-reference contract in fold {evaluation_fold}")
    if any(row["method"] == PSI_METHOD for row in membership):
        raise RuntimeError("PSI-BLAST rows entered HMM-only profile_members ledger")

    all_scores.sort(
        key=lambda row: (
            row["method"], row["task"], row["role"], row["protein_id"]
        )
    )
    contracts.sort(key=lambda row: (row["method"], row["reference_kind"]))
    membership.sort(
        key=lambda row: (
            row["method"], row["reference_kind"], row["profile_id"], row["member_id"]
        )
    )
    inclusion.sort(
        key=lambda row: (
            row["reference_kind"], row["profile_id"], int(row["iteration"]), row["subject_id"]
        )
    )
    seeds.sort(key=lambda row: (row["reference_kind"], row["profile_id"]))
    artifacts.sort(
        key=lambda row: (
            row["method"], row["reference_kind"], row["profile_id"], row["artifact_kind"]
        )
    )
    raw_receipts.sort(
        key=lambda row: (
            row["method"], row["reference_kind"], row["stage"], row["artifact_path"]
        )
    )
    runtimes.sort(
        key=lambda row: (
            row["method"], row["reference_kind"], row["stage"], row["receipt_path"]
        )
    )
    validate_score_matrix(all_scores, query_rows, evaluation_fold)
    validate_raw_coverage(raw_receipts, evaluation_fold, membership, seeds)
    raw_artifact_map, raw_receipt_map, external_output_map = validate_raw_receipt_rows(
        raw_receipts, config, benchmark_root, evaluation_fold
    )

    rows_by_table: dict[str, list[dict[str, str]]] = {
        "scores": all_scores,
        "reference_contract": contracts,
        "profile_members": membership,
        "profile_inclusion": inclusion,
        "psiblast_seeds": seeds,
        "profile_artifacts": artifacts,
        "raw_receipts": raw_receipts,
        "runtime": runtimes,
    }
    table_paths = expected_fold_table_paths(benchmark_root, evaluation_fold)
    for key, rows in rows_by_table.items():
        write_tsv(table_paths[key], rows, TABLE_SPECS[key][1])

    output_sha = {
        relative_path(path, benchmark_root): sha256_file(path) for path in table_paths.values()
    }
    input_attestation = benchmark_root / "inputs/input_attestation.json"
    attestation = {
        "status": "PASS",
        "design_id": config["design_id"],
        "evaluation_fold": evaluation_fold,
        "calibration_fold": calibration_fold,
        "fit_folds": fit_folds,
        "query_role_counts": dict(sorted(Counter(row["benchmark_role"] for row in query_rows).items())),
        "score_role_counts": dict(sorted(Counter(row["role"] for row in all_scores).items())),
        "score_rows": len(all_scores),
        "method_reference_contract_rows": len(contracts),
        "profile_member_rows": len(membership),
        "profile_inclusion_rows": len(inclusion),
        "psiblast_seed_rows": len(seeds),
        "profile_artifact_rows": len(artifacts),
        "raw_receipt_rows": len(raw_receipts),
        "runtime_rows": len(runtimes),
        "config_sha256": sha256_file(config_path.resolve()),
        "run_classical_script_sha256": sha256_file(Path(__file__).resolve()),
        "common_script_sha256": sha256_file(Path(__file__).resolve().with_name("common.py")),
        "input_attestation_sha256": sha256_file(input_attestation),
        "input_sha256": input_details(
            fold_input_paths(config_path, benchmark_root, evaluation_fold), benchmark_root
        ),
        "tool_sha256": {name: tool_sha(config, name) for name in sorted(config["tools"])},
        "output_sha256": dict(sorted(output_sha.items())),
        "raw_artifact_sha256": raw_artifact_map,
        "raw_receipt_sha256": raw_receipt_map,
        "external_output_sha256": external_output_map,
        "validation_prediction_rows": 0,
        "test_prediction_rows": 0,
    }
    attestation_path = benchmark_root / f"work/classical/fold_attestation.fold_{evaluation_fold}.json"
    atomic_json(attestation_path, attestation)
    validate_fold_attestation(config, config_path, benchmark_root, evaluation_fold)
    print(
        f"PASS classical cycle {evaluation_fold}: {len(all_scores)} scores, "
        f"{len(raw_receipts)} receipt-bound raw artifacts"
    )


def merge_classical(config: dict, config_path: Path, benchmark_root: Path) -> None:
    fold_count = int(config["parameters"]["folds"])
    if fold_count != 5:
        raise RuntimeError(f"Frozen benchmark requires five cycles, observed {fold_count}")
    merged: dict[str, list[dict[str, str]]] = {key: [] for key in TABLE_SPECS}
    fold_attestations: dict[str, str] = {}
    for evaluation_fold in range(1, fold_count + 1):
        validate_fold_attestation(config, config_path, benchmark_root, evaluation_fold)
        attestation_path = (
            benchmark_root / f"work/classical/fold_attestation.fold_{evaluation_fold}.json"
        )
        fold_attestations[relative_path(attestation_path, benchmark_root)] = sha256_file(
            attestation_path
        )
        paths = expected_fold_table_paths(benchmark_root, evaluation_fold)
        for key, (_filename, fields) in TABLE_SPECS.items():
            rows = read_tsv_strict(paths[key], fields)
            if any(row["evaluation_fold"] != str(evaluation_fold) for row in rows):
                raise RuntimeError(f"Merged table fold mismatch: {paths[key]}")
            merged[key].extend(rows)

    score_seen: set[tuple[str, str, str, str, str]] = set()
    for row in merged["scores"]:
        key = (
            row["method"],
            row["task"],
            row["evaluation_fold"],
            row["role"],
            row["protein_id"],
        )
        if key in score_seen:
            raise RuntimeError(f"Duplicate merged classical score: {key}")
        score_seen.add(key)
    contract_keys = [
        (row["method"], row["evaluation_fold"], row["reference_kind"])
        for row in merged["reference_contract"]
    ]
    expected_contract_keys = {
        (method, str(fold), reference)
        for method in CLASSICAL_METHODS
        for fold in range(1, 6)
        for reference in ("djr", "vma")
    }
    if len(contract_keys) != 60 or set(contract_keys) != expected_contract_keys:
        raise RuntimeError("Merged classical reference contract is not exactly 6 x 5 x 2")
    if any(row["method"] == PSI_METHOD for row in merged["profile_members"]):
        raise RuntimeError("Merged profile_members contains PSI-BLAST rows")

    merged["scores"].sort(
        key=lambda row: (
            row["method"], row["task"], int(row["evaluation_fold"]), row["role"], row["protein_id"]
        )
    )
    merged["reference_contract"].sort(
        key=lambda row: (row["method"], int(row["evaluation_fold"]), row["reference_kind"])
    )
    merged["profile_members"].sort(
        key=lambda row: (
            row["method"], int(row["evaluation_fold"]), row["reference_kind"],
            row["profile_id"], row["member_id"],
        )
    )
    merged["profile_inclusion"].sort(
        key=lambda row: (
            int(row["evaluation_fold"]), row["reference_kind"], row["profile_id"],
            int(row["iteration"]), row["subject_id"],
        )
    )
    merged["psiblast_seeds"].sort(
        key=lambda row: (int(row["evaluation_fold"]), row["reference_kind"], row["profile_id"])
    )
    merged["profile_artifacts"].sort(
        key=lambda row: (
            row["method"], int(row["evaluation_fold"]), row["reference_kind"],
            row["profile_id"], row["artifact_kind"],
        )
    )
    merged["raw_receipts"].sort(
        key=lambda row: (
            row["method"], int(row["evaluation_fold"]), row["reference_kind"],
            row["stage"], row["artifact_path"],
        )
    )
    merged["runtime"].sort(
        key=lambda row: (
            row["method"], int(row["evaluation_fold"]), row["reference_kind"],
            row["stage"], row["receipt_path"],
        )
    )

    merged_paths: dict[str, Path] = {}
    for key, relative in MERGED_TABLES.items():
        path = benchmark_root / relative
        write_tsv(path, merged[key], TABLE_SPECS[key][1])
        merged_paths[key] = path
    output_sha = {
        relative_path(path, benchmark_root): sha256_file(path)
        for path in merged_paths.values()
    }
    input_attestation = benchmark_root / "inputs/input_attestation.json"
    scores_path = merged_paths["scores"]
    raw_path = merged_paths["raw_receipts"]
    attestation = {
        "status": "PASS",
        "design_id": config["design_id"],
        "config_sha256": sha256_file(config_path.resolve()),
        "run_classical_script_sha256": sha256_file(Path(__file__).resolve()),
        "common_script_sha256": sha256_file(Path(__file__).resolve().with_name("common.py")),
        "input_attestation_sha256": sha256_file(input_attestation),
        "classical_scores_sha256": sha256_file(scores_path),
        "raw_receipt_ledger_sha256": sha256_file(raw_path),
        "fold_attestation_sha256": dict(sorted(fold_attestations.items())),
        "merged_output_sha256": dict(sorted(output_sha.items())),
        "executables": {
            name: {"path": tool(config, name), "sha256": tool_sha(config, name)}
            for name in sorted(config["tools"])
        },
        "score_rows": len(merged["scores"]),
        "score_role_counts": dict(
            sorted(Counter(row["role"] for row in merged["scores"]).items())
        ),
        "method_reference_contract_rows": len(merged["reference_contract"]),
        "profile_member_rows": len(merged["profile_members"]),
        "profile_inclusion_rows": len(merged["profile_inclusion"]),
        "psiblast_seed_rows": len(merged["psiblast_seeds"]),
        "profile_artifact_rows": len(merged["profile_artifacts"]),
        "raw_receipt_rows": len(merged["raw_receipts"]),
        "runtime_rows": len(merged["runtime"]),
        "validation_prediction_rows": 0,
        "test_prediction_rows": 0,
    }
    atomic_json(benchmark_root / "work/classical_attestation.json", attestation)
    print(
        f"PASS merged five classical cycles: {len(merged['scores'])} scores, "
        f"{len(merged['raw_receipts'])} raw receipts"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--fold", type=int, choices=range(1, 6))
    action.add_argument("--merge", action="store_true")
    args = parser.parse_args()
    config, project_root, benchmark_root = load_config(args.config)
    config_path = args.config.resolve()
    input_attestation_path = benchmark_root / "inputs/input_attestation.json"
    input_attestation = read_json(input_attestation_path)
    if (
        input_attestation.get("status") != "PASS"
        or input_attestation.get("design_id") != config["design_id"]
        or input_attestation.get("allowed_split") != "train"
        or input_attestation.get("validation_prediction_rows") != 0
        or input_attestation.get("test_prediction_rows") != 0
    ):
        raise RuntimeError("Prepared inputs do not have a matching PASS cyclic-design attestation")
    input_binding_paths = {
        "config_sha256": config_path,
        "prepare_inputs_script_sha256": Path(__file__).with_name("prepare_inputs.py"),
        "common_script_sha256": Path(__file__).with_name("common.py"),
    }
    for field, path in input_binding_paths.items():
        if not path.is_file() or input_attestation.get(field) != sha256_file(path):
            raise RuntimeError(f"Prepared inputs are not bound to current {path.name}")
    validate_prepared_input_attestation(
        config, project_root, benchmark_root, input_attestation
    )
    if int(config["parameters"]["folds"]) != 5:
        raise RuntimeError("The frozen cyclic benchmark requires exactly five folds")
    if int(config["parameters"]["calibration_fold_offset"]) != 1:
        raise RuntimeError("The frozen cyclic benchmark requires calibration-fold offset 1")
    if int(config["parameters"]["fit_fold_count"]) != 3:
        raise RuntimeError("The frozen cyclic benchmark requires three fit/reference folds")
    if int(config["parameters"]["psiblast_iterations"]) != 3:
        raise RuntimeError("The frozen PSI-BLAST method name requires exactly three iterations")
    if int(config["parameters"]["mmseqs_max_seqs"]) != 50000:
        raise RuntimeError("The frozen MMseqs2 prefilter retention limit must be 50000")
    expected_target_policies = {
        "pairwise_max_target_policy": "all_reference_records",
        "psiblast_enrichment_max_target_policy": "all_reference_records",
        "psiblast_scan_max_target_policy": "all_query_records",
    }
    for name, expected in expected_target_policies.items():
        if config["parameters"].get(name) != expected:
            raise RuntimeError(f"Frozen target-retention policy mismatch for {name}")
    search_evalue_text(config)
    for name in config["tools"]:
        tool_sha(config, name)
    if args.merge:
        merge_classical(config, config_path, benchmark_root)
    else:
        assert args.fold is not None
        run_fold(config, config_path, benchmark_root, args.fold)


if __name__ == "__main__":
    main()
