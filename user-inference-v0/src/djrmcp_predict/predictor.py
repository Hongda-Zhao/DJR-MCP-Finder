"""Frozen H1 -> H2 -> H3 cascade inference."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Sequence

import numpy as np

from .fasta import ProteinRecord
from .release import ReleaseBundle


H3_UNKNOWN = "unknown/other"
NOT_REACHED = "not_reached"
MCP_POSITIVE = "mcp"
MCP_NEGATIVE = "none"


class Predictor:
    def __init__(self, release: ReleaseBundle) -> None:
        self.release = release

    def predict_embeddings(
        self, records: Sequence[ProteinRecord], embeddings: np.ndarray
    ) -> list[dict[str, Any]]:
        values = np.asarray(embeddings, dtype=np.float32)
        if values.ndim != 2 or len(values) != len(records):
            raise ValueError(
                f"Records/embeddings are not aligned: records={len(records)}, shape={values.shape}"
            )
        h1 = self.release.heads["head1"]
        h2 = self.release.heads["head2"]
        h3 = self.release.heads["head3_phylum"]

        h1_score = h1.decision_function(values)
        h2_score = h2.decision_function(values)
        h1_probability = h1.probabilities(values)[:, 1]
        h2_probability = h2.probabilities(values)[:, 1]
        h1_positive = h1_probability >= h1.threshold
        h2_positive = h2_probability >= h2.threshold
        h3_reached = h1_positive & h2_positive

        h3_probability = np.full((len(records), 2), np.nan, dtype=np.float64)
        h3_prediction = np.full(len(records), NOT_REACHED, dtype=object)
        reached_rows = np.flatnonzero(h3_reached)
        if len(reached_rows):
            selected_probability = h3.probabilities(values[reached_rows])
            h3_probability[reached_rows] = selected_probability
            selected_class = selected_probability.argmax(axis=1)
            selected_confidence = selected_probability.max(axis=1)
            for local, global_row in enumerate(reached_rows):
                h3_prediction[global_row] = (
                    H3_UNKNOWN
                    if selected_confidence[local] < h3.threshold
                    else h3.classes[int(selected_class[local])]
                )

        rows: list[dict[str, Any]] = []
        for index, record in enumerate(records):
            head1_label = h1.classes[1] if h1_positive[index] else h1.classes[0]
            head2_raw_label = MCP_POSITIVE if h2_positive[index] else MCP_NEGATIVE
            head2_operational = head2_raw_label if h1_positive[index] else NOT_REACHED
            if not h1_positive[index]:
                final_prediction = "non_djr"
            elif not h2_positive[index]:
                final_prediction = "djr_non_mcp"
            else:
                final_prediction = f"mcp::{h3_prediction[index]}"
            rows.append(
                {
                    "input_row": record.input_row,
                    "protein_id": record.protein_id,
                    "original_header": record.original_header,
                    "sequence_sha256": record.sequence_sha256,
                    "length_aa": record.length_aa,
                    "status": "ok",
                    "head1_raw_score": float(h1_score[index]),
                    "head1_djr_probability": float(h1_probability[index]),
                    "head1_prediction": head1_label,
                    "head2_raw_score": float(h2_score[index]),
                    "head2_mcp_probability": float(h2_probability[index]),
                    "head2_raw_prediction": head2_raw_label,
                    "head2_operational_prediction": head2_operational,
                    "head3_reached": bool(h3_reached[index]),
                    "head3_nucleocytoviricota_probability": (
                        float(h3_probability[index, 0]) if h3_reached[index] else None
                    ),
                    "head3_preplasmiviricota_probability": (
                        float(h3_probability[index, 1]) if h3_reached[index] else None
                    ),
                    "head3_confidence": (
                        float(h3_probability[index].max()) if h3_reached[index] else None
                    ),
                    "head3_prediction": str(h3_prediction[index]),
                    "final_prediction": final_prediction,
                    "warnings": ";".join(record.warnings),
                }
            )
        return rows

    def predict_records(self, records: Sequence[ProteinRecord], embedder: Any) -> list[dict[str, Any]]:
        """Deduplicate exact sequences for embedding, then restore input order."""

        unique: OrderedDict[str, str] = OrderedDict()
        for record in records:
            unique.setdefault(record.sequence_sha256, record.sequence)
        unique_hashes = list(unique)
        unique_embeddings = embedder.embed_sequences(list(unique.values()))
        if len(unique_embeddings) != len(unique_hashes):
            raise RuntimeError("Embedder returned the wrong number of vectors")
        by_hash = {
            digest: unique_embeddings[index] for index, digest in enumerate(unique_hashes)
        }
        aligned = np.stack([by_hash[record.sequence_sha256] for record in records])
        return self.predict_embeddings(records, aligned)
