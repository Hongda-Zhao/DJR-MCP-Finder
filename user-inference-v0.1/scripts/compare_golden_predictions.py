#!/usr/bin/env python3
"""Compare V0.1 user output with the archived mixed-candidate golden result."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


NUMERIC_FIELD_PAIRS = (
    ("head1_djr_probability", "head1_djr_probability"),
    # The archived golden file predates the public MCP terminology.
    ("head2_vma_probability", "head2_mcp_probability"),
    ("head3_nucleocytoviricota_probability", "head3_nucleocytoviricota_probability"),
    ("head3_preplasmiviricota_probability", "head3_preplasmiviricota_probability"),
    ("head3_confidence", "head3_confidence"),
)
LABEL_FIELDS = (
    "head1_prediction",
    "head3_reached",
    "head3_prediction",
    "final_prediction",
    "head1_encoder",
    "head2_encoder",
    "head3_encoder",
)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _optional_float(value: str) -> float | None:
    return None if value in {"", "NA"} else float(value)


def _current_final_label(value: str) -> str:
    if value == "djr_non_vma":
        return "djr_non_mcp"
    if value.startswith("vma::"):
        return f"mcp::{value.removeprefix('vma::')}"
    return value


def _current_head2_label(value: str) -> str:
    """Translate the frozen V0/V0.1 H2 class vocabulary at the comparison boundary."""

    if value == "viral_morphogenesis_associated":
        return "mcp"
    return value


def compare(
    reference_path: Path,
    observed_path: Path,
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    reference = _read(reference_path)
    observed = _read(observed_path)
    reference_ids = [row["sequence_sha256"] for row in reference]
    observed_ids = [row["sequence_sha256"] for row in observed]
    if reference_ids != observed_ids or len(set(reference_ids)) != len(reference_ids):
        raise RuntimeError("Reference and observed sequence identities/order differ")

    mismatches: list[dict[str, Any]] = []
    maximum_delta = {current: 0.0 for _, current in NUMERIC_FIELD_PAIRS}
    for expected, actual in zip(reference, observed, strict=True):
        identity = expected["sequence_sha256"]
        for archived_field, current_field in NUMERIC_FIELD_PAIRS:
            left = _optional_float(expected[archived_field])
            right = _optional_float(actual[current_field])
            if left is None or right is None:
                if left != right:
                    mismatches.append(
                        {
                            "sequence_sha256": identity,
                            "field": current_field,
                            "expected": left,
                            "observed": right,
                        }
                    )
                continue
            delta = abs(left - right)
            maximum_delta[current_field] = max(maximum_delta[current_field], delta)
            if not math.isclose(
                left,
                right,
                abs_tol=absolute_tolerance,
                rel_tol=relative_tolerance,
            ):
                mismatches.append(
                    {
                        "sequence_sha256": identity,
                        "field": current_field,
                        "expected": left,
                        "observed": right,
                        "absolute_delta": delta,
                    }
                )
        expected_labels = dict(expected)
        expected_labels["head2_operational_prediction"] = _current_head2_label(
            expected["head2_prediction"]
        )
        expected_labels["final_prediction"] = _current_final_label(expected["final_prediction"])
        for field in (*LABEL_FIELDS, "head2_operational_prediction"):
            if expected_labels[field] != actual[field]:
                mismatches.append(
                    {
                        "sequence_sha256": identity,
                        "field": field,
                        "expected": expected_labels[field],
                        "observed": actual[field],
                    }
                )
    return {
        "status": "PASS" if not mismatches else "FAIL",
        "records": len(reference),
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "maximum_absolute_probability_delta": maximum_delta,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("observed", type=Path)
    parser.add_argument("--absolute-tolerance", type=float, default=5e-7)
    parser.add_argument("--relative-tolerance", type=float, default=1e-6)
    args = parser.parse_args()
    report = compare(
        args.reference,
        args.observed,
        absolute_tolerance=args.absolute_tolerance,
        relative_tolerance=args.relative_tolerance,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
