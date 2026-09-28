"""Reader-focused English figures from checksum-verified, unchanged benchmark data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.patches import Rectangle

LABELS = ("<250", "250-299", "300-349", "350-399", "400-449", "450-499", "500+")
INK, MUTED, GRID = "#20303C", "#62717D", "#E5EAEE"
TEAL, ORANGE, BLUE = "#137E89", "#DE8244", "#75899B"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_tsv(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))


def configure():
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 8,
            "pdf.fonttype": 42,
            "svg.fonttype": "none",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "text.color": INK,
            "axes.labelcolor": INK,
            "xtick.color": MUTED,
            "ytick.color": INK,
            "axes.unicode_minus": False,
        }
    )
    return font_manager.FontProperties(family=["sans-serif"]).get_name()


def save(fig, out, name):
    fig.savefig(out / f"{name}.png", dpi=300, facecolor="white")
    fig.savefig(out / f"{name}.pdf", facecolor="white")
    fig.savefig(out / f"{name}.svg", facecolor="white")
    plt.close(fig)


def label(value):
    return "≥500" if value == "500+" else value.replace("-", "–")


def overview(counts, out):
    table = {r["length_bin_aa"]: r for r in counts if r["method"] == "v01_candidate"}
    pos = sum(int(r["positive_n"]) for r in table.values())
    tp = sum(int(r["tp"]) for r in table.values())
    neg = sum(int(r["negative_n"]) for r in table.values())
    fp = sum(int(r["fp"]) for r in table.values())
    fig = plt.figure(figsize=(7.2, 5.1))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axis("off")
    ax.text(0.055, 0.942, "MCP detection by protein length", fontsize=15, weight="bold")
    ax.text(
        0.055,
        0.902,
        "V0.1 recipe · Train-only internal cross-fit · Original protein lengths",
        fontsize=8.5,
        color=MUTED,
    )
    for x, number, caption, color in (
        (0.055, f"{tp}/{pos}", "MCPs detected", TEAL),
        (0.59, str(pos - tp), "MCPs missed", ORANGE),
    ):
        ax.text(x, 0.827, number, fontsize=20, weight="bold", color=color)
        ax.text(x, 0.783, caption, fontsize=8.5, color=MUTED)
    ax.plot([0.055, 0.955], [0.746, 0.746], color=GRID, lw=1)
    for x, text, align in (
        (0.055, "Length / aa", "left"),
        (0.255, "Recall", "left"),
        (0.765, "Detected / MCP", "center"),
        (0.922, "Missed", "center"),
    ):
        ax.text(x, 0.71, text, fontsize=8, color=MUTED, ha=align)
    bar_x, bar_w = 0.255, 0.39
    for i, group in enumerate(LABELS):
        r = table[group]
        y = 0.653 - i * 0.079
        n, tp, fn = (int(r[k]) for k in ("positive_n", "tp", "fn"))
        if i % 2 == 0:
            ax.add_patch(Rectangle((0.045, y - 0.034), 0.92, 0.068, color="#F5F7F8", lw=0))
        ax.text(0.055, y, label(group), va="center", fontsize=10, weight="bold")
        if n:
            recall = tp / n
            ax.add_patch(Rectangle((bar_x, y - 0.02), bar_w * recall, 0.04, color=TEAL, lw=0))
            if fn:
                ax.add_patch(
                    Rectangle(
                        (bar_x + bar_w * recall, y - 0.02),
                        bar_w * (1 - recall),
                        0.04,
                        color=ORANGE,
                        lw=0,
                    )
                )
            ax.text(
                bar_x + 0.012,
                y,
                f"{recall:.1%}",
                color="white",
                va="center",
                fontsize=9,
                weight="bold",
            )
            ax.text(0.765, y, f"{tp}/{n}", ha="center", va="center", fontsize=10)
            ax.text(
                0.922,
                y,
                str(fn),
                ha="center",
                va="center",
                fontsize=10,
                color=ORANGE if fn else MUTED,
                weight="bold" if fn else "normal",
            )
        else:
            ax.text(bar_x, y + 0.009, "Recall not estimable", va="center", fontsize=9, color=MUTED)
            ax.text(bar_x, y - 0.015, "No MCP positives", va="center", fontsize=7, color=MUTED)
            ax.text(0.765, y, "No samples", ha="center", va="center", fontsize=9, color=MUTED)
            ax.text(0.922, y, "—", ha="center", va="center", fontsize=10, color=MUTED)
    ax.add_patch(Rectangle((0.055, 0.107), 0.017, 0.014, color=TEAL, lw=0))
    ax.text(0.081, 0.114, "Detected", va="center", fontsize=8)
    ax.add_patch(Rectangle((0.157, 0.107), 0.017, 0.014, color=ORANGE, lw=0))
    ax.text(0.183, 0.114, "Missed", va="center", fontsize=8)
    ax.text(
        0.33,
        0.114,
        "Bars span 100%; counts show actual sample sizes.",
        fontsize=7.5,
        color=MUTED,
        va="center",
    )
    ax.text(
        0.055,
        0.040,
        "Only 13 positives at 250–299 aa; perfect observed recall is not a population guarantee.",
        fontsize=8,
        color=MUTED,
    )
    ax.text(
        0.055,
        0.014,
        "95% intervals and V0 comparisons are in the supplement. Validation/Test remain unscored.",
        fontsize=7.5,
        color=MUTED,
    )
    ax.text(
        0.055, 0.068,
        f"{fp} / {neg:,} false positives overall. Per-length specificity is retained in the supplement.",
        fontsize=8, color=MUTED,
    )
    save(fig, out, "overview.en")


def comparison(metrics, out):
    table = {
        (r["method"], r["length"], r["metric"]): r
        for r in metrics
        if r["panel"] == "observed_length" and r["source_dataset"] == "all"
    }
    fig, axes = plt.subplots(
        1, 2, figsize=(7.2, 4.6), gridspec_kw={"width_ratios": [1.25, 1]}, layout="constrained"
    )
    methods = (("v0", "V0", BLUE, "s", -0.13), ("v01_candidate", "V0.1", TEAL, "o", 0.13))
    for ax, metric, title in zip(
        axes, ("mcp_recall", "mcp_fpr"), ("MCP recall", "MCP false-positive rate")
    ):
        for i, group in enumerate(LABELS):
            if i % 2 == 0:
                ax.axhspan(i - 0.43, i + 0.43, color="#F5F7F8", zorder=0)
            for method, name, color, marker, offset in methods:
                r = table[(method, group, metric)]
                if r["estimate"] == "":
                    if method == "v01_candidate":
                        ax.text(
                            0.5,
                            i,
                            "No MCP positives",
                            transform=ax.get_yaxis_transform(),
                            ha="center",
                            color=MUTED,
                            fontsize=8,
                        )
                    continue
                y = i + offset
                if r["ci_low"] != "":
                    low, high = float(r["ci_low"]) * 100, float(r["ci_high"]) * 100
                    ax.hlines(y, low, high, color=color, lw=1.2)
                    ax.plot([low, high], [y, y], "|", color=color, ms=5)
                ax.plot(
                    float(r["estimate"]) * 100,
                    y,
                    marker=marker,
                    color=color,
                    ms=4,
                    label=name if i == (1 if metric == "mcp_recall" else 0) else None,
                )
        ax.set(
            yticks=range(len(LABELS)),
            yticklabels=[label(x) for x in LABELS],
            ylim=(len(LABELS) - 0.5, -0.7),
            xlabel="Percent / %",
            title=title,
        )
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color=GRID, lw=0.5)
        ax.set_axisbelow(True)
        if ax is axes[0]:
            ax.legend(frameon=False, loc="lower left", fontsize=7)
    axes[0].set_xlim(60, 102)
    axes[0].set_xticks([60, 70, 80, 90, 100])
    axes[0].set_ylabel("Length / aa")
    axes[1].set_xlim(-0.025, 0.65)
    axes[1].set_xticks([0, 0.2, 0.4, 0.6])
    fig.suptitle(
        "V0 and V0.1: estimates and uncertainty\nPoints: observed rates; lines: 95% component-bootstrap intervals (2,000 draws)",
        fontsize=10,
    )
    fig.supxlabel(
        "Recall axis starts at 60%; FPR axis near 0%. Boundary intervals do not prove zero population error.",
        fontsize=7,
    )
    save(fig, out, "comparison.en")


def phylum_detail(metrics, out):
    table = {
        (r["method"], r["length"], r["metric"]): r for r in metrics if r["source_dataset"] == "all"
    }
    row_specs = [
        (phylum, method)
        for phylum in ("Nucleocytoviricota", "Preplasmiviricota")
        for method in ("v0", "v01_candidate")
    ]
    data = np.full((4, len(LABELS)), np.nan)
    text = {}
    for i, (phylum, method) in enumerate(row_specs):
        for j, group in enumerate(LABELS):
            r = table[(method, group, "h3_end_to_end_recall_" + phylum)]
            n = int(r["parents"])
            if n:
                data[i, j] = float(r["estimate"]) * 100
                text[i, j] = f"{data[i, j]:.1f}%\n{r['successes']}/{n}"
            else:
                text[i, j] = "No samples"
    fig, ax = plt.subplots(figsize=(7.2, 3.1), layout="constrained")
    cmap = plt.get_cmap("Blues").copy()
    cmap.set_bad("#EEEEEE")
    im = ax.imshow(np.ma.masked_invalid(data), cmap=cmap, vmin=0, vmax=100, aspect="auto")
    for (i, j), value in text.items():
        ax.text(
            j,
            i,
            value,
            ha="center",
            va="center",
            fontsize=7,
            color="white" if np.isfinite(data[i, j]) and data[i, j] >= 65 else INK,
        )
    ax.set(
        xticks=range(len(LABELS)),
        xticklabels=[label(x) for x in LABELS],
        yticks=range(4),
        yticklabels=[p + "\n" + ("V0" if m == "v0" else "V0.1") for p, m in row_specs],
        xlabel="Length / aa",
    )
    ax.tick_params(length=0)
    ax.spines[["left", "bottom"]].set_visible(False)
    fig.colorbar(im, ax=ax, label="End-to-end phylum recall / %", fraction=0.035)
    fig.suptitle("Phylum classification: recall and counts", fontsize=11)
    fig.supxlabel(
        "Denominator: true MCPs of that phylum, including upstream misses. Small groups (e.g., 0/1) are uncertain.",
        fontsize=7,
    )
    save(fig, out, "phylum_detail.en")


def run(source, out):
    receipt = json.loads((source / "provenance.json").read_text())
    for name in ("metrics.tsv", "confusion_by_length.tsv"):
        if sha(source / name) != receipt["files"][name]:
            raise ValueError("Numeric source checksum mismatch: " + name)
    counts, metrics = read_tsv(source / "confusion_by_length.tsv"), read_tsv(source / "metrics.tsv")
    if {(r["method"], r["length_bin_aa"]) for r in counts} != {
        (m, b) for m in ("v0", "v01_candidate") for b in LABELS
    } or len(counts) != 14:
        raise ValueError("Unexpected bin or method contract")
    for r in counts:
        tp, fn, fp, tn, pos, neg = (
            int(r[k]) for k in ("tp", "fn", "fp", "tn", "positive_n", "negative_n")
        )
        if min(tp, fn, fp, tn) < 0 or tp + fn != pos or fp + tn != neg:
            raise ValueError("Invalid confusion counts")
    out.mkdir(parents=True, exist_ok=True)
    font = configure()
    overview(counts, out)
    comparison(metrics, out)
    phylum_detail(metrics, out)
    record = {
        "status": "PASS",
        "change": "presentation_only",
        "model_or_metric_changes": False,
        "source_numeric_checksums": {
            name: sha(source / name) for name in ("metrics.tsv", "confusion_by_length.tsv")
        },
        "source_analysis_receipt_sha256": sha(source / "provenance.json"),
        "script_sha256": sha(Path(__file__)),
        "font": font,
        "backend": "matplotlib",
        "primary_method": "v01_candidate",
        "primary_figure": "overview.en.png",
        "preserved_supporting_methods": ["v0", "v01_candidate"],
        "interpretation": "Main bars show observed recall with integer event counts; uncertainty is retained in comparison figure and original metric table.",
        "scope": "Train-only internal cross-fit, 336 positive and 6298 non-MCP proteins",
        "excluded_proteins": 0,
        "presentation_revision": "Remove per-length FP column at user request; retain overall FP in caption and full specificity supplement.",
        "main_table_columns_before": 5,
        "main_table_columns_after": 4,
        "files": {p.name: sha(p) for p in out.iterdir() if p.suffix in {".png", ".pdf", ".svg"}},
    }
    (out / "provenance.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = run(args.source, args.out)
    print(
        json.dumps(
            {
                "status": result["status"],
                "primary_figure": result["primary_figure"],
                "font": result["font"],
            }
        )
    )
