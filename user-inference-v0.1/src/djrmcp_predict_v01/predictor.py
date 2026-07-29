"""Frozen H1/H2 gate and conditional H3 prediction for the mixed candidate."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Sequence

import numpy as np

from .fasta import ProteinRecord
from .release import ReleaseBundle


H3_UNKNOWN = "unknown/other"
NOT_REACHED = "not_reached"
PENDING = "pending"


class Predictor:
    def __init__(self, release: ReleaseBundle) -> None:
        self.release = release

    @staticmethod
    def _aligned(records: Sequence[ProteinRecord], embeddings: np.ndarray) -> np.ndarray:
        values = np.asarray(embeddings, dtype=np.float32)
        if values.ndim != 2 or len(values) != len(records):
            raise ValueError(
                f"Records/embeddings are not aligned: records={len(records)}, "
                f"shape={values.shape}"
            )
        return values

    def predict_h12(
        self, records: Sequence[ProteinRecord], embeddings: np.ndarray
    ) -> list[dict[str, Any]]:
        """Run H1 on all proteins and H2 only on proteins that pass H1."""

        values = self._aligned(records, embeddings)
        h1 = self.release.heads["head1"]
        h2 = self.release.heads["head2"]
        if h1.encoder_id != "esm2_3b" or h2.encoder_id != "esm2_3b":
            raise RuntimeError("H1/H2 encoder routing differs from the frozen candidate")

        h1_score = np.asarray(h1.decision_function(values))
        h1_probability = h1.probabilities(values)[:, 1]
        h1_positive = h1_probability >= h1.threshold

        h2_score = np.full(len(records), np.nan, dtype=np.float64)
        h2_probability = np.full(len(records), np.nan, dtype=np.float64)
        h2_positive = np.zeros(len(records), dtype=bool)
        reached_h2 = np.flatnonzero(h1_positive)
        if len(reached_h2):
            selected = values[reached_h2]
            h2_score[reached_h2] = np.asarray(h2.decision_function(selected))
            h2_probability[reached_h2] = h2.probabilities(selected)[:, 1]
            h2_positive[reached_h2] = h2_probability[reached_h2] >= h2.threshold

        rows: list[dict[str, Any]] = []
        for index, record in enumerate(records):
            head1_label = h1.classes[1] if h1_positive[index] else h1.classes[0]
            if not h1_positive[index]:
                head2_raw_label = NOT_REACHED
                head2_operational = NOT_REACHED
                final_prediction = "non_djr"
            else:
                head2_raw_label = h2.classes[1] if h2_positive[index] else h2.classes[0]
                head2_operational = head2_raw_label
                final_prediction = PENDING if h2_positive[index] else "djr_non_vma"
            h3_reached = bool(h1_positive[index] and h2_positive[index])
            rows.append(
                {
                    "input_row": record.input_row,
                    "protein_id": record.protein_id,
                    "original_header": record.original_header,
                    "sequence_sha256": record.sequence_sha256,
                    "length_aa": record.length_aa,
                    "status": "ok",
                    "head1_encoder": "esm2_3b",
                    "head1_raw_score": float(h1_score[index]),
                    "head1_djr_probability": float(h1_probability[index]),
                    "head1_prediction": head1_label,
                    "head2_encoder": "esm2_3b",
                    "head2_raw_score": (
                        float(h2_score[index]) if h1_positive[index] else None
                    ),
                    "head2_vma_probability": (
                        float(h2_probability[index]) if h1_positive[index] else None
                    ),
                    "head2_raw_prediction": head2_raw_label,
                    "head2_operational_prediction": head2_operational,
                    "head3_reached": h3_reached,
                    "head3_encoder": "esmc_6b" if h3_reached else NOT_REACHED,
                    "head3_nucleocytoviricota_probability": None,
                    "head3_preplasmiviricota_probability": None,
                    "head3_confidence": None,
                    "head3_prediction": PENDING if h3_reached else NOT_REACHED,
                    "final_prediction": final_prediction,
                    "warnings": ";".join(record.warnings),
                }
            )
        return rows

    def predict_h3(
        self, sequence_sha256: Sequence[str], embeddings: np.ndarray
    ) -> list[dict[str, Any]]:
        """Classify one embedding per exact unique H3-routed sequence."""

        hashes = list(sequence_sha256)
        if len(set(hashes)) != len(hashes):
            raise ValueError("H3 sequence hashes must be unique")
        values = np.asarray(embeddings, dtype=np.float32)
        if values.ndim != 2 or len(values) != len(hashes):
            raise ValueError(
                f"H3 hashes/embeddings are not aligned: hashes={len(hashes)}, "
                f"shape={values.shape}"
            )
        h3 = self.release.heads["head3_phylum"]
        if h3.encoder_id != "esmc_6b":
            raise RuntimeError("H3 encoder routing differs from the frozen candidate")
        probabilities = h3.probabilities(values)
        rows: list[dict[str, Any]] = []
        for index, digest in enumerate(hashes):
            selected_class = int(probabilities[index].argmax())
            confidence = float(probabilities[index].max())
            prediction = (
                H3_UNKNOWN if confidence < h3.threshold else h3.classes[selected_class]
            )
            rows.append(
                {
                    "subset_row": index + 1,
                    "sequence_sha256": digest,
                    "head3_nucleocytoviricota_probability": float(probabilities[index, 0]),
                    "head3_preplasmiviricota_probability": float(probabilities[index, 1]),
                    "head3_confidence": confidence,
                    "head3_prediction": prediction,
                }
            )
        return rows

    def merge_h3(
        self,
        h12_rows: Sequence[dict[str, Any]],
        h3_rows: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Strictly merge H3 by exact sequence identity and reject partial receipts."""

        expected = list(
            OrderedDict.fromkeys(
                str(row["sequence_sha256"])
                for row in h12_rows
                if bool(row["head3_reached"])
            )
        )
        observed: list[str] = []
        by_hash: dict[str, dict[str, Any]] = {}
        for row in h3_rows:
            digest = str(row.get("sequence_sha256", ""))
            if not digest:
                raise RuntimeError("H3 result is missing sequence_sha256")
            if digest in by_hash:
                raise RuntimeError(f"Duplicate H3 result for sequence SHA256 {digest}")
            observed.append(digest)
            by_hash[digest] = dict(row)
        if observed != expected:
            missing = [digest for digest in expected if digest not in by_hash]
            extra = [digest for digest in observed if digest not in set(expected)]
            raise RuntimeError(
                "H3 result identity/order differs from routed subset: "
                f"missing={missing}, extra={extra}, expected_order={expected}, "
                f"observed_order={observed}"
            )

        h3 = self.release.heads["head3_phylum"]
        probability_fields = (
            "head3_nucleocytoviricota_probability",
            "head3_preplasmiviricota_probability",
        )
        for digest, result in by_hash.items():
            required = (*probability_fields, "head3_confidence", "head3_prediction")
            missing_fields = [field for field in required if field not in result]
            if missing_fields:
                raise RuntimeError(
                    f"H3 result for {digest} is missing fields {missing_fields}"
                )
            raw_numeric = [result[field] for field in (*probability_fields, "head3_confidence")]
            if any(isinstance(value, bool) for value in raw_numeric):
                raise RuntimeError(f"H3 result for {digest} contains Boolean probabilities")
            try:
                first, second, confidence = (float(value) for value in raw_numeric)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"H3 result for {digest} has non-numeric values") from exc
            numeric = np.asarray([first, second, confidence], dtype=np.float64)
            if not np.isfinite(numeric).all() or np.any(numeric < 0.0) or np.any(numeric > 1.0):
                raise RuntimeError(f"H3 result for {digest} has invalid probability values")
            if not np.isclose(first + second, 1.0, rtol=0.0, atol=1e-12):
                raise RuntimeError(f"H3 result for {digest} probabilities do not sum to one")
            if not np.isclose(confidence, max(first, second), rtol=0.0, atol=1e-12):
                raise RuntimeError(
                    f"H3 result for {digest} confidence differs from max probability"
                )
            expected_prediction = (
                H3_UNKNOWN
                if confidence < h3.threshold
                else h3.classes[int(np.argmax([first, second]))]
            )
            if result["head3_prediction"] != expected_prediction:
                raise RuntimeError(
                    f"H3 result for {digest} label differs: "
                    f"expected={expected_prediction}, observed={result['head3_prediction']}"
                )
            result[probability_fields[0]] = first
            result[probability_fields[1]] = second
            result["head3_confidence"] = confidence

        final_rows: list[dict[str, Any]] = []
        for source in h12_rows:
            row = dict(source)
            if row["head3_reached"]:
                result = by_hash[str(row["sequence_sha256"])]
                for field in (*probability_fields, "head3_confidence", "head3_prediction"):
                    row[field] = result[field]
                row["head3_encoder"] = "esmc_6b"
                row["final_prediction"] = f"vma::{row['head3_prediction']}"
            elif row["final_prediction"] == PENDING:
                raise RuntimeError("Non-routed row unexpectedly remained pending")
            final_rows.append(row)
        return final_rows

    def embed_h12_records(
        self, records: Sequence[ProteinRecord], embedder: Any
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Deduplicate exact sequences, embed once, and restore input order."""

        unique: OrderedDict[str, str] = OrderedDict()
        for record in records:
            unique.setdefault(record.sequence_sha256, record.sequence)
        hashes = list(unique)
        unique_embeddings = embedder.embed_sequences(list(unique.values()))
        if len(unique_embeddings) != len(hashes):
            raise RuntimeError("ESM-2 embedder returned the wrong number of vectors")
        by_hash = {digest: unique_embeddings[index] for index, digest in enumerate(hashes)}
        aligned = np.stack([by_hash[record.sequence_sha256] for record in records])
        rows = self.predict_h12(records, aligned)
        return rows, {
            "input_record_count": len(records),
            "embedded_unique_sequence_count": len(hashes),
        }
