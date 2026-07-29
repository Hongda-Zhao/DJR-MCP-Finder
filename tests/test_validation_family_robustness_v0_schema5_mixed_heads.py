from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/validation_family_robustness_v0_schema5_mixed_heads.yaml"
SCORER = ROOT / "scripts/score_validation_family_robustness_v0_schema5_mixed_heads.py"
VALIDATOR = ROOT / "scripts/validate_validation_family_robustness_v0_schema5_mixed_heads.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema5_boundary_has_exact_eight_models_three_shards_and_nine_candidates() -> None:
    scorer = _load("schema5_contract", SCORER)
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    scorer._validate_config(config)
    assert config["schema_version"] == 5
    assert config["selection_feedback_permitted"] is False
    assert config["schema5_robustness_reranking_permitted"] is False
    assert config["released_v0_feedback_permitted"] is False
    assert config["bootstrap_replicates"] == 10_000
    assert config["bootstrap_seed"] == 20260728
    assert len(config["models"]) == 8
    assert len(config["primary_mixed_candidates"]) == 9
    assert set(config["embedding_registries"]) == {
        "viral_family",
        "graph_family",
        "hardnegative_matched",
    }
    assert all(set(registry) == set(config["models"]) for registry in config["embedding_registries"].values())


def test_system_registry_is_17_labels_16_unique_with_exact_all_6b_control() -> None:
    scorer = _load("schema5_registry", SCORER)
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    registry = scorer.build_system_registry(config)
    assert len(registry) == 17
    assert sum(row["unique_prediction_system"] for row in registry) == 16
    control = next(row for row in registry if row["system_id"] == "h12_esmc_6b__h3_esmc_6b")
    assert control["prediction_alias_of"] == "esmc_6b"
    assert control["head1_model"] == control["head2_model"] == control["head3_model"] == "esmc_6b"


def test_real_per_head_rows_are_recomposed_and_na_heads_are_never_invented() -> None:
    scorer = _load("schema5_compose", SCORER)
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    registry = scorer.build_system_registry(config)
    rows = []
    source_heads = {
        "v": ("viral_vma_djr", ("head1", "head2", "head3_phylum")),
        "c": ("cellular_djr_none", ("head1", "head2")),
        "b": ("background_non_djr", ("head1",)),
        "h": ("hard_non_djr", ("head1",)),
    }
    for model_index, model in enumerate(scorer.MODELS):
        for protein, (source, heads) in source_heads.items():
            for head in heads:
                label = "djr" if head == "head1" else "none"
                rows.append(
                    {
                        "model_id": model,
                        "protein_id": protein,
                        "source_dataset": source,
                        "paired_representative_id": protein + "r",
                        "paired_representative_protein_id": protein + "r",
                        "source_cluster_id": protein + "c",
                        "source_cluster_key": source + "::" + protein,
                        "dependence_block_id": protein + "block",
                        "train_relationship_stratum": "",
                        "head": head,
                        "truth_label": label,
                        "expected_prediction": label,
                        "member_probability": model_index / 10,
                        "member_raw_decision_score": model_index,
                        "member_prediction": label,
                        "member_predicted_label": label,
                        "member_correct": 1,
                        "representative_probability": model_index / 10,
                        "representative_raw_decision_score": model_index,
                        "representative_prediction": label,
                        "representative_predicted_label": label,
                        "representative_correct": 1,
                        "threshold": 0.5,
                        "applicable_to_source": 1,
                        "metric_eligible": 1,
                        "test_record": 0,
                    }
                )
    composed = scorer.compose_system_predictions(rows, registry)
    hybrid = [row for row in composed if row["system_id"] == "h12_esm2_650m__h3_esmc_300m"]
    assert {row["head_model_id"] for row in hybrid if row["head"] in {"head1", "head2"}} == {
        "esm2_650m"
    }
    assert {row["head_model_id"] for row in hybrid if row["head"] == "head3_phylum"} == {
        "esmc_300m"
    }
    assert not [
        row
        for row in composed
        if row["source_dataset"] in {"background_non_djr", "hard_non_djr"}
        and row["head"] != "head1"
    ]


