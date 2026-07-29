#!/usr/bin/env python3
"""Render a checksum-bound head-focused companion to schema-5 panels b/c.

The figure is explanatory and downstream-only.  It reads the completed compact
Amendment-D result plus the frozen metric-revision-1 comparison, verifies both
checksum manifests, and never opens embeddings, predictions, Train/Test rows,
or model objects.  It cannot refit, recalibrate, change thresholds, or rerank
with robustness evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


# Plotting imports are lazy: checksum/contract tests work without matplotlib.
mpl: Any = None
plt: Any = None
np: Any = None


def _load_matplotlib() -> None:
    global mpl, plt, np
    if mpl is not None:
        return
    import matplotlib as matplotlib_module

    matplotlib_module.use("Agg")
    import matplotlib.pyplot as pyplot_module
    import numpy as numpy_module

    mpl, plt, np = matplotlib_module, pyplot_module, numpy_module
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "DejaVu Sans", "Liberation Sans"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 6.5,
            "axes.titlesize": 7.2,
            "axes.titleweight": "bold",
            "axes.labelsize": 6.5,
            "axes.linewidth": 0.65,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.labelsize": 6.0,
            "ytick.labelsize": 6.0,
            "legend.fontsize": 6.0,
            "legend.frameon": False,
            "lines.linewidth": 0.9,
        }
    )


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ID = "project_v0_validation_family_robustness_schema5_head_focus"
FIGURE_BASENAME = "validation_family_robustness_v0_schema5_head_focus"
FIGURE_WIDTH_MM = 183.0
FIGURE_HEIGHT_MM = 230.0
EXPORT_SUFFIXES = (".svg", ".pdf", ".png", ".tiff")

MODEL_ORDER = (
    "esmc_6b",
    "esm2_3b",
    "esmc_300m",
    "prostt5",
    "prott5_xl",
    "esm3_open_1_4b",
    "esmc_600m",
    "esm2_650m",
)
MODEL_LABEL = {
    "esmc_6b": "ESM-C 6B",
    "esm2_3b": "ESM-2 3B",
    "esmc_300m": "ESM-C 300M",
    "prostt5": "ProstT5",
    "prott5_xl": "ProtT5-XL-U50",
    "esm3_open_1_4b": "ESM3-open 1.4B",
    "esmc_600m": "ESM-C 600M",
    "esm2_650m": "ESM-2 650M",
}
SOURCE_ORDER = (
    "viral_vma_djr",
    "cellular_djr_none",
    "background_non_djr",
    "hard_non_djr",
)
SOURCE_LABEL = {
    "viral_vma_djr": "Viral VMA-DJR",
    "cellular_djr_none": "Cellular DJR, non-MCP",
    "background_non_djr": "Background non-DJR",
    "hard_non_djr": "Matched HardNeg",
}
HEAD_ENDPOINTS = (
    ("head1", "viral_vma_djr", "positive_sensitivity", "H1 · Viral DJR found"),
    ("head1", "cellular_djr_none", "positive_sensitivity", "H1 · Cellular DJR found"),
    ("head1", "background_non_djr", "negative_specificity", "H1 · Background rejected"),
    ("head1", "hard_non_djr", "negative_specificity", "H1 · HardNeg rejected"),
    ("head2", "viral_vma_djr", "positive_sensitivity", "H2 · Viral MCP retained"),
    ("head2", "cellular_djr_none", "negative_specificity", "H2 · Cellular rejected"),
    ("head3_phylum", "viral_vma_djr", "expected_label_accuracy", "H3 · Expected label correct"),
)
H12_ORDER = ("esm2_650m", "esm2_3b", "esmc_6b")
H3_ORDER = ("esmc_300m", "esmc_600m", "esmc_6b")
CANDIDATE_ORDER = tuple(
    f"h12_{h12}__h3_{h3}" for h12 in H12_ORDER for h3 in H3_ORDER
)
NOMINEE = "h12_esm2_3b__h3_esmc_6b"
SELECTED_H12 = "esm2_3b"
SELECTED_H3 = "esmc_6b"

PALETTE = {
    "blue": "#245B8A",
    "blue_light": "#D9E7F2",
    "orange": "#D9842B",
    "orange_light": "#F7E4CB",
    "teal": "#2A8C82",
    "teal_light": "#D8EEE9",
    "grey": "#777777",
    "grey_mid": "#BDBDBD",
    "grey_light": "#E5E5E5",
    "grey_pale": "#F4F4F4",
    "ink": "#222222",
}

REQUIRED_RESULT_FILES = (
    "source_head_summary.tsv",
    "source_path_summary.tsv",
    "strict_cluster_summary.tsv",
    "train_cv_candidate_summary.tsv",
    "candidate_nomination.tsv",
    "pairwise_source_path_delta.tsv",
    "summary.json",
    "validation.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _write_tsv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _verify_manifest(directory: Path, manifest_name: str) -> dict[str, str]:
    manifest = directory / manifest_name
    if not manifest.is_file():
        raise FileNotFoundError(manifest)
    verified: dict[str, str] = {}
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        digest, relative = raw.split(maxsplit=1)
        relative = relative.strip().lstrip("*")
        path = (directory / relative).resolve()
        if directory.resolve() not in path.parents or not path.is_file():
            raise RuntimeError(f"Unsafe or missing checksum target: {relative}")
        observed = _sha256(path)
        if observed != digest:
            raise RuntimeError(f"Checksum mismatch: {relative}")
        verified[relative] = observed
    return verified


def _float(row: Mapping[str, str], field: str) -> float:
    value = float(row[field])
    if not 0.0 <= value <= 1.0:
        raise RuntimeError(f"Rate outside [0,1]: {field}={value}")
    return value


def _index(rows: Sequence[dict[str, str]], fields: Sequence[str], label: str) -> dict[tuple[str, ...], dict[str, str]]:
    output: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        key = tuple(row[field] for field in fields)
        if key in output:
            raise RuntimeError(f"Duplicate {label}: {key}")
        output[key] = row
    return output


def _load_bundle(result_dir: Path, benchmark_dir: Path) -> dict[str, Any]:
    result_dir = result_dir.resolve()
    benchmark_dir = benchmark_dir.resolve()
    result_verified = _verify_manifest(result_dir, "CHECKSUMS.sha256")
    missing = sorted(set(REQUIRED_RESULT_FILES) - set(result_verified))
    if missing:
        raise RuntimeError(f"Compact result manifest lacks required files: {missing}")

    benchmark_verified = _verify_manifest(benchmark_dir, "COMPARISON_CHECKSUMS.sha256")
    if "model_comparison.tsv" not in benchmark_verified:
        raise RuntimeError("Benchmark comparison manifest lacks model_comparison.tsv")

    summary = json.loads((result_dir / "summary.json").read_text(encoding="utf-8"))
    validation = json.loads((result_dir / "validation.json").read_text(encoding="utf-8"))
    if (
        summary.get("analysis_id") != "project_v0_validation_family_robustness_schema5_mixed_heads"
        or summary.get("record_counts", {}).get("test_records") != 0
        or summary.get("released_v0_artifacts_modified") != 0
        or summary.get("released_v0_feedback_permitted") is not False
        or validation.get("counts", {}).get("test_records") != 0
        or set(validation.get("gates", {}).values()) != {"PASS"}
    ):
        raise RuntimeError("Schema-5 completion/Test/V0 boundary changed")

    head_rows_all = _read_tsv(result_dir / "source_head_summary.tsv")
    head_rows = [row for row in head_rows_all if row.get("system_type") == "homogeneous_model"]
    head_index = _index(head_rows, ("system_id", "head", "source_dataset"), "head endpoint")
    expected_head_keys = {
        (model, head, source)
        for model in MODEL_ORDER
        for head, source, _metric, _label in HEAD_ENDPOINTS
    }
    if set(head_index) != expected_head_keys or len(head_rows) != 56:
        raise RuntimeError("Head-focused input is not exact 8 models x 7 legal endpoints")
    metric_by_key = {(head, source): metric for head, source, metric, _label in HEAD_ENDPOINTS}
    for (model, head, source), row in head_index.items():
        if row["metric"] != metric_by_key[(head, source)]:
            raise RuntimeError(f"Head metric changed: {(model, head, source)}")
        value, low, high = (_float(row, field) for field in ("member_value", "member_ci_low", "member_ci_high"))
        if not low <= value <= high or row.get("weighting") != "equal_dependence_block_then_source_cluster_then_member":
            raise RuntimeError(f"Invalid head interval/weighting: {(model, head, source)}")

    path_rows_all = _read_tsv(result_dir / "source_path_summary.tsv")
    path_rows = [row for row in path_rows_all if row.get("system_type") == "homogeneous_model"]
    path_index = _index(path_rows_all, ("system_id", "source_dataset"), "path endpoint")
    homogeneous_keys = {(model, source) for model in MODEL_ORDER for source in SOURCE_ORDER}
    if {(row["system_id"], row["source_dataset"]) for row in path_rows} != homogeneous_keys or len(path_rows) != 32:
        raise RuntimeError("Path input is not exact 8 models x 4 sources")
    for row in path_rows:
        value, low, high, strict = (
            _float(row, field)
            for field in (
                "member_value",
                "member_ci_low",
                "member_ci_high",
                "proportion_clusters_all_members_correct",
            )
        )
        if not low <= value <= high or value < 0.75:
            raise RuntimeError("Invalid or clipped path value")

    cv_rows = _read_tsv(result_dir / "train_cv_candidate_summary.tsv")
    cv_index = _index(cv_rows, ("candidate_id",), "CV candidate")
    if tuple(row["candidate_id"] for row in cv_rows) != CANDIDATE_ORDER:
        raise RuntimeError("Nine-candidate order changed")
    for row in cv_rows:
        score = float(row["mean_train_cv_score"])
        se = float(row["train_cv_score_se"])
        if not 0.0 <= score <= 1.0 or se < 0.0 or row["primary_evidence"] != "train_only_shared_five_fold_cv":
            raise RuntimeError("Invalid candidate Train-CV evidence")

    nomination_rows = _read_tsv(result_dir / "candidate_nomination.tsv")
    if len(nomination_rows) != 1:
        raise RuntimeError("Expected one nomination row")
    nomination = nomination_rows[0]
    if (
        nomination["candidate_id"] != NOMINEE
        or nomination["robustness_used_for_candidate_ordering"] != "0"
        or nomination["released_v0_change_permitted"] != "0"
        or nomination["prospective_external_confirmation_required"] != "1"
    ):
        raise RuntimeError("Nomination boundary changed")

    pairwise_rows = _read_tsv(result_dir / "pairwise_source_path_delta.tsv")
    pairwise_index = _index(pairwise_rows, ("candidate_id", "source_dataset"), "pairwise diagnostic")
    warning_count = sum(
        pairwise_index[(NOMINEE, source)]["diagnostic_status"] == "source_specific_inferiority_warning"
        for source in SOURCE_ORDER
    )
    if warning_count != int(nomination["source_specific_warning_count"]):
        raise RuntimeError("Nominee warning count changed")

    benchmark_rows = _read_tsv(benchmark_dir / "model_comparison.tsv")
    benchmark_index = _index(benchmark_rows, ("model_id",), "benchmark model")
    for model in set(H12_ORDER) | set(H3_ORDER):
        if (model,) not in benchmark_index:
            raise RuntimeError(f"Missing benchmark component: {model}")
    component_rows: list[dict[str, str]] = []
    for model in H12_ORDER:
        row = benchmark_index[(model,)]
        component_rows.append(
            {
                "component_role": "H1_and_H2_candidate",
                "model_id": model,
                "cv_head1_average_precision": row["cv_head1_average_precision"],
                "cv_head2_average_precision": row["cv_head2_average_precision"],
                "cv_head3_macro_f1": "",
            }
        )
    for model in H3_ORDER:
        row = benchmark_index[(model,)]
        component_rows.append(
            {
                "component_role": "H3_candidate",
                "model_id": model,
                "cv_head1_average_precision": "",
                "cv_head2_average_precision": "",
                "cv_head3_macro_f1": row["cv_head3_macro_f1"],
            }
        )

    return {
        "result_dir": result_dir,
        "benchmark_dir": benchmark_dir,
        "result_verified": result_verified,
        "benchmark_verified": benchmark_verified,
        "summary": summary,
        "validation": validation,
        "head_rows": head_rows,
        "head_index": head_index,
        "path_rows": path_rows,
        "path_index": path_index,
        "cv_rows": cv_rows,
        "cv_index": cv_index,
        "nomination": nomination,
        "pairwise_index": pairwise_index,
        "warning_count": warning_count,
        "benchmark_index": benchmark_index,
        "component_rows": component_rows,
    }


def _panel_label(ax: Any, label: str, *, x: float = -0.15, y: float = 1.08) -> None:
    ax.text(x, y, label, transform=ax.transAxes, fontsize=8.5, fontweight="bold", ha="left", va="bottom")


def _draw_head_endpoint(
    ax: Any,
    bundle: Mapping[str, Any],
    endpoint: tuple[str, str, str, str],
    *,
    show_models: bool,
) -> None:
    head, source, _metric, title = endpoint
    selected = SELECTED_H3 if head == "head3_phylum" else SELECTED_H12
    y = list(range(len(MODEL_ORDER)))
    for yi in y:
        if yi % 2:
            ax.axhspan(yi - 0.5, yi + 0.5, color=PALETTE["grey_pale"], zorder=0)
    for yi, model in zip(y, MODEL_ORDER, strict=True):
        row = bundle["head_index"][(model, head, source)]
        value = float(row["member_value"])
        low = float(row["member_ci_low"])
        high = float(row["member_ci_high"])
        is_selected = model == selected
        ax.errorbar(
            value,
            yi,
            xerr=[[value - low], [high - value]],
            fmt="o",
            markersize=4.8 if is_selected else 3.8,
            markerfacecolor=PALETTE["orange"] if is_selected else PALETTE["blue"],
            markeredgecolor=PALETTE["ink"] if is_selected else "white",
            markeredgewidth=0.65,
            ecolor=PALETTE["orange"] if is_selected else PALETTE["grey_mid"],
            capsize=1.6,
            zorder=3,
        )
    ax.set_xlim(0.55, 1.015)
    ax.set_xticks((0.6, 0.8, 1.0))
    ax.set_ylim(len(MODEL_ORDER) - 0.5, -0.5)
    ax.set_yticks(y)
    ax.set_yticklabels([MODEL_LABEL[model] for model in MODEL_ORDER] if show_models else [""] * len(y))
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=PALETTE["grey_light"], linewidth=0.5)
    ax.set_title(title, loc="left", pad=3)


def _draw_panel_a(figure: Any, spec: Any, bundle: Mapping[str, Any]) -> list[Any]:
    grid = spec.subgridspec(2, 4, hspace=0.62, wspace=0.22)
    axes: list[Any] = []
    for col, endpoint in enumerate(HEAD_ENDPOINTS[:4]):
        ax = figure.add_subplot(grid[0, col])
        _draw_head_endpoint(ax, bundle, endpoint, show_models=col == 0)
        axes.append(ax)
    for col, endpoint in enumerate(HEAD_ENDPOINTS[4:6]):
        ax = figure.add_subplot(grid[1, col])
        _draw_head_endpoint(ax, bundle, endpoint, show_models=col == 0)
        axes.append(ax)
    ax_h3 = figure.add_subplot(grid[1, 2:4])
    _draw_head_endpoint(ax_h3, bundle, HEAD_ENDPOINTS[6], show_models=False)
    axes.append(ax_h3)
    bbox = spec.get_position(figure)
    figure.text(
        bbox.x0 - 0.035,
        bbox.y1 + 0.017,
        "a",
        fontsize=8.5,
        fontweight="bold",
        ha="left",
        va="bottom",
    )
    figure.text(
        bbox.x0,
        bbox.y1 + 0.017,
        "Head-by-head robustness: where does each model succeed or struggle?",
        fontsize=7.8,
        fontweight="bold",
        ha="left",
        va="bottom",
    )
    figure.text(
        bbox.x1,
        bbox.y0 - 0.018,
        "● orange = Train-CV-selected component, not a robustness winner  ·  "
        "H3 endpoint ≠ Train-CV macro-F1; diagnostic only, no reranking",
        color=PALETTE["grey"],
        ha="right",
        va="top",
        fontsize=5.8,
    )
    axes[5].set_xlabel("Correct decision rate [95% CI]  → better")
    return axes


def _path_cmap() -> Any:
    return mpl.colors.LinearSegmentedColormap.from_list(
        "head_focus_blue", ("#F7FAFC", "#BBD4E7", PALETTE["blue"])
    )


def _draw_panel_b(ax: Any, bundle: Mapping[str, Any]) -> Any:
    matrix = np.zeros((len(MODEL_ORDER), len(SOURCE_ORDER)))
    for i, model in enumerate(MODEL_ORDER):
        for j, source in enumerate(SOURCE_ORDER):
            matrix[i, j] = float(bundle["path_index"][(model, source)]["member_value"])
    norm = mpl.colors.Normalize(0.75, 1.0)
    image = ax.imshow(matrix, cmap=_path_cmap(), norm=norm, aspect="auto")
    for i, model in enumerate(MODEL_ORDER):
        for j, source in enumerate(SOURCE_ORDER):
            row = bundle["path_index"][(model, source)]
            value = float(row["member_value"])
            low = float(row["member_ci_low"])
            high = float(row["member_ci_high"])
            strict = float(row["proportion_clusters_all_members_correct"])
            color = "white" if value >= 0.91 else PALETTE["ink"]
            ax.text(j, i - 0.08, f"{value:.3f}\n[{low:.2f}, {high:.2f}]", ha="center", va="center", color=color)
            left = j - 0.40
            ax.plot([left, left + 0.80 * strict], [i + 0.37, i + 0.37], color=PALETTE["orange"], linewidth=2.0, solid_capstyle="butt")
            ax.plot([left + 0.80 * strict, j + 0.40], [i + 0.37, i + 0.37], color=(1, 1, 1, 0.65), linewidth=2.0, solid_capstyle="butt")
    ax.set_xticks(range(len(SOURCE_ORDER)))
    ax.set_xticklabels([SOURCE_LABEL[source] for source in SOURCE_ORDER])
    ax.set_yticks(range(len(MODEL_ORDER)))
    ax.set_yticklabels([MODEL_LABEL[model] for model in MODEL_ORDER])
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title("Whole-cascade robustness: were all applicable Heads correct?", loc="left", pad=4)
    ax.text(
        1.0,
        -0.16,
        "cell: equal block→cluster→member estimate [95% CI]  ·  orange bar: all-members-correct clusters",
        transform=ax.transAxes,
        color=PALETTE["grey"],
        ha="right",
        va="top",
    )
    _panel_label(ax, "b", x=-0.055, y=1.04)
    return image


def _draw_panel_c_recipe(ax: Any, bundle: Mapping[str, Any]) -> None:
    ax.set_xlim(-0.5, 2.5)
    ax.set_ylim(2.5, -0.5)
    for i, h12 in enumerate(H12_ORDER):
        for j, h3 in enumerate(H3_ORDER):
            candidate = f"h12_{h12}__h3_{h3}"
            row = bundle["cv_index"][(candidate,)]
            nominee = candidate == NOMINEE
            ax.add_patch(
                mpl.patches.Rectangle(
                    (j - 0.5, i - 0.5),
                    1.0,
                    1.0,
                    facecolor=PALETTE["orange_light"] if nominee else ("white" if (i + j) % 2 == 0 else PALETTE["grey_pale"]),
                    edgecolor=PALETTE["orange"] if nominee else "white",
                    linewidth=1.7 if nominee else 0.8,
                )
            )
            ax.text(
                j,
                i,
                f"{float(row['mean_train_cv_score']):.4f}\n±{float(row['train_cv_score_se']):.4f}" + ("  ★" if nominee else ""),
                ha="center",
                va="center",
                fontweight="bold" if nominee else "normal",
                color=PALETTE["ink"],
            )
    ax.set_xticks(range(3))
    ax.set_xticklabels([MODEL_LABEL[model].replace("ESM-C ", "C-") for model in H3_ORDER])
    ax.xaxis.tick_top()
    ax.set_yticks(range(3))
    ax.set_yticklabels([MODEL_LABEL[model] for model in H12_ORDER])
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title("1  Select on Train CV only", loc="left", pad=27)
    ax.text(0.5, 1.12, "H3 encoder", transform=ax.transAxes, ha="center", va="bottom", fontweight="bold")
    ax.set_ylabel("H1 + H2 encoder", fontweight="bold", labelpad=6)
    ax.text(
        0.5,
        -0.20,
        "S = 0.60 H1 AP + 0.30 H2 AP + 0.10 H3 known macro-F1\ncell = five-fold mean S ± fold SE",
        transform=ax.transAxes,
        ha="center",
        va="top",
        color=PALETTE["grey"],
        fontsize=5.8,
    )
    _panel_label(ax, "c", x=-0.34, y=1.21)


def _draw_panel_c_assignment(ax: Any, bundle: Mapping[str, Any]) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("2  Freeze Head assignment", loc="left", pad=4)
    h12 = bundle["benchmark_index"][(SELECTED_H12,)]
    h3 = bundle["benchmark_index"][(SELECTED_H3,)]

    def box(y: float, title: str, model: str, metric: str) -> None:
        ax.add_patch(
            mpl.patches.FancyBboxPatch(
                (0.08, y - 0.12),
                0.84,
                0.24,
                boxstyle="round,pad=0.025",
                facecolor=PALETTE["orange_light"],
                edgecolor=PALETTE["orange"],
                linewidth=1.1,
            )
        )
        ax.text(0.50, y + 0.045, title, ha="center", va="center", fontweight="bold")
        ax.text(0.50, y - 0.010, model, ha="center", va="center", color=PALETTE["orange"], fontweight="bold")
        ax.text(0.50, y - 0.070, metric, ha="center", va="center", color=PALETTE["grey"], fontsize=5.7)

    box(
        0.72,
        "H1 + H2",
        "ESM-2 3B",
        f"Train-CV AP {float(h12['cv_head1_average_precision']):.4f} / {float(h12['cv_head2_average_precision']):.4f}",
    )
    box(
        0.30,
        "H3",
        "ESM-C 6B",
        f"Train-CV macro-F1 {float(h3['cv_head3_macro_f1']):.4f}",
    )
    ax.annotate("if viral MCP", xy=(0.50, 0.44), xytext=(0.50, 0.56), ha="center", va="center", color=PALETTE["grey"], arrowprops={"arrowstyle": "-|>", "color": PALETTE["grey"], "linewidth": 0.9})
    ax.text(0.50, 0.055, "Nominee: 3B for H1/H2\n+ C-6B for H3", ha="center", va="center", color=PALETTE["ink"], fontweight="bold")


def _draw_panel_c_check(ax: Any, bundle: Mapping[str, Any]) -> None:
    y_positions = list(range(len(SOURCE_ORDER)))[::-1]
    for y, source in zip(y_positions, SOURCE_ORDER, strict=True):
        row = bundle["path_index"][(NOMINEE, source)]
        value = float(row["member_value"])
        low = float(row["member_ci_low"])
        high = float(row["member_ci_high"])
        ax.errorbar(value, y, xerr=[[value - low], [high - value]], fmt="o", color=PALETTE["orange"], ecolor=PALETTE["blue"], markersize=5.0, capsize=2.0, zorder=3)
        ax.text(1.004, y, f"{value:.3f}", ha="left", va="center", family="monospace")
    ax.axvline(1.0, color=PALETTE["grey_mid"], linewidth=0.6)
    ax.set_xlim(0.895, 1.025)
    ax.set_ylim(-0.65, len(SOURCE_ORDER) - 0.05)
    ax.set_xticks((0.90, 0.95, 1.00))
    ax.set_yticks(y_positions)
    ax.set_yticklabels(("Viral VMA-DJR", "Cellular DJR", "Background", "HardNeg"))
    ax.set_xlabel("Expected-path accuracy [95% CI]")
    ax.grid(axis="x", color=PALETTE["grey_light"], linewidth=0.5)
    ax.set_title("3  Check neighbours — do not rerank", loc="left", pad=4)
    ax.text(
        1.0,
        -0.22,
        f"{bundle['warning_count']}/4 inferiority warnings vs all-6B",
        transform=ax.transAxes,
        ha="right",
        va="top",
        color=PALETTE["teal"],
        fontweight="bold",
    )
    ax.text(
        1.0,
        -0.34,
        "No warning ≠ equivalence  ·  Test accessed = 0\nExternal confirmation required  ·  V0 unchanged",
        transform=ax.transAxes,
        ha="right",
        va="top",
        color=PALETTE["grey"],
        fontsize=5.8,
    )


def _guide_text() -> str:
    return """# 图怎么读

