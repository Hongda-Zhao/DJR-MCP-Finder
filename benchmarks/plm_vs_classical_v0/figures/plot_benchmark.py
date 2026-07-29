#!/usr/bin/env python3
"""Render the validated PLM-versus-classical benchmark figures.

The script is fail-closed: it requires PASS validation/summary artifacts and
the exact frozen method/task/comparison row sets before drawing anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

# Keep the matplotlib cache in a task-specific writable temporary directory.
_MPL_CACHE = Path(tempfile.gettempdir()) / "djrmcp_benchmark_matplotlib_cache"
_MPL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPL_CACHE))
_XDG_CACHE = Path(tempfile.gettempdir()) / "djrmcp_benchmark_xdg_cache"
_XDG_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(_XDG_CACHE))

import matplotlib

matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Rectangle

# Mandatory editable-text and publication export settings.
mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "DejaVu Sans", "Liberation Sans"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "font.size": 7,
        "axes.linewidth": 0.75,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "xtick.major.width": 0.7,
        "ytick.major.width": 0.7,
        "axes.unicode_minus": False,
    }
)

EXPORT_DPI = 600


TASK_ORDER = ["h1_djr", "h2_vma_conditional", "vma_end_to_end"]
TASK_LABEL = {
    "h1_djr": "H1 DJR",
    "h2_vma_conditional": "H2 VMA | DJR",
    "vma_end_to_end": "VMA end-to-end",
}
TASK_SHORT = {
    "h1_djr": "H1",
    "h2_vma_conditional": "H2",
    "vma_end_to_end": "End-to-end",
}
TASK_COLOR = {
    "h1_djr": "#484878",
    "h2_vma_conditional": "#7884B4",
    "vma_end_to_end": "#42949E",
}
TASK_MARKER = {
    "h1_djr": "o",
    "h2_vma_conditional": "s",
    "vma_end_to_end": "D",
}

METHOD_ORDER = [
    "esmc6b_cosine",
    "esm2_650m_cosine",
    "blastp",
    "diamond_ultra",
    "mmseqs_s7.5",
    "hmmer_component",
    "psiblast_longest_seed_positiveDB_3iter",
    "hmmer_family",
    "esmc6b_supervised",
]
CONTROLLED_METHODS = METHOD_ORDER[:6]
CLASSICAL_ORDER = ["blastp", "diamond_ultra", "mmseqs_s7.5", "hmmer_component"]
METHOD_LABEL = {
    "esmc6b_cosine": "ESM-C 6B cosine",
    "esm2_650m_cosine": "ESM2 650M cosine",
    "blastp": "BLASTP",
    "diamond_ultra": "DIAMOND ultra",
    "mmseqs_s7.5": "MMseqs2",
    "hmmer_component": "HMMER component",
    "psiblast_longest_seed_positiveDB_3iter": "PSI-BLAST 3 iter†",
    "hmmer_family": "HMMER family‡",
    "esmc6b_supervised": "ESM-C supervised§",
}
COMPARATOR_LABEL = {
    "blastp": "BLASTP",
    "diamond_ultra": "DIAMOND",
    "mmseqs_s7.5": "MMseqs2",
    "hmmer_component": "HMMER",
}

TRACK_COLOR = {
    "controlled_primary": "#484878",
    "resource_augmented_secondary": "#D2A642",
    "metadata_augmented_secondary": "#9A4D8E",
    "operational_descriptive": "#8F8F8F",
}
DELTA_NEGATIVE = "#B64342"
DELTA_POSITIVE = "#2E8B57"
DELTA_NULL = "#7884B4"
NEUTRAL = "#5E5E5E"
GRID = "#D9D9DF"

SCORE_CMAP = LinearSegmentedColormap.from_list(
    "benchmark_score", ["#F6F6F8", "#D7DDEE", "#8C9BC8", "#484878"]
)
NO_HIT_CMAP = LinearSegmentedColormap.from_list(
    "no_hit", ["#F7F7F7", "#F0D5CF", "#C4584B"]
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_validated_data(benchmark_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    results = benchmark_root / "results"
    validation_path = results / "validation.json"
    summary_path = results / "summary.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    require(validation.get("status") == "PASS", "validation.json is not PASS")
    require(summary.get("status") == "PASS", "summary.json is not PASS")
    require(validation.get("validation_prediction_rows") == 0, "Validation predictions are non-zero")
    require(validation.get("test_prediction_rows") == 0, "Test predictions are non-zero")

    metrics = pd.read_csv(results / "metrics_primary.tsv", sep="\t")
    paired = pd.read_csv(results / "paired_deltas.tsv", sep="\t")
    distance = pd.read_csv(results / "distance_strata.tsv", sep="\t")
    require(len(metrics) == 27, f"Expected 27 metric rows, observed {len(metrics)}")
    require(len(paired) == 12, f"Expected 12 paired rows, observed {len(paired)}")
    require(set(metrics["task"]) == set(TASK_ORDER), "Primary task set changed")
    require(set(metrics["method"]) == set(METHOD_ORDER), "Primary method set changed")
    expected_metric_keys = {(task, method) for task in TASK_ORDER for method in METHOD_ORDER}
    observed_metric_keys = set(zip(metrics["task"], metrics["method"]))
    require(observed_metric_keys == expected_metric_keys, "Primary metric key set changed")
    expected_paired_keys = {(task, method) for task in TASK_ORDER for method in CLASSICAL_ORDER}
    observed_paired_keys = set(zip(paired["task"], paired["comparator_method"]))
    require(observed_paired_keys == expected_paired_keys, "Paired comparison key set changed")
    require(set(paired["anchor_method"]) == {"esmc6b_cosine"}, "Paired anchor changed")
    require(set(paired["bootstrap_replicates"].astype(int)) == {10_000}, "Bootstrap count changed")
    require(
        not any("p_value" in value.lower() or "holm" in value.lower() for value in paired.columns),
        "Forbidden P/Holm column entered paired results",
    )

    for _, row in paired.iterrows():
        require(
            row["bootstrap_ap_delta_ci95_low"]
            <= row["point_delta_fold_macro_component_ap"]
            <= row["bootstrap_ap_delta_ci95_high"],
            "AP point estimate is outside its displayed interval",
        )
        require(
            row["bootstrap_delta_ci95_low"]
            <= row["point_delta_component_sensitivity"]
            <= row["bootstrap_delta_ci95_high"],
            "Sensitivity point estimate is outside its displayed interval",
        )

    low_coverage = distance[
        (distance["distance_stratum"] == "best_local_qcov_lt80")
        & distance["method"].isin(CONTROLLED_METHODS)
    ].copy()
    expected_low_keys = {(task, method) for task in TASK_ORDER for method in CONTROLLED_METHODS}
    observed_low_keys = set(zip(low_coverage["task"], low_coverage["method"]))
    require(observed_low_keys == expected_low_keys, "Low-coverage stratum key set changed")

    source_hashes = {
        "validation.json": sha256_file(validation_path),
        "summary.json": sha256_file(summary_path),
        "metrics_primary.tsv": sha256_file(results / "metrics_primary.tsv"),
        "paired_deltas.tsv": sha256_file(results / "paired_deltas.tsv"),
        "distance_strata.tsv": sha256_file(results / "distance_strata.tsv"),
    }
    return metrics, paired, low_coverage, {
        "validation": validation,
        "summary": summary,
        "source_sha256": source_hashes,
    }


def add_panel_label(ax: mpl.axes.Axes, label: str, x: float = -0.13, y: float = 1.08) -> None:
    ax.text(
        x,
        y,
        label,
        transform=ax.transAxes,
        fontsize=9,
        fontweight="bold",
        ha="left",
        va="bottom",
        clip_on=False,
    )


def text_color_for_rgba(rgba: tuple[float, float, float, float]) -> str:
    r, g, b, _ = rgba
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "white" if luminance < 0.56 else "#202020"


def metric_matrix(metrics: pd.DataFrame, value_column: str) -> np.ndarray:
    lookup = metrics.set_index(["method", "task"])[value_column]
    return np.asarray(
        [[float(lookup.loc[(method, task)]) for task in TASK_ORDER] for method in METHOD_ORDER]
    )


def draw_metric_heatmap(
    fig: mpl.figure.Figure,
    ax: mpl.axes.Axes,
    metrics: pd.DataFrame,
    value_column: str,
    title: str,
    panel: str,
    vmin: float,
    show_ylabels: bool,
) -> None:
    matrix = metric_matrix(metrics, value_column)
    norm = Normalize(vmin=vmin, vmax=1.0, clip=True)
    image = ax.imshow(matrix, cmap=SCORE_CMAP, norm=norm, aspect="auto", interpolation="nearest")
    ax.set_xticks(range(len(TASK_ORDER)))
    ax.set_xticklabels([TASK_LABEL[value] for value in TASK_ORDER], rotation=28, ha="left")
    for label, alignment in zip(ax.get_xticklabels(), ("left", "center", "right")):
        label.set_ha(alignment)
        label.set_rotation_mode("anchor")
    ax.tick_params(axis="x", top=True, labeltop=True, bottom=False, labelbottom=False, length=0, pad=2)
    ax.set_yticks(range(len(METHOD_ORDER)))
    if show_ylabels:
        ax.set_yticklabels([METHOD_LABEL[value] for value in METHOD_ORDER], fontsize=6.3)
    else:
        ax.set_yticklabels([])
    ax.tick_params(axis="y", length=0, pad=3)
    ax.set_title(title, fontsize=7.4, fontweight="bold", pad=30)

    for row_index in range(matrix.shape[0]):
        for column_index in range(matrix.shape[1]):
            value = matrix[row_index, column_index]
            color = text_color_for_rgba(SCORE_CMAP(norm(value)))
            ax.text(
                column_index,
                row_index,
                f"{value:.3f}",
                ha="center",
                va="center",
                fontsize=5.8,
                color=color,
                fontweight="bold" if row_index < 6 else "normal",
            )

    for boundary in (1.5, 5.5, 7.5):
        ax.axhline(boundary, color="white", lw=1.6)
        ax.axhline(boundary, color="#B8B8C0", lw=0.45)

    if show_ylabels:
        track_lookup = metrics.drop_duplicates("method").set_index("method")["track"].to_dict()
        for row_index, method in enumerate(METHOD_ORDER):
            track = track_lookup[method]
            ax.add_patch(
                Rectangle(
                    (-0.68, row_index - 0.44),
                    0.07,
                    0.88,
                    facecolor=TRACK_COLOR[track],
                    edgecolor="none",
                    clip_on=False,
                )
            )

    for spine in ax.spines.values():
        spine.set_visible(False)
    colorbar = fig.colorbar(image, ax=ax, orientation="horizontal", fraction=0.045, pad=0.08, aspect=24)
    colorbar.ax.tick_params(labelsize=5.5, length=2, pad=1)
    colorbar.set_ticks([vmin, (vmin + 1.0) / 2.0, 1.0])
    colorbar.outline.set_linewidth(0.5)
    add_panel_label(ax, panel, x=-0.18 if show_ylabels else -0.08, y=1.13)


def forest_positions() -> tuple[list[float], dict[str, float], list[str]]:
    positions: list[float] = []
    group_labels: dict[str, float] = {}
    comparator_labels: list[str] = []
    current = 12.0
    for task in TASK_ORDER:
        group_labels[task] = current + 0.55
        for comparator in CLASSICAL_ORDER:
            positions.append(current)
            comparator_labels.append(COMPARATOR_LABEL[comparator])
            current -= 1.0
        current -= 0.8
    return positions, group_labels, comparator_labels


def draw_delta_forest(
    ax: mpl.axes.Axes,
    paired: pd.DataFrame,
    point_column: str,
    low_column: str,
    high_column: str,
    xlabel: str,
    panel: str,
    xlim: tuple[float, float],
) -> None:
    positions, group_labels, comparator_labels = forest_positions()
    ordered_rows = []
    for task in TASK_ORDER:
        for comparator in CLASSICAL_ORDER:
            subset = paired[
                (paired["task"] == task) & (paired["comparator_method"] == comparator)
            ]
            require(len(subset) == 1, "Forest row is not unique")
            ordered_rows.append(subset.iloc[0])

    for task_index, task in enumerate(TASK_ORDER):
        top = 12.45 - task_index * 4.8
        bottom = 8.55 - task_index * 4.8
        facecolor = "#F5F5F8" if task_index % 2 == 0 else "#FAFAFB"
        ax.axhspan(bottom, top, color=facecolor, zorder=0)

    for y, row in zip(positions, ordered_rows):
        point = float(row[point_column])
        low = float(row[low_column])
        high = float(row[high_column])
        if high < 0:
            color = DELTA_NEGATIVE
        elif low > 0:
            color = DELTA_POSITIVE
        else:
            color = DELTA_NULL
        conditional = row["task"] != "h1_djr"
        ax.plot([low, high], [y, y], color=color, lw=1.35, solid_capstyle="round", zorder=2)
        ax.scatter(
            [point],
            [y],
            s=23,
            marker="o",
            facecolor="white" if conditional else color,
            edgecolor=color,
            linewidth=1.1,
            zorder=3,
        )

    ax.axvline(0.0, color="#6F6F75", lw=0.9, ls="--", zorder=1)
    ax.set_xlim(*xlim)
    ax.set_ylim(-2.65, 13.1)
    ax.set_yticks(positions)
    ax.set_yticklabels(comparator_labels, fontsize=6.1)
    ax.tick_params(axis="y", length=0, pad=3)
    ax.tick_params(axis="x", labelsize=6)
    ax.xaxis.grid(True, color=GRID, lw=0.5, zorder=0)
    ax.set_xlabel(xlabel, fontsize=6.5, labelpad=4)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color("#7A7A7A")
    for task, y in group_labels.items():
        ax.text(
            xlim[0] + 0.01 * (xlim[1] - xlim[0]),
            y,
            TASK_LABEL[task],
            fontsize=6.4,
            fontweight="bold",
            color="#34343A",
            ha="left",
            va="center",
        )
    ax.text(
        0.98,
        0.99,
        "Open points: conditional H2/end-to-end intervals",
        transform=ax.transAxes,
        fontsize=5.2,
        color=NEUTRAL,
        ha="right",
        va="top",
    )
    add_panel_label(ax, panel, x=-0.20, y=1.02)


def draw_specificity(ax: mpl.axes.Axes, metrics: pd.DataFrame) -> None:
    controlled = metrics[metrics["method"].isin(CONTROLLED_METHODS)].copy()
    x = np.arange(len(CONTROLLED_METHODS), dtype=float)
    offsets = [-0.18, 0.0, 0.18]
    for offset, task in zip(offsets, TASK_ORDER):
        subset = controlled[controlled["task"] == task].set_index("method")
        values = np.asarray(
            [subset.loc[method, "fold_macro_observed_source_balanced_specificity"] for method in CONTROLLED_METHODS],
            dtype=float,
        )
        ax.scatter(
            x + offset,
            values,
            s=28,
            marker=TASK_MARKER[task],
            color=TASK_COLOR[task],
            edgecolor="white",
            linewidth=0.45,
            label=TASK_LABEL[task],
            zorder=3,
        )

    ax.axhline(0.995, color="#6F6F75", lw=0.9, ls="--", zorder=1)
    ax.text(
        len(CONTROLLED_METHODS) - 0.48,
        0.9956,
        "99.5% calibration target",
        fontsize=5.5,
        color="#5A5A60",
        ha="right",
        va="bottom",
    )
    esm2_h2 = controlled[
        (controlled["method"] == "esm2_650m_cosine")
        & (controlled["task"] == "h2_vma_conditional")
    ].iloc[0]
    ax.annotate(
        f"{float(esm2_h2['fold_macro_observed_source_balanced_specificity']) * 100:.1f}%",
        xy=(1.0, float(esm2_h2["fold_macro_observed_source_balanced_specificity"])),
        xytext=(1.35, 0.945),
        fontsize=5.7,
        color=TASK_COLOR["h2_vma_conditional"],
        arrowprops={"arrowstyle": "-", "lw": 0.7, "color": TASK_COLOR["h2_vma_conditional"]},
        ha="left",
        va="center",
    )
    ax.set_xlim(-0.6, len(CONTROLLED_METHODS) - 0.4)
    ax.set_ylim(0.92, 1.002)
    ax.set_yticks([0.92, 0.94, 0.96, 0.98, 1.00])
    ax.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(xmax=1.0, decimals=0))
    ax.set_xticks(x)
    ax.set_xticklabels([METHOD_LABEL[value] for value in CONTROLLED_METHODS], rotation=18, ha="right", fontsize=6)
    ax.set_ylabel("Observed evaluation specificity", fontsize=6.5)
    ax.yaxis.grid(True, color=GRID, lw=0.5, zorder=0)
    ax.legend(
        ncol=3,
        loc="lower left",
        bbox_to_anchor=(0.0, 1.01),
        fontsize=5.7,
        handletextpad=0.35,
        columnspacing=1.2,
    )
    add_panel_label(ax, "e", x=-0.08, y=1.13)


def save_figure(fig: mpl.figure.Figure, base: Path, dpi: int) -> list[Path]:
    base.parent.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for extension in ("svg", "pdf"):
        path = base.with_suffix(f".{extension}")
        fig.savefig(path)
        outputs.append(path)
    png = base.with_suffix(".png")
    fig.savefig(png, dpi=dpi, facecolor="white")
    outputs.append(png)
    tiff = base.with_suffix(".tiff")
    fig.savefig(
        tiff,
        dpi=dpi,
        facecolor="white",
        pil_kwargs={"compression": "tiff_lzw"},
    )
    outputs.append(tiff)
    plt.close(fig)
    return outputs


def render_main(metrics: pd.DataFrame, paired: pd.DataFrame, output_dir: Path, dpi: int) -> list[Path]:
    fig = plt.figure(figsize=(7.2, 8.45), facecolor="white")
    grid = fig.add_gridspec(
        3,
        2,
        height_ratios=[1.05, 1.55, 0.74],
        left=0.235,
        right=0.985,
        top=0.89,
        bottom=0.155,
        wspace=0.34,
        hspace=0.55,
    )
    ax_a = fig.add_subplot(grid[0, 0])
    ax_b = fig.add_subplot(grid[0, 1])
    ax_c = fig.add_subplot(grid[1, 0])
    ax_d = fig.add_subplot(grid[1, 1])
    ax_e = fig.add_subplot(grid[2, :])

    draw_metric_heatmap(
        fig,
        ax_a,
        metrics,
        "fold_macro_component_ap",
        "Component-balanced AP",
        "a",
        0.85,
        True,
    )
    draw_metric_heatmap(
        fig,
        ax_b,
        metrics,
        "fold_macro_component_sensitivity_at_primary_specificity",
        "Calibration-targeted sensitivity",
        "b",
        0.70,
        False,
    )
    draw_delta_forest(
        ax_c,
        paired,
        "point_delta_fold_macro_component_ap",
        "bootstrap_ap_delta_ci95_low",
        "bootstrap_ap_delta_ci95_high",
        "Δ component-balanced AP\n(ESM-C 6B − classical anchor)",
        "c",
        (-0.125, 0.07),
    )
    draw_delta_forest(
        ax_d,
        paired,
        "point_delta_component_sensitivity",
        "bootstrap_delta_ci95_low",
        "bootstrap_delta_ci95_high",
        "Δ calibration-targeted sensitivity\n(ESM-C 6B − classical anchor)",
        "d",
        (-0.24, 0.09),
    )
    draw_specificity(ax_e, metrics)

    fig.text(
        0.235,
        0.035,
        "Thresholds target 99.5% specificity on disjoint calibration folds; evaluation specificity is measured in e.\n"
        "Internal Train-only 3/1/1 component cross-fitting; H2/end-to-end intervals are conditional and resolution-limited.",
        fontsize=5.5,
        color="#4F4F55",
        ha="left",
        va="bottom",
        linespacing=1.35,
    )
    return save_figure(fig, output_dir / "benchmark_summary", dpi)


def draw_low_coverage(ax: mpl.axes.Axes, low_coverage: pd.DataFrame) -> None:
    y = np.arange(len(CONTROLLED_METHODS))[::-1].astype(float)
    offsets = [0.20, 0.0, -0.20]
    lookup = low_coverage.set_index(["method", "task"])
    metric = "component_balanced_sensitivity_at_99.5pct_specificity"
    for offset, task in zip(offsets, TASK_ORDER):
        values = np.asarray([lookup.loc[(method, task), metric] for method in CONTROLLED_METHODS])
        ax.scatter(
            values,
            y + offset,
            s=28,
            marker=TASK_MARKER[task],
            color=TASK_COLOR[task],
            edgecolor="white",
            linewidth=0.45,
            label=TASK_LABEL[task],
            zorder=3,
        )
    ax.set_yticks(y)
    ax.set_yticklabels([METHOD_LABEL[value] for value in CONTROLLED_METHODS], fontsize=6.3)
    ax.tick_params(axis="y", length=0, pad=3)
    ax.set_xlim(0.60, 1.012)
    ax.set_xticks([0.6, 0.7, 0.8, 0.9, 1.0])
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(xmax=1.0, decimals=0))
    ax.set_xlabel("Sensitivity in BLAST qcov <80% stratum", fontsize=6.5)
    ax.xaxis.grid(True, color=GRID, lw=0.5, zorder=0)
    ax.spines["left"].set_visible(False)
    ax.legend(
        ncol=3,
        loc="lower left",
        bbox_to_anchor=(0.0, 1.01),
        fontsize=5.6,
        handletextpad=0.35,
        columnspacing=0.8,
    )
    add_panel_label(ax, "a", x=-0.24, y=1.10)


def draw_no_hit_heatmap(fig: mpl.figure.Figure, ax: mpl.axes.Axes, metrics: pd.DataFrame) -> None:
    controlled = metrics[metrics["method"].isin(CONTROLLED_METHODS)].copy()
    controlled["no_hit_fraction"] = controlled["no_hit_evaluation_records"] / controlled["records"]
    lookup = controlled.set_index(["method", "task"])["no_hit_fraction"]
    matrix = np.asarray(
        [[lookup.loc[(method, task)] for task in TASK_ORDER] for method in CONTROLLED_METHODS],
        dtype=float,
    )
    norm = Normalize(vmin=0.0, vmax=0.85, clip=True)
    image = ax.imshow(matrix, cmap=NO_HIT_CMAP, norm=norm, aspect="auto", interpolation="nearest")
    ax.set_xticks(range(len(TASK_ORDER)))
    ax.set_xticklabels([TASK_SHORT[value] for value in TASK_ORDER], rotation=25, ha="left")
    for label, alignment in zip(ax.get_xticklabels(), ("left", "center", "right")):
        label.set_ha(alignment)
        label.set_rotation_mode("anchor")
    ax.tick_params(axis="x", top=True, labeltop=True, bottom=False, labelbottom=False, length=0, pad=2)
    ax.set_yticks(range(len(CONTROLLED_METHODS)))
    ax.set_yticklabels([])
    ax.tick_params(axis="y", length=0)
    for row_index in range(matrix.shape[0]):
        for column_index in range(matrix.shape[1]):
            value = matrix[row_index, column_index]
            color = text_color_for_rgba(NO_HIT_CMAP(norm(value)))
            ax.text(
                column_index,
                row_index,
                f"{value * 100:.1f}%",
                ha="center",
                va="center",
                fontsize=5.8,
                color=color,
                fontweight="bold" if value >= 0.1 else "normal",
            )
    for spine in ax.spines.values():
        spine.set_visible(False)
    colorbar = fig.colorbar(image, ax=ax, orientation="horizontal", fraction=0.055, pad=0.12, aspect=20)
    colorbar.ax.tick_params(labelsize=5.4, length=2, pad=1)
    colorbar.set_ticks([0.0, 0.4, 0.8])
    colorbar.ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(xmax=1.0, decimals=0))
    colorbar.outline.set_linewidth(0.5)
    ax.set_title("No-hit fraction", fontsize=7.2, fontweight="bold", pad=24)
    add_panel_label(ax, "b", x=-0.10, y=1.12)


def render_remote_homology(
    metrics: pd.DataFrame, low_coverage: pd.DataFrame, output_dir: Path, dpi: int
) -> list[Path]:
    fig = plt.figure(figsize=(7.2, 3.4), facecolor="white")
    grid = fig.add_gridspec(
        1,
        2,
        width_ratios=[1.55, 1.0],
        left=0.22,
        right=0.985,
        top=0.84,
        bottom=0.24,
        wspace=0.35,
    )
    ax_a = fig.add_subplot(grid[0, 0])
    ax_b = fig.add_subplot(grid[0, 1])
    draw_low_coverage(ax_a, low_coverage)
    draw_no_hit_heatmap(fig, ax_b, metrics)
    fig.text(
        0.22,
        0.055,
        "Descriptive only: BLAST local query coverage is not a global evolutionary-distance estimate, and methods are not\n"
        "matched to a common realized evaluation specificity. qcov<80% contains 264 H1 and 100 H2/end positive components.",
        fontsize=5.5,
        color="#4F4F55",
        ha="left",
        va="bottom",
        linespacing=1.35,
    )
    return save_figure(fig, output_dir / "benchmark_remote_homology", dpi)


def write_source_data(
    output_dir: Path,
    metrics: pd.DataFrame,
    paired: pd.DataFrame,
    low_coverage: pd.DataFrame,
) -> list[Path]:
    source_dir = output_dir / "source_data"
    source_dir.mkdir(parents=True, exist_ok=True)
    metric_columns = [
        "task",
        "method",
        "track",
        "primary_eligible",
        "records",
        "positive_records",
        "positive_components",
        "fold_macro_component_ap",
        "fold_component_ap_min",
        "fold_component_ap_max",
        "fold_macro_component_sensitivity_at_primary_specificity",
        "fold_component_sensitivity_min",
        "fold_component_sensitivity_max",
        "fold_macro_observed_source_balanced_specificity",
        "primary_sensitivity_inference_status",
        "no_hit_evaluation_records",
    ]
    delta_columns = [
        "task",
        "anchor_method",
        "comparator_method",
        "point_delta_fold_macro_component_ap",
        "bootstrap_ap_delta_ci95_low",
        "bootstrap_ap_delta_ci95_high",
        "point_delta_component_sensitivity",
        "bootstrap_delta_ci95_low",
        "bootstrap_delta_ci95_high",
        "bootstrap_replicates",
        "ap_inference_status",
        "sensitivity_inference_status",
        "sensitivity_resolution_note",
    ]
    low_columns = [
        "task",
        "method",
        "track",
        "distance_stratum",
        "positive_records",
        "positive_components",
        "component_balanced_sensitivity_at_99.5pct_specificity",
        "inference_status",
        "stratum_caveat",
    ]
    outputs = [
        source_dir / "benchmark_summary_metrics.tsv",
        source_dir / "benchmark_summary_paired_deltas.tsv",
        source_dir / "benchmark_low_coverage_stratum.tsv",
    ]
    metrics[metric_columns].sort_values(["task", "method"]).to_csv(outputs[0], sep="\t", index=False)
    paired[delta_columns].sort_values(["task", "comparator_method"]).to_csv(
        outputs[1], sep="\t", index=False
    )
    low_coverage[low_columns].sort_values(["task", "method"]).to_csv(
        outputs[2], sep="\t", index=False
    )
    return outputs


def publish_visualization_manifest(
    output_dir: Path,
    metadata: dict,
    generated_paths: list[Path],
) -> None:
    validation = metadata["validation"]
    artifact_sha = {
        str(path.relative_to(output_dir)): sha256_file(path)
        for path in sorted(generated_paths)
        if path.is_file()
    }
    manifest = {
        "status": "PASS",
        "benchmark_id": validation["benchmark_id"],
        "design_id": validation["design_id"],
        "claim_boundary": validation["claim_boundary"],
        "backend": "python_matplotlib",
        "source_sha256": metadata["source_sha256"],
        "source_contract": {
            "primary_metric_rows": 27,
            "paired_comparison_rows": 12,
            "bootstrap_replicates": 10_000,
            "validation_prediction_rows": 0,
            "test_prediction_rows": 0,
        },
        "artifact_sha256": artifact_sha,
    }
    manifest_path = output_dir / "visualization_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    checksum_candidates = sorted(
        path
        for path in output_dir.rglob("*")
        if path.is_file()
        and path.name != "CHECKSUMS.sha256"
        and path.suffix.lower() in {".py", ".md", ".tsv", ".json", ".svg", ".pdf", ".png", ".tiff"}
    )
    checksum_lines = [
        f"{sha256_file(path)}  {path.relative_to(output_dir)}" for path in checksum_candidates
    ]
    (output_dir / "CHECKSUMS.sha256").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    default_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-root", type=Path, default=default_root)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--dpi", type=int, default=EXPORT_DPI)
    args = parser.parse_args()

    benchmark_root = args.benchmark_root.resolve()
    output_dir = (args.output_dir or (benchmark_root / "figures")).resolve()
    require(args.dpi >= 300, "Publication raster exports require dpi >= 300")
    metrics, paired, low_coverage, metadata = load_validated_data(benchmark_root)
    source_paths = write_source_data(output_dir, metrics, paired, low_coverage)
    main_paths = render_main(metrics, paired, output_dir, args.dpi)
    remote_paths = render_remote_homology(metrics, low_coverage, output_dir, args.dpi)
    generated = [*source_paths, *main_paths, *remote_paths]
    publish_visualization_manifest(output_dir, metadata, generated)
    print(
        f"PASS rendered {len(main_paths) + len(remote_paths)} figure files, "
        f"{len(source_paths)} source-data tables"
    )


if __name__ == "__main__":
    main()
