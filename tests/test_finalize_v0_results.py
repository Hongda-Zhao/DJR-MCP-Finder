from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import joblib

from djrmcp_finder.stages import classifier


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "finalize_v0_results", ROOT / "scripts" / "finalize_v0_results.py"
)
assert SPEC is not None and SPEC.loader is not None
FINALIZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FINALIZER)


class FrozenDecisionEstimator:
    """Minimal deterministic decision function persisted in synthetic joblib bundles."""

    def __init__(self, columns: tuple[int, ...]):
        self.columns = columns

    def decision_function(self, x: np.ndarray) -> np.ndarray:
        selected = np.asarray(x)[:, self.columns]
        return selected[:, 0] if len(self.columns) == 1 else selected


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            delimiter="\t",
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _build_frozen_result(tmp_path: Path) -> dict[str, Path]:
    selected_model_id = "model_a"
    candidate_ids = ["model_b", "model_a", *[f"model_{index}" for index in range(12)]]
    manifest = tmp_path / "manifest.tsv"

    def master_row(
        protein_id: str,
        source: str,
        head1: str,
        head2: str = "",
        head3: str = "",
        *,
        split: str = "test",
        formal: str = "",
        known: bool = False,
        unknown: bool = False,
        status: str = "not_applicable",
        reason: str = "",
    ) -> dict[str, str]:
        scope = known or unknown
        return {
            "protein_id": protein_id,
            "sequence_sha256": hashlib.sha256(protein_id.encode("utf-8")).hexdigest(),
            "split": split,
            "global_component_id": f"component::{protein_id}",
            "source_dataset": source,
            "head1_label": head1,
            "head2_label": head2,
            "head2_mask": "1" if head1 == "djr" else "0",
            "head3_phylum_label": formal,
            "head3_operational_label": head3,
            "head3_scope_mask": "1" if scope else "0",
            "head3_mask": "1" if known else "0",
            "head3_unknown_diagnostic_mask": "1" if unknown else "0",
            "head3_status": status,
            "head3_unknown_reason": reason,
        }

    manifest_rows = [
        master_row("n_hard", "hard_non_djr", "non_djr"),
        master_row("n_background", "background_non_djr", "non_djr"),
        master_row("cell", "cellular_djr_none", "djr", "none"),
        master_row(
            "nucleo",
            "viral_vma_djr",
            "djr",
            "viral_morphogenesis_associated",
            "Nucleocytoviricota",
            formal="Nucleocytoviricota",
            known=True,
            status="known_supervised",
        ),
        master_row(
            "preplasm",
            "viral_vma_djr",
            "djr",
            "viral_morphogenesis_associated",
            "Preplasmiviricota",
            formal="Preplasmiviricota",
            known=True,
            status="known_supervised",
        ),
        master_row(
            "rare",
            "viral_vma_djr",
            "djr",
            "viral_morphogenesis_associated",
            "unknown/other",
            formal="Produgelaviricota",
            unknown=True,
            status="rare_formal_unknown_diagnostic",
            reason="rare_formal_phylum_mapped_to_operational_unknown",
        ),
        master_row(
            "literature",
            "viral_vma_djr",
            "djr",
            "viral_morphogenesis_associated",
            "unknown/other",
            unknown=True,
            status="literature_unclassified_unknown_diagnostic",
            reason="no_formal_ICTV_MSL41_phylum",
        ),
        master_row(
            "train1",
            "viral_vma_djr",
            "djr",
            "viral_morphogenesis_associated",
            "Nucleocytoviricota",
            split="train",
            formal="Nucleocytoviricota",
            known=True,
            status="known_supervised",
        ),
    ]
    _write_tsv(manifest, manifest_rows)
    fasta = tmp_path / "model_input.faa"
    fasta.write_text(
        "".join(f">{row['protein_id']}\nAAAA\n" for row in manifest_rows),
        encoding="utf-8",
    )
    state_dir = tmp_path / "project_test_state"
    result_dir = tmp_path / "results" / selected_model_id
    embedding_dir = tmp_path / "embeddings" / selected_model_id
    config = tmp_path / "benchmark.yaml"
    config.write_text(
        "\n".join(
            [
                "project:",
                "  name: DJR-MCP-Finder",
                "  version: project-v0-test",
                "  seed: 20260722",
                "paths:",
                f"  v0_fasta: {fasta}",
                f"  test_state_dir: {state_dir}",
                "known_mcps: {}",
                "dataset: {}",
                "embedding: {}",
                "classifier: {}",
                "benchmark:",
                "  models:",
                *(f"    {model_id}: {{}}" for model_id in candidate_ids),
                "",
            ]
        ),
        encoding="utf-8",
    )

    embedding_dir.mkdir(parents=True)
    evidence = {
        "n_hard": (0.1, 0.2, None),
        "n_background": (0.8, 0.1, None),
        "cell": (0.9, 0.2, None),
        "nucleo": (0.9, 0.9, (0.9, 0.1)),
        "preplasm": (0.4, 0.9, (0.1, 0.9)),
        "rare": (0.9, 0.9, (0.55, 0.45)),
        "literature": (0.9, 0.4, (0.52, 0.48)),
        "train1": (0.9, 0.9, (0.9, 0.1)),
    }

    def logit(probability: float) -> float:
        return math.log(probability / (1.0 - probability))

    vectors = []
    for row in manifest_rows:
        h1, h2, h3 = evidence[row["protein_id"]]
        h3 = h3 or (0.5, 0.5)
        vectors.append([logit(h1), logit(h2), math.log(h3[0]), math.log(h3[1])])
    np.save(embedding_dir / "embeddings.float16.npy", np.asarray(vectors, dtype=np.float16))
    np.save(embedding_dir / "completed.npy", np.ones(len(manifest_rows), dtype=bool))
    _write_tsv(
        embedding_dir / "index.tsv",
        [
            {
                "embedding_row": index,
                "protein_id": row["protein_id"],
                "sequence_sha256": row["sequence_sha256"],
                "split": row["split"],
                "length_aa": 4,
            }
            for index, row in enumerate(manifest_rows)
        ],
    )
    embedding_metadata = {
        "status": "complete",
        "benchmark_model_id": selected_model_id,
        "manifest_sha256": _sha256(manifest),
    }
    _write_json(embedding_dir / "metadata.json", embedding_metadata)
    embedding_hashes = {
        name: _sha256(embedding_dir / name)
        for name in (
            "completed.npy",
            "embeddings.float16.npy",
            "index.tsv",
            "metadata.json",
        )
    }
    (embedding_dir / "CHECKSUMS.sha256").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in embedding_hashes.items()),
        encoding="utf-8",
    )

    metrics_dir = result_dir / "metrics"
    models_dir = result_dir / "models"
    metrics_dir.mkdir(parents=True)
    models_dir.mkdir()
    _write_json(metrics_dir / "cross_validation.json", {"heads": {}})
    _write_json(metrics_dir / "validation_metrics.json", {"heads": {}})
    model_hashes: dict[str, str] = {}
    calibration_heads: dict[str, Any] = {}
    for head in ("head1", "head2", "head3_phylum"):
        model_path = models_dir / f"{head}.joblib"
        classes = (
            ["Nucleocytoviricota", "Preplasmiviricota"]
            if head == "head3_phylum"
            else (
                ["non_djr", "djr"]
                if head == "head1"
                else ["none", "viral_morphogenesis_associated"]
            )
        )
        bundle = {
            "head": head,
            "classes": classes,
            "estimator": FrozenDecisionEstimator(
                (2, 3) if head == "head3_phylum" else ((0,) if head == "head1" else (1,))
            ),
            "temperature": 1.0,
            "decision_threshold": 0.6 if head == "head3_phylum" else 0.5,
            "manifest_sha256": _sha256(manifest),
            "embedding_metadata_sha256": _sha256(embedding_dir / "metadata.json"),
        }
        joblib.dump(bundle, model_path)
        model_hashes[head] = _sha256(model_path)
        calibration_heads[head] = {
            "model_path": str(model_path),
            "model_sha256": model_hashes[head],
            "classes": classes,
            "temperature": 1.0,
            "decision_threshold": 0.6 if head == "head3_phylum" else 0.5,
        }
    calibration = {
        "manifest_sha256": _sha256(manifest),
        "embedding_metadata_sha256": _sha256(embedding_dir / "metadata.json"),
        "heads": calibration_heads,
    }
    calibration_path = result_dir / "calibration.json"
    _write_json(calibration_path, calibration)
    selected_evidence = {
        "input_sha256": {
            "embedding_metadata": _sha256(embedding_dir / "metadata.json"),
            "embedding_checksums": _sha256(embedding_dir / "CHECKSUMS.sha256"),
            "calibration": _sha256(calibration_path),
            "cross_validation": _sha256(metrics_dir / "cross_validation.json"),
            "validation": _sha256(metrics_dir / "validation_metrics.json"),
        },
        "embedding_artifact_sha256": embedding_hashes,
        "model_sha256": model_hashes,
    }

    comparison_dir = tmp_path / "comparison"
    comparison_dir.mkdir()
    comparison_rows = [
        {"model_id": model_id, "selected": model_id == selected_model_id}
        for model_id in candidate_ids
    ]
    _write_tsv(comparison_dir / "model_comparison.tsv", comparison_rows)
    _write_tsv(
        comparison_dir / "fold_scores.tsv",
        [{"model_id": model_id, "fold": "1"} for model_id in candidate_ids],
    )
    candidate_hashes = {
        model_id: selected_evidence if model_id == selected_model_id else {
            "input_sha256": {},
            "embedding_artifact_sha256": {},
            "model_sha256": {},
        }
        for model_id in candidate_ids
    }
    comparison = {
        "selected_model_id": selected_model_id,
        "manifest_sha256": _sha256(manifest),
        "config_sha256": _sha256(config),
        "weights": FINALIZER.EXPECTED_WEIGHTS,
        "complete_model_count": len(candidate_ids),
        "candidate_model_ids": candidate_ids,
        "candidate_artifact_hashes": candidate_hashes,
        "models": comparison_rows,
    }
    comparison_path = comparison_dir / "model_comparison.json"
    _write_json(comparison_path, comparison)
    comparison_hashes = {
        name: _sha256(comparison_dir / name)
        for name in (
            "model_comparison.json",
            "model_comparison.tsv",
            "fold_scores.tsv",
        )
    }

    identity_payload = {
        "schema_version": 1,
        "project_name": "DJR-MCP-Finder",
        "project_version": "project-v0-test",
        "manifest_path": str(manifest.resolve()),
        "manifest_sha256": _sha256(manifest),
        "model_input_fasta_path": str(fasta.resolve()),
        "model_input_fasta_sha256": _sha256(fasta),
        "config_path": str(config.resolve()),
        "config_sha256": _sha256(config),
        "comparison_path": str(comparison_path.resolve()),
        "comparison_sha256": comparison_hashes,
        "weights": FINALIZER.EXPECTED_WEIGHTS,
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
        "project_test_identity": FINALIZER._canonical_sha256(identity_payload),
        "weights": FINALIZER.EXPECTED_WEIGHTS,
        "candidate_model_ids": candidate_ids,
        "candidate_count": len(candidate_ids),
        "manifest_sha256": _sha256(manifest),
        "model_input_fasta_path": str(fasta.resolve()),
        "model_input_fasta_sha256": _sha256(fasta),
        "config_path": str(config.resolve()),
        "config_sha256": _sha256(config),
        "comparison_path": str(comparison_path.resolve()),
        "comparison_sha256": comparison_hashes,
        "selected_candidate_evidence": selected_evidence,
    }
    authorization = dict(authorization_core)
    authorization["authorization_id"] = FINALIZER._canonical_sha256(
        authorization_core
    )
    authorization_path = state_dir / "TEST_SELECTION_AUTHORIZATION.json"
    _write_json(authorization_path, authorization)
    authorization_sha256 = _sha256(authorization_path)

    reservation = {
        "schema_version": 2,
        "status": "reserved_fail_closed",
        "authorization_id": authorization["authorization_id"],
        "authorization_path": str(authorization_path),
        "authorization_sha256": authorization_sha256,
        "selected_model_id": selected_model_id,
        "selected_result_dir": str(result_dir.resolve()),
        "project_test_state_dir": str(state_dir.resolve()),
        "project_test_identity": authorization["project_test_identity"],
    }
    reservation_path = state_dir / "TEST_EVALUATION_RESERVED.json"
    _write_json(reservation_path, reservation)

    test_master_rows = manifest_rows[:-1]
    prediction_rows, _ = FINALIZER._reinfer_frozen_test_predictions(
        manifest, embedding_dir, calibration
    )
    predictions_path = result_dir / "predictions" / "frozen_test_predictions.tsv"
    _write_tsv(predictions_path, prediction_rows)
    recomputed, _ = FINALIZER._independently_recompute_test_sections(
        test_master_rows,
        prediction_rows,
        calibration,
        seed=20260722,
    )
    test_metrics = {
        "schema_version": 4,
        "completed_utc": "2026-07-23T00:01:00+00:00",
        "manifest_sha256": _sha256(manifest),
        "embedding_metadata_sha256": _sha256(embedding_dir / "metadata.json"),
        "heads": recomputed["heads"],
        "operational_cascade": recomputed["operational_cascade"],
        "test_use_statement": "synthetic frozen Test fixture",
        "selection_authorization_id": authorization["authorization_id"],
        "project_test_identity": authorization["project_test_identity"],
        "project_test_state_dir": str(state_dir.resolve()),
        "test_reservation_path": str(reservation_path),
        "frozen_inference_artifacts": {
            "embedding_dir": str(embedding_dir.resolve()),
            "embedding_metadata_sha256": _sha256(embedding_dir / "metadata.json"),
            "embedding_index_sha256": _sha256(embedding_dir / "index.tsv"),
            "embedding_vectors_sha256": _sha256(
                embedding_dir / "embeddings.float16.npy"
            ),
            "model_sha256": model_hashes,
        },
    }
    test_metrics_path = metrics_dir / "frozen_test_metrics.json"
    _write_json(test_metrics_path, test_metrics)
    marker = {
        "schema_version": 3,
        "status": "complete_single_test_evaluation",
        "completed_utc": test_metrics["completed_utc"],
        "selected_model_id": selected_model_id,
        "metrics_path": str(test_metrics_path),
        "metrics_sha256": _sha256(test_metrics_path),
        "predictions_path": str(predictions_path),
        "predictions_sha256": _sha256(predictions_path),
        "calibration_sha256": _sha256(calibration_path),
        "selection_authorization_id": authorization["authorization_id"],
        "project_test_identity": authorization["project_test_identity"],
        "project_test_state_dir": str(state_dir.resolve()),
        "selection_authorization_path": str(authorization_path),
        "selection_authorization_sha256": authorization_sha256,
        "test_reservation_path": str(reservation_path),
        "test_reservation_sha256": _sha256(reservation_path),
        "reservation_status": reservation["status"],
    }
    marker_path = result_dir / "FINAL_TEST_EVALUATED.json"
    _write_json(marker_path, marker)
    receipt = {
        "schema_version": 2,
        "status": "complete",
        "authorization_id": authorization["authorization_id"],
        "authorization_path": str(authorization_path),
        "authorization_sha256": authorization_sha256,
        "selected_model_id": selected_model_id,
        "selected_result_dir": str(result_dir.resolve()),
        "project_test_state_dir": str(state_dir.resolve()),
        "project_test_identity": authorization["project_test_identity"],
        "test_marker_path": str(marker_path),
        "test_marker_sha256": _sha256(marker_path),
        "metrics_sha256": _sha256(test_metrics_path),
        "predictions_sha256": _sha256(predictions_path),
    }
    receipt_path = state_dir / "TEST_EVALUATION_RECEIPT.json"
    _write_json(receipt_path, receipt)
    return {
        "manifest": manifest,
        "result_dir": result_dir,
        "predictions": predictions_path,
        "marker": marker_path,
        "receipt": receipt_path,
        "comparison": comparison_path,
        "state_dir": state_dir,
        "embedding_dir": embedding_dir,
    }


