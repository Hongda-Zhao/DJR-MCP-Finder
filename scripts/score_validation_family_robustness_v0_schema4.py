#!/usr/bin/env python3
"""Score the schema-4 matched-family robustness audit with frozen V0 heads.

The audit is deliberately Validation-only and inference-only.  It re-scores the
three schema-3 matched sources and adds legal, matched HardNeg source members.
Only heads that have an operational truth for a source are emitted.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import yaml

from djrmcp_finder.benchmark_config import expand_benchmark_model
from djrmcp_finder.config import load_config
from djrmcp_finder.validation_family_robustness import (
    KNOWN_H3_CLASSES,
    load_frozen_h1_challenge_predictions,
    load_frozen_model_predictions,
)


ANALYSIS_ID = "project_v0_validation_family_robustness_schema4"
MODELS = ("esm2_650m", "esmc_6b")
SOURCES = (
    "viral_vma_djr",
    "cellular_djr_none",
    "background_non_djr",
    "hard_non_djr",
)
APPLICABLE_HEADS = {
    "viral_vma_djr": ("head1", "head2", "head3_phylum"),
    "cellular_djr_none": ("head1", "head2"),
    "background_non_djr": ("head1",),
    "hard_non_djr": ("head1",),
}
EXPECTED_BINARY = {
    ("viral_vma_djr", "head1"): (1, "djr", "positive_sensitivity"),
    ("viral_vma_djr", "head2"): (
        1,
        "viral_morphogenesis_associated",
        "positive_sensitivity",
    ),
    ("cellular_djr_none", "head1"): (1, "djr", "positive_sensitivity"),
    ("cellular_djr_none", "head2"): (0, "none", "negative_specificity"),
    ("background_non_djr", "head1"): (0, "non_djr", "negative_specificity"),
    ("hard_non_djr", "head1"): (0, "non_djr", "negative_specificity"),
}
HEAD_SEED_OFFSET = {
    ("viral_vma_djr", "head1"): 1_000,
    ("viral_vma_djr", "head2"): 1_010,
    ("viral_vma_djr", "head3_phylum"): 1_020,
    ("cellular_djr_none", "head1"): 2_000,
    ("cellular_djr_none", "head2"): 2_010,
    ("background_non_djr", "head1"): 3_000,
    ("hard_non_djr", "head1"): 4_000,
}
PATH_SEED_OFFSET = {
    "viral_vma_djr": 5_000,
    "cellular_djr_none": 5_010,
    "background_non_djr": 5_020,
    "hard_non_djr": 5_030,
}
H3_CLASS_SEED_OFFSET = {
    "Nucleocytoviricota_recall": 6_000,
    "Nucleocytoviricota_f1": 6_001,
    "Preplasmiviricota_recall": 6_010,
    "Preplasmiviricota_f1": 6_011,
    "Produgelaviricota_reject_recall": 6_100,
    "literature_unclassified_reject_recall": 6_110,
}
PATH_ID = "full_expected_path"
WEIGHTING = "equal_dependence_block_then_source_cluster_then_member"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise RuntimeError(f"Missing TSV header: {path}")
        return list(reader)


def _write_tsv(path: Path, fields: list[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def _verify_flat_bundle(directory: Path) -> dict[str, str]:
    manifest = directory / "CHECKSUMS.sha256"
    if not manifest.is_file():
        raise FileNotFoundError(f"Missing checksum manifest: {manifest}")
    verified: dict[str, str] = {}
    for line_number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split(maxsplit=1)
        if len(parts) != 2:
            raise RuntimeError(f"Malformed checksum at {manifest}:{line_number}")
        expected, name = parts[0].lower(), parts[1].strip().lstrip("*")
        target = directory / name
        if Path(name).name != name or name in verified or not target.is_file():
            raise RuntimeError(f"Unsafe or missing checksum target: {target}")
        if _sha256(target) != expected:
            raise RuntimeError(f"Checksum mismatch: {target}")
        verified[name] = expected
    if not verified:
        raise RuntimeError(f"Empty checksum manifest: {manifest}")
    return verified


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes"}:
        return 1
    if text in {"0", "false", "no", ""}:
        return 0
    raise RuntimeError(f"Expected Boolean/integer flag, observed {value!r}")


def _validate_config(config: dict[str, Any]) -> None:
    if (
        config.get("schema_version") != 4
        or config.get("analysis_id") != ANALYSIS_ID
        or tuple(config.get("models", [])) != MODELS
        or config.get("evaluation_role") != "auxiliary_post_freeze_support"
        or config.get("selection_feedback_permitted") is not False
        or config.get("release_gate") is not False
        or config.get("model_state") != "frozen"
        or config.get("test_policy") != "no_test_vector_selection_or_performance_scoring"
        or config.get("frozen_primary_model_id") != "esmc_6b"
        or config.get("fixed_reference_model_id") != "esm2_650m"
        or int(config.get("bootstrap_replicates", 0)) != 10_000
        or int(config.get("bootstrap_seed", 0)) != 20260724
    ):
        raise RuntimeError("Schema-4 frozen auxiliary boundary mismatch")


def _schema3_runtime_config(config: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    schema3 = config.get("schema3")
    if not isinstance(schema3, dict):
        raise RuntimeError("Missing schema3 registry")
    schema3_config_path = Path(schema3["config"])
    runtime = yaml.safe_load(schema3_config_path.read_text(encoding="utf-8"))
    for key in (
        "benchmark_config",
        "comparison_summary",
        "master_manifest",
        "frozen_primary_model_id",
        "fixed_reference_model_id",
        "evaluation_role",
        "selection_feedback_permitted",
        "model_state",
    ):
        runtime[key] = config[key]
    runtime["cohort_dir"] = schema3["full_cohort_dir"]
    return runtime, schema3_config_path


def _source_cluster_key(row: dict[str, Any]) -> str:
    return row.get("source_cluster_key") or (
        f"{row['source_dataset']}::{row['source_cluster_id']}"
    )


def _h3_prediction(run: dict[str, Any], protein_id: str) -> tuple[str, float]:
    probabilities = np.asarray(run["h3_probability"][protein_id], dtype=np.float64)
    index = int(np.argmax(probabilities))
    confidence = float(probabilities[index])
    if confidence < float(run["h3_threshold"]):
        return "unknown/other", confidence
    return KNOWN_H3_CLASSES[index], confidence


def _bootstrap_paired_blocks(
    representative: np.ndarray,
    member: np.ndarray,
    replicates: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bootstrap paired equal-weight dependence blocks with bounded memory."""

    if (
        representative.ndim != 1
        or member.ndim != 1
        or len(representative) != len(member)
        or not len(member)
    ):
        raise RuntimeError("Invalid paired dependence-block values")
    rng = np.random.default_rng(seed)
    representative_draws = np.empty(replicates, dtype=np.float64)
    member_draws = np.empty(replicates, dtype=np.float64)
    batch = 256
    for start in range(0, replicates, batch):
        stop = min(start + batch, replicates)
        selected = rng.integers(0, len(member), size=(stop - start, len(member)))
        representative_draws[start:stop] = representative[selected].mean(axis=1)
        member_draws[start:stop] = member[selected].mean(axis=1)
    return (
        representative_draws,
        member_draws,
        member_draws - representative_draws,
    )


