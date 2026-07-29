"""Static contract checks for the schema-4 four-source renderer.

These tests intentionally do not synthesize scientific results or render a
placeholder figure.  A real render requires the completed checksum-bound
schema-4 result directory.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plot_validation_family_robustness_v0_schema4.py"


def _load_plotter():
    spec = importlib.util.spec_from_file_location("schema4_plotter", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_four_source_cascade_applicability_is_explicit() -> None:
    plotter = _load_plotter()
    assert plotter.SOURCE_ORDER == (
        "viral_vma_djr",
        "cellular_djr_none",
        "background_non_djr",
        "hard_non_djr",
    )
    assert plotter.APPLICABLE_HEADS == {
        "viral_vma_djr": frozenset(
            ("head1", "head2", "head3_phylum")
        ),
        "cellular_djr_none": frozenset(("head1", "head2")),
        "background_non_djr": frozenset(("head1",)),
        "hard_non_djr": frozenset(("head1",)),
    }
    assert plotter.PATH_ID == "full_expected_path"


def test_zero_and_missing_are_distinct() -> None:
    plotter = _load_plotter()
    assert plotter._optional_float("") is None
    assert plotter._optional_float("N/A") is None
    assert plotter._optional_float("NE") is None
    assert plotter._optional_float("0") == 0.0


def test_delivery_and_input_contracts_are_complete() -> None:
    plotter = _load_plotter()
    assert plotter.SUPPORTED_EXPORT_SUFFIXES == (
        ".svg",
        ".pdf",
        ".png",
        ".tiff",
    )
    assert set(plotter.REQUIRED_RESULT_FILES) == {
        "summary.json",
        "coverage_summary.tsv",
        "source_head_summary.tsv",
        "source_path_summary.tsv",
        "cluster_all_members_summary.tsv",
        "hardnegative_summary.tsv",
    }


def test_plotter_has_no_embedded_result_bundle() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert '_resolve(project_root, config["result_dir"])' in source
    assert "result_dir_override.resolve()" in source
    assert "_verify_checksums(result_dir)" in source
    assert "missing_values_encoded_as_zero\": False" in source
    assert "background_or_hardnegative_h2_h3_rows\": 0" in source