def test_nested_bootstrap_is_fixed_seed_and_equal_block_cluster_member() -> None:
    scorer = _load("schema5_nested", SCORER)
    rows = [
        {"dependence_block_id": "b1", "source_cluster_key": "c1", "representative_correct": 1, "member_correct": 1},
        {"dependence_block_id": "b1", "source_cluster_key": "c1", "representative_correct": 1, "member_correct": 0},
        {"dependence_block_id": "b1", "source_cluster_key": "c2", "representative_correct": 0, "member_correct": 0},
        {"dependence_block_id": "b2", "source_cluster_key": "c3", "representative_correct": 1, "member_correct": 1},
    ]
    first = scorer.nested_summary(rows, replicates=200, seed=7)
    second = scorer.nested_summary(rows, replicates=200, seed=7)
    assert first[0]["representative_value"] == 0.75
    assert first[0]["member_value"] == 0.625
    assert first[0]["clusters_all_members_correct"] == 1
    for left, right in zip(first[1], second[1]):
        np.testing.assert_array_equal(left, right)


def test_source_specific_holm_and_contextual_deltas_do_not_rerank() -> None:
    scorer = _load("schema5_pairwise", SCORER)
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    registry = scorer.build_system_registry(config)
    path_summary = []
    path_boot = {}
    for system_index, system in enumerate(registry):
        for source in scorer.SOURCES:
            value = 0.9 + system_index * 1e-4
            path_summary.append(
                {"system_id": system["system_id"], "source_dataset": source, "member_value": value}
            )
            path_boot[(system["system_id"], source)] = np.full(100, value)
    # Make the all-6B alias exactly equal to its positive control source.
    for source in scorer.SOURCES:
        alias = "h12_esmc_6b__h3_esmc_6b"
        reference_value = next(
            row["member_value"]
            for row in path_summary
            if row["system_id"] == "esmc_6b" and row["source_dataset"] == source
        )
        next(row for row in path_summary if row["system_id"] == alias and row["source_dataset"] == source)[
            "member_value"
        ] = reference_value
        path_boot[(alias, source)] = path_boot[("esmc_6b", source)].copy()
    primary = scorer.pairwise_source_deltas(config, path_summary, path_boot)
    contextual = scorer.contextual_source_deltas(config, path_summary, path_boot)
    assert len(primary) == 36
    assert len(contextual) == 27
    assert all("not_reranking" in row["comparison_role"] for row in contextual)
    controls = [row for row in primary if row["positive_control"]]
    assert len(controls) == 4
    assert all(row["diagnostic_status"] == "positive_control_exact_equivalence" for row in controls)


def test_independent_validator_declares_scientific_boundary_gates() -> None:
    text = VALIDATOR.read_text(encoding="utf-8")
    assert "score_validation_family_robustness_v0_schema5_mixed_heads" not in text
    for phrase in (
        "mixed_heads_recomposed_from_real_per_record_predictions",
        "fixed_seed_nested_bootstrap_independently_recomputed",
        "source_specific_holm_diagnostics_recomputed",
        "train_only_cv_one_se_nomination_recomputed",
        "schema5_robustness_not_used_for_reranking",
        "schema4_two_model_per_record_continuity",
        "schema4_canonical_cache_full_recomputation_audit",
        "schema4_legacy_operator_runtime_and_exact_numeric_replay",
        "test_record_count_zero",
    ):
        assert phrase in text


def test_schema5_generalized_loader_does_not_index_two_model_selection_registry() -> None:
    text = SCORER.read_text(encoding="utf-8")
    assert "_build_model_contexts" in text
    assert "_verify_selected_model_artifacts" in text
    assert "selection[\"models\"][model_id]" not in text
    assert "full_14_model_registry_fallback" in text


