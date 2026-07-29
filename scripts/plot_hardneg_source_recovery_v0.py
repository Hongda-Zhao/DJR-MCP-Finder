#!/usr/bin/env python3
"""Render the fail-closed HardNeg V0 source-recovery summary figure."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


ANALYSIS_ID = "project_v0_hardneg_source_recovery"
TEXT = "#263640"
MUTED = "#647681"
GRID = "#DCE4E8"
NEUTRAL = "#EEF3F5"
BLUE = "#4E7896"
BLUE_LIGHT = "#DDEAF2"
GREEN = "#3F8064"
GREEN_LIGHT = "#E2F0E8"
AMBER = "#A9752C"
AMBER_LIGHT = "#F6EEDC"


mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "font.size": 6.5,
        "axes.titlesize": 7.3,
        "axes.labelsize": 6.5,
        "xtick.labelsize": 5.8,
        "ytick.labelsize": 5.8,
        "axes.linewidth": 0.7,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "text.color": TEXT,
        "axes.labelcolor": TEXT,
        "axes.titlecolor": TEXT,
        "xtick.color": TEXT,
        "ytick.color": TEXT,
    }
)


EXPECTED_FUNNEL = [172346, 42266, 42264, 36138, 10880, 10878, 5000]
EXPECTED_GATES = [f"G{index}" for index in range(7)]
VECTOR_DPI = 300
TIFF_DPI = 600
PREVIEW_DPI = 300


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    project_root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=project_root / "results/hardneg_source_recovery_v0",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "results/figures/project_v0/hardneg_source_recovery_v0",
    )
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.075,
        1.035,
        label,
        transform=ax.transAxes,
        fontsize=8.2,
        fontweight="bold",
        ha="left",
        va="top",
        clip_on=False,
    )


def rounded_box(
    ax: plt.Axes,
    xy: tuple[float, float],
    width: float,
    height: float,
    facecolor: str,
    edgecolor: str = "#AEBBC2",
    linewidth: float = 0.65,
) -> FancyBboxPatch:
    box = FancyBboxPatch(
        xy,
        width,
        height,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=linewidth,
    )
    ax.add_patch(box)
    return box


def validate_inputs(
    funnel: list[dict[str, str]],
    checks: list[dict[str, str]],
    gates: list[dict[str, str]],
) -> None:
    funnel.sort(key=lambda row: int(row["stage_order"]))
    counts = [int(row["count"]) for row in funnel]
    if counts != EXPECTED_FUNNEL:
        raise RuntimeError(f"Unexpected recovery funnel: {counts}")
    checks.sort(key=lambda row: int(row["check_order"]))
    if len(checks) != 4 or any(row["status"] != "PASS" for row in checks):
        raise RuntimeError("Equivalence checks are incomplete or not PASS")
    for row in checks:
        observed = int(row["observed"])
        expected = int(row["expected"])
        if expected <= 0 or observed != expected:
            raise RuntimeError(f"Equivalence mismatch: {row}")
    gates.sort(key=lambda row: int(row["gate_order"]))
    if [row["gate_id"] for row in gates] != EXPECTED_GATES:
        raise RuntimeError("G0–G6 gate set is incomplete")
    if any(row["status"] != "PASS" for row in gates):
        raise RuntimeError("At least one operational gate is not PASS")


def draw_funnel(ax: plt.Axes, funnel: list[dict[str, str]]) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    panel_label(ax, "a")
    ax.set_title("Legacy-compatible V0 recovery chain", loc="left", pad=7)

    rounded_box(ax, (0.04, 0.895), 0.92, 0.075, AMBER_LIGHT, "#D5BA83")
    ax.text(
        0.50,
        0.933,
        "Historical merge: query batches 001–004\nacross all 8 UniProt50 shards",
        ha="center",
        va="center",
        fontsize=5.4,
        color="#76541F",
        fontweight="bold",
        linespacing=1.15,
    )

    y_positions = [0.795, 0.685, 0.575, 0.465, 0.355, 0.245, 0.135]
    box_colors = [NEUTRAL, NEUTRAL, BLUE_LIGHT, BLUE_LIGHT, "#D7E7F0", GREEN_LIGHT, GREEN_LIGHT]
    for index, (row, y, color) in enumerate(zip(funnel, y_positions, box_colors)):
        rounded_box(ax, (0.10, y), 0.80, 0.075, color)
        ax.text(
            0.135,
            y + 0.048,
            row["stage_label"],
            fontsize=5.75,
            fontweight="bold",
            ha="left",
            va="center",
        )
        ax.text(
            0.865,
            y + 0.048,
            f"{int(row['count']):,}",
            fontsize=7.2,
            fontweight="bold",
            ha="right",
            va="center",
            color=BLUE if index < 5 else GREEN,
        )
        ax.text(
            0.135,
            y + 0.021,
            row["note"],
            fontsize=5.0,
            ha="left",
            va="center",
            color=MUTED,
        )
        if index < len(y_positions) - 1:
            ax.annotate(
                "",
                xy=(0.50, y_positions[index + 1] + 0.086),
                xytext=(0.50, y - 0.003),
                arrowprops={"arrowstyle": "-|>", "color": "#8D9BA3", "lw": 0.7},
            )

    ax.text(
        0.50,
        0.052,
        "Batches 005–006 belong to a separate six-batch extension, not this retained V0 output.",
        fontsize=5.0,
        ha="center",
        va="center",
        color=AMBER,
    )


def draw_equivalence(ax: plt.Axes, checks: list[dict[str, str]]) -> None:
    panel_label(ax, "b")
    ax.set_title("Recovered identity and coverage", loc="left", pad=5)
    y_positions = list(range(len(checks)))[::-1]
    labels = [row["check_label"] for row in checks]
    fractions = [100.0 * int(row["observed"]) / int(row["expected"]) for row in checks]
    ax.barh(y_positions, [100] * len(checks), color="#EDF1F3", height=0.58, zorder=1)
    ax.barh(y_positions, fractions, color=BLUE, height=0.58, zorder=2)
    ax.scatter([100] * len(checks), y_positions, s=22, color=GREEN, zorder=3)
    for y, row in zip(y_positions, checks):
        ax.text(
            102.2,
            y,
            f"{int(row['observed']):,}/{int(row['expected']):,}",
            fontsize=5.4,
            fontweight="bold",
            color=GREEN,
            va="center",
            ha="left",
        )
    ax.set_yticks(y_positions, labels)
    ax.set_xlim(0, 116)
    ax.set_xticks([0, 50, 100])
    ax.set_xlabel("Recovered / expected (%)")
    ax.grid(axis="x", color=GRID, lw=0.55, zorder=0)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.text(
        0.0,
        -0.27,
        "All comparisons are deterministic identity checks; no sampling or confidence interval.",
        transform=ax.transAxes,
        fontsize=5.0,
        color=MUTED,
        ha="left",
        va="top",
    )


def draw_gates(ax: plt.Axes, gates: list[dict[str, str]]) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    panel_label(ax, "c")
    ax.set_title("Fail-closed operational validation", loc="left", pad=5)
    positions = [
        (0.01, 0.63),
        (0.26, 0.63),
        (0.51, 0.63),
        (0.76, 0.63),
        (0.135, 0.33),
        (0.385, 0.33),
        (0.635, 0.33),
    ]
    for row, (x, y) in zip(gates, positions):
        rounded_box(ax, (x, y), 0.22, 0.20, GREEN_LIGHT, "#8FB8A5")
        ax.text(
            x + 0.11,
            y + 0.145,
            row["gate_id"],
            fontsize=7.0,
            fontweight="bold",
            color=GREEN,
            ha="center",
            va="center",
        )
        ax.text(
            x + 0.11,
            y + 0.092,
            row["gate_label"].replace(" ", "\n", 1),
            fontsize=5.0,
            ha="center",
            va="center",
            linespacing=1.1,
        )
        ax.text(
            x + 0.11,
            y + 0.030,
            "PASS",
            fontsize=5.0,
            fontweight="bold",
            color=GREEN,
            ha="center",
            va="center",
        )

    rounded_box(ax, (0.02, 0.035), 0.96, 0.18, AMBER_LIGHT, "#D5BA83")
    ax.text(
        0.05,
        0.145,
        "Interpretation boundary",
        fontsize=5.5,
        fontweight="bold",
        color="#76541F",
        ha="left",
        va="center",
    )
    ax.text(
        0.05,
        0.088,
        "The lost historical member TSV is not claimed byte-identical. The reconstructed\n"
        "36,138-member map is independently repeatable (A/B canonical equality).",
        fontsize=5.0,
        color="#76541F",
        ha="left",
        va="center",
        linespacing=1.25,
    )


def render(data_dir: Path, output_dir: Path) -> dict[str, object]:
    funnel_path = data_dir / "recovery_funnel.tsv"
    checks_path = data_dir / "equivalence_checks.tsv"
    gates_path = data_dir / "gate_status.tsv"
    funnel = read_tsv(funnel_path)
    checks = read_tsv(checks_path)
    gates = read_tsv(gates_path)
    validate_inputs(funnel, checks, gates)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Explicit literals: 7.2047 in = 183 mm; 4.7244 in = 120 mm.
    fig = plt.figure(figsize=(7.2047, 4.7244), constrained_layout=False)
    grid = fig.add_gridspec(
        2,
        2,
        width_ratios=[1.02, 1.28],
        height_ratios=[0.82, 1.18],
        left=0.055,
        right=0.985,
        bottom=0.105,
        top=0.875,
        wspace=0.30,
        hspace=0.36,
    )
    ax_a = fig.add_subplot(grid[:, 0])
    ax_b = fig.add_subplot(grid[0, 1])
    ax_c = fig.add_subplot(grid[1, 1])

    fig.text(
        0.055,
        0.965,
        "Operational recovery of the historical HardNeg V0 output",
        fontsize=10.2,
        fontweight="bold",
        ha="left",
        va="top",
        color=TEXT,
    )
    fig.text(
        0.055,
        0.925,
        "Exact retained representatives, exclusion buckets and selected sequences; reproducible member mapping",
        fontsize=6.2,
        ha="left",
        va="top",
        color=MUTED,
    )
    draw_funnel(ax_a, funnel)
    draw_equivalence(ax_b, checks)
    draw_gates(ax_c, gates)
    fig.text(
        0.055,
        0.026,
        "Source: checksum-bound reconstruction outputs. FULL_OPERATIONAL_RECOVERY_PASS; G0–G6 all PASS.",
        fontsize=5.0,
        color=MUTED,
        ha="left",
        va="bottom",
    )

    stem = "hardneg_source_recovery_v0"
    output_names = {
        "svg": "hardneg_source_recovery_v0.svg",
        "pdf": "hardneg_source_recovery_v0.pdf",
        "tiff": "hardneg_source_recovery_v0.tiff",
        "png": "hardneg_source_recovery_v0.png",
    }
    outputs: list[Path] = []
    export_specs = (
        ("svg", VECTOR_DPI),
        ("pdf", VECTOR_DPI),
        ("tiff", TIFF_DPI),
        ("png", PREVIEW_DPI),
    )
    for extension, dpi in export_specs:
        destination = output_dir / output_names[extension]
        temporary = output_dir / f".{stem}.{os.getpid()}.tmp.{extension}"
        options: dict[str, object] = {"format": extension, "dpi": dpi, "facecolor": "white"}
        if extension == "tiff":
            options["pil_kwargs"] = {"compression": "tiff_lzw"}
        fig.savefig(temporary, **options)
        os.replace(temporary, destination)
        outputs.append(destination)
    plt.close(fig)

    manifest_rows = [
        {
            "item": path.stem,
            "path": path.name,
            "sha256": sha256(path),
        }
        for path in outputs
    ]
    manifest_rows.extend(
        {
            "item": path.stem,
            "path": str(path.relative_to(data_dir.parent.parent)),
            "sha256": sha256(path),
        }
        for path in (funnel_path, checks_path, gates_path)
    )
    manifest_lines = ["item\tpath\tsha256"]
    manifest_lines.extend(
        f"{row['item']}\t{row['path']}\t{row['sha256']}" for row in manifest_rows
    )
    atomic_text(output_dir / "figure_manifest.tsv", "\n".join(manifest_lines) + "\n")
    checksum_lines = [f"{sha256(path)}  {path.name}" for path in outputs]
    checksum_lines.append(
        f"{sha256(output_dir / 'figure_manifest.tsv')}  figure_manifest.tsv"
    )
    atomic_text(output_dir / "figure_checksums.sha256", "\n".join(checksum_lines) + "\n")
    summary = {
        "analysis_id": ANALYSIS_ID,
        "status": "PASS",
        "backend": "python_matplotlib",
        "final_size_mm": [183, 120],
        "funnel_counts": EXPECTED_FUNNEL,
        "equivalence_checks_passed": len(checks),
        "operational_gates_passed": len(gates),
        "historical_member_table_byte_identity_claimed": False,
    }
    atomic_text(
        output_dir / "render_summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    return summary


def main() -> None:
    args = parse_args()
    summary = render(args.data_dir.resolve(), args.output_dir.resolve())
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
