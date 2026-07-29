from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from djrmcp_predict_v01.fasta import ProteinRecord
from djrmcp_predict_v01.predictor import Predictor
from djrmcp_predict_v01.release import load_release


def _records(count: int) -> list[ProteinRecord]:
    records: list[ProteinRecord] = []
    for index in range(count):
        sequence = f"ACDEFGHIKLMNPQRSTVWY{index}"
        records.append(
            ProteinRecord(
                input_row=index + 1,
                protein_id=f"p{index + 1}",
                original_header=f"p{index + 1} example",
                sequence=sequence,
                sequence_sha256=hashlib.sha256(sequence.encode("ascii")).hexdigest(),
                length_aa=len(sequence),
                warnings=("length_outside_training_range_130_2906",),
            )
        )
    return records


def _h3_row(h12_row: dict[str, object], prediction: str = "Preplasmiviricota") -> dict[str, object]:
    if prediction == "Preplasmiviricota":
        nucleocytoviricota, preplasmiviricota = 0.1, 0.9
    elif prediction == "Nucleocytoviricota":
        nucleocytoviricota, preplasmiviricota = 0.9, 0.1
    else:
        nucleocytoviricota, preplasmiviricota = 0.5, 0.5
    return {
        "protein_id": h12_row["protein_id"],
        "sequence_sha256": h12_row["sequence_sha256"],
        "head3_nucleocytoviricota_probability": nucleocytoviricota,
        "head3_preplasmiviricota_probability": preplasmiviricota,
        "head3_confidence": max(nucleocytoviricota, preplasmiviricota),
        "head3_prediction": prediction,
    }


def test_h12_is_sequential_and_only_routes_joint_positives(tiny_release: Path) -> None:
    predictor = Predictor(load_release(tiny_release, strict_candidate=False))
    records = _records(3)
    # p1 is deliberately strongly H2-positive but H1-negative. A sequential
    # implementation must leave all H2 outputs not_reached/NA for that row.
    embeddings = np.asarray(
        [
            [-2.0, 20.0, 0.0],
            [2.0, -2.0, 0.0],
            [2.0, 2.0, 0.0],
        ],
        dtype=np.float32,
    )

    rows = predictor.predict_h12(records, embeddings)

    assert rows[0]["head1_prediction"] == "non_djr"
    assert rows[0]["head2_raw_score"] is None
    assert rows[0]["head2_vma_probability"] is None
    assert rows[0]["head2_operational_prediction"] == "not_reached"
    assert rows[0]["head3_reached"] is False
    assert rows[1]["head1_prediction"] == "djr"
    assert rows[1]["head2_operational_prediction"] == "none"
    assert rows[1]["head3_reached"] is False
    assert rows[2]["head2_operational_prediction"] == "viral_morphogenesis_associated"
    assert rows[2]["head3_reached"] is True


def test_threshold_equality_is_inclusive_for_h1_and_h2(tiny_release: Path) -> None:
    predictor = Predictor(load_release(tiny_release, strict_candidate=False))
    row = predictor.predict_h12(_records(1), np.zeros((1, 3), dtype=np.float32))[0]

    assert row["head1_djr_probability"] == 0.5
    assert row["head2_vma_probability"] == 0.5
    assert row["head3_reached"] is True


def test_merge_h3_restores_order_and_encoder_provenance(tiny_release: Path) -> None:
    predictor = Predictor(load_release(tiny_release, strict_candidate=False))
    records = _records(3)
    h12 = predictor.predict_h12(
        records,
        np.asarray([[-2.0, 20.0, 0.0], [2.0, -2.0, 0.0], [2.0, 2.0, 0.0]]),
    )

    merged = predictor.merge_h3(h12, [_h3_row(h12[2])])

    assert [row["protein_id"] for row in merged] == ["p1", "p2", "p3"]
    assert [row["final_prediction"] for row in merged] == [
        "non_djr",
        "djr_non_vma",
        "vma::Preplasmiviricota",
    ]
    assert {row["head1_encoder"] for row in merged} == {"esm2_3b"}
    assert {row["head2_encoder"] for row in merged} == {"esm2_3b"}
    assert [row["head3_encoder"] for row in merged] == [
        "not_reached",
        "not_reached",
        "esmc_6b",
    ]
    assert merged[0]["head3_prediction"] == "not_reached"
    assert merged[2]["head3_confidence"] == 0.9


