"""Safe command-line entry points for project V0."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .benchmark_config import expand_benchmark_model
from .config import load_config


PROJECT_RELEASE = "V0"
SOURCE_DATASET_VERSION = "data-curation V3"
VERSION_MAPPING = "data-curation V3 -> project V0"

# This is an inventory of active boundaries, not an alternate orchestration path.
# Test authorization remains solely in the checksum-bound selected-only scripts.
WORKFLOW_BOUNDARIES: tuple[dict[str, str], ...] = (
    {
        "stage": "dataset_build",
        "entrypoint": "pbs/02_build_dataset_v0.pbs",
        "scope": "data-curation V3 exact-sequence representatives -> project V0 dataset",
    },
    {
        "stage": "postsplit_integrity",
        "entrypoint": "pbs/05_postsplit_integrity_audit.pbs",
        "scope": "independent project V0 cross-split MMseqs2 audit",
    },
    {
        "stage": "freeze_train_cv_folds",
        "entrypoint": "scripts/freeze_benchmark_cv_folds.py",
        "scope": "one shared Train-only global-component fold map",
    },
    {
        "stage": "benchmark_embedding",
        "entrypoint": "djrmcp benchmark-embed --model <registry-id>",
        "scope": "one explicitly selected member of the frozen 14-model registry",
    },
    {
        "stage": "benchmark_calibration",
        "entrypoint": "scripts/run_benchmark_metric_revision_1_gds2.pbs",
        "scope": "Train CV and Validation only; no Test",
    },
    {
        "stage": "benchmark_selection",
        "entrypoint": "scripts/summarize_model_benchmark.py",
        "scope": "freeze the development-only comparison and selected model",
    },
    {
        "stage": "selected_only_test",
        "entrypoint": "scripts/evaluate_selected_benchmark_model.py",
        "scope": "external-ledger-authorized selected-only Test; not exposed by this CLI",
    },
    {
        "stage": "validation_family_robustness_schema4_auxiliary",
        "entrypoint": "scripts/score_validation_family_robustness_v0_schema4.py",
        "scope": (
            "post-freeze four-source matched-family consistency diagnostic; "
            "no model, calibration, threshold, Test, or release feedback"
        ),
    },
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="djrmcp", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "plan",
        help="List the active data-curation-V3 to project-V0 workflow boundaries",
    )

    embed = subparsers.add_parser(
        "benchmark-embed",
        help="Embed one explicitly named model from the frozen project-V0 registry",
    )
    embed.add_argument(
        "--config",
        default=Path("configs/model_benchmark_v0.yaml"),
        type=Path,
    )
    embed.add_argument("--model", required=True)
    embed.add_argument("--device", default=None)
    embed.add_argument("--limit", type=int, default=None)
    return parser


def workflow_plan() -> dict[str, Any]:
    return {
        "project_release": PROJECT_RELEASE,
        "source_dataset_version": SOURCE_DATASET_VERSION,
        "version_mapping": VERSION_MAPPING,
        "boundaries": [dict(boundary) for boundary in WORKFLOW_BOUNDARIES],
    }


def _run_benchmark_embedding(
    config: dict[str, Any], *, device_override: str | None, limit: int | None
) -> dict[str, Any]:
    # Keep `plan` independent of NumPy/Torch/model backends; import them only
    # after an explicit benchmark model has been selected.
    from .stages import benchmark_embedding

    return benchmark_embedding.run(
        config,
        device_override=device_override,
        limit=limit,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "plan":
        print(json.dumps(workflow_plan(), indent=2, sort_keys=True))
        return 0

    config = expand_benchmark_model(load_config(args.config), args.model)
    result = _run_benchmark_embedding(
        config,
        device_override=args.device,
        limit=args.limit,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
