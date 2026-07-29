from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rewrite_checksums(root: Path) -> None:
    targets = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name != "CHECKSUMS.sha256"
    )
    (root / "CHECKSUMS.sha256").write_text(
        "".join(f"{file_sha256(path)}  {path.relative_to(root)}\n" for path in targets),
        encoding="utf-8",
    )


@pytest.fixture
def tiny_release(tmp_path: Path) -> Path:
    """A complete schema-2 release with deliberately distinct H1/H2/H3 axes."""

    root = tmp_path / "release"
    heads_dir = root / "heads"
    heads_dir.mkdir(parents=True)
    head_settings = {
        "head1": {
            "encoder_id": "esm2_3b",
            "coef": [1.0, 0.0, 0.0],
            "classes": ["non_djr", "djr"],
            "threshold": 0.5,
        },
        "head2": {
            "encoder_id": "esm2_3b",
            "coef": [0.0, 1.0, 0.0],
            "classes": ["none", "viral_morphogenesis_associated"],
            "threshold": 0.5,
        },
        "head3_phylum": {
            "encoder_id": "esmc_6b",
            "coef": [0.0, 0.0, 1.0],
            "classes": ["Nucleocytoviricota", "Preplasmiviricota"],
            "threshold": 0.7,
        },
    }
    head_specs: dict[str, dict[str, object]] = {}
    for index, (name, settings) in enumerate(head_settings.items(), start=1):
        path = heads_dir / f"{name}.npz"
        np.savez(
            path,
            scaler_mean=np.zeros(3, dtype=np.float32),
            scaler_scale=np.ones(3, dtype=np.float32),
            classifier_coef=np.asarray([settings["coef"]], dtype=np.float32),
            classifier_intercept=np.zeros(1, dtype=np.float32),
        )
        head_specs[name] = {
            "artifact": f"heads/{name}.npz",
            "sha256": file_sha256(path),
            "source_joblib_sha256": f"{index:x}" * 64,
            "encoder_id": settings["encoder_id"],
            "classes": settings["classes"],
            "temperature": 1.0,
            "threshold": settings["threshold"],
            "input_dimension": 3,
            "threshold_rule": "frozen",
        }

    release = {
        "schema_version": 2,
        "release_id": "tiny-v0.1-mixed-release",
        "release_status": "development_candidate_external_confirmation_required",
        "released_v0_unchanged": True,
        "candidate": {
            "candidate_id": "h12_esm2_3b__h3_esmc_6b",
            "nomination_status": "recommended_for_external_confirmation",
            "prospective_external_confirmation_required": True,
            "released_v0_change_permitted": False,
            "test_records": 0,
        },
        "encoders": {
            "esm2_3b": {
                "model_name": "facebook/esm2-test",
                "model_revision": "a" * 40,
                "backend": "transformer_residue",
                "dimension": 3,
                "compute_precision": "float16",
                "window_residues": 4,
                "stride": 2,
                "record_batch_size": 2,
                "window_batch_size": 2,
                "classifier_input_quantization": "float16_roundtrip",
                "transformers_version": "5.14.1",
            },
            "esmc_6b": {
                "model_name": "Biohub/ESMC-test",
                "model_revision": "b" * 40,
                "backend": "esmc_transformer",
                "dimension": 3,
                "compute_precision": "bfloat16",
                "window_residues": 4,
                "stride": 2,
                "record_batch_size": 1,
                "window_batch_size": 1,
                "classifier_input_quantization": "float16_roundtrip",
                "transformers_code_revision": "c" * 40,
            },
        },
        "heads": head_specs,
        "routing": {
            "order": ["head1", "head2", "head3_phylum"],
            "conditional_h3_embedding": True,
        },
        "parity": {"report": "PARITY_REPORT.json", "status": "exact_parity"},
        "limitations": ["test fixture only"],
    }
    (root / "PARITY_REPORT.json").write_text(
        json.dumps(
            {
                "status": "exact_parity",
                "head_encoder_map": {
                    "head1": "esm2_3b",
                    "head2": "esm2_3b",
                    "head3_phylum": "esmc_6b",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "release.json").write_text(
        json.dumps(release, indent=2) + "\n", encoding="utf-8"
    )
    rewrite_checksums(root)
    return root
