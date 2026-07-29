"""Focused safety tests for the schema-5 compact publisher.

The tests never construct scientific result or figure placeholders and never
invoke preflight/publish against configured project paths.  Only the generic
two-directory no-overwrite commit primitive is exercised in a pytest temp
directory.
"""

from __future__ import annotations

import ast
import csv
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts"
    / "publish_validation_family_robustness_v0_schema5_compact.py"
)
PBS = ROOT / "scripts" / "run_validation_family_robustness_v0_schema5_mixed_heads.pbs"


def _load_publisher():
    spec = importlib.util.spec_from_file_location("schema5_compact_publisher", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_full_result_partition_is_explicit_and_high_volume_stays_out() -> None:
    publisher = _load_publisher()
    assert not (
        publisher.COMPACT_RESULT_SOURCE_FILES
        & publisher.EXCLUDED_HIGH_VOLUME_RESULT_FILES
    )
    assert publisher.EXPECTED_FULL_RESULT_FILES == (
        publisher.COMPACT_RESULT_SOURCE_FILES
        | publisher.EXCLUDED_HIGH_VOLUME_RESULT_FILES
    )
    assert len(publisher.EXPECTED_FULL_RESULT_FILES) == 20
    assert "schema4_recomputation_audit_summary.tsv" in (
        publisher.COMPACT_RESULT_SOURCE_FILES
    )
    assert "legacy_numerical_operator_runtime.json" in (
        publisher.COMPACT_RESULT_SOURCE_FILES
    )
    assert {
        "single_model_predictions.tsv",
        "system_predictions.tsv",
        "system_expected_path_predictions.tsv",
        "path_bootstrap_replicates.tsv",
        "schema4_recomputation_audit.tsv",
    } == publisher.EXCLUDED_HIGH_VOLUME_RESULT_FILES


def test_figure_core_keeps_three_primary_exports_and_full_lineage_files() -> None:
    publisher = _load_publisher()
    assert publisher.COMPACT_FIGURE_SOURCE_FILES == {
        f"{publisher.FIGURE_BASENAME}.svg",
        f"{publisher.FIGURE_BASENAME}.pdf",
        f"{publisher.FIGURE_BASENAME}.png",
        "QA.json",
        "figure_manifest.tsv",
        "source_data/panel_a_evidence.tsv",
        "source_data/panel_b_homogeneous.tsv",
        "source_data/panel_c_mixed_candidates.tsv",
        "source_data/panel_d_accuracy_cost_pareto.tsv",
        "source_data/panel_d_h3_boundary.tsv",
    }
    assert f"{publisher.FIGURE_BASENAME}.tiff" not in (
        publisher.COMPACT_FIGURE_SOURCE_FILES
    )


def test_validation_figure_and_active_path_gates_are_present() -> None:
    publisher = _load_publisher()
    source = SCRIPT.read_text(encoding="utf-8")
    assert len(publisher.REQUIRED_VALIDATION_GATES) == 20
    assert publisher.PROTOCOL_AMENDMENT == (
        "D_h3_rare_subgroup_transparency_no_model_change"
    )
    assert "h3_rare_subgroups_independently_recomputed" in (
        publisher.REQUIRED_VALIDATION_GATES
    )
    assert "amendment_c_predictions_threshold_cv_order_byte_equivalent" in (
        publisher.REQUIRED_VALIDATION_GATES
    )
    assert "schema4_canonical_cache_full_recomputation_audit" in (
        publisher.REQUIRED_VALIDATION_GATES
    )
    assert "schema4_legacy_operator_runtime_and_exact_numeric_replay" in (
        publisher.REQUIRED_VALIDATION_GATES
    )
    assert 'inputs.get("result_checksums")' not in source  # strict helper mapping is used
    assert '"result_checksums": result_manifest_sha256' in source
    assert 'qa.get("result_input_sha256") != dict(result_files)' in source
    assert 'config["active_compact_result_dir"]' in source
    assert 'config["active_compact_figure_dir"]' in source
    assert '"--publish"' in source
    assert 'status": "ready_no_writes"' in source


def test_amendment_c_fixed_lineage_and_preflight_call_arity() -> None:
    publisher = _load_publisher()
    assert publisher.AMENDMENT_C_RESULT_CHECKSUMS_SHA256 == (
        "aa9f3cef647487d4eaec7749ceeb49c58085657a38d0d99c7577f3655448e72c"
    )
    assert publisher.AMENDMENT_C_VALIDATION_SHA256 == (
        "2b63cecae7788cce3d4c8ef96d48bf1becfbe8d74b9e9c084b2ab69a47542bcb"
    )
    assert publisher.SCHEMA3_FAMILY_MEMBER_MANIFEST_SHA256 == (
        "8cd9e9ce45ad965eb745cc4ecdf08d7e3205f57b830bca00bcf0041e5bcdf541"
    )

    config_path = ROOT / "configs" / "validation_family_robustness_v0_schema5_mixed_heads.yaml"
    config = publisher.yaml.safe_load(config_path.read_text(encoding="utf-8"))
    publisher._validate_config(config)
    changed = dict(config)
    changed["amendment_c_validation_sha256"] = "0" * 64
    with pytest.raises(publisher.CompactPublishError, match="config boundary"):
        publisher._validate_config(changed)
    changed = dict(config)
    changed["schema3_family_member_manifest_sha256"] = "0" * 64
    with pytest.raises(publisher.CompactPublishError, match="config boundary"):
        publisher._validate_config(changed)

    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    expected_arities = {
        "_validate_amendment_c_equivalence": 5,
        "_validate_independent_validation": 9,
    }
    definitions = {
        node.name: len(node.args.args)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in expected_arities
    }
    calls = {
        name: [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        ]
        for name in expected_arities
    }
    assert definitions == expected_arities
    for name, arity in expected_arities.items():
        assert len(calls[name]) == 1
        assert len(calls[name][0].args) == arity
        assert not calls[name][0].keywords

    source = SCRIPT.read_text(encoding="utf-8")
    assert '"amendment_c_fixed_lineage"' in source
    assert '"amendment_c_validation": state["amendment_c_validation_sha256"]' in source
    assert source.count('"schema3_family_manifest": config[') == 2
    assert '"schema3_family_member_manifest": state["config"][' in source


def test_amendment_d_launcher_uses_config_bound_read_only_reuse() -> None:
    publisher = _load_publisher()
    source = PBS.read_text(encoding="utf-8")
    assert "schema5_v1_amendment_d" in source
    assert 'config.get("inputs", {})' in source
    assert 'config.get("embedding_registries", {})' in source
    assert "frozen read path points into writable Amendment-D root" in source
    assert "receipts=18+6+24" in source
    assert "attest_validation_family_robustness_v0_schema5_reuse.py" not in source
    assert (
        "normalize_validation_family_robustness_v0_schema5_embedding_attestations.py"
        not in source
    )
    validation_code = source.rsplit(
        'python - "$VALIDATION" <<\'PY\'\n', 1
    )[1].rsplit("\nPY", 1)[0]
    tree = ast.parse(validation_code)
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "expected_gates"
            for target in node.targets
        )
    ]
    assert len(assignments) == 1
    assert ast.literal_eval(assignments[0].value) == set(
        publisher.REQUIRED_VALIDATION_GATES
    )
    assert "if set(gates) != expected_gates:" in validation_code
    assert 'gates[gate] != "PASS"' in validation_code