def _refresh_prediction_lineage(paths: dict[str, Path]) -> None:
    marker = FINALIZER.read_json(paths["marker"])
    marker["predictions_sha256"] = _sha256(paths["predictions"])
    _write_json(paths["marker"], marker)
    receipt = FINALIZER.read_json(paths["receipt"])
    receipt["predictions_sha256"] = _sha256(paths["predictions"])
    receipt["test_marker_sha256"] = _sha256(paths["marker"])
    _write_json(paths["receipt"], receipt)


def _refresh_metrics_lineage(paths: dict[str, Path]) -> None:
    marker = FINALIZER.read_json(paths["marker"])
    metrics_path = Path(marker["metrics_path"])
    marker["metrics_sha256"] = _sha256(metrics_path)
    _write_json(paths["marker"], marker)
    receipt = FINALIZER.read_json(paths["receipt"])
    receipt["metrics_sha256"] = _sha256(metrics_path)
    receipt["test_marker_sha256"] = _sha256(paths["marker"])
    _write_json(paths["receipt"], receipt)


def test_finalizer_accepts_dynamic_registry_and_exact_lineage(tmp_path: Path) -> None:
    paths = _build_frozen_result(tmp_path)
    validation = FINALIZER.audit_result(paths["manifest"], paths["result_dir"])
    assert validation["status"] == "pass"
    assert validation["selected_model_id"] == "model_a"
    assert validation["checks"]["authorization_candidate_registry"] is True
    assert validation["checks"]["prediction_id_set_exact"] is True
    assert validation["checks"]["independent_metrics_recomputation"] is True
    assert validation["checks"]["frozen_model_probability_reinference"] is True
    marker = FINALIZER.read_json(paths["marker"])
    metrics = FINALIZER.read_json(Path(marker["metrics_path"]))
    h3 = metrics["heads"]["head3_phylum"]
    assert h3["component_bootstrap_95pct_ci"]["unit"] == "global_component_id"
    assert (
        h3["per_class"]["Nucleocytoviricota"]["component_bootstrap_95pct_ci"][
            "recall"
        ]["effective_replicates"]
        > 0
    )
    assert (
        h3["unknown_diagnostic"][
            "unknown_recall_component_bootstrap_95pct_ci"
        ]["unit"]
        == "global_component_id"
    )
    assert (
        metrics["operational_cascade"]["full_path"][
            "accuracy_component_bootstrap_95pct_ci"
        ]["replicates"]
        == 10_000
    )


