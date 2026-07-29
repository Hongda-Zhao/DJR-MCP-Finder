from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from djrmcp_finder.stages import benchmark_embedding, classifier
from djrmcp_finder import test_ledger


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "evaluate_selected_benchmark_model", SCRIPTS / "evaluate_selected_benchmark_model.py"
)
assert SPEC is not None and SPEC.loader is not None
EVALUATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATOR)

SUMMARY_SPEC = importlib.util.spec_from_file_location(
    "summarize_model_benchmark", SCRIPTS / "summarize_model_benchmark.py"
)
assert SUMMARY_SPEC is not None and SUMMARY_SPEC.loader is not None
SUMMARY = importlib.util.module_from_spec(SUMMARY_SPEC)
SUMMARY_SPEC.loader.exec_module(SUMMARY)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_partial_resume_is_bound_to_resolved_model_revision() -> None:
    benchmark_embedding._validate_resume_revision(None, "commit-a")
    benchmark_embedding._validate_resume_revision(
        {"resolved_model_revision": "commit-a"}, "commit-a"
    )
    with pytest.raises(RuntimeError, match="across resolved model revisions"):
        benchmark_embedding._validate_resume_revision(
            {"resolved_model_revision": "commit-a"}, "commit-b"
        )
    with pytest.raises(RuntimeError, match="across resolved model revisions"):
        benchmark_embedding._validate_resume_revision({}, "commit-a")


