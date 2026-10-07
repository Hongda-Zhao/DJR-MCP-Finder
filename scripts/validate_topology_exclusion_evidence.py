#!/usr/bin/env python3
"""Check the compact topology-exclusion experiment without sequences or checkpoints."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "benchmarks/topology_exclusion_20261007"


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(root: Path, *, check_hashes: bool = True) -> dict:
    """Validate recorded identities, denominators and development-only claims."""
    prior = _tsv(root / "topology/priority_quarantine_review_8.tsv")
    current = _tsv(root / "topology/review_candidates_22.tsv")
    priority = _tsv(root / "topology/priority_audit_5.tsv")
    removed = (root / "pruning/removed_tip_ids.txt").read_text().splitlines()
    retained = (root / "pruning/retained_tip_ids.txt").read_text().splitlines()
    prior_ids = {row["tip_id"] for row in prior}
    current_ids = {row["tip_id"] for row in current}
    _require(len(prior_ids) == len(prior) == 8, "prior exclusion identity mismatch")
    _require(len(current_ids) == len(current) == 22, "current exclusion identity mismatch")
    _require(not prior_ids & current_ids, "exclusion rounds overlap")
    _require(len(priority) == 5 and {r["tip_id"] for r in priority} <= current_ids,
             "priority review subset mismatch")
    _require(len(removed) == 30 and set(removed) == prior_ids | current_ids,
             "cumulative exclusion union mismatch")
    _require(len(retained) == len(set(retained)) == 528 and not set(retained) & set(removed),
             "retained tree identities mismatch")
    for tree in (root / "pruning/trees").glob("*.nwk"):
        names = re.findall(r"(?:Gold|Silver_R3)__[A-Za-z0-9_]+", tree.read_text())
        _require(len(names) == 528 and set(names) == set(retained), "Newick tips mismatch")
    qa = _tsv(root / "pruning/pruning_QA.tsv")
    _require({r["alphabet"] for r in qa} == {"aa", "3di"}, "both tree QA rows required")
    for row in qa:
        _require(row["tree_reinferred"] == "FALSE" and int(row["remaining"]) == 528,
                 "pruning must not claim new inference")
        _require(float(row["max_distance_error"]) < 1e-8, "pruning changed retained distances")

    crosswalk = _tsv(root / "retraining/exclusion_crosswalk_30.tsv")
    _require(len(crosswalk) == 30 and {r["tree_tip_id"] for r in crosswalk} == set(removed),
             "training exclusion identities mismatch")
    by_sha = {r["sequence_sha256"]: r for r in crosswalk}
    _require(len(by_sha) == 30, "duplicate exclusion sequence SHA")
    source = _json(root / "retraining/source_manifest_audit.json")
    _require(source["rows"] == 11060 and source["excluded_matched"] == 30,
             "source manifest count mismatch")
    _require(not source["manifest_modified"] and not source["test_predictions_or_metrics_read"],
             "source audit changed data or accessed Test predictions")
    matches = source["mapped_rows"]
    _require(len(matches) == 30 and {r["sequence_sha256"] for r in matches} == set(by_sha),
             "source manifest mapping is incomplete")
    for row in matches:
        _require(row["tree_tip_id"] == by_sha[row["sequence_sha256"]]["tree_tip_id"],
                 "source manifest mapping has wrong tip ID")
    removed_by_split = Counter(r["split"] for r in matches)
    _require(removed_by_split == {"train": 16, "validation": 7, "test": 7},
             "unexpected development/Test exclusion counts")
    summary = _json(root / "retraining/RESULTS_SUMMARY.json")
    _require(summary["data_counts"]["split_counts"] ==
             {"train": 6618, "validation": 2205, "test": 2214}, "Test rows or split counts changed")
    _require(summary["test_rows_unchanged"] and not summary["test_predictions_or_metrics_computed"]
             and not summary["production_model_replaced"], "experimental/Test boundary violated")
    _require(summary["data_counts"]["rows"] == 11060 - 16 - 7,
             "Test exclusions must not be applied to development experiment")
    published = {r["model"]: r for r in summary["models"]}
    _require(set(published) == {"esmc_6b", "esm2_650m"}, "unexpected model registry")
    fold_contract = None
    for model in published:
        base = root / "retraining/results" / model
        calibration = _json(base / "calibration.json")
        cv = _json(base / "metrics/cross_validation.json")
        validation = _json(base / "metrics/validation_metrics.json")
        _require(not calibration["test_evaluated"], "Test was evaluated")
        _require(calibration["manifest_sha256"] == summary["new_manifest_sha256"],
                 "training manifest hash mismatch")
        _require(calibration["cv_fold_contract"] == cv["cv_fold_contract"],
                 "CV/calibration fold mismatch")
        if fold_contract is None:
            fold_contract = calibration["cv_fold_contract"]
        _require(fold_contract == calibration["cv_fold_contract"], "model fold maps differ")
        for head, cv_key, count in (("head1", "CV_H1_AP", 6618),
                                    ("head2", "CV_H2_AP", 618),
                                    ("head3_phylum", "CV_H3_macro_F1", 305)):
            report = cv["heads"][head]
            best = report["candidates_ranked"][0]
            _require(len(best["fold_scores"]) == 5, "missing CV fold")
            mean = sum(best["fold_scores"]) / 5
            _require(math.isclose(mean, best["mean_score"], abs_tol=1e-12) and
                     math.isclose(mean, published[model][cv_key], abs_tol=1e-12),
                     "published CV score does not match fold scores")
            _require(sum(r["heldout_record_count"] for r in report["fold_diagnostics"]) == count,
                     "CV denominator mismatch")
            _require(best["parameter"] == calibration["heads"][head]["best_parameter"],
                     "calibrated model hyperparameter mismatch")
        for head, count in (("head1", 2205), ("head2", 205), ("head3_phylum", 100)):
            _require(validation["heads"][head]["n"] == count, "Validation denominator mismatch")
        _require(math.isclose(validation["heads"]["head1"]["average_precision"],
                              published[model]["Validation_H1_AP"], abs_tol=1e-12),
                 "Validation summary mismatch")
    hashes = 0
    if check_hashes:
        entries = (root / "CHECKSUMS.sha256").read_text().splitlines()
        expected = set()
        for line in entries:
            digest, name = line.split(maxsplit=1)
            path = (root / name).resolve()
            _require(path.is_relative_to(root.resolve()), "checksum path escapes evidence directory")
            _require(path.is_file(), f"missing evidence: {name}")
            _require(hashlib.sha256(path.read_bytes()).hexdigest() == digest,
                     f"evidence checksum mismatch: {name}")
            expected.add(name)
            hashes += 1
        actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()
                  and p.name != "CHECKSUMS.sha256" and "__pycache__" not in p.parts}
        _require(expected == actual, "checksum inventory does not cover all evidence files")
    return {"status": "PASS", "removed_tips": 30, "retained_tips": 528,
            "development_exclusions": 23, "test_flagged_but_unchanged": 7,
            "models": sorted(published), "verified_evidence_files": hashes,
            "raw_sequences_or_checkpoints_required": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    print(json.dumps(validate(args.root), indent=2))


if __name__ == "__main__":
    main()
