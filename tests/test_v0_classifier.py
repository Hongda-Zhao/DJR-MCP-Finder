import numpy as np
import pytest
from sklearn.metrics import average_precision_score, matthews_corrcoef, roc_auc_score

from djrmcp_finder.stages.classifier import (
    HEAD_SPECS,
    _binary_decision_scores,
    _binary_metrics,
    _component_bootstrap_binary,
    _cv_score,
    _ece,
    _fit_temperature,
    _fpr_at_recall,
    _load_bundle,
    _multiclass_metrics,
    _negative_log_likelihood_from_logits,
    _operational_cascade_metrics,
    _sample_head1_epoch,
    _select_binary_threshold,
    _select_head3_unknown_diagnostic,
    _stable_log_probability_product,
)


def test_model_checksum_is_verified_before_joblib_deserialization(
    tmp_path, monkeypatch
) -> None:
    model_path = tmp_path / "tampered.joblib"
    model_path.write_bytes(b"not a trusted joblib payload")

    def forbidden_load(path):
        raise AssertionError(f"untrusted payload was deserialized: {path}")

    monkeypatch.setattr("djrmcp_finder.stages.classifier.joblib.load", forbidden_load)
    with pytest.raises(RuntimeError, match="Model checksum mismatch"):
        _load_bundle(model_path, {"model_sha256": "0" * 64})


class _FrozenDecisionModel:
    def __init__(self, scores: np.ndarray):
        self.scores = np.asarray(scores, dtype=np.float64)

    def decision_function(self, x: np.ndarray) -> np.ndarray:
        assert len(x) == len(self.scores)
        return self.scores


def test_head1_epoch_uses_all_positives_and_three_to_one_negatives() -> None:
    y = np.asarray([1, 1] + [0] * 12)
    metadata = []
    for index in range(len(y)):
        if y[index] == 1:
            source = "viral_vma_djr"
            family = "positive"
        elif index < 8:
            source = "hard_non_djr"
            family = f"family_{index % 2}"
        else:
            source = "background_non_djr"
            family = "background"
        metadata.append({"source_dataset": source, "family_metadata": family})
    selected = _sample_head1_epoch(y, metadata, 3, np.random.default_rng(7))
    assert set(np.flatnonzero(y == 1)).issubset(set(selected))
    assert len(selected) == 8
    assert int(np.sum(y[selected] == 0)) == 6


def test_binary_threshold_is_validation_optimized() -> None:
    y = np.asarray([0, 0, 1, 1])
    probability = np.asarray([0.1, 0.3, 0.7, 0.9])
    threshold, score = _select_binary_threshold(y, probability, "mcc")
    assert 0.3 < threshold <= 0.7
    assert score == 1.0


def test_binary_ranking_metrics_use_raw_scores_when_probabilities_saturate() -> None:
    y = np.asarray([0, 1, 0, 1])
    raw_score = np.asarray([1000.0, 4000.0, 3000.0, 2000.0])
    saturated_probability = np.ones(4)
    metrics = _binary_metrics(
        y,
        saturated_probability,
        0.5,
        ranking_score=raw_score,
        ranking_score_source="raw_decision_function",
    )
    assert metrics["average_precision"] == pytest.approx(
        average_precision_score(y, raw_score)
    )
    assert metrics["roc_auc"] == pytest.approx(roc_auc_score(y, raw_score))
    assert metrics["fpr_at_95pct_recall"] == pytest.approx(
        _fpr_at_recall(y, raw_score, 0.95)
    )
    assert metrics["average_precision"] != pytest.approx(
        average_precision_score(y, saturated_probability)
    )
    assert metrics["confusion_matrix"].tolist() == [[0, 2], [0, 2]]
    assert metrics["ranking_score_source"] == "raw_decision_function"


def test_stable_log_probability_product_preserves_unsaturated_product_ranking() -> None:
    first = np.asarray([-1000.0, 1000.0, -2.0, 2.0])
    second = np.asarray([1000.0, -1000.0, 3.0, 1.0])
    stable = _stable_log_probability_product(first, second)
    assert np.isfinite(stable).all()
    moderate_first = np.asarray([-2.0, 2.0, -1.0, 1.0])
    moderate_second = np.asarray([2.0, -2.0, 3.0, 1.0])
    product = (1.0 / (1.0 + np.exp(-moderate_first))) * (
        1.0 / (1.0 + np.exp(-moderate_second))
    )
    observed = _stable_log_probability_product(moderate_first, moderate_second)
    assert np.argsort(observed).tolist() == np.argsort(product).tolist()


