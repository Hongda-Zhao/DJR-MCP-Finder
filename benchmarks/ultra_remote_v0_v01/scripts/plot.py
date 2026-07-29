#!/usr/bin/env python3
"""Create the publication figure for the v0/v0.1 ultra-remote audit."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np


METHOD_LABEL = {
    "esmc6b_cosine": "v0 · ESM-C 6B cosine",
    "esm2_3b_cosine": "v0.1 · ESM-2 3B cosine",
    "esm2_650m_cosine": "ESM-2 650M cosine",
    "blastp": "BLASTP",
    "diamond_ultra": "DIAMOND",
    "mmseqs_s7.5": "MMseqs2",
    "hmmer_component": "component HMM",
    "psiblast_longest_seed_positiveDB_3iter": "PSI-BLAST (3 iter)",
    "hmmer_family": "family HMM",
    "esmc6b_supervised": "v0 · supervised",
    "esm2_3b_supervised": "v0.1 · supervised",
}
TASK_LABEL = {
    "h1_djr": "H1 DJR",
    "h2_vma_conditional": "H2 VMA | DJR",
    "vma_end_to_end": "VMA end-to-end",
}
COLORS = {
    "esmc6b_cosine": "#6F87A6",
    "esm2_3b_cosine": "#D86F4C",
    "esm2_650m_cosine": "#B99A55",
    "blastp": "#737373",
    "diamond_ultra": "#969696",
    "mmseqs_s7.5": "#B5B5B5",
    "hmmer_component": "#6B9A8B",
    "psiblast_longest_seed_positiveDB_3iter": "#8877A9",
    "hmmer_family": "#4F7F71",
    "esmc6b_supervised": "#365F91",
    "esm2_3b_supervised": "#B8492E",
}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def value(row: dict[str, str], key: str) -> float:
    return np.nan if row[key] in ("", "NA") else float(row[key])


def panel_label(axis: plt.Axes, label: str) -> None:
    axis.text(
        -0.13,
        1.06,
        label,
        transform=axis.transAxes,
        fontsize=9,
        fontweight="bold",
        va="top",
        ha="left",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--project-root", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    project_root = (
        args.project_root.resolve()
        if args.project_root is not None
        else Path(config["project_root"]).resolve()
    )
    benchmark_root = (project_root / config["benchmark_root"]).resolve()
    results = benchmark_root / "results"
    figures = benchmark_root / "figures"
    source_root = figures / "source_data"
    paired = read_tsv(results / "paired_v0_v01.tsv")
    strata = read_tsv(results / "stratum_sensitivity.tsv")
    summary = read_tsv(results / "method_summary.tsv")

    paired_source = [
        row
        for row in paired
        if row["stratum"]
        in (
            "component_holdout_all",
            "blast_defined_qcov_ge80_pident_20_to_lt30",
            "blast_defined_qcov_lt80",
        )
    ]
    selected_absolute_methods = [
        "esmc6b_cosine",
        "esm2_3b_cosine",
        "blastp",
        "hmmer_component",
        "psiblast_longest_seed_positiveDB_3iter",
        "esmc6b_supervised",
        "esm2_3b_supervised",
    ]
    absolute_source = [
        row
        for row in strata
        if row["stratum"] == "blast_defined_qcov_lt80"
        and row["method"] in selected_absolute_methods
    ]
    pauc_methods = [
        "esmc6b_cosine",
        "esm2_3b_cosine",
        "esm2_650m_cosine",
        "blastp",
        "diamond_ultra",
        "mmseqs_s7.5",
        "hmmer_component",
    ]
    pauc_source = [row for row in summary if row["method"] in pauc_methods]
    count_source = [
        row
        for row in strata
        if row["method"] == "esm2_3b_cosine"
        and row["stratum"]
        in (
            "blast_defined_qcov_ge80_pident_lt20",
            "blast_defined_pident_lt20_any_qcov",
            "blast_defined_qcov_ge80_pident_20_to_lt30",
            "blast_defined_qcov_lt80",
            "component_holdout_all",
        )
    ]
    write_tsv(source_root / "paired_delta.tsv", paired_source)
    write_tsv(source_root / "low_coverage_sensitivity.tsv", absolute_source)
    write_tsv(source_root / "low_fpr_pauc.tsv", pauc_source)
    write_tsv(source_root / "sample_sufficiency.tsv", count_source)

    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 7,
            "axes.titlesize": 8,
            "axes.labelsize": 7,
            "axes.linewidth": 0.7,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.frameon": False,
        }
    )
    fig = plt.figure(figsize=(7.09, 6.10), constrained_layout=False)
    grid = fig.add_gridspec(
        2,
        2,
        left=0.09,
        right=0.985,
        bottom=0.11,
        top=0.84,
        width_ratios=[1.12, 1.0],
        height_ratios=[1.05, 1.0],
        wspace=0.34,
        hspace=0.56,
    )
    ax_a = fig.add_subplot(grid[:, 0])
    ax_b = fig.add_subplot(grid[0, 1])
    lower = grid[1, 1].subgridspec(1, 2, width_ratios=[1.12, 0.88], wspace=0.72)
    ax_c = fig.add_subplot(lower[0, 0])
    ax_d = fig.add_subplot(lower[0, 1])

    # a — paired delta forest (hero panel)
    label_rows = []
    for task in TASK_LABEL:
        for layer in ("encoder", "task_adapted_detector"):
            label_rows.append((task, layer))
    y_base = np.arange(len(label_rows))[::-1]
    stratum_style = {
        "component_holdout_all": ("All component-holdout", "o", "#89939E", -0.20),
        "blast_defined_qcov_ge80_pident_20_to_lt30": (
            "BLAST 20–30% identity",
            "D",
            "#8877A9",
            0.0,
        ),
        "blast_defined_qcov_lt80": ("BLAST qcov <80%", "s", "#1F8A8A", 0.20),
    }
    paired_lookup = {
        (row["task"], row["comparison_layer"], row["stratum"]): row
        for row in paired_source
    }
    for stratum, (legend, marker, color, offset) in stratum_style.items():
        for index, (task, layer) in enumerate(label_rows):
            row = paired_lookup[(task, layer, stratum)]
            point = value(row, "delta_sensitivity_v01_minus_v0")
            low = value(row, "ci95_low_fixed_threshold")
            high = value(row, "ci95_high_fixed_threshold")
            y = y_base[index] + offset
            marker_face = (
                color
                if row["matched_specificity_status"] == "PASS_BOTH_ALL_FOLDS"
                else "white"
            )
            if np.isfinite(low) and np.isfinite(high):
                ax_a.errorbar(
                    point,
                    y,
                    xerr=[[point - low], [high - point]],
                    fmt=marker,
                    color=color,
                    ecolor=color,
                    markersize=4.2,
                    markerfacecolor=marker_face,
                    markeredgecolor=color,
                    markeredgewidth=1.0,
                    elinewidth=1.0,
                    capsize=2,
                    zorder=3,
                )
            else:
                ax_a.plot(
                    point,
                    y,
                    marker=marker,
                    color=color,
                    markerfacecolor=marker_face,
                    markeredgecolor=color,
                    markersize=4.2,
                )
    ax_a.axvline(0, color="#333333", lw=0.8, ls="--")
    ax_a.set_yticks(y_base)
    ax_a.set_yticklabels(
        [
            f"{TASK_LABEL[task]} · {'encoder' if layer == 'encoder' else 'detector'}"
            for task, layer in label_rows
        ]
    )
    ax_a.set_xlabel("Sensitivity difference (v0.1 − v0)")
    ax_a.set_title("Paired change at calibration-fold-locked 99.5% specificity threshold", loc="left")
    ax_a.grid(axis="x", color="#E7E7E7", lw=0.6)
    handles = [
        plt.Line2D([], [], marker=style[1], color=style[2], lw=0, label=style[0], markersize=4)
        for style in stratum_style.values()
    ]
    ax_a.legend(handles=handles, loc="lower right", fontsize=6.3)
    panel_label(ax_a, "a")

    # b — absolute sensitivity in the low-coverage stress stratum
    task_marker = {"h1_djr": "o", "h2_vma_conditional": "s", "vma_end_to_end": "^"}
    absolute_lookup = {
        (row["task"], row["method"]): row for row in absolute_source
    }
    gate_lookup = {(row["task"], row["method"]): row["specificity_gate_99.5"] for row in summary}
    y_method = np.arange(len(selected_absolute_methods))[::-1]
    task_offsets = {"h1_djr": 0.18, "h2_vma_conditional": 0.0, "vma_end_to_end": -0.18}
    for method_y, method in zip(y_method, selected_absolute_methods, strict=True):
        for task in TASK_LABEL:
            row = absolute_lookup[(task, method)]
            sensitivity = value(row, "component_sensitivity_99.5")
            face = COLORS[method] if gate_lookup[(task, method)] == "PASS_ALL_FOLDS" else "white"
            ax_b.plot(
                sensitivity,
                method_y + task_offsets[task],
                marker=task_marker[task],
                ms=4.2,
                markerfacecolor=face,
                markeredgecolor=COLORS[method],
                markeredgewidth=1.0,
                lw=0,
            )
    ax_b.set_xlim(0.45, 1.015)
    ax_b.set_yticks(y_method)
    ax_b.set_yticklabels([METHOD_LABEL[method] for method in selected_absolute_methods])
    ax_b.set_xlabel("Component-balanced sensitivity")
    ax_b.set_title("BLAST-defined low-coverage stress (qcov <80%)", loc="left")
    ax_b.grid(axis="x", color="#E7E7E7", lw=0.6)
    task_handles = [
        plt.Line2D([], [], marker=task_marker[task], color="#444444", lw=0, label=label, markersize=4)
        for task, label in TASK_LABEL.items()
    ]
    ax_b.legend(
        handles=task_handles,
        ncol=3,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.34),
        fontsize=5.9,
        columnspacing=0.9,
        handletextpad=0.3,
    )
    panel_label(ax_b, "b")

    # c — low-FPR representation/system ranking across all component holdouts
    pauc_lookup = {(row["task"], row["method"]): row for row in pauc_source}
    pauc_selected = [
        "esmc6b_cosine",
        "esm2_3b_cosine",
        "esm2_650m_cosine",
        "blastp",
        "hmmer_component",
    ]
    x_method = np.arange(len(pauc_selected))
    offsets = {"h1_djr": -0.18, "h2_vma_conditional": 0.0, "vma_end_to_end": 0.18}
    plotted_pauc_tasks = []
    for task in TASK_LABEL:
        task_values = [
            value(pauc_lookup[(task, method)], "mean_normalized_pauc_fpr_0.005")
            for method in pauc_selected
        ]
        if not np.all(np.isfinite(task_values)):
            continue
        plotted_pauc_tasks.append(task)
        ax_c.plot(
            x_method + offsets[task],
            task_values,
            marker=task_marker[task],
            ms=3.7,
            lw=0.8,
            color={"h1_djr": "#386C8E", "h2_vma_conditional": "#8A5A83", "vma_end_to_end": "#C26B3A"}[task],
            label=TASK_LABEL[task],
        )
    ax_c.set_xticks(x_method)
    ax_c.set_xticklabels(
        ["v0 6B", "v0.1 3B", "ESM2 650M", "BLAST", "HMM"],
        rotation=35,
        ha="right",
    )
    ax_c.set_ylim(0, 1.02)
    ax_c.set_ylabel("Normalized pAUROC")
    ax_c.set_title("All holdout · FPR ≤0.005", loc="left")
    ax_c.grid(axis="y", color="#E7E7E7", lw=0.6)
    ax_c.text(
        0.02,
        0.03,
        "Only H1 shown; H2/E2E lack\nper-source resolution at 0.5% FPR",
        transform=ax_c.transAxes,
        fontsize=5.2,
        color="#666666",
        va="bottom",
    )
    panel_label(ax_c, "c")

    # d — sample-size adequacy boundary
    count_label = {
        "blast_defined_qcov_ge80_pident_lt20": "<20%, cov≥80%",
        "blast_defined_pident_lt20_any_qcov": "<20%, any cov",
        "blast_defined_qcov_ge80_pident_20_to_lt30": "20–30%",
        "blast_defined_qcov_lt80": "cov<80%",
        "component_holdout_all": "all",
    }
    count_lookup = {
        (row["task"], row["stratum"]): int(row["positive_components"])
        for row in count_source
    }
    strata_order = list(count_label)
    y = np.arange(len(strata_order))[::-1]
    for task, marker in (("h1_djr", "o"), ("vma_end_to_end", "^")):
        ax_d.scatter(
            [count_lookup[(task, stratum)] for stratum in strata_order],
            y + (0.10 if task == "h1_djr" else -0.10),
            marker=marker,
            s=17,
            color="#365F91" if task == "h1_djr" else "#C26B3A",
            label=TASK_LABEL[task],
            zorder=3,
        )
    ax_d.axvline(30, color="#9C9C9C", lw=0.8, ls=":")
    ax_d.axvline(100, color="#333333", lw=0.8, ls="--")
    plotted_counts = [
        count_lookup[(task, stratum)]
        for task in ("h1_djr", "vma_end_to_end")
        for stratum in strata_order
    ]
    if any(count <= 0 for count in plotted_counts):
        raise RuntimeError("Sample-sufficiency log plot received a non-positive count")
    ax_d.set_xscale("log")
    ax_d.set_xlim(0.8, 600)
    ax_d.set_yticks(y)
    ax_d.set_yticklabels([count_label[stratum] for stratum in strata_order])
    ax_d.set_xlabel("Positive components (log scale)")
    ax_d.set_title("Evidence sufficiency", loc="left")
    ax_d.grid(axis="x", color="#E7E7E7", lw=0.6, which="both")
    ax_d.text(
        31,
        0.02,
        "n=30",
        transform=ax_d.get_xaxis_transform(),
        fontsize=5.1,
        color="#777777",
        rotation=90,
        va="bottom",
    )
    ax_d.text(
        103,
        0.02,
        "n=100",
        transform=ax_d.get_xaxis_transform(),
        fontsize=5.1,
        color="#444444",
        rotation=90,
        va="bottom",
    )
    ax_d.text(
        0.98,
        0.98,
        "● H1   ▲ E2E",
        transform=ax_d.transAxes,
        fontsize=5.2,
        color="#555555",
        ha="right",
        va="top",
    )
    panel_label(ax_d, "d")

    fig.suptitle(
        "DJR-MCP Finder v0 versus v0.1: remote-component development audit",
        x=0.09,
        y=0.974,
        ha="left",
        fontsize=10,
        fontweight="bold",
    )
    fig.text(
        0.09,
        0.925,
        "Strict ultra-remote inference is blocked (qcov ≥80%, identity <20%: n=1 independent component).",
        ha="left",
        va="top",
        fontsize=7.2,
        color="#8C2D1F",
    )
    fig.text(
        0.09,
        0.018,
        "Train-only cyclic component crossfit; BLAST-derived strata are descriptive and method-conditioned.\nOpen symbols: v0 or v0.1 missed actual 99.5% specificity in ≥1 fold; intervals use fixed calibration thresholds and exclude calibration uncertainty.",
        ha="left",
        va="bottom",
        fontsize=5.3,
        color="#555555",
    )

    base = figures / "ultra_remote_v0_v01"
    fig.savefig(base.with_suffix(".svg"), bbox_inches="tight")
    fig.savefig(base.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(base.with_suffix(".png"), dpi=300, bbox_inches="tight")
    fig.savefig(base.with_suffix(".tiff"), dpi=600, bbox_inches="tight")
    plt.close(fig)

    manifest = {
        "status": "PASS_RENDERED_PENDING_VISUAL_QA",
        "backend": "python_matplotlib",
        "python": sys.version,
        "platform": platform.platform(),
        "matplotlib": mpl.__version__,
        "numpy": np.__version__,
        "core_conclusion": (
            "v0.1 effects can be estimated on component holdouts and a low-coverage "
            "stress layer, but strict ultra-remote inference is blocked at n=1."
        ),
        "source_data": {
            path.name: sha256(path) for path in sorted(source_root.glob("*.tsv"))
        },
        "outputs": {
            path.name: sha256(path)
            for path in sorted(figures.glob("ultra_remote_v0_v01.*"))
        },
        "excluded_rows": 0,
        "selection_notes": (
            "Panels display predeclared method subsets for legibility; complete metrics "
            "remain in results/method_summary.tsv and results/stratum_sensitivity.tsv."
        ),
    }
    (figures / "visualization_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"PASS wrote {base}.svg/.pdf/.png/.tiff")


if __name__ == "__main__":
    main()