def test_comparison_checksum_requires_exact_frozen_triplet(tmp_path: Path) -> None:
    comparison = tmp_path / "model_comparison.json"
    table = tmp_path / "model_comparison.tsv"
    folds = tmp_path / "fold_scores.tsv"
    comparison.write_text("{}\n", encoding="utf-8")
    table.write_text("model_id\n", encoding="utf-8")
    folds.write_text("model_id\n", encoding="utf-8")
    (tmp_path / "COMPARISON_CHECKSUMS.sha256").write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in (table, folds, comparison)),
        encoding="utf-8",
    )
    assert set(EVALUATOR._verify_comparison_checksums(comparison)) == {
        "model_comparison.json",
        "model_comparison.tsv",
        "fold_scores.tsv",
    }
    comparison.write_text('{"selected_model_id":"forged"}\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        EVALUATOR._verify_comparison_checksums(comparison)


def test_test_reservation_is_exclusive_and_crash_fail_closed(tmp_path: Path) -> None:
    result_dir = tmp_path / "results" / "selected"
    result_dir.mkdir(parents=True)
    state_dir = tmp_path / "test_state"
    embedding_dir = tmp_path / "embeddings" / "selected"
    embedding_dir.mkdir(parents=True)
    manifest = tmp_path / "manifest.tsv"
    manifest.write_text("protein_id\tsplit\np1\ttest\n", encoding="utf-8")
    fasta = tmp_path / "input.faa"
    fasta.write_text(">p1\nAAAA\n", encoding="utf-8")
    config_path = tmp_path / "benchmark.yaml"
    config_path.write_text("frozen: true\n", encoding="utf-8")
    comparison_dir = tmp_path / "comparison"
    comparison_dir.mkdir()
    comparison_path = comparison_dir / "model_comparison.json"
    comparison_path.write_text("{}\n", encoding="utf-8")
    (comparison_dir / "model_comparison.tsv").write_text("model_id\n", encoding="utf-8")
    (comparison_dir / "fold_scores.tsv").write_text("model_id\n", encoding="utf-8")
    comparison_hashes = {
        path.name: _sha256(path)
        for path in (
            comparison_path,
            comparison_dir / "model_comparison.tsv",
            comparison_dir / "fold_scores.tsv",
        )
    }
    for name in classifier.TEST_EMBEDDING_ARTIFACTS:
        (embedding_dir / name).write_bytes(name.encode("utf-8"))
    (embedding_dir / "CHECKSUMS.sha256").write_text(
        "".join(
            f"{_sha256(embedding_dir / name)}  {name}\n"
            for name in sorted(classifier.TEST_EMBEDDING_ARTIFACTS)
        ),
        encoding="utf-8",
    )
    (result_dir / "metrics").mkdir()
    (result_dir / "models").mkdir()
    for relative in (
        "calibration.json",
        "metrics/cross_validation.json",
        "metrics/validation_metrics.json",
    ):
        (result_dir / relative).write_text("{}\n", encoding="utf-8")
    for head in classifier.HEAD_SPECS:
        (result_dir / "models" / f"{head}.joblib").write_bytes(head.encode("utf-8"))
    candidate_ids = [f"candidate_{index}" for index in range(14)]
    selected_model_id = candidate_ids[5]
    selected_evidence = {
        "input_sha256": {
            name: _sha256(
                (embedding_dir if location == "embedding" else result_dir) / relative
            )
            for name, (location, relative) in classifier.TEST_SELECTED_INPUT_FILES.items()
        },
        "embedding_artifact_sha256": {
            name: _sha256(embedding_dir / name)
            for name in classifier.TEST_EMBEDDING_ARTIFACTS
        },
        "model_sha256": {
            head: _sha256(result_dir / "models" / f"{head}.joblib")
            for head in classifier.HEAD_SPECS
        },
    }
    identity_payload = {
        "schema_version": 1,
        "project_name": "DJR-MCP-Finder",
        "project_version": "project-v0-test",
        "manifest_path": str(manifest.resolve()),
        "manifest_sha256": _sha256(manifest),
        "model_input_fasta_path": str(fasta.resolve()),
        "model_input_fasta_sha256": _sha256(fasta),
        "config_path": str(config_path.resolve()),
        "config_sha256": _sha256(config_path),
        "comparison_path": str(comparison_path.resolve()),
        "comparison_sha256": comparison_hashes,
        "weights": classifier.TEST_SELECTION_WEIGHTS,
        "candidate_model_ids": candidate_ids,
        "selected_model_id": selected_model_id,
        "selected_result_dir": str(result_dir.resolve()),
        "selected_embedding_dir": str(embedding_dir.resolve()),
        "selected_candidate_evidence": selected_evidence,
    }
    authorization_core = {
        "schema_version": 2,
        "status": "authorized_for_single_test_evaluation",
        "single_test_only": True,
        "selection_evidence_scope": "train_cv_and_validation_only",
        "test_labels_or_metrics_read_for_selection": False,
        "created_utc": "2026-07-23T00:00:00+00:00",
        "selected_model_id": selected_model_id,
        "selected_result_dir": str(result_dir.resolve()),
        "selected_embedding_dir": str(embedding_dir.resolve()),
        "project_test_state_dir": str(state_dir.resolve()),
        "project_test_identity_payload": identity_payload,
        "project_test_identity": EVALUATOR._canonical_sha256(identity_payload),
        "weights": {"head1": 0.60, "head2": 0.30, "head3_phylum": 0.10},
        "candidate_model_ids": candidate_ids,
        "candidate_count": len(candidate_ids),
        "manifest_sha256": _sha256(manifest),
        "model_input_fasta_path": str(fasta.resolve()),
        "model_input_fasta_sha256": _sha256(fasta),
        "config_path": str(config_path.resolve()),
        "config_sha256": _sha256(config_path),
        "comparison_path": str(comparison_path.resolve()),
        "comparison_sha256": comparison_hashes,
        "selected_candidate_evidence": selected_evidence,
    }
    authorization = dict(authorization_core)
    authorization["authorization_id"] = EVALUATOR._canonical_sha256(authorization_core)
    authorization_path = state_dir / "TEST_SELECTION_AUTHORIZATION.json"
    authorization_path.parent.mkdir()
    authorization_path.write_text(
        json.dumps(authorization, sort_keys=True) + "\n", encoding="utf-8"
    )
    config = {
        "project": {
            "name": "DJR-MCP-Finder",
            "version": "project-v0-test",
        },
        "paths": {
            "v0_manifest": str(manifest.resolve()),
            "v0_fasta": str(fasta.resolve()),
            "embedding_output": str(embedding_dir.resolve()),
            "result_output": str(result_dir.resolve()),
            "test_state_dir": str(state_dir.resolve()),
        },
        "embedding": {"benchmark_model_id": selected_model_id},
        "benchmark": {"models": {model_id: {} for model_id in candidate_ids}},
        "test_selection_authorization": {
            "path": str(authorization_path),
            "state_dir": str(state_dir.resolve()),
            "sha256": _sha256(authorization_path),
            "authorization_id": authorization["authorization_id"],
            "project_test_identity": authorization["project_test_identity"],
            "selected_model_id": selected_model_id,
        },
    }
    observed_path, observed = classifier._validate_test_authorization(
        config, result_dir, manifest
    )
    config["benchmark"]["models"]["late_unfrozen_candidate"] = {}
    with pytest.raises(RuntimeError, match="authorization lineage is invalid"):
        classifier._validate_test_authorization(config, result_dir, manifest)
    del config["benchmark"]["models"]["late_unfrozen_candidate"]
    reservation_path, _ = classifier._reserve_test_evaluation(
        state_dir, observed_path, observed
    )
    assert reservation_path.is_file()
    with pytest.raises(RuntimeError, match="already reserved"):
        classifier._reserve_test_evaluation(state_dir, observed_path, observed)
    alternate_result_dir = tmp_path / "results" / "replacement_selected"
    alternate_result_dir.mkdir()
    assert not reservation_path.is_relative_to(result_dir)
    assert not reservation_path.is_relative_to(alternate_result_dir)
    with pytest.raises(RuntimeError, match="already reserved"):
        classifier._reserve_test_evaluation(state_dir, observed_path, observed)


def test_any_alternate_completion_marker_blocks_test_preflight(tmp_path: Path) -> None:
    result_dir = tmp_path / "selected"
    nested = result_dir / "copied"
    nested.mkdir(parents=True)
    alternate = nested / "FINAL_TEST_EVALUATED_copy.json"
    alternate.write_text("{}\n", encoding="utf-8")
    assert classifier._existing_test_completion_markers(result_dir) == [alternate]


def test_candidate_registry_and_h3_unknown_output_are_dynamic() -> None:
    candidate_ids = [f"model_{index}" for index in range(14)]
    config = {"benchmark": {"models": {model_id: {} for model_id in candidate_ids}}}
    assert EVALUATOR._registry_candidate_ids(config) == candidate_ids
    assert classifier._format_head3_prediction(
        -1, ["Nucleocytoviricota", "Preplasmiviricota"]
    ) == "unknown/other"
    assert classifier._format_head3_prediction(None, ["known"]) == "not_reached"
    assert classifier._format_head3_prediction(0, ["known"]) == "known"


def test_selection_weights_and_development_only_scope_remain_frozen() -> None:
    assert EVALUATOR.EXPECTED_WEIGHTS == {
        "head1": 0.60,
        "head2": 0.30,
        "head3_phylum": 0.10,
    }
    evaluator_source = (SCRIPTS / "evaluate_selected_benchmark_model.py").read_text(
        encoding="utf-8"
    )
    summary_source = (SCRIPTS / "summarize_model_benchmark.py").read_text(
        encoding="utf-8"
    )
    assert '"selection_evidence_scope": "train_cv_and_validation_only"' in evaluator_source
    assert '"test_labels_or_metrics_read_for_selection": False' in evaluator_source
    assert "forbidden_test_artifacts" in summary_source
    assert "frozen_test_metrics.json" in summary_source


def test_production_identity_survives_copy_result_root_and_state_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(test_ledger, "PRODUCTION_LEDGER_REGISTRY_ROOT", tmp_path / "ledger")
    base = {
        "project": {"name": "DJR-MCP-Finder", "version": "project-v0"},
        "paths": {
            "v0_manifest": "data/processed/v0/master_manifest.tsv",
            "v0_fasta": "data/interim/v0/model_representatives.faa",
            "embedding_output": "data/processed/embeddings/selected",
            "result_output": "results/model_benchmark_v0/selected",
            "benchmark_cv_fold_map": "results/folds.tsv",
            "benchmark_cv_fold_metadata": "results/folds.json",
        },
        "embedding": {"window_residues": 1022, "stride": 511},
        "classifier": {"cross_validation_folds": 5},
        "benchmark": {"models": {"esm2_650m": {"license": "MIT"}}},
    }
    copied = json.loads(json.dumps(base))
    copied["paths"].update(
        {
            "v0_manifest": "/copied/project/master_manifest.tsv",
            "v0_fasta": "/copied/project/model_representatives.faa",
            "embedding_output": "/new/embedding/root",
            "result_output": "/new/result/root",
        }
    )
    copied["benchmark"]["models"]["esm2_650m"]["reuse_result"] = "/new/result/root"
    copied["benchmark"]["models"]["esm2_650m"]["reuse_embedding"] = "/new/embed/root"
    kwargs = {
        "manifest_sha256": test_ledger.PRODUCTION_MANIFEST_SHA256,
        "fasta_sha256": "f" * 64,
        "selection_decision_sha256": "c" * 64,
        "weights": classifier.TEST_SELECTION_WEIGHTS,
        "candidate_model_ids": ["esm2_650m"],
        "selected_model_id": "esm2_650m",
        "selected_candidate_evidence": {"model_sha256": {"head1": "a" * 64}},
    }
    first_payload = test_ledger.content_identity_payload(config=base, **kwargs)
    copied_payload = test_ledger.content_identity_payload(config=copied, **kwargs)
    assert first_payload == copied_payload
    decision = {
        "schema_version": 3,
        "weights": classifier.TEST_SELECTION_WEIGHTS,
        "validation_regression_tolerance": 0.01,
        "tie_rule": "paired",
        "tie_break_order": ["fpr", "speed", "license", "score/id"],
        "speed_tie_break_policy": "same contract only",
        "candidate_model_ids": ["esm2_650m"],
        "selected_model_id": "esm2_650m",
        "highest_selectable_cv_model_id": "esm2_650m",
        "candidate_artifact_hashes": {"esm2_650m": {"models": "a" * 64}},
        "config_path": "relative/config.yaml",
        "models": [
            {
                "model_id": "esm2_650m",
                "selected": True,
                "selectable": True,
                "result_dir": "relative/results/esm2_650m",
                "embedding_dir": "relative/embeddings/esm2_650m",
            }
        ],
    }
    relocated_decision = json.loads(json.dumps(decision))
    relocated_decision["config_path"] = "/copied/config.yaml"
    relocated_decision["models"][0]["result_dir"] = "/copied/results/esm2_650m"
    relocated_decision["models"][0]["embedding_dir"] = "/copied/embeddings/esm2_650m"
    assert test_ledger.selection_decision_sha256(
        decision
    ) == test_ledger.selection_decision_sha256(relocated_decision)
    identity = test_ledger.canonical_sha256(first_payload)
    mode, registry, state_dir, claim_path = test_ledger.resolve_test_state_locations(
        config=base,
        manifest_sha256=test_ledger.PRODUCTION_MANIFEST_SHA256,
        identity=identity,
    )
    assert mode == test_ledger.PRODUCTION_LEDGER_MODE
    assert registry == (tmp_path / "ledger").resolve()
    assert claim_path is not None

    claim_path.parent.mkdir(parents=True)
    claim_path.write_text(
        json.dumps({"project_test_identity": identity}) + "\n", encoding="utf-8"
    )
    authorization = state_dir / "TEST_SELECTION_AUTHORIZATION.json"
    authorization.parent.mkdir(parents=True)
    authorization.write_text(
        json.dumps({"project_test_identity": identity}) + "\n", encoding="utf-8"
    )
    renamed = state_dir.with_name(f"archived-{identity}")
    state_dir.rename(renamed)
    assert test_ledger.matching_identity_artifacts(registry, identity) == sorted(
        [claim_path.resolve(), (renamed / authorization.name).resolve()]
    )

    overridden = json.loads(json.dumps(base))
    overridden["paths"]["test_state_dir"] = str(tmp_path / "bypass")
    with pytest.raises(RuntimeError, match="overrides are forbidden"):
        test_ledger.resolve_test_state_locations(
            config=overridden,
            manifest_sha256=test_ledger.PRODUCTION_MANIFEST_SHA256,
            identity=identity,
        )


def test_production_cohort_identity_is_independent_of_selection_and_metric_revision() -> None:
    base = {
        "project": {
            "name": "DJR-MCP-Finder",
            "version": "project-v0-model-benchmark__source-database-v3-560",
        },
        "paths": {},
        "benchmark": {"models": {"esm2_650m": {}}},
    }
    revised = json.loads(json.dumps(base))
    revised["project"]["version"] = (
        "project-v0-model-benchmark-metric-revision-1__data-curation-v3-560"
    )
    revised["project"]["name"] = "attempted-selection-specific-project-name"
    revised["benchmark"]["models"] = {"esm2_3b": {}}
    manifest_sha256 = test_ledger.PRODUCTION_MANIFEST_SHA256
    fasta_sha256 = "f" * 64
    first_cohort = test_ledger.cohort_identity_payload(
        config=base,
        manifest_sha256=manifest_sha256,
        fasta_sha256=fasta_sha256,
    )
    revised_cohort = test_ledger.cohort_identity_payload(
        config=revised,
        manifest_sha256=manifest_sha256,
        fasta_sha256=fasta_sha256,
    )
    assert first_cohort == revised_cohort
    assert first_cohort["project_data_cohort_id"] == test_ledger.PRODUCTION_COHORT_ID
    assert "selected_model_id" not in first_cohort
    assert test_ledger.canonical_sha256(first_cohort) == test_ledger.canonical_sha256(
        revised_cohort
    )

    common = {
        "manifest_sha256": manifest_sha256,
        "fasta_sha256": fasta_sha256,
        "selection_decision_sha256": "d" * 64,
        "weights": classifier.TEST_SELECTION_WEIGHTS,
        "candidate_model_ids": ["esm2_650m", "esm2_3b"],
        "selected_candidate_evidence": {"model_sha256": {"head1": "a" * 64}},
    }
    first_selection = test_ledger.content_identity_payload(
        config=base, selected_model_id="esm2_650m", **common
    )
    revised_selection = test_ledger.content_identity_payload(
        config=revised, selected_model_id="esm2_3b", **common
    )
    assert test_ledger.canonical_sha256(
        first_selection
    ) != test_ledger.canonical_sha256(revised_selection)


def test_cohort_scan_links_legacy_claim_authorization_and_receipt_across_selection(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "ledger"
    manifest_sha256 = test_ledger.PRODUCTION_MANIFEST_SHA256
    fasta_sha256 = "f" * 64
    config = {
        "project": {
            "name": "DJR-MCP-Finder",
            "version": "project-v0-model-benchmark-metric-revision-1",
        }
    }
    cohort_payload = test_ledger.cohort_identity_payload(
        config=config,
        manifest_sha256=manifest_sha256,
        fasta_sha256=fasta_sha256,
    )
    cohort_identity = test_ledger.canonical_sha256(cohort_payload)
    legacy_selection_identity = "a" * 64
    legacy_payload = {
        "schema_version": 2,
        "manifest_sha256": manifest_sha256,
        "model_input_fasta_sha256": fasta_sha256,
        "selected_model_id": "esm2_650m",
    }
    claim = registry / "identity_claims" / f"{legacy_selection_identity}.json"
    authorization = (
        registry
        / "states"
        / f"archived-{legacy_selection_identity}"
        / "TEST_SELECTION_AUTHORIZATION.json"
    )
    receipt = authorization.with_name("TEST_EVALUATION_RECEIPT.json")
    claim.parent.mkdir(parents=True)
    authorization.parent.mkdir(parents=True)
    claim.write_text(
        json.dumps(
            {
                "project_test_identity": legacy_selection_identity,
                "project_test_identity_payload": legacy_payload,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    authorization.write_text(
        json.dumps(
            {
                "project_test_identity": legacy_selection_identity,
                "manifest_sha256": manifest_sha256,
                "model_input_fasta_sha256": fasta_sha256,
                "selected_model_id": "esm2_650m",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    receipt.write_text(
        json.dumps(
            {
                "project_test_identity": legacy_selection_identity,
                "selected_model_id": "esm2_650m",
                "status": "complete",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    matches = test_ledger.matching_cohort_artifacts(
        registry,
        cohort_identity=cohort_identity,
        manifest_sha256=manifest_sha256,
        fasta_sha256=fasta_sha256,
    )
    assert matches == sorted(
        [claim.resolve(), authorization.resolve(), receipt.resolve()]
    )

    new_claim_path = test_ledger.production_cohort_claim_path(
        registry, cohort_identity
    )
    assert new_claim_path == (
        registry.resolve() / "cohort_claims" / f"{cohort_identity}.json"
    )


def test_development_only_revision_blocks_before_summary_access(tmp_path: Path) -> None:
    config_path = tmp_path / "development_only.yaml"
    config_path.write_text(
        "\n".join(
            (
                "project:",
                "  name: DJR-MCP-Finder",
                "  version: project-v0-metric-revision-test",
                "  test_evaluation_permitted: false",
                "paths: {}",
                "known_mcps: {}",
                "dataset: {}",
                "embedding: {}",
                "classifier: {}",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="explicitly forbids Test evaluation"):
        EVALUATOR.authorize_selection(config_path, tmp_path / "missing-summary.json")


def test_evaluator_fails_closed_on_prior_cohort_before_writing_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "benchmark.yaml"
    summary_path = tmp_path / "model_comparison.json"
    manifest_path = tmp_path / "manifest.tsv"
    fasta_path = tmp_path / "input.faa"
    result_dir = tmp_path / "results" / "replacement-model"
    embedding_dir = tmp_path / "embeddings" / "replacement-model"
    registry = tmp_path / "external-ledger"
    state_dir = registry / "states" / "new-selection-identity"
    prior = registry / "states" / "old-selection" / "TEST_EVALUATION_RECEIPT.json"
    for path, content in (
        (config_path, "config\n"),
        (summary_path, "{}\n"),
        (manifest_path, "protein_id\tsplit\np1\ttest\n"),
        (fasta_path, ">p1\nAAAA\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    result_dir.mkdir(parents=True)
    embedding_dir.mkdir(parents=True)
    config = {
        "project": {"name": "DJR-MCP-Finder", "version": "project-v0-revision"},
        "paths": {"v0_manifest": str(manifest_path), "v0_fasta": str(fasta_path)},
        "benchmark": {"models": {"replacement": {}}},
    }
    cv_contract = {"fold_count": 5}
    summary = {
        "weights": EVALUATOR.EXPECTED_WEIGHTS,
        "config_sha256": "config-sha",
        "manifest_sha256": test_ledger.PRODUCTION_MANIFEST_SHA256,
        "schema_version": 3,
        "cv_fold_contract": cv_contract,
        "tie_rule": EVALUATOR.PAIRED_TIE_RULE,
        "tie_break_order": EVALUATOR.TIE_BREAK_ORDER,
        "speed_tie_break_policy": EVALUATOR.SPEED_TIE_BREAK_POLICY,
    }
    selected = {
        "model_id": "replacement",
        "input_sha256": {},
        "embedding_artifact_sha256": {},
        "model_sha256": {},
    }
    hashes = {
        config_path.resolve(): "config-sha",
        manifest_path.resolve(): test_ledger.PRODUCTION_MANIFEST_SHA256,
        fasta_path.resolve(): "f" * 64,
    }
    monkeypatch.setattr(EVALUATOR, "load_config", lambda _: config)
    monkeypatch.setattr(EVALUATOR, "_verify_comparison_checksums", lambda _: {})
    monkeypatch.setattr(EVALUATOR, "_read_json", lambda _: summary)
    monkeypatch.setattr(
        EVALUATOR, "sha256_file", lambda path: hashes[Path(path).resolve()]
    )
    monkeypatch.setattr(EVALUATOR, "_registry_candidate_ids", lambda _: ["replacement"])
    monkeypatch.setattr(
        EVALUATOR, "load_frozen_cv_fold_map", lambda *_: (cv_contract, None)
    )
    monkeypatch.setattr(
        EVALUATOR,
        "_reconstruct_selection",
        lambda *_: ([selected], selected),
    )
    monkeypatch.setattr(EVALUATOR, "_validate_selected_row", lambda *_: None)
    monkeypatch.setattr(EVALUATOR, "_paths", lambda *_: (embedding_dir, result_dir))
    monkeypatch.setattr(EVALUATOR, "selection_decision_sha256", lambda _: "d" * 64)
    monkeypatch.setattr(
        EVALUATOR,
        "resolve_test_state_locations",
        lambda **_: (
            test_ledger.PRODUCTION_LEDGER_MODE,
            registry,
            state_dir,
            registry / "identity_claims" / "new-selection-identity.json",
        ),
    )
    monkeypatch.setattr(
        EVALUATOR, "matching_cohort_artifacts", lambda *_, **__: [prior]
    )

    def unexpected_write(*_: object, **__: object) -> None:
        raise AssertionError("cohort collision must be detected before any ledger write")

    monkeypatch.setattr(EVALUATOR, "_exclusive_json", unexpected_write)
    with pytest.raises(RuntimeError, match="changing the selected model cannot authorize"):
        EVALUATOR.authorize_selection(config_path, summary_path)


def test_evaluator_independently_replays_incomparable_speed_tie_break() -> None:
    key_a = {
        "definition": "accumulated_inference_seconds_excluding_model_load",
        "host": "host",
        "gpu": "gpu",
        "device": "cuda",
        "python": "3.12",
        "platform": "linux",
        "torch": "2.13",
        "transformers": "5.14",
        "cuda_runtime": "13.0",
    }
    key_b = dict(key_a)
    key_b["definition"] = "metadata_timestamp_wall_time"
    rows = [
        {
            "model_id": "esm2_650m",
            "composite_fold_scores": [0.9] * 5,
            "composite_score": 0.9,
            "val_head1_average_precision": 0.9,
            "val_head2_macro_f1": 0.9,
            "val_head3_macro_f1": 0.9,
            "val_head1_fpr_at_95pct_recall": 0.1,
            "gpu_seconds_per_sequence": 10.0,
            "permissive_license": True,
            "speed_tie_break_eligible": True,
            "timing_comparability_key": key_a,
        },
        {
            "model_id": "candidate",
            "composite_fold_scores": [0.9] * 5,
            "composite_score": 0.9,
            "val_head1_average_precision": 0.9,
            "val_head2_macro_f1": 0.9,
            "val_head3_macro_f1": 0.9,
            "val_head1_fpr_at_95pct_recall": 0.1,
            "gpu_seconds_per_sequence": 0.01,
            "permissive_license": False,
            "speed_tie_break_eligible": True,
            "timing_comparability_key": key_b,
        },
    ]
    summary_rows = json.loads(json.dumps(rows))
    evaluator_rows = json.loads(json.dumps(rows))
    _, _, summary_selected = SUMMARY._apply_development_selection(summary_rows)
    evaluator_selected = EVALUATOR._independent_development_selection(evaluator_rows)
    assert summary_selected["model_id"] == evaluator_selected["model_id"] == "esm2_650m"
    assert all(
        row["speed_tie_break_status"] == "skipped_incomparable_same_fpr_group"
        for row in evaluator_rows
    )
    evaluator_source = (SCRIPTS / "evaluate_selected_benchmark_model.py").read_text(
        encoding="utf-8"
    )
    assert "from summarize_model_benchmark import (\n    GATE_TOLERANCE" in evaluator_source
    assert "_apply_development_selection" not in evaluator_source


def test_selected_row_validation_uses_registry_candidate_set(tmp_path: Path) -> None:
    candidate_ids = [f"model_{index}" for index in range(14)]
    rebuilt = []
    for index, model_id in enumerate(candidate_ids):
        rebuilt.append(
            {
                "model_id": model_id,
                "status": "complete",
                "selectable": True,
                "selected": index == 4,
                "raw_cv_rank": index + 1,
                "composite_score": 1.0 - index / 100,
                "composite_se": 0.01,
                "composite_se_method": "sd_of_five_shared_fold_composites_div_sqrt5",
                "composite_fold_scores": [1.0 - index / 100] * 5,
                "cv_fold_map_sha256": "f" * 64,
                "cv_fold_metadata_sha256": "e" * 64,
                "one_se_reference_model_id": candidate_ids[0],
                "difference_from_best_selectable_cv": index / 100,
                "paired_fold_deltas_vs_best_selectable_cv": [index / 100] * 5,
                "paired_delta_se_vs_best_selectable_cv": 0.0,
                "within_one_paired_se": index == 0,
                "input_sha256": {"artifact": str(index)},
                "embedding_artifact_sha256": {"embedding": str(index)},
                "model_sha256": {"head1": str(index)},
            }
        )
    selected = rebuilt[4]
    candidate_hashes = {
        row["model_id"]: {
            "input_sha256": row["input_sha256"],
            "embedding_artifact_sha256": row["embedding_artifact_sha256"],
            "model_sha256": row["model_sha256"],
        }
        for row in rebuilt
    }
    summary = {
        "models": [dict(row) for row in rebuilt],
        "pending_models": [],
        "candidate_model_ids": candidate_ids,
        "complete_model_count": len(candidate_ids),
        "selected_model_id": selected["model_id"],
        "candidate_artifact_hashes": candidate_hashes,
    }
    (tmp_path / "model_comparison.tsv").write_text(
        "model_id\tselected\n"
        + "".join(
            f"{model_id}\t{model_id == selected['model_id']}\n"
            for model_id in candidate_ids
        ),
        encoding="utf-8",
    )
    EVALUATOR._validate_selected_row(
        summary, tmp_path, rebuilt, selected, candidate_ids
    )