def test_cv_binary_ap_uses_raw_decision_score() -> None:
    y = np.asarray([0, 1, 0, 1])
    raw_score = np.asarray([1000.0, 4000.0, 3000.0, 2000.0])
    probabilities = np.column_stack([np.zeros(4), np.ones(4)])
    assert _cv_score("head1", y, raw_score, probabilities) == pytest.approx(
        average_precision_score(y, raw_score)
    )


def test_binary_decision_score_requires_one_dimension() -> None:
    model = _FrozenDecisionModel(np.asarray([[0.0, 1.0], [1.0, 0.0]]))
    with pytest.raises(ValueError, match="1D positive-class"):
        _binary_decision_scores(model, np.zeros((2, 1)))


def test_stable_logit_nll_does_not_clip_extreme_binary_scores() -> None:
    y = np.asarray([0, 1])
    logits = np.asarray([1000.0, -1000.0])
    assert _negative_log_likelihood_from_logits(y, logits, 1.0) == pytest.approx(
        1000.0
    )


def test_stable_logit_nll_supports_multiclass_scores() -> None:
    y = np.asarray([0, 1])
    logits = np.asarray([[1000.0, 0.0], [0.0, 1000.0]])
    assert _negative_log_likelihood_from_logits(y, logits, 1.0) == 0.0


def test_temperature_search_is_explicit_and_not_stuck_on_old_bounds() -> None:
    logits = np.asarray([-1000.0, -100.0, 100.0, 1000.0])
    model = _FrozenDecisionModel(logits)
    x = np.zeros((4, 1))
    y = np.asarray([0, 1, 1, 1])
    settings = {
        "temperature_objective": "stable_label_smoothed_logit_nll",
        "temperature_label_smoothing": 0.001,
        "temperature_boundary_policy": "fail",
        "temperature_log10_min": -6,
        "temperature_log10_max": 6,
        "temperature_coarse_points": 481,
        "temperature_fine_points": 401,
    }
    temperature, nll, diagnostics = _fit_temperature(model, x, y, settings)
    assert 20.0 < temperature < 1e6
    assert np.isfinite(nll)
    assert diagnostics["objective"] == "stable_label_smoothed_logit_nll"
    assert diagnostics["label_smoothing"] == 0.001
    assert diagnostics["coarse_boundary_hit"] is False


def test_temperature_search_fails_when_global_boundary_is_optimal() -> None:
    model = _FrozenDecisionModel(np.asarray([-1.0, 1.0]))
    settings = {
        "temperature_objective": "stable_label_smoothed_logit_nll",
        "temperature_label_smoothing": 0.001,
        "temperature_boundary_policy": "fail",
        "temperature_log10_min": -6,
        "temperature_log10_max": -5,
        "temperature_coarse_points": 5,
        "temperature_fine_points": 5,
    }
    with pytest.raises(RuntimeError, match="global search boundary"):
        _fit_temperature(
            model,
            np.zeros((2, 1)),
            np.asarray([0, 1]),
            settings,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "temperature_objective",
            "clipped_probability_nll",
            "stable_label_smoothed_logit_nll",
        ),
        ("temperature_boundary_policy", "warn", "boundary_policy must be fail"),
    ],
)
def test_temperature_search_rejects_unfrozen_policy(
    field: str, value: str, message: str
) -> None:
    settings = {
        "temperature_objective": "stable_label_smoothed_logit_nll",
        "temperature_label_smoothing": 0.001,
        "temperature_boundary_policy": "fail",
        "temperature_log10_min": -6,
        "temperature_log10_max": 6,
        "temperature_coarse_points": 481,
        "temperature_fine_points": 401,
    }
    settings[field] = value
    with pytest.raises(ValueError, match=message):
        _fit_temperature(
            _FrozenDecisionModel(np.asarray([-1.0, 1.0])),
            np.zeros((2, 1)),
            np.asarray([0, 1]),
            settings,
        )


def test_multiclass_unknown_is_counted_as_error() -> None:
    y = np.asarray([0, 1, 2])
    probabilities = np.asarray(
        [[0.90, 0.05, 0.05], [0.34, 0.35, 0.31], [0.05, 0.05, 0.90]]
    )
    metrics, prediction = _multiclass_metrics(
        y, probabilities, ["a", "b", "c"], unknown_threshold=0.5
    )
    assert prediction.tolist() == [0, -1, 2]
    assert metrics["unknown_rejections"] == 1
    assert metrics["per_class"]["b"]["recall"] == 0.0


def test_ece_is_zero_for_perfect_certain_predictions() -> None:
    assert _ece(np.ones(4), np.ones(4)) == 0.0


