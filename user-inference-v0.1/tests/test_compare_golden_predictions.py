from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "compare_golden_predictions",
    ROOT / "scripts" / "compare_golden_predictions.py",
)
assert SPEC is not None and SPEC.loader is not None
COMPARATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPARATOR)


def _write_tsv(path: Path, row: dict[str, str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            delimiter="\t",
            fieldnames=list(row),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(row)


def test_archived_positive_h2_and_final_labels_map_to_current_mcp_terms(
    tmp_path: Path,
) -> None:
    common = {
        "sequence_sha256": "a" * 64,
        "head1_djr_probability": "0.9",
        "head3_nucleocytoviricota_probability": "0.8",
        "head3_preplasmiviricota_probability": "0.2",
        "head3_confidence": "0.8",
        "head1_prediction": "djr",
        "head3_reached": "true",
        "head3_prediction": "Nucleocytoviricota",
        "head1_encoder": "esm2_3b",
        "head2_encoder": "esm2_3b",
        "head3_encoder": "esmc_6b",
    }
    reference = {
        **common,
        "head2_vma_probability": "0.95",
        "head2_prediction": "viral_morphogenesis_associated",
        "final_prediction": "vma::Nucleocytoviricota",
    }
    observed = {
        **common,
        "head2_mcp_probability": "0.95",
        "head2_operational_prediction": "mcp",
        "final_prediction": "mcp::Nucleocytoviricota",
    }
    reference_path = tmp_path / "reference.tsv"
    observed_path = tmp_path / "observed.tsv"
    _write_tsv(reference_path, reference)
    _write_tsv(observed_path, observed)

    report = COMPARATOR.compare(
        reference_path,
        observed_path,
        absolute_tolerance=5e-7,
        relative_tolerance=1e-6,
    )

    assert report["status"] == "PASS"
    assert report["mismatch_count"] == 0
