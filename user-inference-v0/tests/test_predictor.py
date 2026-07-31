from pathlib import Path

import numpy as np

from djrmcp_predict.fasta import ProteinRecord
from djrmcp_predict.predictor import Predictor
from djrmcp_predict.release import load_release


def _records(count: int) -> list[ProteinRecord]:
    return [
        ProteinRecord(
            input_row=index + 1,
            protein_id=f"p{index + 1}",
            original_header=f"p{index + 1}",
            sequence="ACDE",
            sequence_sha256=f"{index + 1:064x}",
            length_aa=4,
            warnings=("length_outside_training_range_130_2906",),
        )
        for index in range(count)
    ]


def test_frozen_cascade_covers_all_five_outputs(tiny_release: Path) -> None:
    release = load_release(tiny_release)
    embeddings = np.asarray(
        [
            [-2.0, 2.0, 2.0],
            [2.0, -2.0, 2.0],
            [2.0, 2.0, -2.0],
            [2.0, 2.0, 2.0],
            [2.0, 2.0, 0.0],
        ],
        dtype=np.float32,
    )
    rows = Predictor(release).predict_embeddings(_records(5), embeddings)
    assert [row["final_prediction"] for row in rows] == [
        "non_djr",
        "djr_non_mcp",
        "mcp::Nucleocytoviricota",
        "mcp::Preplasmiviricota",
        "mcp::unknown/other",
    ]
    assert rows[0]["head2_operational_prediction"] == "not_reached"
    assert rows[0]["head3_prediction"] == "not_reached"
    assert rows[1]["head3_prediction"] == "not_reached"
    assert rows[4]["head3_reached"] is True


def test_binary_threshold_equality_is_accepted(tiny_release: Path) -> None:
    release = load_release(tiny_release)
    row = Predictor(release).predict_embeddings(
        _records(1), np.zeros((1, 3), dtype=np.float32)
    )[0]
    assert row["head1_djr_probability"] == 0.5
    assert row["head2_mcp_probability"] == 0.5
    assert row["final_prediction"] == "mcp::unknown/other"


def test_exact_sequences_are_embedded_once(tiny_release: Path) -> None:
    release = load_release(tiny_release)
    records = _records(2)
    same = [
        records[0],
        ProteinRecord(
            input_row=2,
            protein_id="other-id",
            original_header="other-id",
            sequence=records[0].sequence,
            sequence_sha256=records[0].sequence_sha256,
            length_aa=records[0].length_aa,
            warnings=records[0].warnings,
        ),
    ]

    class FakeEmbedder:
        calls = []

        def embed_sequences(self, sequences):
            self.calls.append(list(sequences))
            return np.asarray([[-2.0, 0.0, 0.0]], dtype=np.float32)

    embedder = FakeEmbedder()
    rows = Predictor(release).predict_records(same, embedder)
    assert len(embedder.calls[0]) == 1
    assert [row["final_prediction"] for row in rows] == ["non_djr", "non_djr"]