def test_finalizer_rejects_forged_test_id_even_if_lineage_hashes_are_refreshed(
    tmp_path: Path,
) -> None:
    paths = _build_frozen_result(tmp_path)
    rows = FINALIZER.read_prediction_rows(paths["predictions"])
    rows[-1]["protein_id"] = "forged"
    _write_tsv(paths["predictions"], rows)
    _refresh_prediction_lineage(paths)
    with pytest.raises(RuntimeError, match="frozen_model_reinference"):
        FINALIZER.audit_result(paths["manifest"], paths["result_dir"])


def test_finalizer_rejects_upstream_attrition_relabeled_as_unknown(tmp_path: Path) -> None:
    paths = _build_frozen_result(tmp_path)
    rows = FINALIZER.read_prediction_rows(paths["predictions"])
    preplasm = next(row for row in rows if row["protein_id"] == "preplasm")
    assert preplasm["head3_predicted"] == "not_reached"
    preplasm["head3_predicted"] = "unknown/other"
    _write_tsv(paths["predictions"], rows)
    _refresh_prediction_lineage(paths)
    with pytest.raises(RuntimeError, match="frozen_model_reinference"):
        FINALIZER.audit_result(paths["manifest"], paths["result_dir"])


def test_finalizer_rejects_metrics_tampering_after_all_hashes_are_refreshed(
    tmp_path: Path,
) -> None:
    paths = _build_frozen_result(tmp_path)
    marker = FINALIZER.read_json(paths["marker"])
    metrics_path = Path(marker["metrics_path"])
    metrics = FINALIZER.read_json(metrics_path)
    metrics["operational_cascade"]["full_path"]["correct"] += 1
    _write_json(metrics_path, metrics)
    _refresh_metrics_lineage(paths)
    with pytest.raises(RuntimeError, match="independent_metrics_recomputation"):
        FINALIZER.audit_result(paths["manifest"], paths["result_dir"])


