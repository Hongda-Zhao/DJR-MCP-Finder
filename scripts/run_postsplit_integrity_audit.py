#!/usr/bin/env python3
"""Portable Python orchestration for the project-V0 post-split audit.

This runner preserves the frozen three-direction MMseqs2 contract and the
fail-closed publication behavior of the former PBS launcher.  It requires only
Python plus an ``mmseqs`` executable on ``PATH``; no scheduler or Environment
Modules installation is assumed.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

DIRECTIONS: tuple[tuple[str, str], ...] = (
    ("validation", "train"),
    ("test", "train"),
    ("test", "validation"),
)
MMSEQS_FORMAT = "query,target,pident,qcov,tcov,alnlen,evalue,bits"
FROZEN_MMSEQS_VERSION = "18-8cc5c"


@dataclass(frozen=True)
class CommandResult:
    """Minimal subprocess result used by the orchestration layer."""

    returncode: int
    output: str = ""


class CommandRunner(Protocol):
    """Injectable command boundary used by unit tests."""

    def __call__(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        capture_output: bool = False,
    ) -> CommandResult: ...


@dataclass(frozen=True)
class AuditRunConfig:
    """Resolved inputs and runtime settings for one integrity audit."""

    project_root: Path
    master_manifest: Path
    quarantine_manifest: Path
    membership: Path
    component_fasta: Path
    model_fasta: Path
    member_fastas: tuple[Path, ...]
    audit_dir: Path
    staging_dir: Path
    job_tmp: Path | None
    threads: int
    python: str
    mmseqs: str
    run_id: str
    min_sequence_id: float = 0.30
    min_query_coverage: float = 0.80
    min_target_coverage: float = 0.80
    sensitivity: float = 7.5
    max_sequences: int = 50_000


class CommandFailed(RuntimeError):
    """Raised when one orchestration command exits unexpectedly."""

    def __init__(self, command: Sequence[str], returncode: int) -> None:
        self.command = tuple(command)
        self.returncode = returncode
        super().__init__(
            f"Command exited with status {returncode}: {' '.join(self.command)}"
        )


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    capture_output: bool = False,
) -> CommandResult:
    """Run one child process without invoking a shell."""

    completed = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.STDOUT if capture_output else None,
    )
    return CommandResult(completed.returncode, completed.stdout or "")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_root_checksums(staging_dir: Path) -> None:
    """Write deterministic recursive checksums for the publishable audit tree."""

    targets = sorted(
        (
            path
            for path in staging_dir.rglob("*")
            if path.is_file() and path.name != "CHECKSUMS.sha256"
        ),
        key=lambda path: path.relative_to(staging_dir).as_posix(),
    )
    lines = [
        f"{file_sha256(path)}  ./{path.relative_to(staging_dir).as_posix()}"
        for path in targets
    ]
    (staging_dir / "CHECKSUMS.sha256").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _append_metadata(staging_dir: Path, *lines: str) -> None:
    with (staging_dir / "RUN_METADATA.txt").open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line + "\n")


def _publish(config: AuditRunConfig) -> None:
    """Publish the complete staging tree with one same-filesystem rename."""

    os.replace(config.staging_dir, config.audit_dir)


def _publish_preflight_failure(config: AuditRunConfig, status: int) -> int:
    _append_metadata(
        config.staging_dir,
        f"audit_exit_code={status}",
        "audit_status=fail_preflight",
    )
    (config.staging_dir / "RUN.FAIL").touch()
    write_root_checksums(config.staging_dir)
    _publish(config)
    return status


def require_mmseqs_version(
    config: AuditRunConfig,
    *,
    runner: CommandRunner,
) -> str:
    """Fail closed unless MMseqs2 reports the configured frozen version."""

    command = (config.mmseqs, "version")
    result = runner(
        command,
        cwd=config.project_root,
        capture_output=True,
    )
    if result.returncode != 0:
        raise CommandFailed(command, result.returncode)
    version_lines = result.output.splitlines()
    observed = version_lines[0].strip() if version_lines else ""
    if observed != FROZEN_MMSEQS_VERSION:
        raise ValueError(
            "MMseqs2 version mismatch: "
            f"expected {FROZEN_MMSEQS_VERSION!r}, observed {observed or '<empty>'!r}"
        )
    return observed


def _create_job_tmp(config: AuditRunConfig) -> Path:
    if config.job_tmp is not None:
        config.job_tmp.mkdir(parents=True)
        return config.job_tmp
    run_token = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in config.run_id
    )
    return Path(
        tempfile.mkdtemp(prefix=f"djrmcp_split_audit_{run_token or 'run'}_")
    )


def _run(
    runner: CommandRunner,
    command: Sequence[str],
    *,
    cwd: Path,
    capture_output: bool = False,
) -> CommandResult:
    result = runner(command, cwd=cwd, capture_output=capture_output)
    if result.returncode != 0:
        raise CommandFailed(command, result.returncode)
    return result


def _validate_config(config: AuditRunConfig) -> None:
    if not (config.project_root / "pyproject.toml").is_file():
        raise ValueError(f"Invalid project root: {config.project_root}")
    if config.threads < 1:
        raise ValueError("threads must be at least 1")
    if config.max_sequences < 1:
        raise ValueError("max_sequences must be at least 1")
    for name, value in (
        ("min_sequence_id", config.min_sequence_id),
        ("min_query_coverage", config.min_query_coverage),
        ("min_target_coverage", config.min_target_coverage),
    ):
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be a fraction in [0, 1]")
    audit_dir = config.audit_dir.resolve(strict=False)
    staging_dir = config.staging_dir.resolve(strict=False)
    expected_staging = audit_dir.with_name(audit_dir.name + ".building")
    if staging_dir != expected_staging:
        raise ValueError(
            "staging_dir must be the adjacent audit publish path "
            f"{expected_staging}; observed {staging_dir}"
        )
    if config.job_tmp is not None and config.job_tmp.exists():
        raise FileExistsError(f"Refusing to reuse audit scratch path: {config.job_tmp}")
    if audit_dir.exists() or staging_dir.exists():
        raise FileExistsError(
            f"Refusing to overwrite post-split audit output: {audit_dir}"
        )


def run_audit(
    config: AuditRunConfig,
    *,
    runner: CommandRunner = run_command,
) -> int:
    """Run preparation, three directional searches, and atomic publication."""

    _validate_config(config)
    # Verify the frozen runtime before creating staging or scratch directories.
    mmseqs_version = require_mmseqs_version(config, runner=runner)
    (config.staging_dir / "raw").mkdir(parents=True)
    job_tmp = _create_job_tmp(config)
    metadata = (
        "audit=postsplit_integrity_v0",
        "orchestrator=scripts/run_postsplit_integrity_audit.py",
        f"python_executable={config.python}",
        f"mmseqs_executable={config.mmseqs}",
        f"mmseqs_version={mmseqs_version}",
        f"expected_mmseqs_version={FROZEN_MMSEQS_VERSION}",
        f"scratch_path={job_tmp}",
        "directions=validation->train,test->train,test->validation",
        f"min_seq_id={config.min_sequence_id:.2f}",
        f"min_query_coverage={config.min_query_coverage:.2f}",
        f"min_target_coverage={config.min_target_coverage:.2f}",
        "cov_mode=0",
        f"sensitivity={config.sensitivity}",
        f"max_seqs={config.max_sequences}",
        f"threads={config.threads}",
        f"job_id={config.run_id}",
        f"hostname={socket.gethostname()}",
    )
    (config.staging_dir / "RUN_METADATA.txt").write_text(
        "\n".join(metadata) + "\n", encoding="utf-8"
    )

    audit_script = config.project_root / "scripts" / "postsplit_integrity_audit.py"
    preparation_dir = config.staging_dir / "inputs"
    prepare_command: list[str] = [
        config.python,
        str(audit_script),
        "prepare",
        "--master-manifest",
        str(config.master_manifest),
        "--quarantine-manifest",
        str(config.quarantine_manifest),
        "--membership",
        str(config.membership),
        "--component-fasta",
        str(config.component_fasta),
        "--model-fasta",
        str(config.model_fasta),
    ]
    for member_fasta in config.member_fastas:
        prepare_command.extend(("--member-fasta", str(member_fasta)))
    prepare_command.extend(("--output-dir", str(preparation_dir)))
    prepare_result = runner(prepare_command, cwd=config.project_root)
    if prepare_result.returncode != 0:
        if prepare_result.returncode == 2 and preparation_dir.is_dir():
            status = _publish_preflight_failure(config, prepare_result.returncode)
            shutil.rmtree(job_tmp)
            return status
        raise CommandFailed(prepare_command, prepare_result.returncode)

    raw_paths: dict[str, Path] = {}
    for query_split, target_split in DIRECTIONS:
        name = f"{query_split}_vs_{target_split}"
        raw_path = config.staging_dir / "raw" / f"{name}.raw.tsv"
        raw_paths[name] = raw_path
        search_command = (
            config.mmseqs,
            "easy-search",
            str(preparation_dir / f"{query_split}_all_nodes.faa"),
            str(preparation_dir / f"{target_split}_all_nodes.faa"),
            str(raw_path),
            str(job_tmp / name),
            "-s",
            str(config.sensitivity),
            "--min-seq-id",
            f"{config.min_sequence_id:.2f}",
            "-c",
            f"{min(config.min_query_coverage, config.min_target_coverage):.2f}",
            "--cov-mode",
            "0",
            "--max-seqs",
            str(config.max_sequences),
            "--format-output",
            MMSEQS_FORMAT,
            "--threads",
            str(config.threads),
        )
        _run(runner, search_command, cwd=config.project_root)

    report_dir = config.staging_dir / "report"
    finalize_command = (
        config.python,
        str(audit_script),
        "finalize",
        "--preparation-dir",
        str(preparation_dir),
        "--membership",
        str(config.membership),
        "--validation-vs-train",
        str(raw_paths["validation_vs_train"]),
        "--test-vs-train",
        str(raw_paths["test_vs_train"]),
        "--test-vs-validation",
        str(raw_paths["test_vs_validation"]),
        "--output-dir",
        str(report_dir),
        "--min-seq-id",
        f"{config.min_sequence_id:.2f}",
        "--min-qcov",
        f"{config.min_query_coverage:.2f}",
        "--min-tcov",
        f"{config.min_target_coverage:.2f}",
    )
    finalize_result = runner(finalize_command, cwd=config.project_root)
    audit_status = finalize_result.returncode
    if audit_status not in {0, 2}:
        raise CommandFailed(finalize_command, audit_status)

    status_label = "pass" if audit_status == 0 else "fail_integrity"
    _append_metadata(
        config.staging_dir,
        f"audit_exit_code={audit_status}",
        f"audit_status={status_label}",
    )
    (config.staging_dir / ("RUN.PASS" if audit_status == 0 else "RUN.FAIL")).touch()
    write_root_checksums(config.staging_dir)
    _publish(config)
    shutil.rmtree(job_tmp)
    print(f"Post-split integrity audit published at: {config.audit_dir}")
    return audit_status


def _environment_path(*names: str) -> Path | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return Path(value)
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=_environment_path("DJRMCP_PROJECT_ROOT", "PROJECT_ROOT"),
        help="Repository root (env: DJRMCP_PROJECT_ROOT or PROJECT_ROOT)",
    )
    parser.add_argument(
        "--master-manifest",
        type=Path,
        default=_environment_path("MASTER_MANIFEST"),
    )
    parser.add_argument(
        "--quarantine-manifest",
        type=Path,
        default=_environment_path("QUARANTINE_MANIFEST"),
    )
    parser.add_argument(
        "--membership",
        type=Path,
        default=_environment_path("MEMBERSHIP"),
    )
    parser.add_argument(
        "--component-fasta",
        type=Path,
        default=_environment_path("COMPONENT_FASTA"),
    )
    parser.add_argument(
        "--model-fasta",
        type=Path,
        default=_environment_path("MODEL_FASTA"),
    )
    parser.add_argument(
        "--member-fasta",
        action="append",
        type=Path,
        default=[],
        help="Optional component-member FASTA to reconcile (repeatable)",
    )
    parser.add_argument(
        "--audit-dir",
        type=Path,
        default=_environment_path("AUDIT_DIR"),
    )
    parser.add_argument(
        "--staging-dir",
        type=Path,
        default=_environment_path("STAGING_DIR"),
    )
    parser.add_argument(
        "--job-tmp",
        type=Path,
        default=_environment_path("JOB_TMP"),
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=int(os.environ.get("NCPUS", "8")),
    )
    parser.add_argument(
        "--python",
        default=os.environ.get("PYTHON", sys.executable),
    )
    parser.add_argument(
        "--mmseqs",
        default=os.environ.get("DJRMCP_MMSEQS", "mmseqs"),
    )
    parser.add_argument(
        "--run-id",
        default=os.environ.get("DJRMCP_RUN_ID", "manual"),
    )
    parser.add_argument("--min-seq-id", type=float, default=0.30)
    parser.add_argument("--min-qcov", type=float, default=0.80)
    parser.add_argument("--min-tcov", type=float, default=0.80)
    parser.add_argument("--sensitivity", type=float, default=7.5)
    parser.add_argument("--max-seqs", type=int, default=50_000)
    return parser


def _absolute_from_root(path: Path, project_root: Path) -> Path:
    return path if path.is_absolute() else project_root / path


def resolve_config(args: argparse.Namespace) -> AuditRunConfig:
    fallback_root = Path(__file__).resolve().parents[1]
    project_root = (args.project_root or fallback_root).expanduser().resolve()

    def rooted(value: Path | None, fallback: str) -> Path:
        return _absolute_from_root(value or Path(fallback), project_root).expanduser()

    audit_dir = rooted(args.audit_dir, "results/postsplit_integrity_v0")
    staging_dir = (
        _absolute_from_root(args.staging_dir, project_root).expanduser()
        if args.staging_dir is not None
        else audit_dir.with_name(audit_dir.name + ".building")
    )
    job_tmp = args.job_tmp.expanduser() if args.job_tmp is not None else None
    if job_tmp is not None and not job_tmp.is_absolute():
        job_tmp = project_root / job_tmp
    return AuditRunConfig(
        project_root=project_root,
        master_manifest=rooted(
            args.master_manifest, "data/processed/v0/master_manifest.tsv"
        ),
        quarantine_manifest=rooted(
            args.quarantine_manifest, "data/processed/v0/quarantine_manifest.tsv"
        ),
        membership=rooted(
            args.membership, "data/processed/v0/global_component_membership.tsv"
        ),
        component_fasta=rooted(
            args.component_fasta, "data/interim/v0/component_input.faa"
        ),
        model_fasta=rooted(
            args.model_fasta, "data/interim/v0/model_representatives.faa"
        ),
        member_fastas=tuple(
            _absolute_from_root(path, project_root).expanduser()
            for path in args.member_fasta
        ),
        audit_dir=audit_dir,
        staging_dir=staging_dir,
        job_tmp=job_tmp,
        threads=args.threads,
        python=args.python,
        mmseqs=args.mmseqs,
        run_id=args.run_id,
        min_sequence_id=args.min_seq_id,
        min_query_coverage=args.min_qcov,
        min_target_coverage=args.min_tcov,
        sensitivity=args.sensitivity,
        max_sequences=args.max_seqs,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_audit(resolve_config(args))
    except CommandFailed as error:
        print(error, file=sys.stderr)
        return error.returncode
    except FileNotFoundError as error:
        print(f"Required executable or input was not found: {error}", file=sys.stderr)
        return 127
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
