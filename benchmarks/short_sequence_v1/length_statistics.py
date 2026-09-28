#!/usr/bin/env python3
"""Describe labeled MCP-positive lengths; metadata only, never model evaluation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

GROUPS = ("Nucleocytoviricota", "Preplasmiviricota", "unknown/other")
COLORS = ("#4C78A8", "#E69F00", "#888888")
BINS = (
    (0, 250),
    (250, 300),
    (300, 350),
    (350, 400),
    (400, 450),
    (450, 500),
    (500, 550),
    (550, 600),
    (600, 700),
    (700, 1000),
    (1000, None),
)


def read_tsv(path):
    with path.open() as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def describe(lengths):
    values = np.asarray(lengths, dtype=float)
    quantiles = np.quantile(values, [0.05, 0.25, 0.5, 0.75, 0.95], method="linear")
    return {
        "n": len(values),
        "min": int(values.min()),
        "max": int(values.max()),
        "mean": float(values.mean()),
        "sample_sd": float(values.std(ddof=1)),
        **{k: float(v) for k, v in zip(("p05", "q1", "median", "q3", "p95"), quantiles)},
    }


def run(parents, out, scope="train"):
    if scope not in {"train", "all"}:
        raise ValueError("Unknown scope")
    rows = read_tsv(parents)
    if not rows or any(r["split"] not in {"train", "validation", "test"} for r in rows):
        raise ValueError("Invalid split")
    if scope == "train" and any(r["split"] != "train" for r in rows):
        raise ValueError("Use --scope all explicitly for metadata statistics across all splits")
    for row in rows:
        if "is_mcp" not in row:
            row["is_mcp"] = str(
                int(
                    row["head2_mask"] == "1"
                    and row["head2_label"] == "viral_morphogenesis_associated"
                )
            )
            phylum = row.get("head3_operational_label", "")
            row["phylum"] = (
                phylum if row.get("head3_mask") == "1" and phylum in GROUPS[:2] else "unknown/other"
            )
            row["fold"] = ""
    prepared = parents.parent.parent / "prepared.json"
    source_sha = hashlib.sha256(parents.read_bytes()).hexdigest()
    if prepared.exists():
        expected = json.loads(prepared.read_text())["files"]["inputs/parents.tsv"]
        if source_sha != expected:
            raise ValueError("Parent table differs from frozen preparation")
    selected = sorted(
        (r for r in rows if r["is_mcp"] == "1"),
        key=lambda r: (int(r["length_aa"]), r["protein_id"]),
    )
    if not selected or len({r["protein_id"] for r in selected}) != len(selected):
        raise ValueError("Missing or duplicate positive parents")
    if any(r["phylum"] not in GROUPS or int(r["length_aa"]) <= 0 for r in selected):
        raise ValueError("Invalid phylum or length")
    x = np.array([int(r["length_aa"]) for r in selected])
    out.mkdir(parents=True, exist_ok=True)
    write_tsv(
        out / "positive_sequences.tsv",
        [
            {
                k: r[k]
                for k in (
                    "protein_id",
                    "length_aa",
                    "phylum",
                    "family_metadata",
                    "global_component_id",
                    "fold",
                    "split",
                    "sequence_sha256",
                )
            }
            for r in selected
        ],
    )
    groups = [{"group": "all", **describe(x)}]
    groups.extend(
        {
            "group": group,
            **describe([int(r["length_aa"]) for r in selected if r["phylum"] == group]),
        }
        for group in GROUPS
        if any(r["phylum"] == group for r in selected)
    )
    write_tsv(out / "summary.tsv", groups)
    splits = [
        {"split": split, **describe([int(r["length_aa"]) for r in selected if r["split"] == split])}
        for split in ("train", "validation", "test")
        if any(r["split"] == split for r in selected)
    ]
    write_tsv(out / "by_split.tsv", splits)
    counts = []
    for lo, hi in BINS:
        subset = [
            r
            for r in selected
            if int(r["length_aa"]) >= lo and (hi is None or int(r["length_aa"]) < hi)
        ]
        counts.append(
            {
                "length_bin_aa": f">={lo}" if hi is None else f"{lo}-{hi - 1}",
                "n": len(subset),
                "percent": len(subset) / len(x) * 100,
                **{group: sum(r["phylum"] == group for r in subset) for group in GROUPS},
            }
        )
    assert sum(r["n"] for r in counts) == len(x)
    write_tsv(out / "length_bins.tsv", counts)
    cumulative = [
        {
            "length_below_aa": threshold,
            "n": int((x < threshold).sum()),
            "percent": float((x < threshold).mean() * 100),
        }
        for threshold in (130, 150, 200, 250, 300, 350, 400, 500, 600, 700, 1000)
    ]
    write_tsv(out / "cumulative_counts.tsv", cumulative)
    manifest = {
        "scope": "labeled_mcp_positive_length_statistics_" + scope,
        "model_evaluation": False,
        "split_statistics": splits,
        "input_parents": len(rows),
        "positive_parents": len(x),
        "unique_positive_sequences": len({r["sequence_sha256"] for r in selected}),
        "unit": "amino_acids",
        "filter": "is_mcp=1; scope=" + scope,
        "source_sha256": source_sha,
        "quantile_method": "numpy linear",
        "sd_ddof": 1,
        "statistics": groups,
        "length_bins": counts,
        "cumulative_counts": cumulative,
        "note": "Original input lengths; not predictions, fragments or proof of complete proteins. unknown/other is an operational H3 label. No positive outliers excluded.",
    }
    (out / "summary.json").write_text(json.dumps(manifest, indent=2) + "\n")
    plot(selected, out, scope)
    files = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in out.iterdir()
        if p.is_file() and p.name != "CHECKSUMS.json"
    }
    (out / "CHECKSUMS.json").write_text(json.dumps(files, indent=2) + "\n")
    return manifest


def plot(selected, out, scope):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 8,
            "pdf.fonttype": 42,
            "svg.fonttype": "none",
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    groups = [np.array([int(r["length_aa"]) for r in selected if r["phylum"] == g]) for g in GROUPS]
    all_lengths = np.concatenate(groups)
    upper = int(np.ceil(all_lengths.max() / 50) * 50)
    edges = np.arange(0, upper + 50, 50)
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 5.3), constrained_layout=True)
    labels = [f"{group} (n={len(v)})" for group, v in zip(GROUPS, groups)]
    axes[0].hist(
        groups,
        bins=edges,
        stacked=True,
        color=COLORS,
        label=labels,
        edgecolor="white",
        linewidth=0.4,
    )
    median = float(np.median(all_lengths))
    axes[0].axvline(median, color="#333333", linestyle="--", linewidth=1)
    axes[0].text(median + 15, axes[0].get_ylim()[1] * 0.90, f"Median {median:g} aa", fontsize=8)
    axes[0].set(title="a  Length distribution (50-aa bins)", ylabel="MCP-positive proteins")
    axes[0].legend(frameon=False, loc="upper right", fontsize=7)
    for group, values, color in zip(GROUPS, groups, COLORS):
        if len(values):
            ordered = np.sort(values)
            axes[1].step(
                np.r_[0, ordered, upper],
                np.r_[0, np.arange(1, len(values) + 1) / len(values), 1],
                where="post",
                color=color,
                linewidth=1.5,
                label=group,
            )
    axes[1].set(
        title="b  Cumulative fraction within each operational phylum group",
        ylabel="Fraction of positive proteins",
        ylim=(-0.02, 1.04),
    )
    axes[1].yaxis.set_major_formatter(PercentFormatter(1))
    for ax in axes:
        ax.axvspan(0, 250, color="#DDDDDD", alpha=0.3, zorder=-1)
        ax.set(xlim=(0, upper), xlabel="Original protein length (aa)")
    axes[0].text(
        125, axes[0].get_ylim()[1] * 0.55, "No MCP\npositives\n<250 aa", ha="center", fontsize=7
    )
    fig.suptitle(
        f"MCP-positive length distribution | {'Train' if scope == 'train' else 'All splits'} n={len(selected)}\n"
        f"All records retained: {all_lengths.min()}–{all_lengths.max()} aa",
        fontsize=10,
    )
    fig.savefig(out / "mcp_positive_lengths.png", dpi=300)
    fig.savefig(out / "mcp_positive_lengths.pdf")
    fig.savefig(out / "mcp_positive_lengths.svg")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parents", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--scope", choices=("train", "all"), default="train")
    args = parser.parse_args()
    result = run(args.parents, args.out, args.scope)
    print(json.dumps(result["statistics"], indent=2))