def test_finalizer_rejects_duplicate_test_completion_marker(tmp_path: Path) -> None:
    paths = _build_frozen_result(tmp_path)
    duplicate = paths["result_dir"] / "FINAL_TEST_EVALUATED_copy.json"
    duplicate.write_bytes(paths["marker"].read_bytes())
    with pytest.raises(RuntimeError, match="unique_canonical_test_completion_marker"):
        FINALIZER.audit_result(paths["manifest"], paths["result_dir"])


def test_classifier_and_finalizer_use_independent_matching_cascade_and_ci_formulas() -> None:
    metadata = [
        {
            "head1_label": "non_djr",
            "head2_label": "",
            "head3_operational_label": "",
            "head3_scope_mask": "0",
            "head3_unknown_diagnostic_mask": "0",
            "head3_unknown_reason": "",
        },
        {
            "head1_label": "djr",
            "head2_label": "viral_morphogenesis_associated",
            "head3_operational_label": "Nucleocytoviricota",
            "head3_scope_mask": "1",
            "head3_unknown_diagnostic_mask": "0",
            "head3_unknown_reason": "",
        },
        {
            "head1_label": "djr",
            "head2_label": "viral_morphogenesis_associated",
            "head3_operational_label": "unknown/other",
            "head3_scope_mask": "1",
            "head3_unknown_diagnostic_mask": "1",
            "head3_unknown_reason": "rare_formal_phylum_mapped_to_operational_unknown",
        },
    ]
    h1_probability = np.asarray([0.1, 0.9, 0.9])
    h2_probability = np.asarray([0.9, 0.9, 0.2])
    h3_prediction = ["not_reached", "Nucleocytoviricota", "not_reached"]
    groups = np.asarray(["a", "b", "b"])
    classifier_cascade, _, _ = classifier._operational_cascade_metrics(
        metadata,
        h1_probability,
        h2_probability,
        0.5,
        0.5,
        h3_prediction,
        groups=groups,
        seed=7,
    )
    finalizer_cascade, _, _ = FINALIZER._operational_cascade_metrics(
        metadata,
        h1_probability >= 0.5,
        h2_probability >= 0.5,
        h3_prediction,
        groups=groups,
        seed=7,
    )
    assert classifier._jsonable(classifier_cascade) == finalizer_cascade
    assert (
        finalizer_cascade["full_path"]["accuracy_component_bootstrap_95pct_ci"][
            "unit"
        ]
        == "global_component_id"
    )

    y = np.asarray([0, 0, 1, 1])
    probability = np.asarray([0.1, 0.2, 0.8, 0.9])
    groups = np.asarray(["a", "a", "b", "c"])
    classifier_ci = classifier._component_bootstrap_binary(
        y,
        probability,
        groups,
        ranking_score=probability,
        ranking_score_source="test_probability_equivalence",
        threshold=0.5,
        seed=7,
        replicates=200,
    )
    finalizer_ci = FINALIZER._component_bootstrap_binary(
        y, probability, groups, threshold=0.5, seed=7, replicates=200
    )
    classifier_ci.pop("ranking_score_source")
    assert classifier._jsonable(classifier_ci) == finalizer_ci


