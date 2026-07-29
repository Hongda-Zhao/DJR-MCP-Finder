"""Expand one model from the preregistered V0 benchmark registry."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


def benchmark_artifact_paths(
    config: dict[str, Any], model_id: str
) -> tuple[Path, Path]:
    """Resolve immutable embeddings and versioned development-result roots."""

    paths = config.get("paths", {})
    embedding_root = Path(paths.get("benchmark_embedding_root", "data/processed/embeddings"))
    result_root = Path(paths.get("benchmark_result_root", "results/model_benchmark_v0"))
    overrides = paths.get("benchmark_embedding_overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("paths.benchmark_embedding_overrides must be a mapping")
    embedding = Path(overrides.get(model_id, embedding_root / f"v0_benchmark_{model_id}"))
    return embedding, result_root / model_id


def expand_benchmark_model(config: dict[str, Any], model_id: str) -> dict[str, Any]:
    expanded = deepcopy(config)
    models = expanded["benchmark"]["models"]
    if model_id not in models:
        raise KeyError(f"Unknown benchmark model {model_id!r}; choices={sorted(models)}")
    spec = deepcopy(models[model_id])
    if "reuse_embedding" in spec:
        raise ValueError(f"{model_id} is a reuse-only benchmark entry")
    non_embedding = {
        "label",
        "license",
        "source_kind",
        "pretraining_overlap_risk",
        "reported_parameter_count",
        "reuse_embedding",
        "reuse_result",
    }
    settings = deepcopy(expanded["benchmark"]["common"])
    settings.update({key: value for key, value in spec.items() if key not in non_embedding})
    settings["benchmark_model_id"] = model_id
    expanded["embedding"] = settings
    embedding_output, result_output = benchmark_artifact_paths(expanded, model_id)
    expanded["paths"]["embedding_output"] = str(embedding_output)
    expanded["paths"]["result_output"] = str(result_output)
    return expanded
