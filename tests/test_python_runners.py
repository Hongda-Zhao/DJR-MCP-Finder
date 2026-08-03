from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


DATASET = _load("run_v0_dataset", "scripts/run_v0_dataset.py")
AUDIT = _load("run_postsplit_integrity_audit", "scripts/run_postsplit_integrity_audit.py")


def _audit_config(root: Path, *, staging_dir: Path | None = None) -> object:
    audit_dir = root / "audit"
    return AUDIT.AuditRunConfig(
        project_root=root,
        master_manifest=root / "master.tsv",
        quarantine_manifest=root / "quarantine.tsv",
        membership=root / "membership.tsv",
        component_fasta=root / "component.faa",
        model_fasta=root / "model.faa",
        member_fastas=(),
        audit_dir=audit_dir,
        staging_dir=staging_dir or root / "audit.building",
        job_tmp=root / "scratch",
        threads=4,
        python="python-test",
        mmseqs="mmseqs-test",
        run_id="unit-test",
    )


def _prepared_inputs(staging_dir: Path) -> None:
    inputs = staging_dir / "inputs"
    inputs.mkdir()
    for split in ("train", "validation", "test"):
        (inputs / f"{split}_all_nodes.faa").write_text(">p\nAA\n", encoding="utf-8")


def test_dataset_runner_preserves_cluster_and_sensitive_search_contract(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    work = root / "work"
    output = root / "output"
    commands: list[tuple[str, ...]] = []

    def fake_runner(command, *, cwd, capture_output=False):
        assert cwd == root
        command = tuple(command)
        commands.append(command)
        if command[-1] == "version":
            assert capture_output
            return DATASET.CommandResult(0, "18-8cc5c\n")
        assert not capture_output
        if "prepare" in command:
            work.mkdir()
            (work / "component_input.faa").write_text(">p\nAA\n", encoding="utf-8")
        if "finalize" in command:
            output.mkdir()
        return DATASET.CommandResult(0)

    config = DATASET.DatasetRunConfig(
        project_root=root,
        config=root / "config.json",
        work_dir=work,
        output_dir=output,
        threads=6,
        python="python-test",
        mmseqs="mmseqs-test",
    )
    assert DATASET.run_dataset(config, runner=fake_runner) == 0
    cluster = next(command for command in commands if "easy-cluster" in command)
    search = next(command for command in commands if "easy-search" in command)
    assert ("--min-seq-id", "0.30") == cluster[cluster.index("--min-seq-id") :][:2]
    assert ("--cluster-mode", "1") == cluster[cluster.index("--cluster-mode") :][:2]
    assert ("-s", "7.5") == search[search.index("-s") :][:2]
    assert ("--max-seqs", "50000") == search[search.index("--max-seqs") :][:2]
    assert search.count(str(work / "component_input.faa")) == 2


def test_dataset_runner_refuses_overwrite_before_commands(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    output = root / "output"
    output.mkdir()
    called = False

    def fake_runner(command, *, cwd, capture_output=False):
        nonlocal called
        called = True
        return DATASET.CommandResult(0)

    config = DATASET.DatasetRunConfig(
        project_root=root,
        config=root / "config.json",
        work_dir=root / "work",
        output_dir=output,
        threads=1,
        python="python-test",
        mmseqs="mmseqs-test",
    )
    try:
        DATASET.run_dataset(config, runner=fake_runner)
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing output was not rejected")
    assert not called


def test_dataset_runner_rejects_mmseqs_mismatch_before_work(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    work = root / "work"
    commands: list[tuple[str, ...]] = []

    def fake_runner(command, *, cwd, capture_output=False):
        commands.append(tuple(command))
        assert capture_output
        return DATASET.CommandResult(0, "17-old\n")

    config = DATASET.DatasetRunConfig(
        project_root=root,
        config=root / "config.json",
        work_dir=work,
        output_dir=root / "output",
        threads=1,
        python="python-test",
        mmseqs="mmseqs-test",
    )
    with pytest.raises(ValueError, match="MMseqs2 version mismatch"):
        DATASET.run_dataset(config, runner=fake_runner)
    assert commands == [("mmseqs-test", "version")]
    assert not work.exists()
    assert not config.output_dir.exists()


def test_audit_runner_searches_three_directions_and_publishes_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    audit_dir = root / "audit"
    staging_dir = root / "audit.building"
    commands: list[tuple[str, ...]] = []

    def fake_runner(command, *, cwd, capture_output=False):
        command = tuple(command)
        commands.append(command)
        if command[-1] == "version":
            return AUDIT.CommandResult(0, "18-8cc5c\n")
        if "prepare" in command:
            inputs = staging_dir / "inputs"
            inputs.mkdir()
            for split in ("train", "validation", "test"):
                (inputs / f"{split}_all_nodes.faa").write_text(">p\nAA\n", encoding="utf-8")
        elif "easy-search" in command:
            Path(command[4]).write_text("", encoding="utf-8")
        elif "finalize" in command:
            report = staging_dir / "report"
            report.mkdir()
            (report / "SUMMARY.json").write_text('{"status":"pass"}\n', encoding="utf-8")
        return AUDIT.CommandResult(0)

    scratch_path = tmp_path / "unique-scratch"

    def fake_mkdtemp(*, prefix):
        assert prefix.startswith("djrmcp_split_audit_unit-test_")
        scratch_path.mkdir()
        return str(scratch_path)

    monkeypatch.setattr(AUDIT.tempfile, "mkdtemp", fake_mkdtemp)
    config = AUDIT.AuditRunConfig(
        project_root=root,
        master_manifest=root / "master.tsv",
        quarantine_manifest=root / "quarantine.tsv",
        membership=root / "membership.tsv",
        component_fasta=root / "component.faa",
        model_fasta=root / "model.faa",
        member_fastas=(),
        audit_dir=audit_dir,
        staging_dir=staging_dir,
        job_tmp=None,
        threads=4,
        python="python-test",
        mmseqs="mmseqs-test",
        run_id="unit-test",
    )
    assert AUDIT.run_audit(config, runner=fake_runner) == 0
    searches = [command for command in commands if "easy-search" in command]
    assert len(searches) == 3
    assert [(Path(c[2]).stem, Path(c[3]).stem) for c in searches] == [
        ("validation_all_nodes", "train_all_nodes"),
        ("test_all_nodes", "train_all_nodes"),
        ("test_all_nodes", "validation_all_nodes"),
    ]
    assert audit_dir.is_dir()
    assert not staging_dir.exists()
    assert (audit_dir / "RUN.PASS").is_file()
    assert not scratch_path.exists()
    assert f"scratch_path={scratch_path}" in (audit_dir / "RUN_METADATA.txt").read_text(
        encoding="utf-8"
    )
    checksums = (audit_dir / "CHECKSUMS.sha256").read_text(encoding="utf-8")
    assert "./RUN_METADATA.txt" in checksums
    assert "./report/SUMMARY.json" in checksums
    for line in checksums.splitlines():
        expected, relative = line.split("  ", 1)
        target = audit_dir / relative.removeprefix("./")
        assert hashlib.sha256(target.read_bytes()).hexdigest() == expected


def test_audit_runner_rejects_mmseqs_mismatch_before_work(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    config = _audit_config(root)
    commands: list[tuple[str, ...]] = []

    def fake_runner(command, *, cwd, capture_output=False):
        commands.append(tuple(command))
        assert capture_output
        return AUDIT.CommandResult(0, "19-new\n")

    with pytest.raises(ValueError, match="MMseqs2 version mismatch"):
        AUDIT.run_audit(config, runner=fake_runner)
    assert commands == [("mmseqs-test", "version")]
    assert not config.staging_dir.exists()
    assert config.job_tmp is not None and not config.job_tmp.exists()


@pytest.mark.parametrize(
    "staging_factory",
    [
        lambda root: root / "audit",
        lambda root: root / "audit" / "nested.building",
        lambda root: root / "elsewhere" / "audit.building",
    ],
    ids=("same", "nested", "different-parent"),
)
def test_audit_runner_rejects_nonadjacent_staging_paths(
    tmp_path: Path, staging_factory
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    config = _audit_config(root, staging_dir=staging_factory(root))
    called = False

    def fake_runner(command, *, cwd, capture_output=False):
        nonlocal called
        called = True
        return AUDIT.CommandResult(0, "18-8cc5c\n")

    with pytest.raises(ValueError, match="staging_dir must be the adjacent"):
        AUDIT.run_audit(config, runner=fake_runner)
    assert not called
    assert not config.staging_dir.exists()


def test_audit_prepare_integrity_failure_is_published_and_scratch_removed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    config = _audit_config(root)
    commands: list[tuple[str, ...]] = []

    def fake_runner(command, *, cwd, capture_output=False):
        command = tuple(command)
        commands.append(command)
        if command[-1] == "version":
            return AUDIT.CommandResult(0, "18-8cc5c\n")
        if "prepare" in command:
            _prepared_inputs(config.staging_dir)
            return AUDIT.CommandResult(2)
        raise AssertionError(f"unexpected command: {command}")

    assert AUDIT.run_audit(config, runner=fake_runner) == 2
    assert config.audit_dir.is_dir()
    assert not config.staging_dir.exists()
    assert config.job_tmp is not None and not config.job_tmp.exists()
    assert (config.audit_dir / "RUN.FAIL").is_file()
    metadata = (config.audit_dir / "RUN_METADATA.txt").read_text(encoding="utf-8")
    assert "audit_status=fail_preflight" in metadata
    assert not any("easy-search" in command for command in commands)


def test_audit_finalize_integrity_failure_is_published_and_scratch_removed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    config = _audit_config(root)

    def fake_runner(command, *, cwd, capture_output=False):
        command = tuple(command)
        if command[-1] == "version":
            return AUDIT.CommandResult(0, "18-8cc5c\n")
        if "prepare" in command:
            _prepared_inputs(config.staging_dir)
        elif "easy-search" in command:
            Path(command[4]).write_text("", encoding="utf-8")
        elif "finalize" in command:
            report = config.staging_dir / "report"
            report.mkdir()
            (report / "SUMMARY.json").write_text(
                '{"status":"fail"}\n', encoding="utf-8"
            )
            return AUDIT.CommandResult(2)
        return AUDIT.CommandResult(0)

    assert AUDIT.run_audit(config, runner=fake_runner) == 2
    assert config.audit_dir.is_dir()
    assert not config.staging_dir.exists()
    assert config.job_tmp is not None and not config.job_tmp.exists()
    assert (config.audit_dir / "RUN.FAIL").is_file()
    metadata = (config.audit_dir / "RUN_METADATA.txt").read_text(encoding="utf-8")
    assert "audit_status=fail_integrity" in metadata


def test_audit_command_crash_preserves_staging_and_scratch_without_publish(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    config = _audit_config(root)

    def fake_runner(command, *, cwd, capture_output=False):
        command = tuple(command)
        if command[-1] == "version":
            return AUDIT.CommandResult(0, "18-8cc5c\n")
        if "prepare" in command:
            _prepared_inputs(config.staging_dir)
            return AUDIT.CommandResult(0)
        if "easy-search" in command:
            return AUDIT.CommandResult(9)
        raise AssertionError(f"unexpected command: {command}")

    with pytest.raises(AUDIT.CommandFailed) as error:
        AUDIT.run_audit(config, runner=fake_runner)
    assert error.value.returncode == 9
    assert not config.audit_dir.exists()
    assert config.staging_dir.is_dir()
    assert config.job_tmp is not None and config.job_tmp.is_dir()
    assert not (config.staging_dir / "CHECKSUMS.sha256").exists()