def test_full_model_context_builder_resolves_all_six_nonselection_models(
    tmp_path: Path, monkeypatch,
) -> None:
    scorer = _load("schema5_full_registry", SCORER)
    comparison = tmp_path / "model_comparison.json"
    comparison.write_text(
        json.dumps(
            {
                "models": [
                    {"model_id": model, "label": model, "resolved_model_revision": model + "-rev"}
                    for model in scorer.MODELS
                ]
            }
        ),
        encoding="utf-8",
    )
    master = tmp_path / "master.tsv"
    master.write_text("protein_id\nfixture\n", encoding="utf-8")
    monkeypatch.setattr(
        scorer,
        "load_frozen_benchmark_selection",
        lambda *_args, **_kwargs: ({"fixture": True}, {"models": {"esm2_650m": {}}}),
    )
    called = []

    def verify(_config, model_id, _row, _manifest_sha):
        called.append(model_id)
        return {"model_id": model_id, "verified": True}

    monkeypatch.setattr(scorer, "_verify_selected_model_artifacts", verify)
    monkeypatch.setattr(
        scorer,
        "expand_benchmark_model",
        lambda _config, model_id: {
            "paths": {
                "embedding_output": str(tmp_path / f"base-{model_id}"),
                "result_output": str(tmp_path / f"result-{model_id}"),
            }
        },
    )
    config = {
        "benchmark_config": str(tmp_path / "benchmark.yaml"),
        "comparison_summary": str(comparison),
        "master_manifest": str(master),
        "embedding_registries": {
            "viral_family": {model: str(tmp_path / model) for model in scorer.MODELS}
        },
    }
    contexts = scorer._build_model_contexts(config)
    assert set(contexts) == set(scorer.MODELS)
    assert set(called) == set(scorer.MODELS)
    assert "esm2_3b" in contexts and "esmc_300m" in contexts


def test_amendment_d_pbs_reuses_exact_receipt_inventory_without_normalizing() -> None:
    text = (ROOT / "scripts/run_validation_family_robustness_v0_schema5_mixed_heads.pbs").read_text(
        encoding="utf-8"
    )
    scoring = text.index("score_validation_family_robustness_v0_schema5_mixed_heads.py")
    assert "normalize_validation_family_robustness_v0_schema5_embedding_attestations.py" not in text
    assert text.index("amendment_d_path_preflight=PASS") < scoring
    assert '"materialization_receipt_dir": 18' in text
    assert '"reuse_attestation_dir": 6' in text
    assert '"normalized_embedding_attestation_dir": 24' in text
    assert "config is the" in text and "sole authority for every path" in text
    assert "frozen read path points into writable Amendment-D root" in text
    assert "test ! -e \"$RESULTS\"" in text
    assert "test ! -e \"$VALIDATION\"" in text
    assert "test ! -e \"$FIGURES\"" in text
    assert "schema5_v1_amendment_d" in text
    assert "#PBS -l select=1:ncpus=4:mem=32gb" in text
    for assignment in (
        "OMP_NUM_THREADS=4",
        "MKL_NUM_THREADS=4",
        "OPENBLAS_NUM_THREADS=4",
        "PYTHONHASHSEED=20260724",
    ):
        assert assignment in text


def _schema4_binary_row(model_id: str) -> dict[str, object]:
    return {
        "model_id": model_id,
        "protein_id": f"p-{model_id}",
        "source_dataset": "background_non_djr",
        "paired_representative_id": f"r-{model_id}",
        "paired_representative_protein_id": f"r-{model_id}",
        "source_cluster_id": f"c-{model_id}",
        "source_cluster_key": f"background_non_djr::c-{model_id}",
        "dependence_block_id": f"b-{model_id}",
        "train_relationship_stratum": "no_train_relation",
        "head": "head1",
        "truth_label": "non_djr",
        "expected_prediction": "0",
        "member_probability": "0.0900000000000000",
        "member_raw_decision_score": "-100000.0",
        "member_prediction": "0",
        "member_predicted_label": "non_djr",
        "member_correct": "1",
        "representative_probability": "0.0800000000000000",
        "representative_raw_decision_score": "-60000.0",
        "representative_prediction": "0",
        "representative_predicted_label": "non_djr",
        "representative_correct": "1",
        "threshold": "0.5",
        "applicable_to_source": "1",
        "metric_eligible": "1",
        "test_record": "0",
    }


