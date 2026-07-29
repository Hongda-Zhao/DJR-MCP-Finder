#!/usr/bin/env python3
"""Fail before compute if frozen classical executables/options are unavailable."""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path

from common import atomic_json, load_config, sha256_file


def capture(args: list[str]) -> str:
    completed = subprocess.run(args, check=False, capture_output=True, text=True)
    text = (completed.stdout + "\n" + completed.stderr).strip()
    if completed.returncode not in {0, 1}:  # several bioinformatics help commands return 1
        raise RuntimeError(f"Preflight command failed ({completed.returncode}): {args}\n{text[:1000]}")
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    config, _, benchmark_root = load_config(args.config)
    tools = {}
    for name, raw_path in config["tools"].items():
        path = Path(raw_path)
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimeError(f"Missing/non-executable frozen tool: {name} -> {path}")
        tools[name] = {"path": str(path), "sha256": sha256_file(path)}

    help_contracts = {
        "psiblast_save_last_round": (
            [config["tools"]["psiblast"], "-help"],
            "save_pssm_after_last_round",
        ),
        "hmmer_max": ([config["tools"]["hmmscan"], "-h"], "--max"),
        "hmmer_domain_report_threshold": (
            [config["tools"]["hmmscan"], "-h"],
            "--domE",
        ),
        "mmseqs_prefilter_limit": (
            [config["tools"]["mmseqs"], "easy-search", "-h"],
            "--max-seqs",
        ),
    }
    option_checks = {}
    for name, (command, token) in help_contracts.items():
        output = capture(command)
        if token not in output:
            raise RuntimeError(f"Frozen CLI contract {name} lacks {token!r}")
        option_checks[name] = {"token": token, "status": "PASS"}

    versions = {
        "blastp": capture([config["tools"]["blastp"], "-version"]).splitlines()[:2],
        "psiblast": capture([config["tools"]["psiblast"], "-version"]).splitlines()[:2],
        "diamond": capture([config["tools"]["diamond"], "version"]).splitlines()[:2],
        "mmseqs": capture([config["tools"]["mmseqs"], "version"]).splitlines()[:2],
        "hmmer": capture([config["tools"]["hmmbuild"], "-h"]).splitlines()[:2],
        "mafft": capture([config["tools"]["mafft"], "--version"]).splitlines()[:2],
    }
    atomic_json(
        benchmark_root / "work/software_environment.preflight.json",
        {
            "status": "PASS",
            "config_sha256": sha256_file(args.config.resolve()),
            "configured_versions": config["tool_versions"],
            "tools": tools,
            "version_output": versions,
            "option_checks": option_checks,
            "python": sys.version,
            "platform": platform.platform(),
        },
    )
    print(f"PASS preflighted {len(tools)} frozen executables and {len(option_checks)} CLI options")


if __name__ == "__main__":
    main()

