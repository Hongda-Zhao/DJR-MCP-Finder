#!/usr/bin/env python3
"""Portable Python orchestration for the project-V0 dataset build.

The scientific preparation and finalization logic remains in
``build_v0_dataset.py``.  This runner replaces the cluster-specific launcher:
it invokes an MMseqs2 executable available on ``PATH`` (or supplied explicitly)
without PBS or Environment Modules.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

MIN_SEQUENCE_ID = 0.30
MIN_COVERAGE = 0.80
SENSITIVITY = 7.5
MAX_SEQUENCES = 50_000
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
class DatasetRunConfig:
    """Resolved paths and executables for one dataset build."""

    project_root: Path
    config: Path
    work_dir: Path
    output_dir: Path
    threads: int
    python: str
    mmseqs: str


class CommandFailed(RuntimeError):
    """Raised when one orchestration command exits unsuccessfully."""

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


def _absolute_from_root(path: Path, project_root: Path) -> Path:
    return path if path.is_absolute() else project_root / path


def _require_success(
    runner: CommandRunner,
    command: Sequence[str],
    *,
    cwd: Path,
) -> None:
    result = runner(command, cwd=cwd)
    if result.returncode != 0:
        raise CommandFailed(command, result.returncode)


def require_mmseqs_version(
    config: DatasetRunConfig,
    *,
    runner: CommandRunner,
) -> str:
    """Fail closed unless MMseqs2 reports the configured frozen version."""

    command = (config.mmseqs, "version")
    result = runner(command, cwd=config.project_root, capture_output=True)
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


def run_dataset(
    config: DatasetRunConfig,
    *,
    runner: CommandRunner = run_command,
) -> int:
    """Run preparation, MMseqs2 graph construction, and finalization."""

    if config.threads < 1:
        raise ValueError("threads must be at least 1")
    if not (config.project_root / "pyproject.toml").is_file():
        raise ValueError(f"Invalid project root: {config.project_root}")
    if config.output_dir.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing V0 output: {config.output_dir}"
        )

    # Version-lock before preparation writes into WORK_DIR.  The dataset
    # metadata is only meaningful when the frozen MMseqs2 runtime is enforced.
    require_mmseqs_version(config, runner=runner)

    dataset_script = config.project_root / "scripts" / "build_v0_dataset.py"
    prepare_command = (
        config.python,
        str(dataset_script),
        "prepare",
        "--config",
        str(config.config),
        "--work-dir",
        str(config.work_dir),
    )
    _require_success(runner, prepare_command, cwd=config.project_root)

    mmseqs_dir = config.work_dir / "mmseqs"
    mmseqs_dir.mkdir(parents=True, exist_ok=True)
    component_fasta = config.work_dir / "component_input.faa"
    cluster_prefix = mmseqs_dir / "global"
    cluster_command = (
        config.mmseqs,
        "easy-cluster",
        str(component_fasta),
        str(cluster_prefix),
        str(mmseqs_dir / "tmp"),
        "--min-seq-id",
        f"{MIN_SEQUENCE_ID:.2f}",
        "-c",
        f"{MIN_COVERAGE:.2f}",
        "--cov-mode",
        "0",
        "--cluster-mode",
        "1",
        "--threads",
        str(config.threads),
    )
    _require_success(runner, cluster_command, cwd=config.project_root)

    search_tsv = mmseqs_dir / "full_search.tsv"
    search_command = (
        config.mmseqs,
        "easy-search",
        str(component_fasta),
        str(component_fasta),
        str(search_tsv),
        str(mmseqs_dir / "full_search_tmp"),
        "-s",
        str(SENSITIVITY),
        "--min-seq-id",
        f"{MIN_SEQUENCE_ID:.2f}",
        "-c",
        f"{MIN_COVERAGE:.2f}",
        "--cov-mode",
        "0",
        "--max-seqs",
        str(MAX_SEQUENCES),
        "--format-output",
        MMSEQS_FORMAT,
        "--threads",
        str(config.threads),
    )
    _require_success(runner, search_command, cwd=config.project_root)

    finalize_command = (
        config.python,
        str(dataset_script),
        "finalize",
        "--config",
        str(config.config),
        "--work-dir",
        str(config.work_dir),
        "--cluster-tsv",
        str(cluster_prefix) + "_cluster.tsv",
        "--search-tsv",
        str(search_tsv),
        "--output-dir",
        str(config.output_dir),
    )
    _require_success(runner, finalize_command, cwd=config.project_root)
    print(f"V0 dataset completed: {config.output_dir}")
    return 0


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
        "--config",
        type=Path,
        default=_environment_path("DJRMCP_DATASET_CONFIG", "CONFIG"),
        help="Dataset JSON configuration (env: DJRMCP_DATASET_CONFIG or CONFIG)",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=_environment_path("WORK_DIR"),
        help="Empty preparation directory (env: WORK_DIR)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_environment_path("OUTPUT_DIR"),
        help="New finalized dataset directory (env: OUTPUT_DIR)",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=int(os.environ.get("NCPUS", "8")),
        help="MMseqs2 worker threads (env: NCPUS; default: 8)",
    )
    parser.add_argument(
        "--python",
        default=os.environ.get("PYTHON", sys.executable),
        help="Python executable used for scientific stages (env: PYTHON)",
    )
    parser.add_argument(
        "--mmseqs",
        default=os.environ.get("DJRMCP_MMSEQS", "mmseqs"),
        help="MMseqs2 executable or command on PATH (env: DJRMCP_MMSEQS)",
    )
    return parser


def resolve_config(args: argparse.Namespace) -> DatasetRunConfig:
    fallback_root = Path(__file__).resolve().parents[1]
    project_root = (args.project_root or fallback_root).expanduser().resolve()
    config = _absolute_from_root(
        args.config or Path("configs/v0_dataset.json"), project_root
    ).expanduser()
    work_dir = _absolute_from_root(
        args.work_dir or Path("data/interim/v0"), project_root
    ).expanduser()
    output_dir = _absolute_from_root(
        args.output_dir or Path("data/processed/v0"), project_root
    ).expanduser()
    return DatasetRunConfig(
        project_root=project_root,
        config=config,
        work_dir=work_dir,
        output_dir=output_dir,
        threads=args.threads,
        python=args.python,
        mmseqs=args.mmseqs,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_dataset(resolve_config(args))
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