def nested_summary(
    rows: list[dict[str, Any]],
    *,
    replicates: int,
    seed: int,
) -> tuple[dict[str, object], np.ndarray, np.ndarray, np.ndarray]:
    """Equal block -> cluster -> member paired summary for correctness rows."""

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["dependence_block_id"], row["source_cluster_key"])].append(row)
    if not grouped:
        raise RuntimeError("No applicable rows for nested summary")
    representative_by_block: dict[str, list[float]] = defaultdict(list)
    member_by_block: dict[str, list[float]] = defaultdict(list)
    cluster_all_correct: list[int] = []
    for (block, _cluster), members in sorted(grouped.items()):
        representative_values = {int(row["representative_correct"]) for row in members}
        if len(representative_values) != 1:
            raise RuntimeError("Representative correctness changed within one cluster")
        representative_by_block[block].append(float(next(iter(representative_values))))
        member_calls = [float(int(row["member_correct"])) for row in members]
        member_by_block[block].append(float(np.mean(member_calls)))
        cluster_all_correct.append(int(all(member_calls)))
    blocks = sorted(member_by_block)
    representative_values = np.asarray(
        [np.mean(representative_by_block[block]) for block in blocks], dtype=np.float64
    )
    member_values = np.asarray(
        [np.mean(member_by_block[block]) for block in blocks], dtype=np.float64
    )
    representative_boot, member_boot, delta_boot = _bootstrap_paired_blocks(
        representative_values, member_values, replicates, seed
    )
    point_rep = float(representative_values.mean())
    point_member = float(member_values.mean())
    payload: dict[str, object] = {
        "representative_value": point_rep,
        "representative_ci_low": float(np.quantile(representative_boot, 0.025)),
        "representative_ci_high": float(np.quantile(representative_boot, 0.975)),
        "member_value": point_member,
        "member_ci_low": float(np.quantile(member_boot, 0.025)),
        "member_ci_high": float(np.quantile(member_boot, 0.975)),
        "delta_members_minus_representative": point_member - point_rep,
        "delta_ci_low": float(np.quantile(delta_boot, 0.025)),
        "delta_ci_high": float(np.quantile(delta_boot, 0.975)),
        "n_member_records": len(rows),
        "n_source_clusters": len(grouped),
        "n_dependence_blocks": len(blocks),
        "clusters_all_members_correct": sum(cluster_all_correct),
        "proportion_clusters_all_members_correct": float(np.mean(cluster_all_correct)),
        "bootstrap_replicates": replicates,
        "bootstrap_seed": seed,
        "bootstrap_status": "complete_fixed_seed_nested_block_bootstrap",
        "bootstrap_unit": "dependence_block",
        "weighting": WEIGHTING,
    }
    return payload, representative_boot, member_boot, delta_boot


def _write_subset_embedding_bundle(
    config: dict[str, Any],
    model_id: str,
    representative_ids: list[str],
    output: Path,
) -> Path:
    """Materialize only Validation HardNeg representatives from base embeddings."""

    # The frozen metric-revision config extends the base 14-model registry;
    # use the project loader so the parent is checksum-verified and expanded.
    benchmark = load_config(Path(config["benchmark_config"]))
    model_config = expand_benchmark_model(benchmark, model_id)
    source = Path(model_config["paths"]["embedding_output"])
    _verify_flat_bundle(source)
    master_path = Path(config["master_manifest"])
    master_rows = _read_tsv(master_path)
    master_by_id = {row["protein_id"]: row for row in master_rows}
    if len(master_by_id) != len(master_rows):
        raise RuntimeError("Duplicate IDs in master manifest")
    missing = set(representative_ids) - set(master_by_id)
    if missing:
        raise RuntimeError(f"HardNeg representatives absent from master: {len(missing)}")
    selected_manifest = [master_by_id[protein_id] for protein_id in representative_ids]
    if any(row["split"] != "validation" for row in selected_manifest):
        raise RuntimeError("HardNeg representative subset is not Validation-only")

    source_index_rows = _read_tsv(source / "index.tsv")
    source_index = {row["protein_id"]: row for row in source_index_rows}
    source_vectors = np.load(source / "embeddings.float16.npy", mmap_mode="r")
    selected_indices = [int(source_index[value]["embedding_row"]) for value in representative_ids]

    output.mkdir(parents=True)
    manifest_path = output / "representative_manifest.tsv"
    _write_tsv(manifest_path, list(master_rows[0]), selected_manifest)
    index_rows: list[dict[str, object]] = []
    for embedding_row, protein_id in enumerate(representative_ids):
        copied: dict[str, object] = dict(source_index[protein_id])
        copied["embedding_row"] = embedding_row
        index_rows.append(copied)
    _write_tsv(output / "index.tsv", list(source_index_rows[0]), index_rows)
    np.save(output / "embeddings.float16.npy", np.asarray(source_vectors[selected_indices]))
    np.save(output / "completed.npy", np.ones(len(representative_ids), dtype=bool))
    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    metadata["manifest_sha256"] = _sha256(manifest_path)
    for key in ("records", "record_count", "n_records", "num_sequences"):
        if key in metadata:
            metadata[key] = len(representative_ids)
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifacts = (
        "completed.npy",
        "embeddings.float16.npy",
        "index.tsv",
        "metadata.json",
    )
    (output / "CHECKSUMS.sha256").write_text(
        "".join(f"{_sha256(output / name)}  {name}\n" for name in artifacts),
        encoding="utf-8",
    )
    return manifest_path


