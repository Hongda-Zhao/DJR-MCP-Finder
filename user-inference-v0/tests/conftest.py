from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def tiny_release(tmp_path: Path) -> Path:
    root = tmp_path / "release"
    heads_dir = root / "heads"
    heads_dir.mkdir(parents=True)
    head_settings = {
        "head1": ([1.0, 0.0, 0.0], ["non_djr", "djr"], 0.5),
        "head2": ([0.0, 1.0, 0.0], ["none", "viral_morphogenesis_associated"], 0.5),
        "head3_phylum": (
            [0.0, 0.0, 1.0],
            ["Nucleocytoviricota", "Preplasmiviricota"],
            0.7,
        ),
    }
    specs = {}
    for name, (coef, classes, threshold) in head_settings.items():
        path = heads_dir / f"{name}.npz"
        np.savez(
            path,
            scaler_mean=np.zeros(3, dtype=np.float64),
            scaler_scale=np.ones(3, dtype=np.float64),
            classifier_coef=np.asarray([coef], dtype=np.float32),
            classifier_intercept=np.zeros(1, dtype=np.float32),
        )
        specs[name] = {
            "artifact": f"heads/{name}.npz",
            "sha256": _sha(path),
            "source_joblib_sha256": "0" * 64,
            "classes": classes,
            "temperature": 1.0,
            "threshold": threshold,
            "input_dimension": 3,
            "threshold_rule": "frozen",
        }
    release = {
        "schema_version": 1,
        "release_id": "tiny-test-release",
        "embedding": {
            "model_name": "test/model",
            "model_revision": "1" * 40,
            "transformers_repository": "https://example.test/transformers.git",
            "transformers_code_revision": "2" * 40,
            "dimension": 3,
            "window_residues": 4,
            "stride": 2,
            "window_batch_size": 1,
            "classifier_input_quantization": "float16_roundtrip",
        },
        "heads": specs,
        "limitations": ["test only"],
    }
    release_path = root / "release.json"
    release_path.write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
    targets = [release_path, *sorted(heads_dir.glob("*.npz"))]
    (root / "CHECKSUMS.sha256").write_text(
        "".join(f"{_sha(path)}  {path.relative_to(root)}\n" for path in targets),
        encoding="utf-8",
    )
    return root

