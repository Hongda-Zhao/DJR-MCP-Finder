from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plot_validation_family_robustness_v0_schema5_head_focus.py"
RESULT = ROOT / "results" / "validation_family_robustness_v0_schema5_mixed_heads"
BENCHMARK = ROOT / "results" / "model_benchmark_v0_metric_revision_1"


def _module():
    spec = importlib.util.spec_from_file_location("head_focus_plot", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_head_focus_contract_and_exact_row_counts() -> None:
    module = _module()
    bundle = module._load_bundle(RESULT, BENCHMARK)

    assert len(bundle["head_rows"]) == 56
    assert len(bundle["path_rows"]) == 32
    assert len(bundle["cv_rows"]) == 9
    assert len(bundle["component_rows"]) == 6
    assert bundle["warning_count"] == 0
    assert bundle["nomination"]["candidate_id"] == module.NOMINEE
    assert bundle["nomination"]["robustness_used_for_candidate_ordering"] == "0"
    assert bundle["summary"]["record_counts"]["test_records"] == 0


def test_only_legal_head_source_endpoints_are_planned() -> None:
    module = _module()
    assert module.HEAD_ENDPOINTS == (
        ("head1", "viral_vma_djr", "positive_sensitivity", "H1 · Viral DJR found"),
        ("head1", "cellular_djr_none", "positive_sensitivity", "H1 · Cellular DJR found"),
        ("head1", "background_non_djr", "negative_specificity", "H1 · Background rejected"),
        ("head1", "hard_non_djr", "negative_specificity", "H1 · HardNeg rejected"),
        ("head2", "viral_vma_djr", "positive_sensitivity", "H2 · Viral MCP retained"),
        ("head2", "cellular_djr_none", "negative_specificity", "H2 · Cellular rejected"),
        ("head3_phylum", "viral_vma_djr", "expected_label_accuracy", "H3 · Expected label correct"),
    )
    assert len(module.MODEL_ORDER) * len(module.HEAD_ENDPOINTS) == 56


def test_h3_family_diagnostic_is_not_silently_used_for_selection() -> None:
    module = _module()
    bundle = module._load_bundle(RESULT, BENCHMARK)
    esm3 = float(bundle["head_index"][("esm3_open_1_4b", "head3_phylum", "viral_vma_djr")]["member_value"])
    c6b = float(bundle["head_index"][("esmc_6b", "head3_phylum", "viral_vma_djr")]["member_value"])

    # This deliberate regression guard forces the figure to retain the caveat:
    # family-neighbour expected-label accuracy is not Train-CV H3 macro-F1.
    assert esm3 > c6b
    assert module.SELECTED_H3 == "esmc_6b"
    assert "diagnostic only, no reranking" in SCRIPT.read_text(encoding="utf-8")


def test_publication_exports_and_fail_closed_boundaries_are_explicit() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for token in (
        '".svg"',
        '".pdf"',
        '".png"',
        '".tiff"',
        '"svg.fonttype": "none"',
        '"pdf.fonttype": 42',
        'dpi=600',
        'Refusing to overwrite',
        'Test accessed = 0',
        'No warning ≠ equivalence',
        'rows_excluded_from_requested_scope',
        'cross_head_average_plotted',
    ):
        assert token in text


def test_guide_explains_choose_assign_check_in_plain_language() -> None:
    module = _module()
    guide = module._guide_text()
    assert "1. 只用 Train" in guide
    assert "2. 最高的预注册配方" in guide
    assert "3. 选定后才检查" in guide
    assert "robustness 没有参与候选排序" in guide
    assert "Test accessed=0" in guide