def _hardnegative_runs(
    config: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    matched = config["hardnegative_matched"]
    manifest_path = Path(
        matched.get(
            "legal_manifest", Path(matched["legal_dir"]) / "member_manifest.tsv"
        )
    )
    representative_ids = sorted(
        {row["paired_representative_protein_id"] for row in rows}
    )
    runs: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="djrmcp-schema4-hardneg-reps-") as raw_tmp:
        base = Path(raw_tmp)
        for model_id in MODELS:
            member = load_frozen_h1_challenge_predictions(
                config,
                model_id,
                manifest_path,
                Path(matched["member_embeddings"][model_id]),
            )
            representative_dir = base / model_id
            representative_manifest = _write_subset_embedding_bundle(
                config, model_id, representative_ids, representative_dir
            )
            representative = load_frozen_h1_challenge_predictions(
                config, model_id, representative_manifest, representative_dir
            )
            if float(member["threshold"]) != float(representative["threshold"]):
                raise RuntimeError("HardNeg member/representative H1 threshold mismatch")
            runs[model_id] = {
                "member": member,
                "representative": representative,
                "provenance": {
                    "member": member["provenance"],
                    "representative_validation_subset": representative["provenance"],
                    "representative_subset_records": len(representative_ids),
                    "test_vectors_selected_for_inference": 0,
                    "test_predictions_or_metrics_computed": 0,
                },
            }
    return runs


def _binary_labels(head: str, prediction: int) -> str:
    if head == "head1":
        return "djr" if prediction else "non_djr"
    if head == "head2":
        return "viral_morphogenesis_associated" if prediction else "none"
    raise RuntimeError(f"Not a binary head: {head}")


