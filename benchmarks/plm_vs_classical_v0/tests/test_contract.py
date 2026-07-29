#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

from common import cyclic_fold_roles, profile_group  # noqa: E402
from prepare_inputs import validate_derived_outputs  # noqa: E402
from run_plm import empirical_tail_evidence  # noqa: E402
from summarize import (  # noqa: E402
    ALL_METHODS,
    batched_component_average_precision,
    calibration_resolution_status,
    component_weights,
    conservative_threshold,
    finite_ranking_score,
    prepare_component_ap_plan,
    source_component_weights,
    validate_reference_contracts,
)
from validation_metrics import (  # noqa: E402
    conservative_threshold as independent_conservative_threshold,
    weighted_ap as independent_weighted_ap,
)


class ContractTests(unittest.TestCase):
    def test_frozen_design_and_bootstrap_contract(self):
        config_path = Path(__file__).resolve().parents[1] / "config/benchmark.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["parameters"]["folds"], 5)
        self.assertEqual(config["parameters"]["fit_fold_count"], 3)
        self.assertEqual(config["parameters"]["bootstrap_replicates"], 10_000)

    def test_single_component_zero_fp_resolution_is_explicit(self):
        rows = [
            {"global_component_id": "singleton", "source_dataset": "cellular_djr"}
            for _ in range(62)
        ]
        status, minimum_mass = calibration_resolution_status(
            rows, source_component_weights(rows), 0.995
        )
        self.assertEqual(
            status, "CALIBRATION_RESOLUTION_LIMITED_SINGLE_COMPONENT_ZERO_FP"
        )
        self.assertAlmostEqual(minimum_mass, 1.0 / 62.0)

    def test_independent_validator_matches_ap_and_threshold_contract(self):
        labels = [1, 1, 0, 0]
        scores = [2.0, 2.0, 2.0, -math.inf]
        weights = [0.5, 0.5, 1.0, 1.0]
        expected_ap = average_precision_score(
            labels, finite_ranking_score(np.asarray(scores)), sample_weight=weights
        )
        self.assertAlmostEqual(
            independent_weighted_ap(labels, scores, weights), expected_ap, places=14
        )
        threshold, achieved = independent_conservative_threshold(
            [3.0, 3.0, 2.0], [1.0, 1.0, 1.0], 0.5
        )
        self.assertEqual(threshold, math.nextafter(3.0, math.inf))
        self.assertEqual(achieved, 0.0)

    def test_conservative_threshold_rejects_an_overweight_tie(self):
        threshold, achieved = conservative_threshold(
            np.asarray([3.0, 3.0, 2.0]), np.asarray([1.0, 1.0, 1.0]), 0.5
        )
        self.assertEqual(threshold, np.nextafter(3.0, math.inf))
        self.assertEqual(achieved, 0.0)

    def test_conservative_threshold_includes_complete_tie_only(self):
        threshold, achieved = conservative_threshold(
            np.asarray([3.0, 2.0, 2.0, 1.0]), np.asarray([0.1, 0.2, 0.2, 0.5]), 0.7
        )
        self.assertEqual(threshold, np.nextafter(2.0, math.inf))
        self.assertAlmostEqual(achieved, 0.1)

    def test_source_component_weighting(self):
        rows = [
            {"source_dataset": "a", "global_component_id": "x"},
            {"source_dataset": "a", "global_component_id": "x"},
            {"source_dataset": "a", "global_component_id": "y"},
            {"source_dataset": "b", "global_component_id": "z"},
        ]
        weights = source_component_weights(rows)
        self.assertAlmostEqual(float(weights[:3].sum()), 0.5)
        self.assertAlmostEqual(float(weights[3:].sum()), 0.5)
        self.assertAlmostEqual(weights[0] + weights[1], weights[2])

    def test_equal_component_then_record(self):
        rows = [
            {"global_component_id": "x"},
            {"global_component_id": "x"},
            {"global_component_id": "y"},
        ]
        weights = component_weights(rows)
        self.assertEqual(weights.tolist(), [0.5, 0.5, 1.0])

    def test_no_hit_is_strictly_below_finite_scores(self):
        values = finite_ranking_score(np.asarray([-math.inf, -2.0, 1.0]))
        self.assertLess(values[0], values[1])

    def test_tail_evidence_uses_inclusive_ties(self):
        values = empirical_tail_evidence(np.asarray([2.0]), np.asarray([1.0, 2.0, 2.0, 3.0]))
        self.assertAlmostEqual(values[0], -math.log10(4.0 / 5.0))

    def test_profile_group_does_not_encode_component(self):
        row = {
            "protein_id": "p",
            "source_dataset": "viral_vma_djr",
            "source_cluster_id": "Imitervirales_C0012",
            "family_metadata": "Bamfordvirae",
        }
        self.assertEqual(profile_group(row), "viral__Imitervirales")

    def test_cyclic_roles_are_disjoint_and_complete(self):
        for evaluation in range(1, 6):
            calibration, fit = cyclic_fold_roles(evaluation)
            self.assertNotEqual(evaluation, calibration)
            self.assertEqual(len(fit), 3)
            self.assertEqual(set(fit) | {evaluation, calibration}, set(range(1, 6)))

    def test_reference_contract_is_fail_closed(self):
        rows = []
        for method in [value for value in ALL_METHODS if value != "esmc6b_supervised"]:
            for evaluation_fold in range(1, 6):
                calibration_fold, _ = cyclic_fold_roles(evaluation_fold)
                for reference_kind in ("djr", "vma"):
                    rows.append(
                        {
                            "method": method,
                            "evaluation_fold": str(evaluation_fold),
                            "calibration_fold": str(calibration_fold),
                            "reference_kind": reference_kind,
                            "expected_record_count": "3",
                            "observed_record_count": "3",
                            "expected_id_set_sha256": "a" * 64,
                            "observed_id_set_sha256": "a" * 64,
                            "reference_fasta_sha256": "b" * 64,
                            "reference_manifest_sha256": "c" * 64,
                            "exact_equal": "1",
                            "receipt_kind": "test",
                            "receipt_status": "PASS",
                        }
                    )
        validate_reference_contracts(rows)
        for field in ("exact_equal", "receipt_status", "observed_id_set_sha256"):
            broken = [dict(row) for row in rows]
            broken[0][field] = ""
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                validate_reference_contracts(broken)

    def test_batched_component_ap_matches_sklearn_with_ties_and_no_hit(self):
        rows = [
            {"global_component_id": "a"},
            {"global_component_id": "a"},
            {"global_component_id": "b"},
            {"global_component_id": "c"},
        ]
        labels = np.asarray([1, 1, 0, 0])
        scores = np.asarray([2.0, 2.0, 2.0, -math.inf])
        plan = prepare_component_ap_plan(rows, labels, scores, {"a": 0, "b": 1, "c": 2})
        multiplicities = np.asarray([[1.0, 1.0, 1.0], [3.0, 1.0, 0.0]])
        observed = batched_component_average_precision(multiplicities, plan)
        base = np.asarray([0.5, 0.5, 1.0, 1.0])
        for index, component_mass in enumerate(multiplicities):
            weights = base * component_mass[[0, 0, 1, 2]]
            expected = average_precision_score(
                labels, finite_ranking_score(scores), sample_weight=weights
            )
            self.assertAlmostEqual(observed[index], expected, places=14)

    def test_batched_component_ap_fails_on_class_loss(self):
        rows = [
            {"global_component_id": "positive"},
            {"global_component_id": "negative"},
        ]
        plan = prepare_component_ap_plan(
            rows,
            np.asarray([1, 0]),
            np.asarray([1.0, 0.0]),
            {"negative": 0, "positive": 1},
        )
        with self.assertRaises(RuntimeError):
            batched_component_average_precision(np.asarray([[1.0, 0.0]]), plan)

    def test_component_ap_plan_accepts_bounded_sparse_roundoff(self):
        # This mirrors the 470-record hard/background component that exposed a
        # ~1e-14 sparse-summation residual when most DIAMOND scores were tied.
        rows = [
            *({"global_component_id": "positive"} for _ in range(3)),
            *({"global_component_id": "large_negative"} for _ in range(470)),
        ]
        labels = np.asarray([1, 1, 1, *([0] * 470)])
        scores = np.asarray(
            [3.0, 2.0, 1.0, *([-math.inf] * 462), *np.linspace(-5.0, 0.0, 8)]
        )
        component_index = {"large_negative": 0, "positive": 1}
        plan = prepare_component_ap_plan(rows, labels, scores, component_index)
        observed = batched_component_average_precision(
            np.ones((1, len(component_index)), dtype=np.float64), plan
        )[0]
        expected = average_precision_score(
            labels,
            finite_ranking_score(scores),
            sample_weight=component_weights(rows),
        )
        self.assertAlmostEqual(observed, expected, places=14)

    def test_prepared_input_reuse_checks_derived_file_sha(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "cohort.tsv"
            artifact.write_text("frozen\n", encoding="utf-8")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            self.assertTrue(validate_derived_outputs(root, {"cohort.tsv": digest}))
            artifact.write_text("changed\n", encoding="utf-8")
            self.assertFalse(validate_derived_outputs(root, {"cohort.tsv": digest}))


if __name__ == "__main__":
    unittest.main()
