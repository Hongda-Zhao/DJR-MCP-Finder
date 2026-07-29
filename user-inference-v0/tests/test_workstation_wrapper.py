from __future__ import annotations

import os
import subprocess
from pathlib import Path


WRAPPER = Path(__file__).resolve().parents[1] / "workstation" / "run_user_fasta.sh"
DOCKERFILE = Path(__file__).resolve().parents[1] / "workstation" / "Dockerfile"


def test_wrapper_refuses_to_mount_host_root_as_output_parent(tmp_path: Path) -> None:
    fasta = tmp_path / "input.faa"
    fasta.write_text(">protein\n" + "ACDEFGHIKLMNPQRSTVWY" * 7 + "\n", encoding="utf-8")
    environment = os.environ.copy()
    environment["DJRMCP_DOCKER"] = "/usr/bin/false"

    completed = subprocess.run(
        ["bash", str(WRAPPER), str(fasta), "/djrmcp-unsafe-output"],
        cwd="/",
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "refusing to mount / as the output parent" in completed.stderr


def test_dockerfile_reuses_default_base_image_uid() -> None:
    source = DOCKERFILE.read_text(encoding="utf-8")
    assert "Reusing base-image account with UID" in source
    assert "USER ${DJRMCP_UID}:${DJRMCP_GID}" in source
    assert "is already assigned in the base image" not in source


def test_wrapper_refuses_symbolic_link_output_directory(tmp_path: Path) -> None:
    fasta = tmp_path / "input.faa"
    fasta.write_text(">protein\n" + "ACDEFGHIKLMNPQRSTVWY" * 7 + "\n", encoding="utf-8")
    target = tmp_path / "target"
    target.mkdir()
    output_link = tmp_path / "output-link"
    output_link.symlink_to(target, target_is_directory=True)
    environment = os.environ.copy()
    environment["DJRMCP_DOCKER"] = "/usr/bin/false"

    completed = subprocess.run(
        ["bash", str(WRAPPER), str(fasta), str(output_link)],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "refusing a symbolic-link output directory" in completed.stderr
