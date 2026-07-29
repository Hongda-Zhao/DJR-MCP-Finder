"""Static contract checks for the schema-5 publication renderer.

These tests intentionally create neither mock scientific tables nor a
placeholder figure.  Rendering is permitted only after the real schema-5
result bundle exists and passes its checksum gate.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plot_validation_family_robustness_v0_schema5_mixed_heads.py"


def _load_plotter():
    spec = importlib.util.spec_from_file_location("schema5_plotter", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_four_source_and_model_candidate_contract() -> None:
    plotter = _load_plotter()
    assert plotter.SOURCE_ORDER == (
        "viral_vma_djr",
        "cellular_djr_none",
        "background_non_djr",
        "hard_non_djr",
    )
    assert plotter.APPLICABLE_HEADS == {
        "viral_vma_djr": frozenset(("head1", "head2", "head3_phylum")),
        "cellular_djr_none": frozenset(("head1", "head2")),
        "background_non_djr": frozenset(("head1",)),
        "hard_non_djr": frozenset(("head1",)),
    }
    assert len(plotter.MODEL_ORDER) == 8
    assert len(set(plotter.MODEL_ORDER)) == 8
    assert len(plotter.CANDIDATE_ORDER) == 9
    assert len(set(plotter.CANDIDATE_ORDER)) == 9
    assert all("h12_" in value and "__h3_" in value for value in plotter.CANDIDATE_ORDER)


def test_na_ne_and_numeric_zero_are_three_distinct_states() -> None:
    plotter = _load_plotter()
    assert plotter._classify_cell(False, None) == plotter.CELL_NOT_APPLICABLE
    assert plotter._classify_cell(True, None) == plotter.CELL_NOT_ESTIMABLE
    assert plotter._classify_cell(True, 0.0) == plotter.CELL_ESTIMATED
    assert plotter._optional_float("N/A") is None
    assert plotter._optional_float("NE") is None
    assert plotter._optional_float("0") == 0.0
    assert plotter._format_rate(None) == "NE"
    assert plotter._format_rate(0.0) == "0.000"


def test_checksum_gate_covers_every_scientific_input_table() -> None:
    plotter = _load_plotter()
    required = set(plotter.REQUIRED_RESULT_FILES)
    assert {
        "source_path_summary.tsv",
        "strict_cluster_summary.tsv",
        "train_cv_candidate_summary.tsv",
        "pairwise_source_path_delta.tsv",
        "contextual_source_path_delta.tsv",
        "accuracy_cost_pareto.tsv",
        "candidate_nomination.tsv",
        "h3_class_summary.tsv",
        "model_cost_registry.tsv",
        "materialization_summary.tsv",
        "schema4_recomputation_audit.tsv",
        "schema4_recomputation_audit_summary.tsv",
        "legacy_numerical_operator_runtime.json",
        "summary.json",
    } <= required
    source = SCRIPT.read_text(encoding="utf-8")
    assert "verified = _verify_checksums(result_dir, REQUIRED_RESULT_FILES)" in source
    assert '_verify_checksums(schema4_result_dir, ("coverage_summary.tsv",))' in source
    assert "contextual_source_path_delta.tsv" in source


def test_renderer_requires_exact_lineage_and_independent_validation() -> None:
    plotter = _load_plotter()
    source = SCRIPT.read_text(encoding="utf-8")
    assert len(plotter.REQUIRED_VALIDATION_GATES) == 20
    assert "schema4_canonical_cache_full_recomputation_audit" in (
        plotter.REQUIRED_VALIDATION_GATES
    )
    assert "schema4_legacy_operator_runtime_and_exact_numeric_replay" in (
        plotter.REQUIRED_VALIDATION_GATES
    )
    assert "h3_rare_subgroups_independently_recomputed" in (
        plotter.REQUIRED_VALIDATION_GATES
    )
    assert "amendment_c_predictions_threshold_cv_order_byte_equivalent" in (
        plotter.REQUIRED_VALIDATION_GATES
    )
    assert 'lineage.get("config") != config_sha256' in source
    assert 'lineage.get("protocol") != protocol_sha256' in source
    assert '_sha256(checksum_manifest) != config["schema4_result_checksums_sha256"]' in source
    assert 'validation.get("status") != "PASS"' in source
    assert 'validation.get("counts", {}).get("test_records") != 0' in source
    assert 'validation_inputs.get("result_checksums")' in source
    assert 'validation_inputs.get("config") != config_sha256' in source
    assert 'validation_inputs.get("legacy_numerical_operator_runtime")' in source
    assert 'set(validation_gates) != set(REQUIRED_VALIDATION_GATES)' in source
    assert '"--validation"' in source


def test_nominee_is_train_cv_only_and_robustness_is_context() -> None:
    plotter = _load_plotter()
    assert plotter.NOMINATION_PRIMARY_EVIDENCE == "train_only_shared_five_fold_cv"
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'row["robustness_used_for_pareto_or_ordering"]' in source
    assert 'nomination["robustness_used_for_candidate_ordering"]' in source
    assert "auxiliary Validation-family diagnostics from" in source
    assert '"panel_c_candidates_in_source_diagnostic": 1' in source
    assert '"panel_c_full_nine_by_four_retained_in_source_data": True' in source
    assert '"cross_source_average_plotted": False' in source
    assert "mean_train_cv_score" in source
    assert "source-specific expected-path accuracy" in source


def test_h3_amendment_d_subgroups_support_and_raw_counts_are_explicit() -> None:
    plotter = _load_plotter()
    assert plotter.PROTOCOL_AMENDMENT == (
        "D_h3_rare_subgroup_transparency_no_model_change"
    )
    assert plotter.H3_PRIMARY_DISPLAY_ENDPOINTS == (
        "Nucleocytoviricota_f1",
        "Preplasmiviricota_f1",
        "Produgelaviricota_reject_recall",
        "literature_unclassified_reject_recall",
    )
    assert plotter.H3_ALL_ENDPOINTS == (
        "Nucleocytoviricota_f1",
        "Preplasmiviricota_f1",
        "known_two_phylum_macro_f1",
        "Produgelaviricota_reject_recall",
        "literature_unclassified_reject_recall",
        "rare_or_unclassified_reject_recall",
    )
    assert plotter.REPRESENTATIVE_RARE_N == 5
    assert plotter.MATCHED_RARE_RELATIONS_N == 8
    assert plotter.MATCHED_RARE_PARENTS_N == 3
    assert plotter.MATCHED_RARE_BLOCKS_N == 3
    assert (
        plotter.PRODUGELAVIRICOTA_RELATIONS_N,
        plotter.PRODUGELAVIRICOTA_PARENTS_N,
        plotter.PRODUGELAVIRICOTA_BLOCKS_N,
    ) == (7, 2, 2)
    assert (
        plotter.LITERATURE_UNCLASSIFIED_RELATIONS_N,
        plotter.LITERATURE_UNCLASSIFIED_PARENTS_N,
        plotter.LITERATURE_UNCLASSIFIED_BLOCKS_N,
    ) == (1, 1, 1)
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"raw_member_reject_k"' in source
    assert '"raw_member_reject_n"' in source
    assert '"descriptive_subgroup"' in source
    assert '"descriptive_single_record_subgroup"' in source
    assert '"secondary_pooled_diagnostic"' in source
    assert "Single-record literature subgroup must be point-only" in source
    assert "different_cohort" in source
    assert "representative_benchmark_rare_unknown_recall" in source
    assert '"h3_raw_k_n_displayed": True' in source
    assert '"h3_pooled_used_as_primary": False' in source
    assert '"h3_pooled_secondary_only": True' in source
    assert '"h3_secondary_pooled_and_representative_rows_plotted": False' in source
    assert '"h3_secondary_rows_retained_in_source_data": True' in source
    assert '"h3_single_block_ci_drawn": False' in source
    assert '"h3_unknown_generalization_claim_permitted": False' in source


def test_h3_panel_source_data_keeps_primary_and_secondary_roles_distinct() -> None:
    plotter = _load_plotter()
    source = SCRIPT.read_text(encoding="utf-8")
    assert "for y, endpoint in zip(y_positions, H3_PRIMARY_DISPLAY_ENDPOINTS" in source
    assert '"scope": "matched_family_member"' in source
    assert '"scope": "matched_family_member_secondary"' in source
    assert '"scope": "representative_benchmark_secondary"' in source
    for field in (
        "n_evaluation_records",
        "n_dependence_blocks",
        "raw_member_k",
        "raw_member_n",
        "raw_representative_k",
        "raw_representative_n",
        "endpoint_role",
    ):
        assert f'"{field}"' in source
    assert "panel_d_h3_boundary.tsv" in source


def test_python_only_publication_export_and_atomic_publish_contract() -> None:
    plotter = _load_plotter()
    assert plotter.SUPPORTED_EXPORT_SUFFIXES == (".svg", ".pdf", ".png", ".tiff")
    assert plotter.FIGURE_WIDTH_MM == 183.0
    assert 220.0 <= plotter.FIGURE_HEIGHT_MM <= 230.0
    assert plotter.PANEL_LABELS == ("a", "b", "c", "d", "e")
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'matplotlib_module.use("Agg")' in source
    assert 'plt.rcParams["svg.fonttype"] = "none"' in source
    assert 'plt.rcParams["pdf.fonttype"] = 42' in source
    assert 'dpi=300' in source and 'dpi=600' in source
    assert 'pil_kwargs={"compression": "tiff_lzw"}' in source
    assert "os.replace(temporary, output_dir)" in source
    assert "Refusing to overwrite figure directory" in source
    assert "np.random" not in source
    assert "synthetic_data" not in source


def test_layout_keeps_dense_annotations_out_of_the_main_canvas() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "Cell key:" not in source
    assert "same evidence for all 8 models" not in source
    assert "Test accessed = 0" in source
    assert "_draw_panel_c_context" not in source
    assert "_draw_panel_c_nominee_source" in source
    assert "_draw_panel_e_h3" in source
    assert "secondary pooled family:" not in source
    assert "separate benchmark: raw" not in source
    assert "figure.text(" not in source
