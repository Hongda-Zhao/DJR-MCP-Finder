"""Reporting must preserve bin boundaries, counts, and missing denominators."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks/short_sequence_v1"))
import length_bins_report as report


@pytest.mark.parametrize(
    "length,expected",
    [
        (249, "<250"),
        (250, "250-299"),
        (299, "250-299"),
        (300, "300-349"),
        (349, "300-349"),
        (350, "350-399"),
        (400, "400-449"),
        (450, "450-499"),
        (499, "450-499"),
        (500, "500+"),
        (2906, "500+"),
    ],
)
def test_half_open_bins(length, expected):
    assert report.length_bin(length) == expected


def test_rebin_counts_full_parents_once_and_keeps_empty_denominators():
    def row(pid, length, positive, call, position="full"):
        return dict(
            parent_id=pid,
            method="v01_candidate",
            position=position,
            length_aa=str(length),
            is_mcp=str(positive),
            mcp_positive=str(call),
            is_djr=str(positive),
            head1_positive=str(call),
            head2_positive=str(call),
            phylum="unknown/other",
            head3_diagnostic_label="unknown/other",
            global_component_id="component_" + pid,
            source_dataset="viral_vma_djr" if positive else "hard_non_djr",
        )

    rows = [
        row("p1", 299, 1, 1),
        row("p2", 300, 1, 0),
        row("p3", 500, 0, 1),
        row("p4", 249, 0, 0),
        row("p1", 50, 1, 0, "n_terminal"),
    ]
    config = dict(methods={"v01_candidate": "esm2_3b"}, bootstrap_replicates=100, seed=1)
    metrics, counts = report.aggregate(rows, config)
    by_bin = {r["length_bin_aa"]: r for r in counts}
    assert sum(r["total"] for r in counts) == 4
    assert by_bin["250-299"]["tp"] == 1
    assert by_bin["300-349"]["fn"] == 1
    assert by_bin["500+"]["fp"] == 1
    assert by_bin["<250"]["recall"] == "" and by_bin["<250"]["fpr"] == 0
    missing = next(
        r
        for r in metrics
        if r["length"] == "350-399" and r["source_dataset"] == "all" and r["metric"] == "mcp_recall"
    )
    assert missing["ci_status"] == "NOT_ESTIMABLE"
    with pytest.raises(ValueError, match="Duplicate"):
        report.aggregate(rows + [rows[0]], config)