def _write_rows(module, path: Path, rows: list[dict[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        fields.extend(field for field in row if field not in fields)
    module._write_tsv(path, fields, rows)


def test_schema4_cache_requires_exact_legacy_operator_replay_before_all_or_none(
    tmp_path: Path,
) -> None:
    scorer = _load("schema5_cache", SCORER)
    schema4 = tmp_path / "schema4"
    schema4.mkdir()
    old = [
        _schema4_binary_row("esm2_650m"),
        _schema4_binary_row("esmc_6b"),
    ]
    _write_rows(scorer, schema4 / "predictions.tsv", old)
    fresh = [dict(row) for row in old]
    noncanonical = _schema4_binary_row("esmc_300m")
    fresh.append(noncanonical)
    config = {
        "schema4_result_dir": str(schema4),
        "schema4_expected_prediction_rows": 2,
    }
    canonicalized, audit, report = scorer._canonicalize_schema4_predictions(config, fresh)
    assert canonicalized[:2] == old
    assert canonicalized[2] is noncanonical
    assert len(audit) == report["row_level_audit_rows"] == 2
    assert report["status"] == "PASS"
    assert report["exact_numeric_string_comparisons"] == 10
    assert report["numeric_string_mismatches"] == 0
    assert report["numeric_fields"]["member_probability"]["nonexact_comparisons"] == 0
    assert report["numeric_fields"]["threshold"]["nonexact_comparisons"] == 0
    assert all(row["audit_status"] == "PASS" for row in audit)
    assert all(row["member_probability_exact_replay"] == 1 for row in audit)
    assert all(row["threshold_absolute_delta"] == 0.0 for row in audit)

    within_b_but_nonexact = [dict(row) for row in fresh]
    within_b_but_nonexact[0]["member_probability"] = (
        float(within_b_but_nonexact[0]["member_probability"]) + 3.0e-7
    )
    with pytest.raises(RuntimeError, match="exact numeric replay failed"):
        scorer._canonicalize_schema4_predictions(config, within_b_but_nonexact)

    bad = [dict(row) for row in fresh]
    bad[0]["member_probability"] = 0.091
    with pytest.raises(RuntimeError, match="exceeded retained Amendment-B upper bound"):
        scorer._canonicalize_schema4_predictions(config, bad)


def test_independent_validator_recomputes_every_schema4_audit_delta(
    tmp_path: Path,
) -> None:
    scorer = _load("schema5_cache_writer", SCORER)
    validator = _load("schema5_cache_validator", VALIDATOR)
    schema4 = tmp_path / "schema4"
    schema4.mkdir()
    old = [
        _schema4_binary_row("esm2_650m"),
        _schema4_binary_row("esmc_6b"),
    ]
    _write_rows(scorer, schema4 / "predictions.tsv", old)
    fresh = [dict(row) for row in old]
    config = {
        "schema4_result_dir": str(schema4),
        "schema4_expected_prediction_rows": 2,
    }
    canonicalized, audit, report = scorer._canonicalize_schema4_predictions(config, fresh)
    aggregate = scorer._schema4_audit_summary_rows(report)
    audit_path = tmp_path / "audit.tsv"
    aggregate_path = tmp_path / "aggregate.tsv"
    _write_rows(scorer, audit_path, audit)
    _write_rows(scorer, aggregate_path, aggregate)
    parsed_audit = validator._read(audit_path)
    parsed_aggregate = validator._read(aggregate_path)
    checked = validator._validate_schema4_canonical_cache(
        config,
        {"schema4_canonical_prediction_cache": report},
        canonicalized,
        parsed_audit,
        parsed_aggregate,
    )
    assert checked["row_level_audit_rows"] == 2
    assert checked["exact_numeric_string_comparisons"] == 10
    assert checked["numeric_string_mismatches"] == 0
    assert checked["test_records"] == 0

    tampered = [dict(row) for row in parsed_audit]
    tampered[0]["member_probability_absolute_delta"] = "0.1"
    with pytest.raises(RuntimeError, match="audit upper-bound failure"):
        validator._validate_schema4_canonical_cache(
            config,
            {"schema4_canonical_prediction_cache": report},
            canonicalized,
            tampered,
            parsed_aggregate,
        )


def test_schema4_cache_fails_closed_on_semantic_blank_threshold_and_reject_changes(
    tmp_path: Path,
) -> None:
    scorer = _load("schema5_cache_fail_closed", SCORER)
    schema4 = tmp_path / "schema4"
    schema4.mkdir()
    old = [
        _schema4_binary_row("esm2_650m"),
        _schema4_binary_row("esmc_6b"),
    ]
    _write_rows(scorer, schema4 / "predictions.tsv", old)
    config = {
        "schema4_result_dir": str(schema4),
        "schema4_expected_prediction_rows": 2,
    }
    semantic = [dict(row) for row in old]
    semantic[0]["train_relationship_stratum"] = "changed"
    with pytest.raises(RuntimeError, match="semantic mismatch"):
        scorer._canonicalize_schema4_predictions(config, semantic)
    blank = [dict(row) for row in old]
    blank[0]["member_raw_decision_score"] = ""
    with pytest.raises(RuntimeError, match="raw score is blank|blank mismatch"):
        scorer._canonicalize_schema4_predictions(config, blank)
    threshold = [dict(row) for row in old]
    threshold[0]["threshold"] = "0.5000000000000000"
    with pytest.raises(RuntimeError, match="exact numeric replay failed"):
        scorer._canonicalize_schema4_predictions(config, threshold)

    h3 = dict(old[0])
    h3.update(
        {
            "source_dataset": "viral_vma_djr",
            "head": "head3_phylum",
            "truth_label": "Nucleocytoviricota",
            "expected_prediction": "Nucleocytoviricota",
            "member_probability": "0.4",
            "member_raw_decision_score": "",
            "member_prediction": "Nucleocytoviricota",
            "member_predicted_label": "Nucleocytoviricota",
            "representative_probability": "0.4",
            "representative_raw_decision_score": "",
            "representative_prediction": "Nucleocytoviricota",
            "representative_predicted_label": "Nucleocytoviricota",
            "threshold": "0.5",
        }
    )
    with pytest.raises(RuntimeError, match="H3 reject/call derivation mismatch"):
        scorer._validate_recomputed_decisions(h3)


def test_amendment_d_preserves_c_replay_and_adds_h3_display_contract() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    protocol = (ROOT / "VALIDATION_FAMILY_ROBUSTNESS_V0_SCHEMA5_MIXED_HEADS_PROTOCOL.md").read_text(
        encoding="utf-8"
    )
    assert config["protocol_amendment"] == "D_h3_rare_subgroup_transparency_no_model_change"
    assert config["schema4_expected_prediction_rows"] == 92_844
    assert config["schema4_recomputation_tolerances"] == {
        "probability": {"absolute": 5e-7, "relative": 1e-6},
        "raw_decision_score": {"absolute": 1e-5, "relative": 1e-6},
        "threshold": {"absolute": 0.0, "relative": 0.0},
    }
    assert "No model-specific or data-adaptive enlargement is permitted" in protocol
    operator = config["legacy_schema4_numerical_operator"]
    assert operator["operator_id"] == "schema4_job_4968695_python3117_blas_threads4"
    assert operator["canonical_schema4_job"] == 4968695
    assert operator["diagnostic_jobs"]["schema4_canonical"]["overall_exit_status"] == 1
    assert operator["diagnostic_jobs"]["exact_threads4_replay"]["job_id"] == 4968820
    assert operator["exact_numeric_string_replay_required"] is True
    assert operator["amendment_b_tolerances_retained_as_upper_bound"] is True
    assert "4968820` was an exact-numeric/finite/Test diagnostic only" in protocol
    assert "Post-result H3 display-contract amendment D" in protocol
    h3 = config["h3_rare_endpoint_contract"]
    assert h3["model_inference_repeated_for_subgroups"] is False
    assert h3["refit_recalibration_or_threshold_change_permitted"] is False
    assert h3["endpoints"]["Produgelaviricota_reject_recall"] == {
        "endpoint_role": "descriptive_subgroup",
        "expected_records": 7,
        "expected_parents": 2,
        "expected_dependence_blocks": 2,
        "bootstrap_seed_offset": 6100,
        "interpretation": "rare_formal_phylum_rejection_descriptive_not_general_unknown_detection",
    }
    assert h3["endpoints"]["literature_unclassified_reject_recall"][
        "interpretation"
    ] == "single_record_descriptive_only_no_generalization"
    assert h3["endpoints"]["rare_or_unclassified_reject_recall"][
        "endpoint_role"
    ] == "secondary_pooled_diagnostic"
    assert tuple(config["amendment_d_required_byte_equivalent_artifacts"]) == (
        "single_model_predictions.tsv",
        "system_predictions.tsv",
        "system_expected_path_predictions.tsv",
        "system_registry.tsv",
        "train_cv_candidate_summary.tsv",
        "accuracy_cost_pareto.tsv",
        "candidate_nomination.tsv",
    )
    assert config["amendment_c_result_checksums_sha256"] == (
        "aa9f3cef647487d4eaec7749ceeb49c58085657a38d0d99c7577f3655448e72c"
    )
    assert config["amendment_c_validation_sha256"] == (
        "2b63cecae7788cce3d4c8ef96d48bf1becfbe8d74b9e9c084b2ab69a47542bcb"
    )
    assert config["schema3_family_member_manifest_sha256"] == (
        "8cd9e9ce45ad965eb745cc4ecdf08d7e3205f57b830bca00bcf0041e5bcdf541"
    )
    assert "8cd9e9ce45ad965eb745cc4ecdf08d7e3205f57b830bca00bcf0041e5bcdf541" in protocol
    for filename in (
        "schema4_recomputation_audit.tsv",
        "schema4_recomputation_audit_summary.tsv",
        "legacy_numerical_operator_runtime.json",
    ):
        assert filename in SCORER.read_text(encoding="utf-8")
        assert filename in VALIDATOR.read_text(encoding="utf-8")


def test_amendment_d_h3_subgroups_come_only_from_frozen_manifest_and_raw_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    scorer = _load("schema5_h3_amendment_d", SCORER)
    validator = _load("schema5_h3_amendment_d_validator", VALIDATOR)
    manifest = tmp_path / "family.tsv"
    rows: list[dict[str, object]] = []
    for index in range(7):
        rows.append(
            {
                "protein_id": f"produ-{index}",
                "source_dataset": "viral_vma_djr",
                "source_cluster_id": "produ-a" if index < 4 else "produ-b",
                "source_cluster_key": "viral_vma_djr::produ-a"
                if index < 4
                else "viral_vma_djr::produ-b",
                "dependence_block_id": "block-a" if index < 4 else "block-b",
                "h3_analysis_included": 1,
                "head3_operational_label": "unknown/other",
                "head3_status": "rare_formal_unknown_diagnostic",
                "head3_phylum_label": "Produgelaviricota",
            }
        )
    rows.append(
        {
            "protein_id": "literature-0",
            "source_dataset": "viral_vma_djr",
            "source_cluster_id": "literature",
            "source_cluster_key": "viral_vma_djr::literature",
            "dependence_block_id": "block-c",
            "h3_analysis_included": 1,
            "head3_operational_label": "unknown/other",
            "head3_status": "literature_unclassified_unknown_diagnostic",
            "head3_phylum_label": "",
        }
    )
    _write_rows(scorer, manifest, rows)
    schema4_config = tmp_path / "schema4.yaml"
    schema4_config.write_text(
        yaml.safe_dump({"schema3": {"family_member_manifest": str(manifest)}}),
        encoding="utf-8",
    )
    frozen_sha256 = scorer._sha256(manifest)
    monkeypatch.setattr(
        scorer, "SCHEMA3_FAMILY_MEMBER_MANIFEST_SHA256", frozen_sha256
    )
    monkeypatch.setattr(
        validator, "SCHEMA3_FAMILY_MEMBER_MANIFEST_SHA256", frozen_sha256
    )
    config = {
        "schema4_config": str(schema4_config),
        "schema3_family_member_manifest_sha256": frozen_sha256,
    }
    provenance = {
        "family_manifest": str(manifest),
        "family_manifest_sha256": frozen_sha256,
    }
    mapping = scorer._load_h3_rare_subgroups(config, provenance)
    assert list(mapping.values()).count("Produgelaviricota") == 7
    assert list(mapping.values()).count("literature-unclassified") == 1
    assert validator._load_h3_rare_subgroups(
        config, provenance["family_manifest_sha256"]
    ) == mapping
    bad_config = dict(config)
    bad_config["schema3_family_member_manifest_sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="manifest lineage changed"):
        scorer._load_h3_rare_subgroups(bad_config, provenance)
    with pytest.raises(RuntimeError, match="differs from result lineage"):
        validator._load_h3_rare_subgroups(bad_config, frozen_sha256)

    prediction_rows = [
        {
            "dependence_block_id": row["dependence_block_id"],
            "source_cluster_key": row["source_cluster_key"],
            "member_predicted_label": "unknown/other" if index != 4 else "Nucleocytoviricota",
            "representative_predicted_label": "unknown/other"
            if row["source_cluster_id"] != "produ-b"
            else "Nucleocytoviricota",
        }
        for index, row in enumerate(rows)
    ]
    assert scorer._raw_reject_counts(prediction_rows) == {
        "raw_member_reject_k": 7,
        "raw_member_reject_n": 8,
        "raw_representative_reject_k": 2,
        "raw_representative_reject_n": 3,
    }
    point_only, status = scorer._finalize_h3_reject_uncertainty(
        {
            "representative_ci_low": 1.0,
            "representative_ci_high": 1.0,
            "member_ci_low": 1.0,
            "member_ci_high": 1.0,
            "delta_ci_low": 0.0,
            "delta_ci_high": 0.0,
            "bootstrap_replicates": 10_000,
        },
        dependence_blocks=1,
    )
    assert status == "point_only_ci_not_estimable_single_block"
    assert point_only["bootstrap_replicates"] == 0
    assert all(point_only[field] == "" for field in (
        "representative_ci_low",
        "representative_ci_high",
        "member_ci_low",
        "member_ci_high",
        "delta_ci_low",
        "delta_ci_high",
    ))


def _runtime_fixture(
    config: dict[str, object], tmp_path: Path,
) -> tuple[dict[str, object], dict[str, str], list[dict[str, object]]]:
    copied = dict(config)
    operator = dict(copied["legacy_schema4_numerical_operator"])
    venv = tmp_path / "legacy-venv"
    operator["venv_root"] = str(venv)
    copied["legacy_schema4_numerical_operator"] = operator
    copied["protocol"] = str(
        ROOT / "VALIDATION_FAMILY_ROBUSTNESS_V0_SCHEMA5_MIXED_HEADS_PROTOCOL.md"
    )
    environ = {
        "OMP_NUM_THREADS": "4",
        "MKL_NUM_THREADS": "4",
        "OPENBLAS_NUM_THREADS": "4",
        "PYTHONHASHSEED": "20260724",
        "SCHEMA5_LEGACY_OPERATOR_ID": "schema4_job_4968695_python3117_blas_threads4",
        "SCHEMA5_PBS_NCPUS": "4",
        "SCHEMA5_PBS_MEMORY_GB": "32",
        "SCHEMA5_PYTHON_MODULE": "Python/3.11.7",
        "VIRTUAL_ENV": str(venv),
        "PBS_JOBID": "fixture.server",
        "PBS_JOBNAME": "schema5-fixture",
    }
    pools = [
        {
            "user_api": "blas",
            "internal_api": "openblas",
            "prefix": "libscipy_openblas_numpy",
            "version": "0.3.31",
            "num_threads": 4,
            "filepath": str(tmp_path / "libscipy_openblas_numpy.so"),
        },
        {
            "user_api": "blas",
            "internal_api": "openblas",
            "prefix": "libscipy_openblas_scipy",
            "version": "0.3.30",
            "num_threads": 4,
            "filepath": str(tmp_path / "libscipy_openblas_scipy.so"),
        },
        {
            "user_api": "openmp",
            "internal_api": "openmp",
            "prefix": "libgomp",
            "version": "fixture",
            "num_threads": 4,
            "filepath": str(tmp_path / "libgomp.so"),
        },
    ]
    return copied, environ, pools


def test_runtime_attestation_accepts_only_exact_four_thread_operator(
    tmp_path: Path,
) -> None:
    scorer = _load("schema5_runtime_attestation", SCORER)
    config, environ, pools = _runtime_fixture(
        yaml.safe_load(CONFIG.read_text(encoding="utf-8")), tmp_path
    )
    executable = str(Path(config["legacy_schema4_numerical_operator"]["venv_root"]) / "bin/python")
    attestation = scorer._legacy_operator_runtime_attestation(
        config,
        CONFIG,
        environ=environ,
        observed_python_version="3.11.7",
        observed_executable=executable,
        observed_threadpools=pools,
    )
    assert attestation["status"] == "PASS"
    assert attestation["threadpool_count"] == 3
    assert {pool["num_threads"] for pool in attestation["threadpools"]} == {4}

    wrong = [dict(pool) for pool in pools]
    wrong[0]["num_threads"] = 12
    with pytest.raises(RuntimeError, match="threadpool attestation failed"):
        scorer._legacy_operator_runtime_attestation(
            config,
            CONFIG,
            environ=environ,
            observed_python_version="3.11.7",
            observed_executable=executable,
            observed_threadpools=wrong,
        )


def test_independent_validator_rejects_tampered_runtime_attestation(
    tmp_path: Path,
) -> None:
    scorer = _load("schema5_runtime_writer", SCORER)
    validator = _load("schema5_runtime_validator", VALIDATOR)
    config, environ, pools = _runtime_fixture(
        yaml.safe_load(CONFIG.read_text(encoding="utf-8")), tmp_path
    )
    executable = str(Path(config["legacy_schema4_numerical_operator"]["venv_root"]) / "bin/python")
    runtime = scorer._legacy_operator_runtime_attestation(
        config,
        CONFIG,
        environ=environ,
        observed_python_version="3.11.7",
        observed_executable=executable,
        observed_threadpools=pools,
    )
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    runtime_path = result_dir / "legacy_numerical_operator_runtime.json"
    runtime_path.write_text(json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    runtime_sha = scorer._sha256(runtime_path)
    summary = {
        "legacy_numerical_operator_runtime": {
            "status": "PASS",
            "operator_id": scorer.LEGACY_OPERATOR_ID,
            "artifact": runtime_path.name,
            "artifact_sha256": runtime_sha,
            "pbs_job_id": "fixture.server",
            "python_version": "3.11.7",
            "threadpool_count": 3,
            "exact_numeric_string_replay_required": True,
        },
        "lineage_sha256": {"legacy_numerical_operator_runtime": runtime_sha},
    }
    summary["legacy_numerical_operator_runtime"]["runtime_preload_modules"] = [
        "scipy.linalg",
        "sklearn.linear_model",
    ]
    checked = validator._validate_legacy_operator_runtime(
        config, CONFIG, result_dir, summary
    )
    assert checked["status"] == "PASS"

    runtime["threadpools"][0]["num_threads"] = 12
    runtime_path.write_text(json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="threadpool record mismatch"):
        validator._validate_legacy_operator_runtime(config, CONFIG, result_dir, summary)


def test_runtime_preload_occurs_before_threadpool_attestation_and_inference_boundary(
    tmp_path: Path,
) -> None:
    scorer = _load("schema5_runtime_order", SCORER)
    config, environ, pools = _runtime_fixture(
        yaml.safe_load(CONFIG.read_text(encoding="utf-8")), tmp_path
    )
    executable = str(Path(config["legacy_schema4_numerical_operator"]["venv_root"]) / "bin/python")
    events: list[str] = []

    def preload(_config):
        events.append("preload")
        return [
            {
                "module": name,
                "package_version": "fixture",
                "module_file": str(tmp_path / f"{name}.py"),
            }
            for name in ("scipy.linalg", "sklearn.linear_model")
        ]

    def inspect_pools():
        events.append("inspect_threadpools")
        return pools

    scorer._legacy_operator_runtime_attestation(
        config,
        CONFIG,
        environ=environ,
        observed_python_version="3.11.7",
        observed_executable=executable,
        preload_fn=preload,
        threadpool_info_fn=inspect_pools,
    )
    assert events == ["preload", "inspect_threadpools"]
    source = SCORER.read_text(encoding="utf-8")
    assert source.index("_legacy_operator_runtime_attestation(config, config_path)") < source.index(
        "_load_single_model_predictions(config)"
    )
