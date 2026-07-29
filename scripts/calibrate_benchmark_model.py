#!/usr/bin/env python3
"""Run development-only calibration for one preregistered benchmark model.

This entry point intentionally exposes no Test phase.  It is safe to use for
cross-model selection after the corresponding complete embedding is present.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from djrmcp_finder.benchmark_config import expand_benchmark_model
from djrmcp_finder.config import load_config
from djrmcp_finder.cv_folds import load_frozen_cv_fold_map
from djrmcp_finder.stages.classifier import run
from djrmcp_finder.stages.embedding import sha256_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()

    config = expand_benchmark_model(load_config(args.config), args.model)
    result_dir = Path(config["paths"]["result_output"])
    calibration_path = result_dir / "calibration.json"
    if calibration_path.is_file():
        result = json.loads(calibration_path.read_text(encoding="utf-8"))
        manifest_path = Path(config["paths"]["v0_manifest"])
        embedding_metadata = Path(config["paths"]["embedding_output"]) / "metadata.json"
        expected_manifest = sha256_file(manifest_path)
        expected_embedding = sha256_file(embedding_metadata)
        cv_fold_contract, _ = load_frozen_cv_fold_map(config, manifest_path)
        if result.get("manifest_sha256") != expected_manifest:
            raise RuntimeError(
                "Existing calibration belongs to a different dataset manifest; "
                "archive it and use a clean result directory"
            )
        if result.get("embedding_metadata_sha256") != expected_embedding:
            raise RuntimeError(
                "Existing calibration belongs to different embeddings; archive it "
                "and use a clean result directory"
            )
        metric_revision = config.get("project", {}).get("metric_revision_id")
        expected_calibration_schema = 4 if metric_revision else 3
        expected_cv_schema = 3 if metric_revision else 2
        if (
            result.get("schema_version") != expected_calibration_schema
            or result.get("cv_fold_contract") != cv_fold_contract
        ):
            raise RuntimeError(
                "Existing calibration did not use the current shared frozen CV fold map; "
                "archive it and use a clean result directory"
            )
        cv_path = result_dir / "metrics" / "cross_validation.json"
        cv = json.loads(cv_path.read_text(encoding="utf-8"))
        if (
            cv.get("schema_version") != expected_cv_schema
            or cv.get("cv_fold_contract") != cv_fold_contract
        ):
            raise RuntimeError("Existing cross-validation report has invalid fold lineage")
        result["resume_status"] = "already_complete"
    else:
        result = run(config, phase="calibrate")
        result["resume_status"] = "completed_now"
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