def test_h3_panel_source_data_requires_split_primary_and_secondary_pooled(
    tmp_path: Path,
) -> None:
    publisher = _load_publisher()
    path = tmp_path / "panel_d_h3_boundary.tsv"
    fields = (
        "candidate_id",
        "head3_model",
        "endpoint_id",
        "display_label",
        "scope",
        "value",
        "ci_low",
        "ci_high",
        "n_relations",
        "n_evaluation_records",
        "n_parents",
        "n_dependence_blocks",
        "raw_member_k",
        "raw_member_n",
        "raw_representative_k",
        "raw_representative_n",
        "endpoint_role",
        "interpretation",
    )
    common = {
        "candidate_id": "nominee",
        "head3_model": "esmc_6b",
        "value": "1",
        "ci_low": "",
        "ci_high": "",
        "n_relations": "10",
        "n_evaluation_records": "10",
        "n_parents": "2",
        "n_dependence_blocks": "2",
        "raw_member_k": "",
        "raw_member_n": "",
        "raw_representative_k": "",
        "raw_representative_n": "",
        "interpretation": "reviewed endpoint",
    }
    rows = [
        {
            **common,
            "endpoint_id": "Nucleocytoviricota_f1",
            "display_label": "Nuc F1",
            "scope": "matched_family_member",
            "endpoint_role": "primary_known_class",
        },
        {
            **common,
            "endpoint_id": "Preplasmiviricota_f1",
            "display_label": "Prep F1",
            "scope": "matched_family_member",
            "endpoint_role": "primary_known_class",
        },
    ]
    for endpoint, label, role, support in (
        (
            "Produgelaviricota_reject_recall",
            "Produ reject",
            "descriptive_subgroup",
            (7, 2, 2),
        ),
        (
            "literature_unclassified_reject_recall",
            "Lit reject",
            "descriptive_single_record_subgroup",
            (1, 1, 1),
        ),
        (
            "rare_or_unclassified_reject_recall",
            "Pooled rare reject (secondary only)",
            "secondary_pooled_diagnostic",
            (8, 3, 3),
        ),
    ):
        relations, parents, blocks = support
        rows.append(
            {
                **common,
                "endpoint_id": endpoint,
                "display_label": label,
                "scope": (
                    "matched_family_member_secondary"
                    if endpoint == "rare_or_unclassified_reject_recall"
                    else "matched_family_member"
                ),
                "n_relations": str(relations),
                "n_evaluation_records": str(relations),
                "n_parents": str(parents),
                "n_dependence_blocks": str(blocks),
                "raw_member_k": str(relations),
                "raw_member_n": str(relations),
                "raw_representative_k": str(parents),
                "raw_representative_n": str(parents),
                "endpoint_role": role,
                "interpretation": "secondary_not_general_unknown_detection",
            }
        )
    rows.append(
        {
            **common,
            "endpoint_id": "representative_benchmark_rare_unknown_recall",
            "display_label": "Separate benchmark",
            "scope": "representative_benchmark_secondary",
            "n_relations": "5",
            "n_evaluation_records": "5",
            "n_parents": "",
            "n_dependence_blocks": "",
            "raw_representative_k": "5",
            "raw_representative_n": "5",
            "endpoint_role": "secondary_external_benchmark_different_cohort",
        }
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    qa = {"train_cv_nominee": "nominee", "h3_nominee_model": "esmc_6b"}
    publisher._validate_h3_figure_source_data(path, qa)

    rows[4]["scope"] = "matched_family_member"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(publisher.CompactPublishError, match="role/scope"):
        publisher._validate_h3_figure_source_data(path, qa)


def test_existing_second_destination_rolls_back_first_without_overwrite(
    tmp_path: Path,
) -> None:
    publisher = _load_publisher()
    result_stage = tmp_path / "result-stage"
    figure_stage = tmp_path / "figure-stage"
    result_output = tmp_path / "result-active"
    figure_output = tmp_path / "figure-active"
    result_stage.mkdir()
    figure_stage.mkdir()
    (result_stage / "generic.txt").write_text("result-stage\n", encoding="utf-8")
    (figure_stage / "generic.txt").write_text("figure-stage\n", encoding="utf-8")
    figure_output.mkdir()
    marker = figure_output / "owner.txt"
    marker.write_text("pre-existing owner\n", encoding="utf-8")

    with pytest.raises(publisher.ArchiveError, match="overwrite"):
        publisher._commit_pair(
            result_stage,
            result_output,
            figure_stage,
            figure_output,
            lambda: None,
        )

    assert result_stage.is_dir()
    assert not result_output.exists()
    assert figure_stage.is_dir()
    assert marker.read_text(encoding="utf-8") == "pre-existing owner\n"


def test_postcommit_verification_failure_rolls_back_both(tmp_path: Path) -> None:
    publisher = _load_publisher()
    result_stage = tmp_path / "result-stage"
    figure_stage = tmp_path / "figure-stage"
    result_output = tmp_path / "result-active"
    figure_output = tmp_path / "figure-active"
    result_stage.mkdir()
    figure_stage.mkdir()

    def fail_verification() -> None:
        raise publisher.CompactPublishError("injected post-commit failure")

    with pytest.raises(publisher.CompactPublishError, match="injected"):
        publisher._commit_pair(
            result_stage,
            result_output,
            figure_stage,
            figure_output,
            fail_verification,
        )

    assert result_stage.is_dir() and figure_stage.is_dir()
    assert not result_output.exists() and not figure_output.exists()


def test_paths_and_source_have_no_placeholder_or_destructive_mode() -> None:
    publisher = _load_publisher()
    for unsafe in ("../escape", "/absolute", "a/./b", "a//b", "a\\b"):
        with pytest.raises(publisher.CompactPublishError):
            publisher._safe_relative(unsafe)
    source = SCRIPT.read_text(encoding="utf-8")
    assert "synthetic" not in source.lower()
    assert "placeholder" not in source.lower()
    assert "os.remove" not in source and "shutil.rmtree" not in source
    assert "_atomic_rename_noreplace" in source
    assert "_preserve_failed_stages" in source
