#!/usr/bin/env python3
"""Authorize and evaluate Test once for the uniquely reconstructed benchmark winner."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from djrmcp_finder.benchmark_config import expand_benchmark_model
from djrmcp_finder.config import load_config
from djrmcp_finder.cv_folds import load_frozen_cv_fold_map
from djrmcp_finder.stages.classifier import run
from djrmcp_finder.stages.embedding import sha256_file
from djrmcp_finder.test_ledger import (
    PRODUCTION_LEDGER_MODE,
    canonical_sha256 as _ledger_canonical_sha256,
    cohort_identity_payload,
    content_identity_payload,
    matching_cohort_artifacts,
    matching_identity_artifacts,
    production_cohort_claim_path,
    resolve_test_state_locations,
    selection_decision_sha256,
)
from summarize_model_benchmark import (
    GATE_TOLERANCE,
    PAIRED_TIE_RULE,
    SPEED_TIE_BREAK_POLICY,
    TIE_BREAK_ORDER,
    _development_row,
    _paths,
)


EXPECTED_WEIGHTS = {"head1": 0.60, "head2": 0.30, "head3_phylum": 0.10}
COMPARISON_FILES = {"model_comparison.json", "model_comparison.tsv", "fold_scores.tsv"}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return value


def _canonical_sha256(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _mean(values: list[float]) -> float:
    return float(sum(values) / len(values))


def _se(values: list[float]) -> float:
    return float(statistics.stdev(values) / math.sqrt(len(values))) if len(values) > 1 else 0.0


def _resolved(path: str | Path) -> Path:
    return Path(path).resolve()


def _assert_external_project_state_dir(state_dir: Path, result_dir: Path) -> None:
    state_dir = state_dir.resolve()
    result_dir = result_dir.resolve()
    if state_dir == result_dir or state_dir.is_relative_to(result_dir):
        raise RuntimeError(
            "Project Test state directory must be outside the selected result directory"
        )


def _exclusive_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError as exc:
        raise RuntimeError(f"Fail-closed artifact already exists: {path}") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _verify_comparison_checksums(summary_path: Path) -> dict[str, str]:
    if summary_path.name != "model_comparison.json":
        raise RuntimeError("Summary must be the frozen model_comparison.json artifact")
    checksum_path = summary_path.parent / "COMPARISON_CHECKSUMS.sha256"
    observed: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        checksum_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        parts = raw_line.split(maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError(f"Malformed comparison checksum line {line_number}")
        digest, name = parts[0], parts[1].strip().lstrip("*")
        if (
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or Path(name).name != name
            or name in observed
        ):
            raise RuntimeError(f"Unsafe comparison checksum entry: {name!r}")
        artifact = summary_path.parent / name
        if not artifact.is_file() or sha256_file(artifact) != digest:
            raise RuntimeError(f"Comparison checksum mismatch: {artifact}")
        observed[name] = digest
    if set(observed) != COMPARISON_FILES:
        raise RuntimeError(f"Comparison checksum coverage must be {sorted(COMPARISON_FILES)}")
    return observed


def _registry_candidate_ids(config: dict[str, Any]) -> list[str]:
    models = config.get("benchmark", {}).get("models")
    if not isinstance(models, dict) or not models:
        raise RuntimeError("Frozen benchmark config has no candidate registry")
    candidate_ids = list(models)
    if any(not isinstance(model_id, str) or not model_id for model_id in candidate_ids):
        raise RuntimeError("Frozen benchmark registry contains an invalid candidate ID")
    return candidate_ids


def _independent_development_selection(
    rows: list[dict[str, Any]], *, baseline_model_id: str = "esm2_650m"
) -> dict[str, Any]:
    """Independently replay gates, paired one-SE and the staged tie-break."""

    baselines = [row for row in rows if row["model_id"] == baseline_model_id]
    if len(baselines) != 1:
        raise RuntimeError(f"Benchmark requires exactly one {baseline_model_id} baseline")
    baseline = baselines[0]
    for row in rows:
        deltas = {
            "head1": row["val_head1_average_precision"]
            - baseline["val_head1_average_precision"],
            "head2": row["val_head2_macro_f1"] - baseline["val_head2_macro_f1"],
            "head3": row["val_head3_macro_f1"] - baseline["val_head3_macro_f1"],
        }
        failures = [head for head, delta in deltas.items() if delta < -GATE_TOLERANCE]
        row["validation_delta_vs_esm2_650m"] = deltas
        row["validation_gate_failures"] = failures
        row["selectable"] = not failures

    raw = sorted(rows, key=lambda row: (-row["composite_score"], row["model_id"]))
    for rank, row in enumerate(raw, start=1):
        row["raw_cv_rank"] = rank
    eligible = [row for row in rows if row["selectable"]]
    if not eligible:
        raise RuntimeError("No selectable benchmark candidate")
    reference = min(
        eligible, key=lambda row: (-row["composite_score"], row["model_id"])
    )
    reference_folds = [float(value) for value in reference["composite_fold_scores"]]
    if len(reference_folds) < 2:
        raise RuntimeError("Paired one-SE selection requires at least two shared folds")

    one_se: list[dict[str, Any]] = []
    for row in rows:
        candidate_folds = [float(value) for value in row["composite_fold_scores"]]
        if len(candidate_folds) != len(reference_folds):
            raise RuntimeError(f"Composite fold-count mismatch for {row['model_id']}")
        deltas = [
            reference_score - candidate_score
            for reference_score, candidate_score in zip(reference_folds, candidate_folds)
        ]
        difference = reference["composite_score"] - row["composite_score"]
        if not math.isclose(_mean(deltas), difference, rel_tol=0.0, abs_tol=1e-12):
            raise RuntimeError(f"Paired fold delta mean is inconsistent for {row['model_id']}")
        delta_se = _se(deltas)
        row["one_se_reference_model_id"] = reference["model_id"]
        row["difference_from_best_selectable_cv"] = difference
        row["paired_fold_deltas_vs_best_selectable_cv"] = deltas
        row["paired_delta_se_vs_best_selectable_cv"] = delta_se
        row["within_one_paired_se"] = bool(
            row["selectable"] and difference <= delta_se + 1e-15
        )
        if row["within_one_paired_se"]:
            one_se.append(row)

    fpr_groups: dict[float, list[dict[str, Any]]] = {}
    for row in one_se:
        fpr = row["val_head1_fpr_at_95pct_recall"]
        fpr_groups.setdefault(math.inf if fpr is None else float(fpr), []).append(row)
    ordered: list[dict[str, Any]] = []
    for fpr in sorted(fpr_groups):
        group = fpr_groups[fpr]
        comparable = bool(
            len(group) > 1
            and all(row.get("speed_tie_break_eligible") is True for row in group)
            and len(
                {
                    json.dumps(
                        row.get("timing_comparability_key"),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    for row in group
                }
            )
            == 1
        )
        if comparable:
            group.sort(
                key=lambda row: (
                    float(row["gpu_seconds_per_sequence"]),
                    0 if row["permissive_license"] else 1,
                    -row["composite_score"],
                    row["model_id"],
                )
            )
            status = "used_comparable_same_fpr_group"
        else:
            group.sort(
                key=lambda row: (
                    0 if row["permissive_license"] else 1,
                    -row["composite_score"],
                    row["model_id"],
                )
            )
            status = (
                "not_invoked_single_model_after_fpr"
                if len(group) == 1
                else "skipped_incomparable_same_fpr_group"
            )
        for row in group:
            row["speed_tie_break_status"] = status
        ordered.extend(group)
    if not ordered:
        raise RuntimeError("Paired one-SE set is unexpectedly empty")
    for rank, row in enumerate(ordered, start=1):
        row["tie_break_rank"] = rank
        row["selected"] = rank == 1
    for row in rows:
        if row not in ordered:
            row["selected"] = False
    return ordered[0]


def _reconstruct_selection(
    config: dict[str, Any],
    manifest_sha256: str,
    candidate_ids: list[str],
    cv_fold_contract: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    models = config["benchmark"]["models"]
    rows = []
    for model_id in candidate_ids:
        spec = models[model_id]
        row, _ = _development_row(
            model_id, spec, manifest_sha256, cv_fold_contract, config
        )
        if row.get("status") != "complete":
            raise RuntimeError(f"Benchmark candidate is incomplete: {model_id}")
        rows.append(row)
    selected = _independent_development_selection(rows)
    return rows, selected


def _validate_selected_row(
    summary: dict[str, Any],
    comparison_dir: Path,
    rebuilt: list[dict[str, Any]],
    selected: dict[str, Any],
    candidate_ids: list[str],
) -> None:
    summary_rows = summary.get("models")
    candidate_count = len(candidate_ids)
    if not isinstance(summary_rows, list) or len(summary_rows) != candidate_count:
        raise RuntimeError(
            f"Summary does not contain exactly {candidate_count} registry candidate rows"
        )
    if summary.get("pending_models") != []:
        raise RuntimeError("Benchmark has pending candidates")
    if summary.get("candidate_model_ids") != candidate_ids:
        raise RuntimeError("Summary candidate order/set differs from frozen config registry")
    if summary.get("complete_model_count") != candidate_count:
        raise RuntimeError("Summary complete candidate count differs from frozen config registry")
    selected_rows = [row for row in summary_rows if row.get("selected") is True]
    if (
        len(selected_rows) != 1
        or summary.get("selected_model_id") != selected_rows[0].get("model_id")
    ):
        raise RuntimeError("Summary does not contain one unambiguous selected candidate")
    if selected_rows[0]["model_id"] != selected["model_id"]:
        raise RuntimeError("Hand-edited summary selection differs from reconstructed selection")
    rebuilt_by_id = {row["model_id"]: row for row in rebuilt}
    if (
        len(rebuilt_by_id) != candidate_count
        or [row.get("model_id") for row in summary_rows] != candidate_ids
        or list(rebuilt_by_id) != candidate_ids
    ):
        raise RuntimeError("Summary candidate IDs differ from the frozen config registry")
    critical = (
        "status",
        "selectable",
        "selected",
        "raw_cv_rank",
        "composite_score",
        "composite_se",
        "composite_se_method",
        "composite_fold_scores",
        "cv_fold_map_sha256",
        "cv_fold_metadata_sha256",
        "one_se_reference_model_id",
        "difference_from_best_selectable_cv",
        "paired_fold_deltas_vs_best_selectable_cv",
        "paired_delta_se_vs_best_selectable_cv",
        "within_one_paired_se",
        "tie_break_rank",
        "speed_tie_break_eligible",
        "speed_tie_break_status",
        "timing_comparability_key",
        "validation_delta_vs_esm2_650m",
        "validation_gate_failures",
        "input_sha256",
        "embedding_artifact_sha256",
        "model_sha256",
    )
    for summary_row in summary_rows:
        expected = rebuilt_by_id[summary_row["model_id"]]
        if any(summary_row.get(field) != expected.get(field) for field in critical):
            raise RuntimeError(
                f"Summary row differs from candidate evidence: {summary_row['model_id']}"
            )
    expected_hashes = {
        row["model_id"]: {
            "input_sha256": row["input_sha256"],
            "embedding_artifact_sha256": row["embedding_artifact_sha256"],
            "model_sha256": row["model_sha256"],
        }
        for row in rebuilt
    }
    if summary.get("candidate_artifact_hashes") != expected_hashes:
        raise RuntimeError("Candidate artifact hashes differ from reconstructed evidence")

    with (comparison_dir / "model_comparison.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        tsv_rows = list(csv.DictReader(handle, delimiter="\t"))
    tsv_selected = [row for row in tsv_rows if row.get("selected") == "True"]
    if (
        len(tsv_rows) != candidate_count
        or [row.get("model_id") for row in tsv_rows] != candidate_ids
        or len(tsv_selected) != 1
    ):
        raise RuntimeError(
            "Comparison TSV does not contain the exact registry candidates and one selection"
        )
    if tsv_selected[0]["model_id"] != selected["model_id"]:
        raise RuntimeError("Comparison TSV selected row differs from reconstructed selection")


def authorize_selection(
    config_path: Path, summary_path: Path
) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    config = load_config(config_path)
    if config.get("project", {}).get("test_evaluation_permitted") is False:
        raise RuntimeError(
            "This development-only metric revision explicitly forbids Test evaluation"
        )
    checksum_map = _verify_comparison_checksums(summary_path)
    summary = _read_json(summary_path)
    if summary.get("weights") != EXPECTED_WEIGHTS:
        raise RuntimeError("Benchmark weights must be exactly 0.60/0.30/0.10")
    if summary.get("config_sha256") != sha256_file(config_path):
        raise RuntimeError("Benchmark summary was generated from a different config")
    manifest_path = Path(config["paths"]["v0_manifest"])
    manifest_sha256 = sha256_file(manifest_path)
    if summary.get("manifest_sha256") != manifest_sha256:
        raise RuntimeError("Benchmark summary and current V0 manifest differ")
    candidate_ids = _registry_candidate_ids(config)
    cv_fold_contract, _ = load_frozen_cv_fold_map(config, manifest_path)
    if summary.get("schema_version") != 3:
        raise RuntimeError("Benchmark comparison schema must be selection-contract version 3")
    if summary.get("cv_fold_contract") != cv_fold_contract:
        raise RuntimeError("Benchmark summary and frozen CV-fold contract differ")
    if summary.get("tie_rule") != PAIRED_TIE_RULE:
        raise RuntimeError("Benchmark summary does not use paired-fold one-SE selection")
    if summary.get("tie_break_order") != TIE_BREAK_ORDER:
        raise RuntimeError("Benchmark summary tie-break order differs from the frozen protocol")
    if summary.get("speed_tie_break_policy") != SPEED_TIE_BREAK_POLICY:
        raise RuntimeError("Benchmark summary speed-comparability policy differs from protocol")
    rebuilt, selected = _reconstruct_selection(
        config, manifest_sha256, candidate_ids, cv_fold_contract
    )
    _validate_selected_row(
        summary, summary_path.parent, rebuilt, selected, candidate_ids
    )

    selected_id = selected["model_id"]
    selected_spec = config["benchmark"]["models"][selected_id]
    embedding_dir, result_dir = _paths(selected_id, selected_spec, config)
    embedding_dir = embedding_dir.resolve()
    result_dir = result_dir.resolve()
    fasta_path = _resolved(config["paths"]["v0_fasta"])
    if not fasta_path.is_file():
        raise RuntimeError(f"Canonical model-input FASTA is missing: {fasta_path}")
    fasta_sha256 = sha256_file(fasta_path)
    config_path = config_path.resolve()
    summary_path = summary_path.resolve()
    manifest_path = manifest_path.resolve()
    selected_evidence = {
        "input_sha256": selected["input_sha256"],
        "embedding_artifact_sha256": selected["embedding_artifact_sha256"],
        "model_sha256": selected["model_sha256"],
    }
    identity_payload = content_identity_payload(
        config=config,
        manifest_sha256=manifest_sha256,
        fasta_sha256=fasta_sha256,
        selection_decision_sha256=selection_decision_sha256(summary),
        weights=EXPECTED_WEIGHTS,
        candidate_model_ids=candidate_ids,
        selected_model_id=selected_id,
        selected_candidate_evidence=selected_evidence,
    )
    project_test_identity = _ledger_canonical_sha256(identity_payload)
    cohort_payload = cohort_identity_payload(
        config=config,
        manifest_sha256=manifest_sha256,
        fasta_sha256=fasta_sha256,
    )
    project_test_cohort_identity = _ledger_canonical_sha256(cohort_payload)
    ledger_mode, registry_root, state_dir, claim_path = resolve_test_state_locations(
        config=config,
        manifest_sha256=manifest_sha256,
        identity=project_test_identity,
    )
    _assert_external_project_state_dir(state_dir, result_dir)
    claim_sha256: str | None = None
    cohort_claim_path: Path | None = None
    cohort_claim_sha256: str | None = None
    if ledger_mode == PRODUCTION_LEDGER_MODE:
        assert registry_root is not None and claim_path is not None
        cohort_claim_path = production_cohort_claim_path(
            registry_root, project_test_cohort_identity
        )
        existing_cohort = matching_cohort_artifacts(
            registry_root,
            cohort_identity=project_test_cohort_identity,
            manifest_sha256=manifest_sha256,
            fasta_sha256=fasta_sha256,
        )
        if existing_cohort:
            raise RuntimeError(
                "Canonical production Test cohort is already claimed/authorized/evaluated; "
                "changing the selected model cannot authorize another Test evaluation: "
                f"{[str(path) for path in existing_cohort]}"
            )
        existing = matching_identity_artifacts(registry_root, project_test_identity)
        if existing:
            raise RuntimeError(
                "Canonical production Test identity is already claimed; refusing "
                f"reauthorization: {[str(path) for path in existing]}"
            )
        cohort_claim = {
            "schema_version": 1,
            "status": "cohort_claimed_fail_closed",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "ledger_mode": ledger_mode,
            "ledger_registry_root": str(registry_root),
            "project_test_cohort_identity_payload": cohort_payload,
            "project_test_cohort_identity": project_test_cohort_identity,
            "policy": (
                "This selection-independent claim permits at most one Test lifecycle "
                "for the frozen project/data cohort, regardless of selected model."
            ),
        }
        _exclusive_json(cohort_claim_path, cohort_claim)
        cohort_claim_sha256 = sha256_file(cohort_claim_path)
        claim = {
            "schema_version": 1,
            "status": "identity_claimed_fail_closed",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "ledger_mode": ledger_mode,
            "ledger_registry_root": str(registry_root),
            "project_test_state_dir": str(state_dir),
            "project_test_identity_payload": identity_payload,
            "project_test_identity": project_test_identity,
            "project_test_cohort_identity_payload": cohort_payload,
            "project_test_cohort_identity": project_test_cohort_identity,
            "cohort_claim_path": str(cohort_claim_path),
            "cohort_claim_sha256": cohort_claim_sha256,
            "policy": (
                "This claim is never auto-removed. Administrative deletion of the fixed "
                "external registry is outside the workflow threat model."
            ),
        }
        _exclusive_json(claim_path, claim)
        claim_sha256 = sha256_file(claim_path)
    authorization_core = {
        "schema_version": 3,
        "status": "authorized_for_single_test_evaluation",
        "single_test_only": True,
        "selection_evidence_scope": "train_cv_and_validation_only",
        "test_labels_or_metrics_read_for_selection": False,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "selected_model_id": selected_id,
        "selected_result_dir": str(result_dir),
        "selected_embedding_dir": str(embedding_dir),
        "ledger_mode": ledger_mode,
        "ledger_registry_root": str(registry_root) if registry_root is not None else None,
        "identity_claim_path": str(claim_path) if claim_path is not None else None,
        "identity_claim_sha256": claim_sha256,
        "cohort_claim_path": (
            str(cohort_claim_path) if cohort_claim_path is not None else None
        ),
        "cohort_claim_sha256": cohort_claim_sha256,
        "project_test_state_dir": str(state_dir),
        "project_test_identity_payload": identity_payload,
        "project_test_identity": project_test_identity,
        "project_test_cohort_identity_payload": cohort_payload,
        "project_test_cohort_identity": project_test_cohort_identity,
        "weights": EXPECTED_WEIGHTS,
        "candidate_model_ids": candidate_ids,
        "candidate_count": len(candidate_ids),
        "manifest_sha256": manifest_sha256,
        "model_input_fasta_path": str(fasta_path),
        "model_input_fasta_sha256": fasta_sha256,
        "config_path": str(config_path),
        "config_sha256": sha256_file(config_path),
        "comparison_path": str(summary_path),
        "comparison_sha256": checksum_map,
        "selected_candidate_evidence": selected_evidence,
    }
    authorization = dict(authorization_core)
    authorization["authorization_id"] = _canonical_sha256(authorization_core)
    authorization_path = state_dir / "TEST_SELECTION_AUTHORIZATION.json"
    _exclusive_json(authorization_path, authorization)
    config = expand_benchmark_model(config, selected_id)
    config["paths"]["v0_manifest"] = str(manifest_path)
    config["paths"]["v0_fasta"] = str(fasta_path)
    config["paths"]["embedding_output"] = str(embedding_dir)
    config["paths"]["result_output"] = str(result_dir)
    if ledger_mode != PRODUCTION_LEDGER_MODE:
        config["paths"]["test_state_dir"] = str(state_dir)
    config["test_selection_authorization"] = {
        "path": str(authorization_path),
        "state_dir": str(state_dir),
        "sha256": sha256_file(authorization_path),
        "authorization_id": authorization["authorization_id"],
        "project_test_identity": authorization["project_test_identity"],
        "selected_model_id": selected_id,
        "ledger_mode": ledger_mode,
        "ledger_registry_root": str(registry_root) if registry_root is not None else None,
        "identity_claim_path": str(claim_path) if claim_path is not None else None,
        "identity_claim_sha256": claim_sha256,
        "cohort_claim_path": (
            str(cohort_claim_path) if cohort_claim_path is not None else None
        ),
        "cohort_claim_sha256": cohort_claim_sha256,
        "project_test_cohort_identity": project_test_cohort_identity,
    }
    return config, authorization_path, authorization


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()

    config, authorization_path, authorization = authorize_selection(args.config, args.summary)
    result = run(config, phase="test")
    result_dir = Path(config["paths"]["result_output"])
    marker_path = result_dir / "FINAL_TEST_EVALUATED.json"
    marker = _read_json(marker_path)
    state_dir = Path(authorization["project_test_state_dir"])
    receipt = {
        "schema_version": authorization["schema_version"],
        "status": "complete",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "authorization_id": authorization["authorization_id"],
        "authorization_path": str(authorization_path),
        "authorization_sha256": sha256_file(authorization_path),
        "selected_model_id": authorization["selected_model_id"],
        "selected_result_dir": str(result_dir.resolve()),
        "project_test_state_dir": str(state_dir.resolve()),
        "project_test_identity": authorization["project_test_identity"],
        "project_test_cohort_identity": authorization[
            "project_test_cohort_identity"
        ],
        "ledger_mode": authorization.get("ledger_mode"),
        "ledger_registry_root": authorization.get("ledger_registry_root"),
        "identity_claim_path": authorization.get("identity_claim_path"),
        "identity_claim_sha256": authorization.get("identity_claim_sha256"),
        "cohort_claim_path": authorization.get("cohort_claim_path"),
        "cohort_claim_sha256": authorization.get("cohort_claim_sha256"),
        "test_marker_path": str(marker_path),
        "test_marker_sha256": sha256_file(marker_path),
        "metrics_sha256": marker["metrics_sha256"],
        "predictions_sha256": marker["predictions_sha256"],
    }
    _exclusive_json(state_dir / "TEST_EVALUATION_RECEIPT.json", receipt)
    print(
        json.dumps(
            {"authorization": authorization, "receipt": receipt, "test_result": result},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
