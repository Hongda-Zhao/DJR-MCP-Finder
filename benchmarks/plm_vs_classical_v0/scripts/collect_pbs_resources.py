#!/usr/bin/env python3
"""Collect immutable PBS history fields for completed benchmark jobs."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from common import read_tsv, write_tsv


FIELDS = [
    "job_id",
    "job_name",
    "job_state",
    "exit_status",
    "queue",
    "resources_used_walltime",
    "resources_used_cput",
    "resources_used_mem",
    "resources_used_ncpus",
    "resources_used_cpupercent",
    "exec_host",
]


def parse_qstat(text: str, requested_job_id: str) -> dict[str, str]:
    logical: list[str] = []
    for line in text.splitlines():
        if line[:1].isspace() and logical and "=" not in line:
            logical[-1] += line.strip()
        else:
            logical.append(line.strip())
    values: dict[str, str] = {}
    job_id = requested_job_id
    for line in logical:
        if line.startswith("Job Id:"):
            job_id = line.split(":", 1)[1].strip()
        elif " = " in line:
            key, value = line.split(" = ", 1)
            values[key.strip()] = value.strip()
    row = {
        "job_id": job_id,
        "job_name": values.get("Job_Name", ""),
        "job_state": values.get("job_state", ""),
        "exit_status": values.get("Exit_status", ""),
        "queue": values.get("queue", ""),
        "resources_used_walltime": values.get("resources_used.walltime", ""),
        "resources_used_cput": values.get("resources_used.cput", ""),
        "resources_used_mem": values.get("resources_used.mem", ""),
        "resources_used_ncpus": values.get("resources_used.ncpus", ""),
        "resources_used_cpupercent": values.get("resources_used.cpupercent", ""),
        "exec_host": values.get("exec_host", ""),
    }
    if row["job_state"] != "F" or row["exit_status"] != "0":
        raise RuntimeError(f"PBS job is not successfully complete: {row}")
    if not re.fullmatch(r"\d+:[0-5]\d:[0-5]\d", row["resources_used_walltime"]):
        raise RuntimeError(f"Malformed PBS walltime: {row}")
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", action="append", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = read_tsv(args.output) if args.output.exists() else []
    by_id = {row["job_id"]: row for row in rows}
    for job_id in args.job_id:
        completed = subprocess.run(
            ["qstat", "-x", "-f", job_id],
            check=True,
            capture_output=True,
            text=True,
        )
        row = parse_qstat(completed.stdout, job_id)
        by_id[row["job_id"]] = row
    write_tsv(args.output, [by_id[key] for key in sorted(by_id)], FIELDS)
    print(f"PASS collected {len(by_id)} completed PBS job receipts")


if __name__ == "__main__":
    main()

