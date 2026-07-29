#!/usr/bin/env python3
"""Render the checksum-bound project-V0 four-source robustness figure.

The renderer is deliberately downstream-only.  It reads ``result_dir`` from
the schema-4 config, verifies the completed result bundle, and never opens
embeddings or prediction artifacts directly.  Missing values are represented
as ``NE`` and cascade-inapplicable cells as ``N/A``; neither is converted to
zero.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
from pathlib import Path
from typing import Any, Iterable, Optional

# Loaded only for a real render. This keeps ``--help`` and static contract
# tests usable on transfer hosts without a compatible plotting runtime.
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
    # Editable text in SVG is a delivery requirement.
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
    plt.rcParams["svg.fonttype"] = "none"


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ID = "project_v0_validation_family_robustness_schema4"
FIGURE_BASENAME = "validation_family_robustness_v0_schema4"
FIGURE_WIDTH_MM = 183.0
FIGURE_HEIGHT_MM = 158.0
SUPPORTED_EXPORT_SUFFIXES = (".svg", ".pdf", ".png", ".tiff")

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
    "hard_non_djr": "Selected HardNeg",
}
HEAD_ORDER = ("head1", "head2", "head3_phylum")
HEAD_SHORT = {"head1": "H1", "head2": "H2", "head3_phylum": "H3"}
APPLICABLE_HEADS = {
    "viral_vma_djr": frozenset(HEAD_ORDER),
    "cellular_djr_none": frozenset(("head1", "head2")),
    "background_non_djr": frozenset(("head1",)),
    "hard_non_djr": frozenset(("head1",)),
}
PATH_ID = "full_expected_path"
MODEL_LABEL = {"esmc_6b": "ESM-C 6B", "esm2_650m": "ESM-2 650M"}
MODEL_COLOR = {"esmc_6b": "#0F4D92", "esm2_650m": "#6F6F79"}

REQUIRED_RESULT_FILES = (
    "summary.json",
    "coverage_summary.tsv",
    "source_head_summary.tsv",
    "source_path_summary.tsv",
    "cluster_all_members_summary.tsv",
    "hardnegative_summary.tsv",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve(project_root: Path, value: Any) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else project_root / path


def _read_tsv(path: Path, *, allow_empty: bool = False) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise RuntimeError(f"TSV has no header: {path}")
        rows = list(reader)
    if not rows and not allow_empty:
        raise RuntimeError(f"TSV has no rows: {path}")
    return rows


def _write_tsv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def _verify_checksums(result_dir: Path) -> dict[str, str]:
    manifest = result_dir / "CHECKSUMS.sha256"
    if not manifest.is_file():
        raise RuntimeError(f"Missing result checksum manifest: {manifest}")
    verified: dict[str, str] = {}
    for line_number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split(maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError(f"Malformed checksum row {manifest}:{line_number}")
        expected, relative = parts[0].lower(), parts[1].strip().lstrip("*")
        rel = Path(relative)
        if (
            len(expected) != 64
            or any(char not in "0123456789abcdef" for char in expected)
            or rel.is_absolute()
            or ".." in rel.parts
            or relative in verified
        ):
            raise RuntimeError(f"Unsafe checksum target: {relative}")
        target = result_dir / rel
        if not target.is_file() or _sha256(target) != expected:
            raise RuntimeError(f"Missing or mismatched checksum target: {target}")
        verified[relative] = expected
    missing = sorted(set(REQUIRED_RESULT_FILES) - set(verified))
    if missing:
        raise RuntimeError(f"Required result files are not checksum-bound: {missing}")
    return verified


def _require_fields(rows: list[dict[str, str]], fields: set[str], label: str) -> None:
    if not rows:
        raise RuntimeError(f"{label} is empty")
    missing = fields - set(rows[0])
    if missing:
        raise RuntimeError(f"{label} is missing fields: {sorted(missing)}")


def _as_int(value: str, label: str) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid integer {label}: {value!r}") from exc
    if not math.isfinite(number) or not number.is_integer() or number < 0:
        raise RuntimeError(f"Invalid nonnegative integer {label}: {value!r}")
    return int(number)


def _optional_float(value: Optional[str], label: str = "value") -> Optional[float]:
    if value is None or value.strip().lower() in {"", "na", "n/a", "ne", "nan"}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid numeric {label}: {value!r}") from exc
    if not math.isfinite(number):
        raise RuntimeError(f"Non-finite numeric {label}: {value!r}")
    return number


def _unique_index(
    rows: list[dict[str, str]], fields: tuple[str, ...], label: str
) -> dict[tuple[str, ...], dict[str, str]]:
    result: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        key = tuple(row[field] for field in fields)
        if key in result:
            raise RuntimeError(f"Duplicate {label} key: {key}")
        result[key] = row
    return result


def _validate_rate_row(row: dict[str, str], label: str) -> None:
    status = row["bootstrap_status"]
    member = _optional_float(row["member_value"], f"{label} member_value")
    representative = _optional_float(
        row["representative_value"], f"{label} representative_value"
    )
    delta = _optional_float(
        row["delta_members_minus_representative"], f"{label} delta"
    )
    triplets = (
        ("member", member, "member_ci_low", "member_ci_high", 0.0, 1.0),
        (
            "representative",
            representative,
            "representative_ci_low",
            "representative_ci_high",
            0.0,
            1.0,
        ),
        ("delta", delta, "delta_ci_low", "delta_ci_high", -1.0, 1.0),
    )
    if member is None:
        if any(value is not None for value in (representative, delta)):
            raise RuntimeError(f"Partial not-estimable row: {label}")
        if "not_estimable" not in status:
            raise RuntimeError(f"Blank estimate lacks not_estimable status: {label}")
        return
    if representative is None or delta is None:
        raise RuntimeError(f"Complete row lacks representative/delta: {label}")
    if abs((member - representative) - delta) > 1e-6:
        raise RuntimeError(f"Paired delta does not equal member-representative: {label}")
    for name, point, low_field, high_field, lower, upper in triplets:
        assert point is not None
        if not lower - 1e-9 <= point <= upper + 1e-9:
            raise RuntimeError(f"Out-of-range {name} estimate: {label}")
        low = _optional_float(row[low_field], f"{label} {low_field}")
        high = _optional_float(row[high_field], f"{label} {high_field}")
        if (low is None) != (high is None):
            raise RuntimeError(f"Half-empty interval: {label}/{name}")
        if low is not None and (
            low > high
            or low < lower - 1e-9
            or high > upper + 1e-9
        ):
            raise RuntimeError(f"Invalid interval bounds: {label}/{name}")


def _load_and_validate(
    config_path: Path, result_dir_override: Optional[Path] = None
) -> dict[str, Any]:
    import yaml

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if (
        config.get("analysis_id") != ANALYSIS_ID
        or config.get("schema_version") != 4
        or config.get("model_state") != "frozen"
        or config.get("selection_feedback_permitted") is not False
        or config.get("test_policy") != "no_test_vector_selection_or_performance_scoring"
    ):
        raise RuntimeError("Schema-4 plotting config contract mismatch")
    project_root = config_path.resolve().parents[1]
    result_dir = (
        result_dir_override.resolve()
        if result_dir_override is not None
        else _resolve(project_root, config["result_dir"])
    )
    verified = _verify_checksums(result_dir)

    summary = json.loads((result_dir / "summary.json").read_text(encoding="utf-8"))
    if (
        summary.get("analysis_id") != ANALYSIS_ID
        or int(summary.get("schema_version", -1)) != 4
        or summary.get("status") != "complete_four_source"
        or summary.get("model_state") != "frozen"
        or summary.get("selection_feedback_permitted") is not False
    ):
        raise RuntimeError("Result summary is not a completed frozen schema-4 result")
    for field in (
        "test_vectors_selected_for_inference",
        "test_predictions_or_metrics_computed",
        "test_records_scored",
    ):
        if int(summary.get(field, 0)) != 0:
            raise RuntimeError(f"Refusing result with nonzero {field}")

    models = tuple(config.get("models", []))
    primary = config.get("frozen_primary_model_id")
    reference = config.get("fixed_reference_model_id")
    if set(models) != {"esmc_6b", "esm2_650m"} or {primary, reference} != set(models):
        raise RuntimeError("Unexpected schema-4 model set")
    model_order = (primary, reference)

    coverage = _read_tsv(result_dir / "coverage_summary.tsv")
    _require_fields(
        coverage,
        {
            "source_dataset",
            "n_validation_representatives",
            "n_candidate_clusters",
            "n_candidate_members",
            "n_legal_clusters",
            "n_legal_members",
            "n_excluded_clusters",
            "n_excluded_members",
            "coverage_status",
            "exclusion_reason",
        },
        "coverage_summary.tsv",
    )
    coverage_index = _unique_index(coverage, ("source_dataset",), "coverage")
    if set(key[0] for key in coverage_index) != set(SOURCE_ORDER):
        raise RuntimeError("Coverage must contain exactly the four frozen sources")
    for source in SOURCE_ORDER:
        row = coverage_index[(source,)]
        candidate = _as_int(row["n_candidate_members"], f"{source} candidates")
        legal = _as_int(row["n_legal_members"], f"{source} legal")
        excluded = _as_int(row["n_excluded_members"], f"{source} excluded")
        for field in (
            "n_validation_representatives",
            "n_candidate_clusters",
            "n_legal_clusters",
            "n_excluded_clusters",
        ):
            _as_int(row[field], f"{source} {field}")
        if legal + excluded != candidate:
            raise RuntimeError(f"Coverage member funnel does not close for {source}")

    summary_fields = {
        "model_id",
        "source_dataset",
        "metric",
        "representative_value",
        "representative_ci_low",
        "representative_ci_high",
        "member_value",
        "member_ci_low",
        "member_ci_high",
        "delta_members_minus_representative",
        "delta_ci_low",
        "delta_ci_high",
        "n_member_records",
        "n_source_clusters",
        "n_dependence_blocks",
        "clusters_all_members_correct",
        "proportion_clusters_all_members_correct",
        "bootstrap_status",
    }
    head_rows = _read_tsv(result_dir / "source_head_summary.tsv")
    _require_fields(head_rows, summary_fields | {"head"}, "source_head_summary.tsv")
    head_index = _unique_index(
        head_rows, ("model_id", "source_dataset", "head"), "head summary"
    )
    expected_heads = {
        (model, source, head)
        for model in model_order
        for source in SOURCE_ORDER
        for head in APPLICABLE_HEADS[source]
    }
    if set(head_index) != expected_heads:
        missing = sorted(expected_heads - set(head_index))
        extra = sorted(set(head_index) - expected_heads)
        raise RuntimeError(f"Head applicability mismatch; missing={missing}, extra={extra}")
    for key, row in head_index.items():
        _validate_rate_row(row, "/".join(key))

    path_rows = _read_tsv(result_dir / "source_path_summary.tsv")
    _require_fields(path_rows, summary_fields | {"path_id"}, "source_path_summary.tsv")
    path_index = _unique_index(
        path_rows, ("model_id", "source_dataset", "path_id"), "path summary"
    )
    expected_paths = {
        (model, source, PATH_ID) for model in model_order for source in SOURCE_ORDER
    }
    if set(path_index) != expected_paths:
        missing = sorted(expected_paths - set(path_index))
        extra = sorted(set(path_index) - expected_paths)
        raise RuntimeError(f"Complete-path rows mismatch; missing={missing}, extra={extra}")
    for key, row in path_index.items():
        _validate_rate_row(row, "/".join(key))

    cluster_rows = _read_tsv(result_dir / "cluster_all_members_summary.tsv")
    _require_fields(
        cluster_rows,
        {
            "model_id",
            "source_dataset",
            "endpoint_id",
            "head_or_path",
            "n_clusters",
            "clusters_all_members_correct",
            "proportion_clusters_all_members_correct",
            "status",
        },
        "cluster_all_members_summary.tsv",
    )
    cluster_path_rows = [
        row
        for row in cluster_rows
        if row["endpoint_id"] == PATH_ID or row["head_or_path"] == "path"
    ]
    cluster_index = _unique_index(
        cluster_path_rows, ("model_id", "source_dataset"), "cluster path summary"
    )
    expected_cluster_keys = {
        (model, source) for model in model_order for source in SOURCE_ORDER
    }
    if set(cluster_index) != expected_cluster_keys:
        raise RuntimeError("Cluster all-correct table lacks an exact four-source path grid")
    for key, row in cluster_index.items():
        total = _as_int(row["n_clusters"], f"{key} n_clusters")
        correct = _as_int(
            row["clusters_all_members_correct"], f"{key} clusters correct"
        )
        proportion = _optional_float(
            row["proportion_clusters_all_members_correct"], f"{key} proportion"
        )
        if total == 0:
            if correct != 0 or proportion is not None or "not_estimable" not in row["status"]:
                raise RuntimeError(f"Invalid zero-support cluster row: {key}")
        elif (
            correct > total
            or proportion is None
            or not 0.0 <= proportion <= 1.0
            or abs(proportion - correct / total) > 1e-6
        ):
            raise RuntimeError(f"Invalid all-members-correct proportion: {key}")

    hardnegative = _read_tsv(
        result_dir / "hardnegative_summary.tsv", allow_empty=True
    )
    for row in hardnegative:
        if row.get("source_dataset", "hard_non_djr") != "hard_non_djr":
            raise RuntimeError("hardnegative_summary.tsv contains a non-HardNeg source")
        if row.get("head", "head1") not in {"head1", ""}:
            raise RuntimeError("HardNeg summary must not contain H2/H3 predictions")

    return {
        "config": config,
        "project_root": project_root,
        "result_dir": result_dir,
        "verified": verified,
        "summary": summary,
        "model_order": model_order,
        "coverage": coverage,
        "coverage_index": coverage_index,
        "head_rows": head_rows,
        "head_index": head_index,
        "path_rows": path_rows,
        "path_index": path_index,
        "cluster_rows": cluster_rows,
        "cluster_index": cluster_index,
        "hardnegative": hardnegative,
    }


def _apply_style() -> None:
    _load_matplotlib()
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "DejaVu Sans", "Liberation Sans"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 7.0,
            "axes.titlesize": 8.0,
            "axes.titleweight": "bold",
            "axes.labelsize": 7.0,
            "axes.linewidth": 0.7,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.labelsize": 6.2,
            "ytick.labelsize": 6.2,
            "legend.frameon": False,
        }
    )


def _add_panel_label(ax: Any, label: str) -> None:
    ax.text(
        -0.10,
        1.05,
        label,
        transform=ax.transAxes,
        fontsize=10,
        fontweight="bold",
        ha="left",
        va="bottom",
    )


def _matrix_rows(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in SOURCE_ORDER:
        for model in bundle["model_order"]:
            for endpoint in (*HEAD_ORDER, PATH_ID):
                applicable = endpoint == PATH_ID or endpoint in APPLICABLE_HEADS[source]
                if not applicable:
                    rows.append(
                        {
                            "source_dataset": source,
                            "model_id": model,
                            "endpoint": endpoint,
                            "metric": "",
                            "value": "",
                            "ci_low": "",
                            "ci_high": "",
                            "cell_state": "not_applicable",
                            "bootstrap_status": "not_applicable_by_cascade",
                        }
                    )
                    continue
                if endpoint == PATH_ID:
                    row = bundle["path_index"][(model, source, PATH_ID)]
                else:
                    row = bundle["head_index"][(model, source, endpoint)]
                value = _optional_float(row["member_value"])
                rows.append(
                    {
                        "source_dataset": source,
                        "model_id": model,
                        "endpoint": endpoint,
                        "metric": row["metric"],
                        "value": "" if value is None else value,
                        "ci_low": row["member_ci_low"],
                        "ci_high": row["member_ci_high"],
                        "cell_state": "not_estimable" if value is None else "estimated",
                        "bootstrap_status": row["bootstrap_status"],
                    }
                )
    return rows


def _draw_panel_a(ax: Any, bundle: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    y = np.arange(len(SOURCE_ORDER))[::-1]
    ax.barh(y, np.ones(len(y)), color="#ECECF2", height=0.62, edgecolor="none")
    for position, source in zip(y, SOURCE_ORDER):
        row = bundle["coverage_index"][(source,)]
        candidate = _as_int(row["n_candidate_members"], "candidate")
        legal = _as_int(row["n_legal_members"], "legal")
        excluded = _as_int(row["n_excluded_members"], "excluded")
        fraction = legal / candidate if candidate else 0.0
        color = "#B4533C" if source == "hard_non_djr" else "#4E89C7"
        ax.barh(position, fraction, color=color, height=0.62, edgecolor="none")
        if excluded:
            ax.barh(
                position,
                excluded / candidate,
                left=fraction,
                color="#E8B36A",
                height=0.62,
                edgecolor="none",
            )
        ax.text(
            1.02,
            position,
            f"{legal:,} / {candidate:,}",
            transform=ax.get_yaxis_transform(),
            ha="left",
            va="center",
            fontsize=6.2,
        )
        output.append(dict(row))
    ax.set_yticks(y)
    ax.set_yticklabels([SOURCE_LABEL[source] for source in SOURCE_ORDER])
    ax.set_xlim(0, 1)
    ax.set_xticks((0, 0.5, 1.0))
    ax.set_xticklabels(("0", "50", "100"))
    ax.set_xlabel("Legal members / candidate members (%)")
    ax.set_title("Coverage and member-level gates", loc="left")
    ax.grid(axis="x", color="#D8D8D8", linewidth=0.5, zorder=0)
    ax.text(
        0,
        -0.33,
        "blue/red: legal  ·  orange: excluded  ·  labels: legal / candidate",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=5.8,
        color="#555555",
    )
    _add_panel_label(ax, "a")
    return output


def _draw_panel_b(
    ax: Any, bundle: dict[str, Any], matrix_rows: list[dict[str, Any]]
) -> None:
    columns = [
        (model, endpoint)
        for model in bundle["model_order"]
        for endpoint in (*HEAD_ORDER, PATH_ID)
    ]
    lookup = {
        (row["source_dataset"], row["model_id"], row["endpoint"]): row
        for row in matrix_rows
    }
    values = np.full((len(SOURCE_ORDER), len(columns)), np.nan)
    for row_index, source in enumerate(SOURCE_ORDER):
        for col_index, (model, endpoint) in enumerate(columns):
            row = lookup[(source, model, endpoint)]
            if row["cell_state"] == "estimated":
                values[row_index, col_index] = float(row["value"])
    ax.imshow(values, cmap="Blues", norm=mpl.colors.Normalize(0, 1), aspect="auto")
    for row_index, source in enumerate(SOURCE_ORDER):
        for col_index, (model, endpoint) in enumerate(columns):
            row = lookup[(source, model, endpoint)]
            if row["cell_state"] == "not_applicable":
                ax.add_patch(
                    mpl.patches.Rectangle(
                        (col_index - 0.5, row_index - 0.5),
                        1,
                        1,
                        facecolor="#E1E1E1",
                        edgecolor="white",
                        linewidth=1,
                    )
                )
                label, color = "N/A", "#676767"
            elif row["cell_state"] == "not_estimable":
                ax.add_patch(
                    mpl.patches.Rectangle(
                        (col_index - 0.5, row_index - 0.5),
                        1,
                        1,
                        facecolor="#FFF0C2",
                        edgecolor="white",
                        linewidth=1,
                    )
                )
                label, color = "NE", "#805A00"
            else:
                value = float(row["value"])
                label = f"{value:.2f}"
                color = "white" if value >= 0.58 else "#1D1D1D"
            ax.text(col_index, row_index, label, ha="center", va="center", color=color)
    ax.set_xticks(np.arange(len(columns)))
    ax.set_xticklabels(
        [
            f"{HEAD_SHORT.get(endpoint, 'Path')}\n{MODEL_LABEL.get(model, model)}"
            for model, endpoint in columns
        ],
        rotation=38,
        ha="right",
    )
    ax.set_yticks(np.arange(len(SOURCE_ORDER)))
    ax.set_yticklabels([SOURCE_LABEL[source] for source in SOURCE_ORDER])
    ax.axvline(3.5, color="white", linewidth=2.2)
    ax.set_title("Correct output at each applicable stage", loc="left")
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    _add_panel_label(ax, "b")


def _path_source_rows(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(bundle["path_index"][(model, source, PATH_ID)])
        for source in SOURCE_ORDER
        for model in bundle["model_order"]
    ]


def _cluster_source_rows(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(bundle["cluster_index"][(model, source)])
        for source in SOURCE_ORDER
        for model in bundle["model_order"]
    ]


def _draw_panel_c(
    ax_delta: Any,
    ax_cluster: Any,
    bundle: dict[str, Any],
    path_rows: list[dict[str, Any]],
    cluster_rows: list[dict[str, Any]],
) -> None:
    path_lookup = {
        (row["model_id"], row["source_dataset"]): row for row in path_rows
    }
    cluster_lookup = {
        (row["model_id"], row["source_dataset"]): row for row in cluster_rows
    }
    x = np.arange(len(SOURCE_ORDER))
    offsets = (-0.11, 0.11)
    for offset, model in zip(offsets, bundle["model_order"]):
        for position, source in zip(x + offset, SOURCE_ORDER):
            row = path_lookup[(model, source)]
            value = _optional_float(row["delta_members_minus_representative"])
            if value is None:
                ax_delta.text(position, 0, "NE", ha="center", va="center", color="#805A00")
                continue
            low = _optional_float(row["delta_ci_low"])
            high = _optional_float(row["delta_ci_high"])
            yerr = None if low is None else [[value - low], [high - value]]
            ax_delta.errorbar(
                position,
                value,
                yerr=yerr,
                fmt="o",
                markersize=4.3,
                color=MODEL_COLOR[model],
                capsize=2.2,
                linewidth=1.0,
                label=MODEL_LABEL[model] if source == SOURCE_ORDER[0] else None,
            )
        proportions: list[float] = []
        plotted_positions: list[float] = []
        for position, source in zip(x + offset, SOURCE_ORDER):
            row = cluster_lookup[(model, source)]
            value = _optional_float(row["proportion_clusters_all_members_correct"])
            if value is None:
                ax_cluster.text(position, 0.03, "NE", ha="center", va="bottom", color="#805A00")
                continue
            plotted_positions.append(position)
            proportions.append(value)
        ax_cluster.scatter(
            plotted_positions,
            proportions,
            s=22,
            color=MODEL_COLOR[model],
            edgecolor="white",
            linewidth=0.5,
            zorder=3,
        )

    for ax in (ax_delta, ax_cluster):
        ax.set_xticks(x)
        ax.set_xticklabels(
            [SOURCE_LABEL[source] for source in SOURCE_ORDER], rotation=25, ha="right"
        )
        ax.grid(axis="y", color="#DEDEDE", linewidth=0.5, zorder=0)
    ax_delta.axhline(0, color="#555555", linewidth=0.7)
    ax_delta.set_ylim(-1.02, 1.02)
    ax_delta.set_ylabel("Member − representative")
    ax_delta.set_title("Full-path paired change", loc="left")
    ax_delta.legend(loc="lower left", fontsize=6.0)
    ax_cluster.set_ylim(-0.02, 1.02)
    ax_cluster.set_ylabel("All-members-correct clusters")
    ax_cluster.set_title("Within-cluster consistency", loc="left")
    _add_panel_label(ax_delta, "c")


def _render(bundle: dict[str, Any], output_dir: Path, config_path: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite figure directory: {output_dir}")
    temporary = output_dir.with_name(f"{output_dir.name}.tmp-{os.getpid()}")
    if temporary.exists():
        raise FileExistsError(f"Temporary figure directory exists: {temporary}")
    temporary.mkdir(parents=True)
    source_dir = temporary / "source_data"
    source_dir.mkdir()
    try:
        _apply_style()
        figure = plt.figure(
            figsize=(FIGURE_WIDTH_MM / 25.4, FIGURE_HEIGHT_MM / 25.4),
            constrained_layout=True,
        )
        outer = figure.add_gridspec(
            2, 2, width_ratios=(0.83, 1.50), height_ratios=(0.98, 1.05)
        )
        ax_a = figure.add_subplot(outer[0, 0])
        ax_b = figure.add_subplot(outer[0, 1])
        lower = outer[1, :].subgridspec(1, 2, wspace=0.20)
        ax_c1 = figure.add_subplot(lower[0, 0])
        ax_c2 = figure.add_subplot(lower[0, 1])

        coverage_rows = _draw_panel_a(ax_a, bundle)
        matrix_rows = _matrix_rows(bundle)
        _draw_panel_b(ax_b, bundle, matrix_rows)
        path_rows = _path_source_rows(bundle)
        cluster_rows = _cluster_source_rows(bundle)
        _draw_panel_c(ax_c1, ax_c2, bundle, path_rows, cluster_rows)

        base = temporary / FIGURE_BASENAME
        figure.savefig(base.with_suffix(".svg"), bbox_inches="tight")
        figure.savefig(base.with_suffix(".pdf"), bbox_inches="tight")
        figure.savefig(base.with_suffix(".png"), dpi=300, bbox_inches="tight")
        figure.savefig(
            base.with_suffix(".tiff"),
            dpi=600,
            bbox_inches="tight",
            pil_kwargs={"compression": "tiff_lzw"},
        )
        plt.close(figure)

        _write_tsv(
            source_dir / "panel_a_coverage.tsv", list(coverage_rows[0]), coverage_rows
        )
        _write_tsv(
            source_dir / "panel_b_matrix.tsv",
            [
                "source_dataset",
                "model_id",
                "endpoint",
                "metric",
                "value",
                "ci_low",
                "ci_high",
                "cell_state",
                "bootstrap_status",
            ],
            matrix_rows,
        )
        _write_tsv(source_dir / "panel_c_path_delta.tsv", list(path_rows[0]), path_rows)
        _write_tsv(
            source_dir / "panel_c_cluster_correct.tsv",
            list(cluster_rows[0]),
            cluster_rows,
        )
        shutil.copyfile(
            bundle["result_dir"] / "hardnegative_summary.tsv",
            source_dir / "hardnegative_summary.tsv",
        )

        exported = [base.with_suffix(suffix) for suffix in SUPPORTED_EXPORT_SUFFIXES]
        svg_text = exported[0].read_text(encoding="utf-8")
        if "<text" not in svg_text:
            raise RuntimeError("SVG export does not retain editable text")
        if not all(path.is_file() and path.stat().st_size > 0 for path in exported):
            raise RuntimeError("One or more figure exports are empty")
        state_counts = {
            state: sum(row["cell_state"] == state for row in matrix_rows)
            for state in ("estimated", "not_applicable", "not_estimable")
        }
        if len(matrix_rows) != 32 or sum(state_counts.values()) != 32:
            raise RuntimeError("Panel-b state accounting does not close")
        if state_counts["not_applicable"] != 10:
            raise RuntimeError("Static cascade N/A count changed unexpectedly")

        qa = {
            "schema_version": 1,
            "analysis_id": ANALYSIS_ID,
            "status": "pass",
            "figure_contract": "four_source_quantitative_grid",
            "config_name": config_path.name,
            "result_checksum_manifest_verified": True,
            "result_input_sha256": {
                name: bundle["verified"][name] for name in REQUIRED_RESULT_FILES
            },
            "backend": "python_matplotlib",
            "exports": [path.name for path in exported],
            "svg_text_editable": True,
            "n_matrix_cells": len(matrix_rows),
            "matrix_cell_states": state_counts,
            "missing_values_encoded_as_zero": False,
            "background_or_hardnegative_h2_h3_rows": 0,
            "test_vectors_selected_for_inference": 0,
            "test_predictions_or_metrics_computed": 0,
            "source_data_tables": sorted(path.name for path in source_dir.iterdir()),
        }
        qa_path = temporary / "QA.json"
        qa_path.write_text(json.dumps(qa, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        manifest_rows: list[dict[str, Any]] = []
        for path in sorted(
            item for item in temporary.rglob("*") if item.is_file()
        ):
            relative = path.relative_to(temporary).as_posix()
            manifest_rows.append(
                {
                    "path": relative,
                    "role": "figure" if path.suffix in SUPPORTED_EXPORT_SUFFIXES else "source_or_qa",
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        _write_tsv(
            temporary / "figure_manifest.tsv",
            ["path", "role", "bytes", "sha256"],
            manifest_rows,
        )
        checksummed = sorted(
            item
            for item in temporary.rglob("*")
            if item.is_file() and item.name != "CHECKSUMS.sha256"
        )
        with (temporary / "CHECKSUMS.sha256").open("x", encoding="utf-8") as handle:
            for path in checksummed:
                relative = path.relative_to(temporary).as_posix()
                handle.write(f"{_sha256(path)}  {relative}\n")
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output_dir)
        return qa
    except Exception:
        # Preserve the failed render for forensic inspection; never publish it.
        failed = temporary.with_name(f"{temporary.name}.failed")
        if temporary.exists() and not failed.exists():
            os.replace(temporary, failed)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "validation_family_robustness_v0_schema4.yaml",
    )
    parser.add_argument(
        "--result-dir",
        type=Path,
        help=(
            "Optional read-only location of a transferred checksum-bound result bundle; "
            "the frozen config itself is not rewritten."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional figure output override.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the completed result bundle without creating a figure.",
    )
    args = parser.parse_args()
    bundle = _load_and_validate(args.config.resolve(), args.result_dir)
    if args.validate_only:
        print(
            json.dumps(
                {
                    "analysis_id": ANALYSIS_ID,
                    "status": "validated",
                    "result_checksum_manifest_verified": True,
                    "sources": list(SOURCE_ORDER),
                    "models": list(bundle["model_order"]),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    output_dir = args.output_dir
    if output_dir is None:
        output_dir = _resolve(bundle["project_root"], bundle["config"]["figure_dir"])
    qa = _render(bundle, output_dir, args.config.resolve())
    print(json.dumps({"output_dir": str(output_dir), **qa}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