def test_head3_contract_has_two_named_classes() -> None:
    assert HEAD_SPECS["head3_phylum"]["classes"] == [
        "Nucleocytoviricota",
        "Preplasmiviricota",
    ]
    assert HEAD_SPECS["head3_phylum"]["label"] == "head3_operational_label"


def test_unknown_diagnostic_selector_is_separate_from_known_mask() -> None:
    manifest = [
        {
            "split": "validation",
            "head3_unknown_diagnostic_mask": "0",
            "protein_id": "known",
        },
        {
            "split": "validation",
            "head3_unknown_diagnostic_mask": "1",
            "protein_id": "unknown",
        },
    ]
    vectors = np.asarray([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    selected, metadata, rows = _select_head3_unknown_diagnostic(
        manifest, vectors, "validation"
    )
    assert rows.tolist() == [1]
    assert metadata[0]["protein_id"] == "unknown"
    assert selected.tolist() == [[3.0, 4.0]]


def test_operational_head3_is_gated_and_not_reached_is_not_unknown() -> None:
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
            "head2_label": "none",
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
            "head3_operational_label": "Preplasmiviricota",
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
    metrics, truth_paths, predicted_paths = _operational_cascade_metrics(
        metadata,
        np.asarray([0.1, 0.9, 0.9, 0.4, 0.9]),
        np.asarray([0.9, 0.1, 0.9, 0.9, 0.9]),
        0.5,
        0.5,
        [
            "not_reached",
            "not_reached",
            "Nucleocytoviricota",
            "not_reached",
            "unknown/other",
        ],
    )
    assert metrics["stage_reach_attrition"]["head3_reached"] == 2
    assert metrics["stage_reach_attrition"]["truth_head3_scope_attrited_at_head1"] == 1
    assert metrics["head3_operational"]["all_scope_confusion_3x4"][1][0] == 1
    assert metrics["head3_operational"]["unknown_reason_strata"][
        "rare_formal_phylum_mapped_to_operational_unknown"
    ]["numerator"] == 1
    assert metrics["full_path"]["correct"] == 4
    assert truth_paths[3] == "vma::Preplasmiviricota"
    assert predicted_paths[3] == "non_djr"


def test_head1_head2_ci_resamples_global_components() -> None:
    report = _component_bootstrap_binary(
        np.asarray([0, 0, 1, 1]),
        np.asarray([0.1, 0.2, 0.8, 0.9]),
        np.asarray(["c0", "c0", "c1", "c2"]),
        ranking_score=np.asarray([0.1, 0.2, 0.8, 0.9]),
        ranking_score_source="raw_decision_function",
        threshold=0.5,
        seed=17,
        replicates=200,
    )
    assert report["unit"] == "global_component_id"
    assert report["component_count"] == 3
    assert report["replicates"] == 200
    assert report["metrics"]["average_precision"]["effective_replicates"] > 0


def test_vectorized_component_bootstrap_matches_expanded_cluster_draws() -> None:
    y = np.asarray([0, 1, 0, 1, 1])
    probability = np.asarray([0.9, 0.8, 0.8, 0.4, 0.2])
    groups = np.asarray(["a", "a", "b", "c", "c"])
    seed = 29
    replicates = 200
    observed = _component_bootstrap_binary(
        y,
        probability,
        groups,
        ranking_score=probability,
        ranking_score_source="raw_decision_function",
        threshold=0.5,
        seed=seed,
        replicates=replicates,
    )

    unique_groups, inverse = np.unique(groups, return_inverse=True)
    rng = np.random.default_rng(seed)
    draws = rng.multinomial(
        len(unique_groups),
        np.full(len(unique_groups), 1.0 / len(unique_groups)),
        size=replicates,
    )
    reference = {
        "average_precision": [],
        "roc_auc": [],
        "mcc": [],
    }
    prediction = (probability >= 0.5).astype(np.int64)
    for counts in draws:
        expanded = np.repeat(np.arange(len(y)), counts[inverse])
        if set(y[expanded]) != {0, 1}:
            continue
        reference["average_precision"].append(
            average_precision_score(y[expanded], probability[expanded])
        )
        reference["roc_auc"].append(
            roc_auc_score(y[expanded], probability[expanded])
        )
        reference["mcc"].append(
            matthews_corrcoef(y[expanded], prediction[expanded])
        )
    for metric, values in reference.items():
        assert observed["metrics"][metric]["effective_replicates"] == len(values)
        assert observed["metrics"][metric]["ci_95pct"] == pytest.approx(
            np.quantile(values, [0.025, 0.975])
        )