def test_finalizer_rejects_selection_receipt_mismatch(tmp_path: Path) -> None:
    paths = _build_frozen_result(tmp_path)
    receipt = FINALIZER.read_json(paths["receipt"])
    receipt["selected_model_id"] = "model_b"
    _write_json(paths["receipt"], receipt)
    with pytest.raises(RuntimeError, match="receipt_authorization_lineage"):
        FINALIZER.audit_result(paths["manifest"], paths["result_dir"])


def test_finalizer_rejects_changed_frozen_comparison(tmp_path: Path) -> None:
    paths = _build_frozen_result(tmp_path)
    comparison = FINALIZER.read_json(paths["comparison"])
    comparison["selected_model_id"] = "model_b"
    _write_json(paths["comparison"], comparison)
    with pytest.raises(RuntimeError, match="authorization_comparison_lineage"):
        FINALIZER.audit_result(paths["manifest"], paths["result_dir"])


def test_finalizer_rejects_forged_probability_even_when_result_hashes_are_refreshed(
    tmp_path: Path,
) -> None:
    paths = _build_frozen_result(tmp_path)
    rows = FINALIZER.read_prediction_rows(paths["predictions"])
    rows[0]["head1_djr_probability"] = "0.123456789"
    _write_tsv(paths["predictions"], rows)
    _refresh_prediction_lineage(paths)
    with pytest.raises(RuntimeError, match="frozen_model_reinference"):
        FINALIZER.audit_result(paths["manifest"], paths["result_dir"])


def test_finalizer_rejects_embedding_index_row_swap(tmp_path: Path) -> None:
    paths = _build_frozen_result(tmp_path)
    index_path = paths["embedding_dir"] / "index.tsv"
    with index_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    rows[0], rows[1] = rows[1], rows[0]
    _write_tsv(index_path, rows)
    with pytest.raises(RuntimeError, match="frozen_embedding_reinference"):
        FINALIZER.audit_result(paths["manifest"], paths["result_dir"])


def test_finalizer_rejects_duplicate_project_reservation(tmp_path: Path) -> None:
    paths = _build_frozen_result(tmp_path)
    duplicate = paths["state_dir"] / "nested" / "TEST_EVALUATION_RESERVED_copy.json"
    duplicate.parent.mkdir()
    duplicate.write_bytes((paths["state_dir"] / "TEST_EVALUATION_RESERVED.json").read_bytes())
    with pytest.raises(RuntimeError, match="unique_project_test_lifecycle_artifacts"):
        FINALIZER.audit_result(paths["manifest"], paths["result_dir"])
