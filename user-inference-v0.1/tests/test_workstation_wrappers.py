from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_WRAPPER = ROOT / "workstation" / "build.sh"
RUN_WRAPPER = ROOT / "workstation" / "run_user_fasta.sh"


def _environment(cache_source: Path) -> dict[str, str]:
    false_command = shutil.which("false")
    assert false_command is not None
    environment = os.environ.copy()
    environment["DJRMCP_DOCKER"] = false_command
    environment["DJRMCP_CACHE_SOURCE"] = str(cache_source)
    environment["DJRMCP_UID"] = "1000"
    environment["DJRMCP_GID"] = "1000"
    return environment


def test_build_refuses_cache_symlink_resolving_to_host_root(tmp_path: Path) -> None:
    root_link = tmp_path / "root-link"
    root_link.symlink_to("/")
    completed = subprocess.run(
        ["bash", str(BUILD_WRAPPER)],
        env=_environment(root_link),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "refusing to use / as the cache source" in completed.stderr


def test_run_refuses_cache_symlink_resolving_to_host_root(tmp_path: Path) -> None:
    root_link = tmp_path / "root-link"
    root_link.symlink_to("/")
    fasta = tmp_path / "input.faa"
    fasta.write_text(">protein\n" + "ACDEFGHIKLMNPQRSTVWY" * 7 + "\n", encoding="utf-8")
    completed = subprocess.run(
        ["bash", str(RUN_WRAPPER), str(fasta), str(tmp_path / "output" / "run")],
        env=_environment(root_link),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "refusing to use / as the cache source" in completed.stderr


def test_run_canonicalizes_output_parent_before_creating_output(tmp_path: Path) -> None:
    fasta = tmp_path / "input.faa"
    fasta.write_text(">protein\n" + "ACDEFGHIKLMNPQRSTVWY" * 7 + "\n", encoding="utf-8")
    unsafe_name = f"djrmcp-{tmp_path.name}"
    unsafe_path = Path("/") / unsafe_name
    assert not unsafe_path.exists()
    completed = subprocess.run(
        ["bash", str(RUN_WRAPPER), str(fasta), f"/tmp/../{unsafe_name}"],
        env=_environment(Path("djrmcp-test-cache")),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "refusing to mount / as the output parent" in completed.stderr
    assert not unsafe_path.exists()


def test_run_refuses_parent_basename_and_output_symlink(tmp_path: Path) -> None:
    fasta = tmp_path / "input.faa"
    fasta.write_text(">protein\n" + "ACDEFGHIKLMNPQRSTVWY" * 7 + "\n", encoding="utf-8")
    environment = _environment(Path("djrmcp-test-cache"))

    parent = subprocess.run(
        ["bash", str(RUN_WRAPPER), str(fasta), ".."],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert parent.returncode == 2
    assert "refusing unsafe output directory" in parent.stderr

    target = tmp_path / "target"
    target.mkdir()
    output_link = tmp_path / "output-link"
    output_link.symlink_to(target, target_is_directory=True)
    symbolic = subprocess.run(
        ["bash", str(RUN_WRAPPER), str(fasta), str(output_link)],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert symbolic.returncode == 2
    assert "refusing a symbolic-link output directory" in symbolic.stderr


def test_derived_dockerfile_uses_numeric_parent_identity() -> None:
    source = (ROOT / "workstation" / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG DJRMCP_UID=1000" in source
    assert "ARG DJRMCP_GID=1000" in source
    assert "USER ${DJRMCP_UID}:${DJRMCP_GID}" in source
    assert "USER djrmcp" not in source
    assert "HOME=/work" in source
    assert 'chown -R "${DJRMCP_UID}:${DJRMCP_GID}" /models/huggingface /work' in source


def test_build_checks_writable_home_and_mounted_cache() -> None:
    source = BUILD_WRAPPER.read_text(encoding="utf-8")
    assert 'test -w "$HOME"' in source
    assert "test -w /models/huggingface" in source
    assert '.djrmcp-write-test.$$' in source