def _schema3_prediction_rows(
    family_rows: list[dict[str, Any]], runs: dict[str, dict[str, Any]]
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for model_id in MODELS:
        run = runs[model_id]
        for row in family_rows:
            source = row["source_dataset"]
            if source not in APPLICABLE_HEADS or source == "hard_non_djr":
                raise RuntimeError(f"Unexpected schema-3 source: {source}")
            protein_id = row["protein_id"]
            representative_id = row["paired_representative_id"]
            common = {
                "model_id": model_id,
                "protein_id": protein_id,
                "source_dataset": source,
                "paired_representative_id": representative_id,
                "paired_representative_protein_id": representative_id,
                "source_cluster_id": row["source_cluster_id"],
                "source_cluster_key": _source_cluster_key(row),
                "dependence_block_id": row["dependence_block_id"],
                "train_relationship_stratum": row.get("train_relationship_stratum", ""),
            }
            for head in APPLICABLE_HEADS[source]:
                if head == "head3_phylum":
                    member_prediction, member_probability = _h3_prediction(run, protein_id)
                    rep_prediction, rep_probability = _h3_prediction(run, representative_id)
                    truth = row.get("head3_operational_label", "")
                    eligible = _as_int(row.get("h3_analysis_included", 0)) == 1 and bool(truth)
                    output.append(
                        {
                            **common,
                            "head": head,
                            "truth_label": truth if eligible else "",
                            "expected_prediction": truth if eligible else "",
                            "member_probability": member_probability,
                            "member_raw_decision_score": "",
                            "member_prediction": member_prediction,
                            "member_predicted_label": member_prediction,
                            "member_correct": int(member_prediction == truth) if eligible else "",
                            "representative_probability": rep_probability,
                            "representative_raw_decision_score": "",
                            "representative_prediction": rep_prediction,
                            "representative_predicted_label": rep_prediction,
                            "representative_correct": (
                                int(rep_prediction == truth) if eligible else ""
                            ),
                            "threshold": run["h3_threshold"],
                            "applicable_to_source": 1,
                            "metric_eligible": int(eligible),
                            "test_record": 0,
                        }
                    )
                    continue
                expected, truth_label, _metric = EXPECTED_BINARY[(source, head)]
                threshold = float(run["thresholds"][head])
                member_probability = float(run["probability"][head][protein_id])
                rep_probability = float(run["probability"][head][representative_id])
                member_prediction = int(member_probability >= threshold)
                rep_prediction = int(rep_probability >= threshold)
                output.append(
                    {
                        **common,
                        "head": head,
                        "truth_label": truth_label,
                        "expected_prediction": expected,
                        "member_probability": member_probability,
                        "member_raw_decision_score": run["raw_score"][head][protein_id],
                        "member_prediction": member_prediction,
                        "member_predicted_label": _binary_labels(head, member_prediction),
                        "member_correct": int(member_prediction == expected),
                        "representative_probability": rep_probability,
                        "representative_raw_decision_score": run["raw_score"][head][
                            representative_id
                        ],
                        "representative_prediction": rep_prediction,
                        "representative_predicted_label": _binary_labels(head, rep_prediction),
                        "representative_correct": int(rep_prediction == expected),
                        "threshold": threshold,
                        "applicable_to_source": 1,
                        "metric_eligible": 1,
                        "test_record": 0,
                    }
                )
    return output


def _hardnegative_prediction_rows(
    rows: list[dict[str, Any]], runs: dict[str, dict[str, Any]]
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for model_id in MODELS:
        member = runs[model_id]["member"]
        representative = runs[model_id]["representative"]
        threshold = float(member["threshold"])
        for row in rows:
            if (
                row["source_dataset"] != "hard_non_djr"
                or _as_int(row.get("score_head1", 0)) != 1
                or _as_int(row.get("score_head2", 0)) != 0
                or _as_int(row.get("h3_analysis_included", 0)) != 0
                or _as_int(row.get("test_record", 0)) != 0
            ):
                raise RuntimeError("Illegal HardNeg source/head/Test contract")
            protein_id = row["protein_id"]
            representative_id = row["paired_representative_protein_id"]
            member_probability = float(member["probability"][protein_id])
            rep_probability = float(representative["probability"][representative_id])
            member_prediction = int(member_probability >= threshold)
            rep_prediction = int(rep_probability >= threshold)
            output.append(
                {
                    "model_id": model_id,
                    "protein_id": protein_id,
                    "source_dataset": "hard_non_djr",
                    "paired_representative_id": row["paired_representative_id"],
                    "paired_representative_protein_id": representative_id,
                    "source_cluster_id": row["source_cluster_id"],
                    "source_cluster_key": _source_cluster_key(row),
                    "dependence_block_id": row["dependence_block_id"],
                    "train_relationship_stratum": row.get("train_relationship_stratum", ""),
                    "head": "head1",
                    "truth_label": "non_djr",
                    "expected_prediction": 0,
                    "member_probability": member_probability,
                    "member_raw_decision_score": member["raw_score"][protein_id],
                    "member_prediction": member_prediction,
                    "member_predicted_label": _binary_labels("head1", member_prediction),
                    "member_correct": int(member_prediction == 0),
                    "representative_probability": rep_probability,
                    "representative_raw_decision_score": representative["raw_score"][
                        representative_id
                    ],
                    "representative_prediction": rep_prediction,
                    "representative_predicted_label": _binary_labels("head1", rep_prediction),
                    "representative_correct": int(rep_prediction == 0),
                    "threshold": threshold,
                    "applicable_to_source": 1,
                    "metric_eligible": 1,
                    "test_record": 0,
                }
            )
    return output


def _path_rows(predictions: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in predictions:
        grouped[(str(row["model_id"]), str(row["protein_id"]))].append(row)
    output: list[dict[str, object]] = []
    for (_model, _protein), records in sorted(grouped.items()):
        first = records[0]
        source = str(first["source_dataset"])
        eligible = [row for row in records if _as_int(row["metric_eligible"]) == 1]
        if not eligible:
            raise RuntimeError("Path record has no applicable scored head")
        ordered = sorted(eligible, key=lambda row: APPLICABLE_HEADS[source].index(str(row["head"])))
        output.append(
            {
                "model_id": first["model_id"],
                "protein_id": first["protein_id"],
                "source_dataset": source,
                "paired_representative_id": first["paired_representative_id"],
                "source_cluster_id": first["source_cluster_id"],
                "source_cluster_key": first["source_cluster_key"],
                "dependence_block_id": first["dependence_block_id"],
                "path_id": PATH_ID,
                "expected_path": ">".join(str(row["truth_label"]) for row in ordered),
                "member_observed_path": ">".join(
                    str(row["member_predicted_label"]) for row in ordered
                ),
                "representative_observed_path": ">".join(
                    str(row["representative_predicted_label"]) for row in ordered
                ),
                "member_correct": int(all(_as_int(row["member_correct"]) for row in ordered)),
                "representative_correct": int(
                    all(_as_int(row["representative_correct"]) for row in ordered)
                ),
                "n_applicable_heads": len(ordered),
                "test_record": 0,
            }
        )
    return output


def _summary_tables(
    prediction_rows: list[dict[str, object]],
    path_rows: list[dict[str, object]],
    replicates: int,
    base_seed: int,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    head_rows: list[dict[str, object]] = []
    path_summary_rows: list[dict[str, object]] = []
    cluster_rows: list[dict[str, object]] = []
    bootstrap_rows: list[dict[str, object]] = []
    for model_id in MODELS:
        for source in SOURCES:
            for head in APPLICABLE_HEADS[source]:
                selected = [
                    row
                    for row in prediction_rows
                    if row["model_id"] == model_id
                    and row["source_dataset"] == source
                    and row["head"] == head
                    and _as_int(row["metric_eligible"]) == 1
                ]
                if not selected:
                    raise RuntimeError(f"Missing applicable source/head rows: {source}/{head}")
                local_seed = base_seed + HEAD_SEED_OFFSET[(source, head)]
                values, rep_boot, member_boot, delta_boot = nested_summary(
                    selected, replicates=replicates, seed=local_seed
                )
                metric = (
                    "expected_label_accuracy"
                    if head == "head3_phylum"
                    else EXPECTED_BINARY[(source, head)][2]
                )
                head_rows.append(
                    {
                        "model_id": model_id,
                        "source_dataset": source,
                        "head": head,
                        "metric": metric,
                        **values,
                    }
                )
                cluster_rows.append(
                    {
                        "model_id": model_id,
                        "source_dataset": source,
                        "endpoint_id": head,
                        "head_or_path": "head",
                        "n_clusters": values["n_source_clusters"],
                        "clusters_all_members_correct": values[
                            "clusters_all_members_correct"
                        ],
                        "proportion_clusters_all_members_correct": values[
                            "proportion_clusters_all_members_correct"
                        ],
                        "status": "complete",
                    }
                )
                for index, (rep, member, delta) in enumerate(
                    zip(rep_boot, member_boot, delta_boot, strict=True), 1
                ):
                    bootstrap_rows.append(
                        {
                            "analysis_part": "source_head",
                            "bootstrap_index": index,
                            "model_id": model_id,
                            "source_dataset": source,
                            "endpoint_id": head,
                            "representative_value": rep,
                            "member_value": member,
                            "delta_member_minus_representative": delta,
                            "bootstrap_seed": local_seed,
                        }
                    )
            selected_paths = [
                row
                for row in path_rows
                if row["model_id"] == model_id and row["source_dataset"] == source
            ]
            local_seed = base_seed + PATH_SEED_OFFSET[source]
            values, rep_boot, member_boot, delta_boot = nested_summary(
                selected_paths, replicates=replicates, seed=local_seed
            )
            path_summary_rows.append(
                {
                    "model_id": model_id,
                    "source_dataset": source,
                    "path_id": PATH_ID,
                    "metric": "expected_path_accuracy",
                    **values,
                }
            )
            cluster_rows.append(
                {
                    "model_id": model_id,
                    "source_dataset": source,
                    "endpoint_id": PATH_ID,
                    "head_or_path": "path",
                    "n_clusters": values["n_source_clusters"],
                    "clusters_all_members_correct": values["clusters_all_members_correct"],
                    "proportion_clusters_all_members_correct": values[
                        "proportion_clusters_all_members_correct"
                    ],
                    "status": "complete",
                }
            )
            for index, (rep, member, delta) in enumerate(
                zip(rep_boot, member_boot, delta_boot, strict=True), 1
            ):
                bootstrap_rows.append(
                    {
                        "analysis_part": "source_path",
                        "bootstrap_index": index,
                        "model_id": model_id,
                        "source_dataset": source,
                        "endpoint_id": PATH_ID,
                        "representative_value": rep,
                        "member_value": member,
                        "delta_member_minus_representative": delta,
                        "bootstrap_seed": local_seed,
                    }
                )
    return head_rows, path_summary_rows, cluster_rows, bootstrap_rows


def _f1_summary(
    rows: list[dict[str, Any]], target: str, replicates: int, seed: int
) -> tuple[dict[str, object], np.ndarray, np.ndarray, np.ndarray]:
    """One-vs-rest F1 over the two frozen known H3 classes."""

    blocks = sorted({str(row["dependence_block_id"]) for row in rows})
    block_index = {block: index for index, block in enumerate(blocks)}
    clusters_by_block: dict[str, set[str]] = defaultdict(set)
    records_by_cluster: Counter[tuple[str, str]] = Counter()
    for row in rows:
        block = str(row["dependence_block_id"])
        cluster = str(row["source_cluster_key"])
        clusters_by_block[block].add(cluster)
        records_by_cluster[(block, cluster)] += 1
    representative = np.zeros((len(blocks), 3), dtype=np.float64)
    member = np.zeros_like(representative)
    for row in rows:
        block = str(row["dependence_block_id"])
        cluster = str(row["source_cluster_key"])
        weight = 1.0 / len(clusters_by_block[block]) / records_by_cluster[(block, cluster)]
        truth_positive = row["truth_label"] == target
        for role, matrix in (("representative", representative), ("member", member)):
            predicted_positive = row[f"{role}_predicted_label"] == target
            if truth_positive and predicted_positive:
                column = 0  # TP
            elif not truth_positive and predicted_positive:
                column = 1  # FP
            elif truth_positive:
                column = 2  # FN
            else:
                continue
            matrix[block_index[block], column] += weight

    def f1(contribution: np.ndarray) -> np.ndarray:
        denominator = 2.0 * contribution[:, 0] + contribution[:, 1] + contribution[:, 2]
        return np.divide(
            2.0 * contribution[:, 0],
            denominator,
            out=np.zeros_like(denominator),
            where=denominator != 0,
        )

    point_rep = float(f1(representative.sum(axis=0)[None, :])[0])
    point_member = float(f1(member.sum(axis=0)[None, :])[0])
    rng = np.random.default_rng(seed)
    rep_boot = np.empty(replicates, dtype=np.float64)
    member_boot = np.empty(replicates, dtype=np.float64)
    batch = 256
    for start in range(0, replicates, batch):
        stop = min(start + batch, replicates)
        selected = rng.integers(0, len(blocks), size=(stop - start, len(blocks)))
        rep_boot[start:stop] = f1(representative[selected].sum(axis=1))
        member_boot[start:stop] = f1(member[selected].sum(axis=1))
    delta_boot = member_boot - rep_boot
    payload: dict[str, object] = {
        "representative_value": point_rep,
        "representative_ci_low": float(np.quantile(rep_boot, 0.025)),
        "representative_ci_high": float(np.quantile(rep_boot, 0.975)),
        "member_value": point_member,
        "member_ci_low": float(np.quantile(member_boot, 0.025)),
        "member_ci_high": float(np.quantile(member_boot, 0.975)),
        "delta_members_minus_representative": point_member - point_rep,
        "delta_ci_low": float(np.quantile(delta_boot, 0.025)),
        "delta_ci_high": float(np.quantile(delta_boot, 0.975)),
        "bootstrap_replicates": replicates,
        "bootstrap_seed": seed,
        "bootstrap_status": "complete_fixed_seed_nested_block_bootstrap",
        "bootstrap_unit": "dependence_block",
        "weighting": WEIGHTING,
    }
    return payload, rep_boot, member_boot, delta_boot


def _h3_class_summaries(
    family_rows: list[dict[str, Any]],
    predictions: list[dict[str, object]],
    replicates: int,
    base_seed: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    eligible_manifest = {
        row["protein_id"]: row
        for row in family_rows
        if row["source_dataset"] == "viral_vma_djr"
        and _as_int(row.get("h3_analysis_included", 0)) == 1
    }
    summaries: list[dict[str, object]] = []
    bootstraps: list[dict[str, object]] = []
    for model_id in MODELS:
        all_rows = [
            row
            for row in predictions
            if row["model_id"] == model_id
            and row["source_dataset"] == "viral_vma_djr"
            and row["head"] == "head3_phylum"
            and _as_int(row["metric_eligible"]) == 1
        ]
        known_rows = [row for row in all_rows if row["truth_label"] in KNOWN_H3_CLASSES]
        endpoint_inputs: list[tuple[str, str, str, list[dict[str, Any]], str]] = []
        for label in KNOWN_H3_CLASSES:
            endpoint_inputs.append(
                (
                    f"{label}_recall",
                    "known_phylum",
                    label,
                    [r for r in all_rows if r["truth_label"] == label],
                    "recall",
                )
            )
            endpoint_inputs.append(
                (f"{label}_f1", "known_phylum", label, known_rows, "f1")
            )
        rare_ids = {
            protein_id
            for protein_id, row in eligible_manifest.items()
            if row.get("head3_status") == "rare_formal_unknown_diagnostic"
            and row.get("head3_phylum_label") == "Produgelaviricota"
        }
        literature_ids = {
            protein_id
            for protein_id, row in eligible_manifest.items()
            if row.get("head3_status") == "literature_unclassified_unknown_diagnostic"
        }
        endpoint_inputs.extend(
            [
                (
                    "Produgelaviricota_reject_recall",
                    "rare_formal_phylum_rejection",
                    "Produgelaviricota",
                    [row for row in all_rows if row["protein_id"] in rare_ids],
                    "reject_recall",
                ),
                (
                    "literature_unclassified_reject_recall",
                    "literature_unclassified_rejection",
                    "literature_unclassified",
                    [row for row in all_rows if row["protein_id"] in literature_ids],
                    "reject_recall",
                ),
            ]
        )
        for endpoint_id, group, truth, rows, metric in endpoint_inputs:
            if not rows:
                raise RuntimeError(f"Missing frozen H3 diagnostic support: {endpoint_id}")
            local_seed = base_seed + H3_CLASS_SEED_OFFSET[endpoint_id]
            if metric == "f1":
                values, rep_boot, member_boot, delta_boot = _f1_summary(
                    rows, truth, replicates, local_seed
                )
                evaluation_rows = rows
                truth_rows = [row for row in rows if row["truth_label"] == truth]
            else:
                values, rep_boot, member_boot, delta_boot = nested_summary(
                    rows, replicates=replicates, seed=local_seed
                )
                evaluation_rows = rows
                truth_rows = rows
            summaries.append(
                {
                    "model_id": model_id,
                    "endpoint_id": endpoint_id,
                    "diagnostic_group": group,
                    "truth_label": truth,
                    "metric": metric,
                    **values,
                    "n_truth_records": len(truth_rows),
                    "n_truth_clusters": len({row["source_cluster_key"] for row in truth_rows}),
                    "n_truth_blocks": len({row["dependence_block_id"] for row in truth_rows}),
                    "n_evaluation_records": len(evaluation_rows),
                    "n_evaluation_clusters": len(
                        {row["source_cluster_key"] for row in evaluation_rows}
                    ),
                    "n_evaluation_blocks": len(
                        {row["dependence_block_id"] for row in evaluation_rows}
                    ),
                    "interpretation": (
                        "small_prespecified_diagnostic_not_general_unknown_detection"
                        if metric == "reject_recall"
                        else "two_known_inherited_phyla_only"
                    ),
                }
            )
            for index, (rep, member, delta) in enumerate(
                zip(rep_boot, member_boot, delta_boot, strict=True), 1
            ):
                bootstraps.append(
                    {
                        "analysis_part": "h3_class",
                        "bootstrap_index": index,
                        "model_id": model_id,
                        "source_dataset": "viral_vma_djr",
                        "endpoint_id": endpoint_id,
                        "representative_value": rep,
                        "member_value": member,
                        "delta_member_minus_representative": delta,
                        "bootstrap_seed": local_seed,
                    }
                )
    return summaries, bootstraps


def _coverage_rows(
    config: dict[str, Any],
    schema3_rows: list[dict[str, Any]],
    hard_rows: list[dict[str, Any]],
) -> list[dict[str, object]]:
    schema3 = config["schema3"]
    cohort_dir = Path(schema3["full_cohort_dir"])
    legacy_coverage = {
        row["source_id"]: row for row in _read_tsv(cohort_dir / "source_coverage_summary.tsv")
    }
    excluded_path = cohort_dir / "excluded_entities.tsv"
    excluded = _read_tsv(excluded_path) if excluded_path.is_file() else []
    rows: list[dict[str, object]] = []
    for source in SOURCES[:-1]:
        selected = [row for row in schema3_rows if row["source_dataset"] == source]
        excluded_source = [row for row in excluded if row.get("source_dataset") == source]
        legacy = legacy_coverage[source]
        legal_clusters = len({_source_cluster_key(row) for row in selected})
        candidate_clusters = int(legacy.get("recovered_validation_parents") or legal_clusters)
        rows.append(
            {
                "source_dataset": source,
                "n_validation_representatives": int(
                    legacy["model_validation_representatives"]
                ),
                "n_candidate_clusters": candidate_clusters,
                "n_candidate_members": len(selected) + len(excluded_source),
                "n_legal_clusters": legal_clusters,
                "n_legal_members": len(selected),
                "n_excluded_clusters": max(0, candidate_clusters - legal_clusters),
                "n_excluded_members": len(excluded_source),
                "coverage_status": "complete",
                "exclusion_reason": (
                    ";".join(
                        f"{key}:{value}"
                        for key, value in sorted(
                            Counter(
                                row.get("exclusion_reason", "unspecified")
                                for row in excluded_source
                            ).items()
                        )
                    )
                    if excluded_source
                    else ""
                ),
            }
        )
    matched = config["hardnegative_matched"]
    expected_clusters = int(matched["expected_candidate_clusters"])
    expected_members = int(matched["expected_candidate_members"])
    legal_clusters = len({_source_cluster_key(row) for row in hard_rows})
    legal_members = len(hard_rows)
    legal_dir = Path(matched["legal_dir"])
    excluded_path = Path(matched.get("excluded_entities", legal_dir / "excluded_entities.tsv"))
    excluded_rows = _read_tsv(excluded_path) if excluded_path.is_file() else []
    reasons = Counter()
    for row in excluded_rows:
        legal_flag = row.get("legal", row.get("analysis_included", ""))
        if legal_flag and _as_int(legal_flag) == 1:
            continue
        reason = row.get("exclusion_reason") or row.get("reason") or "excluded"
        reasons[reason] += 1
    rows.append(
        {
            "source_dataset": "hard_non_djr",
            "n_validation_representatives": int(matched["expected_validation_anchors"]),
            "n_candidate_clusters": expected_clusters,
            "n_candidate_members": expected_members,
            "n_legal_clusters": legal_clusters,
            "n_legal_members": legal_members,
            "n_excluded_clusters": max(0, expected_clusters - legal_clusters),
            "n_excluded_members": max(0, expected_members - legal_members),
            "coverage_status": "complete" if legal_members else "not_estimable_no_legal_members",
            "exclusion_reason": ";".join(
                f"{key}:{value}" for key, value in sorted(reasons.items())
            ),
        }
    )
    return rows


def _error_destinations(
    predictions: list[dict[str, object]], paths: list[dict[str, object]]
) -> list[dict[str, object]]:
    counts: Counter[tuple[str, ...]] = Counter()
    for row in predictions:
        if _as_int(row["metric_eligible"]) != 1:
            continue
        for role in ("member", "representative"):
            counts[
                (
                    str(row["model_id"]),
                    str(row["source_dataset"]),
                    str(row["head"]),
                    role,
                    str(row["truth_label"]),
                    str(row[f"{role}_predicted_label"]),
                    "correct" if _as_int(row[f"{role}_correct"]) else "error",
                )
            ] += 1
    for row in paths:
        for role in ("member", "representative"):
            counts[
                (
                    str(row["model_id"]),
                    str(row["source_dataset"]),
                    PATH_ID,
                    role,
                    str(row["expected_path"]),
                    str(row[f"{role}_observed_path"]),
                    "correct" if _as_int(row[f"{role}_correct"]) else "error",
                )
            ] += 1
    return [
        {
            "model_id": key[0],
            "source_dataset": key[1],
            "endpoint_id": key[2],
            "record_role": key[3],
            "expected_destination": key[4],
            "observed_destination": key[5],
            "outcome": key[6],
            "n_records": value,
        }
        for key, value in sorted(counts.items())
    ]


def score(config_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    _validate_config(config)
    output = Path(config["result_dir"])
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite result: {output}")
    temporary = output.with_name(f"{output.name}.tmp-{os.getpid()}")
    if temporary.exists():
        raise FileExistsError(f"Temporary result exists: {temporary}")
    temporary.mkdir(parents=True)

    schema3_config, schema3_config_path = _schema3_runtime_config(config)
    schema3_manifest = Path(config["schema3"]["family_member_manifest"])
    family_rows: list[dict[str, Any]] = _read_tsv(schema3_manifest)
    if (
        not family_rows
        or {row["source_dataset"] for row in family_rows} != set(SOURCES[:-1])
        or any(_as_int(row.get("test_record", 0)) for row in family_rows)
    ):
        raise RuntimeError("Schema-3 matched cohort is not the expected Validation-only source set")
    schema3_runs = {
        model_id: load_frozen_model_predictions(schema3_config, model_id, family_rows)
        for model_id in MODELS
    }

    matched = config["hardnegative_matched"]
    hard_manifest = Path(
        matched.get("legal_manifest", Path(matched["legal_dir"]) / "member_manifest.tsv")
    )
    hard_rows: list[dict[str, Any]] = _read_tsv(hard_manifest)
    _verify_flat_bundle(Path(matched["legal_dir"]))
    if not hard_rows or any(_as_int(row.get("test_record", 0)) for row in hard_rows):
        raise RuntimeError("HardNeg matched cohort is empty or contains Test records")
    hard_runs = _hardnegative_runs(config, hard_rows)

    prediction_rows = _schema3_prediction_rows(family_rows, schema3_runs)
    prediction_rows.extend(_hardnegative_prediction_rows(hard_rows, hard_runs))
    path_rows = _path_rows(prediction_rows)
    replicates = int(config["bootstrap_replicates"])
    seed = int(config["bootstrap_seed"])
    head_rows, path_summary_rows, cluster_rows, bootstrap_rows = _summary_tables(
        prediction_rows, path_rows, replicates, seed
    )
    h3_class_rows, h3_bootstrap_rows = _h3_class_summaries(
        family_rows, prediction_rows, replicates, seed
    )
    bootstrap_rows.extend(h3_bootstrap_rows)
    coverage_rows = _coverage_rows(config, family_rows, hard_rows)
    error_rows = _error_destinations(prediction_rows, path_rows)
    hardnegative_rows = [
        {
            "model_id": row["model_id"],
            "source_dataset": row["source_dataset"],
            "endpoint_id": "head1_specificity",
            "metric": row["metric"],
            "value": row["member_value"],
            "ci_low": row["member_ci_low"],
            "ci_high": row["member_ci_high"],
            "n_records": row["n_member_records"],
            "n_clusters": row["n_source_clusters"],
            "n_blocks": row["n_dependence_blocks"],
            "status": row["bootstrap_status"],
        }
        for row in head_rows
        if row["source_dataset"] == "hard_non_djr" and row["head"] == "head1"
    ]

    _write_tsv(temporary / "predictions.tsv", list(prediction_rows[0]), prediction_rows)
    _write_tsv(temporary / "expected_path_predictions.tsv", list(path_rows[0]), path_rows)
    _write_tsv(temporary / "source_head_summary.tsv", list(head_rows[0]), head_rows)
    _write_tsv(
        temporary / "source_path_summary.tsv", list(path_summary_rows[0]), path_summary_rows
    )
    _write_tsv(
        temporary / "cluster_all_members_summary.tsv", list(cluster_rows[0]), cluster_rows
    )
    _write_tsv(temporary / "h3_class_summary.tsv", list(h3_class_rows[0]), h3_class_rows)
    _write_tsv(
        temporary / "hardnegative_summary.tsv",
        list(hardnegative_rows[0]),
        hardnegative_rows,
    )
    _write_tsv(temporary / "coverage_summary.tsv", list(coverage_rows[0]), coverage_rows)
    _write_tsv(
        temporary / "error_destination_summary.tsv", list(error_rows[0]), error_rows
    )
    _write_tsv(
        temporary / "bootstrap_replicates.tsv", list(bootstrap_rows[0]), bootstrap_rows
    )

    summary: dict[str, Any] = {
        "schema_version": 4,
        "analysis_id": ANALYSIS_ID,
        "status": "complete_four_source",
        "project_version": config["project_version"],
        "data_curation_version": config["data_curation_version"],
        "evaluation_role": "auxiliary_post_freeze_support",
        "selection_feedback_permitted": False,
        "release_gate": False,
        "model_state": "frozen",
        "model_fit_operations": 0,
        "calibration_fit_operations": 0,
        "threshold_optimization_operations": 0,
        "benchmark_selection_operations": 0,
        "test_vectors_selected_for_inference": 0,
        "test_predictions_or_metrics_computed": 0,
        "sources": list(SOURCES),
        "applicable_heads": {key: list(value) for key, value in APPLICABLE_HEADS.items()},
        "path_id": PATH_ID,
        "metrics": {
            "source_head": head_rows,
            "source_path": path_summary_rows,
            "cluster_all_members": cluster_rows,
            "h3_class": h3_class_rows,
            "hardnegative_h1": hardnegative_rows,
        },
        "coverage": coverage_rows,
        "models": {
            model_id: {
                "schema3_matched_sources": schema3_runs[model_id]["provenance"],
                "hardnegative_matched": hard_runs[model_id]["provenance"],
            }
            for model_id in MODELS
        },
        "bootstrap": {
            "replicates": replicates,
            "seed": seed,
            "unit": "dependence_block",
            "weighting": WEIGHTING,
            "interval": "paired_percentile_95pct_descriptive",
        },
        "interpretation": (
            "matched_validation_family_expected_head_and_path_consistency_only;"
            "not_model_selection_not_independent_test_not_generalization_claim"
        ),
        "negative_only_metric_policy": "specificity_only_no_AP_AUC_or_F1",
        "input_sha256": {
            "config": _sha256(config_path),
            "schema3_config": _sha256(schema3_config_path),
            "schema3_family_member_manifest": _sha256(schema3_manifest),
            "hardnegative_legal_manifest": _sha256(hard_manifest),
            "hardnegative_legal_checksums": _sha256(
                Path(matched["legal_dir"]) / "CHECKSUMS.sha256"
            ),
        },
        "record_counts": {
            "schema3_family_members": len(family_rows),
            "hardnegative_legal_members": len(hard_rows),
            "predictions": len(prediction_rows),
            "expected_paths": len(path_rows),
            "bootstrap_rows": len(bootstrap_rows),
            "hardnegative_h2_predictions": sum(
                row["source_dataset"] == "hard_non_djr" and row["head"] == "head2"
                for row in prediction_rows
            ),
            "hardnegative_h3_predictions": sum(
                row["source_dataset"] == "hard_non_djr"
                and row["head"] == "head3_phylum"
                for row in prediction_rows
            ),
        },
        "limits": [
            "Labels are inherited from source clusters and provide auxiliary robustness support.",
            "Four source classes are reported separately and are never averaged.",
            "Heads without an operational source truth are N/A and have no prediction rows.",
            "Negative-only sources use specificity; AP, AUC, and F1 are not estimable here.",
            "H3 F1 is restricted to its two known inherited phyla; rare and literature-"
            "unclassified rejection recalls are separate small diagnostics and are not a "
            "general unknown-virus estimate.",
            "No Test vector is selected, inferred, or scored.",
        ],
    }
    (temporary / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    targets = sorted(path for path in temporary.iterdir() if path.name != "CHECKSUMS.sha256")
    (temporary / "CHECKSUMS.sha256").write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in targets), encoding="utf-8"
    )
    os.replace(temporary, output)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/validation_family_robustness_v0_schema4.yaml"),
    )
    args = parser.parse_args()
    print(json.dumps(score(args.config), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