## a：逐个 Head 看

每个点是一种模型在一个合法来源上的正确决策率，横线是 95% CI，越靠右越好。H1 有四个合法来源，
H2 有两个，H3 只有 viral。橙色只是标出 Train-CV 已经选定的组件，不表示用本图重新选模。

## b：看整条工具路径

一个输入在该来源所有应运行的 Head 都答对，才算 expected path 正确。格内是点估计和 95% CI；橙线是
“整个 cluster 的所有近亲都正确”的 cluster 比例。

## c：按 1 → 2 → 3 阅读

1. 只用 Train 的五折 CV 比较 3×3 种配方；每格是 S ± fold SE。
2. 最高的预注册配方把 H1/H2 交给 ESM-2 3B，把 H3 交给 ESM-C 6B。
3. 选定后才检查四来源同簇近亲；0/4 warning 只表示没有建立相对 all-6B 的来源特异劣势，不能证明等价。

重要边界：robustness 没有参与候选排序；Test accessed=0；冻结 V0 没有改变，仍需外部/前瞻确认。
ESM3-open 1.4B 在本次 H3 family-neighbour expected-label accuracy 上点估计较高，但这不是 Train-CV
known macro-F1，也不是同一个证据层，不能用来事后重排。
"""


def _render(bundle: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite: {output_dir}")
    temporary = output_dir.with_name(f"{output_dir.name}.tmp-{os.getpid()}")
    if temporary.exists():
        raise FileExistsError(f"Temporary output exists: {temporary}")
    temporary.mkdir(parents=True)
    source_dir = temporary / "source_data"
    source_dir.mkdir()
    try:
        _load_matplotlib()
        figure = plt.figure(
            figsize=(FIGURE_WIDTH_MM / 25.4, FIGURE_HEIGHT_MM / 25.4),
            constrained_layout=False,
        )
        figure.subplots_adjust(left=0.135, right=0.975, top=0.945, bottom=0.085, hspace=0.42)
        outer = figure.add_gridspec(3, 1, height_ratios=(1.86, 1.20, 1.24), hspace=0.42)
        _draw_panel_a(figure, outer[0, 0], bundle)
        ax_b = figure.add_subplot(outer[1, 0])
        image = _draw_panel_b(ax_b, bundle)
        colorbar = figure.colorbar(image, ax=ax_b, fraction=0.018, pad=0.012)
        colorbar.set_ticks((0.75, 0.875, 1.0))
        colorbar.set_ticklabels(("0.75", "0.875", "1.00"))

        c_grid = outer[2, 0].subgridspec(1, 3, width_ratios=(1.00, 0.70, 1.24), wspace=0.34)
        ax_recipe = figure.add_subplot(c_grid[0, 0])
        ax_assignment = figure.add_subplot(c_grid[0, 1])
        ax_check = figure.add_subplot(c_grid[0, 2])
        _draw_panel_c_recipe(ax_recipe, bundle)
        _draw_panel_c_assignment(ax_assignment, bundle)
        _draw_panel_c_check(ax_check, bundle)

        base = temporary / FIGURE_BASENAME
        figure.savefig(base.with_suffix(".svg"))
        figure.savefig(base.with_suffix(".pdf"))
        figure.savefig(base.with_suffix(".png"), dpi=300)
        figure.savefig(base.with_suffix(".tiff"), dpi=600, pil_kwargs={"compression": "tiff_lzw"})
        plt.close(figure)

        head_source_rows: list[dict[str, Any]] = []
        for row in bundle["head_rows"]:
            key = (row["head"], row["source_dataset"])
            endpoint = next(item for item in HEAD_ENDPOINTS if item[:2] == key)
            selected = SELECTED_H3 if row["head"] == "head3_phylum" else SELECTED_H12
            head_source_rows.append(
                {
                    **row,
                    "plain_endpoint_label": endpoint[3],
                    "train_cv_selected_component": int(row["system_id"] == selected),
                    "selection_role": "display_only_selection_preceded_robustness",
                }
            )
        head_fields = list(head_source_rows[0])
        _write_tsv(source_dir / "panel_a_head_robustness.tsv", head_fields, head_source_rows)
        _write_tsv(source_dir / "panel_b_expected_path.tsv", list(bundle["path_rows"][0]), bundle["path_rows"])
        _write_tsv(source_dir / "panel_c_train_cv_recipes.tsv", list(bundle["cv_rows"][0]), bundle["cv_rows"])
        _write_tsv(source_dir / "panel_c_train_cv_components.tsv", list(bundle["component_rows"][0]), bundle["component_rows"])
        nominee_rows: list[dict[str, Any]] = []
        for source in SOURCE_ORDER:
            path = dict(bundle["path_index"][(NOMINEE, source)])
            diagnostic = bundle["pairwise_index"][(NOMINEE, source)]
            path.update(
                {
                    "holm_adjusted_p_vs_all_6b": diagnostic["holm_adjusted_p"],
                    "diagnostic_status_vs_all_6b": diagnostic["diagnostic_status"],
                    "robustness_used_for_candidate_ordering": 0,
                }
            )
            nominee_rows.append(path)
        _write_tsv(source_dir / "panel_c_nominee_check.tsv", list(nominee_rows[0]), nominee_rows)

        (temporary / "FIGURE_GUIDE.md").write_text(_guide_text(), encoding="utf-8")
        qa = {
            "analysis_id": ANALYSIS_ID,
            "status": "pass_pending_manual_visual_qa",
            "backend": "python_matplotlib_only",
            "figure_contract": "head_resolved_plus_expected_path_plus_choose_assign_check",
            "figure_size_mm": {"width": FIGURE_WIDTH_MM, "height": FIGURE_HEIGHT_MM},
            "minimum_text_pt": 5.8,
            "exports": [FIGURE_BASENAME + suffix for suffix in EXPORT_SUFFIXES],
            "svg_text_editable": True,
            "result_checksum_manifest_sha256": _sha256(bundle["result_dir"] / "CHECKSUMS.sha256"),
            "benchmark_checksum_manifest_sha256": _sha256(bundle["benchmark_dir"] / "COMPARISON_CHECKSUMS.sha256"),
            "result_validation_sha256": _sha256(bundle["result_dir"] / "validation.json"),
            "head_rows_plotted": 56,
            "head_rows_expected": 56,
            "head_endpoint_count": 7,
            "homogeneous_models": 8,
            "path_rows_plotted": 32,
            "train_cv_recipes_plotted": 9,
            "nominee_source_rows_plotted": 4,
            "rows_excluded_from_requested_scope": 0,
            "mixed_head_duplicate_component_rows_plotted": 0,
            "cross_head_average_plotted": False,
            "cross_source_average_plotted": False,
            "head_robustness_used_for_reranking": False,
            "h3_robustness_metric": "expected_label_accuracy_not_train_cv_macro_f1",
            "head_uncertainty": "95pct_dependence_block_bootstrap_ci",
            "weighting": "equal_dependence_block_then_source_cluster_then_member",
            "nominee": NOMINEE,
            "source_specific_warning_count": bundle["warning_count"],
            "test_records": 0,
            "released_v0_changed": False,
            "external_confirmation_required": True,
            "manual_visual_qa_required_before_publication": True,
            "source_data_tables": sorted(path.name for path in source_dir.iterdir()),
        }
        (temporary / "QA.json").write_text(json.dumps(qa, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        exported = [base.with_suffix(suffix) for suffix in EXPORT_SUFFIXES]
        if not all(path.is_file() and path.stat().st_size > 0 for path in exported):
            raise RuntimeError("One or more figure exports are empty")
        if "<text" not in base.with_suffix(".svg").read_text(encoding="utf-8"):
            raise RuntimeError("SVG text is not editable")

        manifest_rows: list[dict[str, Any]] = []
        for path in sorted(item for item in temporary.rglob("*") if item.is_file()):
            relative = path.relative_to(temporary).as_posix()
            manifest_rows.append(
                {
                    "path": relative,
                    "role": "figure" if path.suffix in EXPORT_SUFFIXES else "source_data" if path.parent == source_dir else "qa_or_guide",
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        _write_tsv(temporary / "figure_manifest.tsv", ("path", "role", "bytes", "sha256"), manifest_rows)
        with (temporary / "CHECKSUMS.sha256").open("x", encoding="utf-8") as handle:
            for path in sorted(item for item in temporary.rglob("*") if item.is_file() and item.name != "CHECKSUMS.sha256"):
                handle.write(f"{_sha256(path)}  {path.relative_to(temporary).as_posix()}\n")
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output_dir)
        return qa
    except Exception:
        failed = temporary.with_name(f"{temporary.name}.failed")
        if temporary.exists() and not failed.exists():
            os.replace(temporary, failed)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--result-dir",
        type=Path,
        default=ROOT / "results" / "validation_family_robustness_v0_schema5_mixed_heads",
    )
    parser.add_argument(
        "--benchmark-dir",
        type=Path,
        default=ROOT / "results" / "model_benchmark_v0_metric_revision_1",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results" / "figures" / "project_v0" / "validation_family_robustness_v0_schema5_head_focus",
    )
    args = parser.parse_args()
    bundle = _load_bundle(args.result_dir, args.benchmark_dir)
    qa = _render(bundle, args.output_dir)
    print(json.dumps({"output_dir": str(args.output_dir.resolve()), "qa": qa}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