def test_merge_accepts_empty_h3_only_when_nothing_is_routed(tiny_release: Path) -> None:
    predictor = Predictor(load_release(tiny_release, strict_candidate=False))
    h12 = predictor.predict_h12(
        _records(2), np.asarray([[-2.0, 2.0, 0.0], [2.0, -2.0, 0.0]])
    )

    merged = predictor.merge_h3(h12, [])

    assert [row["final_prediction"] for row in merged] == ["non_djr", "djr_non_vma"]
    assert all(row["head3_encoder"] == "not_reached" for row in merged)


def test_merge_rejects_missing_h3_prediction(tiny_release: Path) -> None:
    predictor = Predictor(load_release(tiny_release, strict_candidate=False))
    h12 = predictor.predict_h12(_records(1), np.asarray([[2.0, 2.0, 0.0]]))

    with pytest.raises((ValueError, RuntimeError), match="coverage|missing|expected"):
        predictor.merge_h3(h12, [])


def test_merge_rejects_extra_h3_prediction(tiny_release: Path) -> None:
    predictor = Predictor(load_release(tiny_release, strict_candidate=False))
    h12 = predictor.predict_h12(_records(1), np.asarray([[-2.0, 2.0, 0.0]]))

    with pytest.raises((ValueError, RuntimeError), match="coverage|extra|unexpected|expected"):
        predictor.merge_h3(h12, [_h3_row(h12[0])])


def test_merge_rejects_duplicate_h3_prediction(tiny_release: Path) -> None:
    predictor = Predictor(load_release(tiny_release, strict_candidate=False))
    h12 = predictor.predict_h12(_records(1), np.asarray([[2.0, 2.0, 0.0]]))
    h3 = _h3_row(h12[0])

    with pytest.raises((ValueError, RuntimeError), match="uplicate"):
        predictor.merge_h3(h12, [h3, dict(h3)])


def test_merge_rejects_sequence_sha_mismatch(tiny_release: Path) -> None:
    predictor = Predictor(load_release(tiny_release, strict_candidate=False))
    h12 = predictor.predict_h12(_records(1), np.asarray([[2.0, 2.0, 0.0]]))
    h3 = _h3_row(h12[0])
    h3["sequence_sha256"] = "f" * 64

    with pytest.raises(
        (ValueError, RuntimeError), match="identity|order|missing|extra|sequence|SHA|sha"
    ):
        predictor.merge_h3(h12, [h3])


@pytest.mark.parametrize(
    "mutation, message",
    [
        ({"head3_nucleocytoviricota_probability": float("nan")}, "invalid probability"),
        (
            {
                "head3_nucleocytoviricota_probability": 1.2,
                "head3_preplasmiviricota_probability": -0.2,
                "head3_confidence": 1.2,
            },
            "invalid probability",
        ),
        (
            {
                "head3_nucleocytoviricota_probability": 0.4,
                "head3_preplasmiviricota_probability": 0.5,
                "head3_confidence": 0.5,
            },
            "sum to one",
        ),
        ({"head3_confidence": 0.1}, "differs from max"),
        ({"head3_prediction": "corrupt_label"}, "label differs"),
    ],
)
def test_merge_rejects_semantically_invalid_h3_results(
    tiny_release: Path, mutation: dict[str, object], message: str
) -> None:
    predictor = Predictor(load_release(tiny_release, strict_candidate=False))
    h12 = predictor.predict_h12(_records(1), np.asarray([[2.0, 2.0, 0.0]]))
    h3 = _h3_row(h12[0])
    h3.update(mutation)

    with pytest.raises(RuntimeError, match=message):
        predictor.merge_h3(h12, [h3])


def test_merge_accepts_threshold_rejected_unknown_h3(tiny_release: Path) -> None:
    predictor = Predictor(load_release(tiny_release, strict_candidate=False))
    h12 = predictor.predict_h12(_records(1), np.asarray([[2.0, 2.0, 0.0]]))

    merged = predictor.merge_h3(h12, [_h3_row(h12[0], "unknown/other")])

    assert merged[0]["final_prediction"] == "vma::unknown/other"


def test_predict_h12_rejects_record_embedding_misalignment(tiny_release: Path) -> None:
    predictor = Predictor(load_release(tiny_release, strict_candidate=False))

    with pytest.raises(ValueError, match="aligned|shape|records"):
        predictor.predict_h12(_records(2), np.zeros((1, 3), dtype=np.float32))
