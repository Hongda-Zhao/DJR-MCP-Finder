"""Pinned Biohub Transformers adapter for ESM-C benchmark checkpoints.

The frozen ESM-C Hugging Face checkpoints require Biohub's Transformers fork.
This wrapper fails closed unless that distribution was installed directly from
the preregistered git commit, then delegates tokenization, no-truncation checks,
special-token masking, batched forward inference, and residue pooling to the
common ``TransformerResidueAdapter``.
"""

from __future__ import annotations

import json
import re
from importlib import metadata as importlib_metadata
from typing import Any

from .benchmark_embedding import TransformerResidueAdapter


_FULL_GIT_SHA = re.compile(r"[0-9a-f]{40}")
_SUPPORTED_REPOS = {
    "Biohub/ESMC-300M",
    "Biohub/ESMC-600M",
    "Biohub/ESMC-6B",
}


def _full_git_sha(value: Any, *, field: str) -> str:
    revision = str(value or "").lower()
    if _FULL_GIT_SHA.fullmatch(revision) is None:
        raise ValueError(f"{field} must be a full 40-character hexadecimal commit SHA")
    return revision


def _installed_vcs_revision(distribution_name: str) -> str:
    """Return the VCS commit recorded for a pinned direct-url installation."""

    try:
        raw = importlib_metadata.distribution(distribution_name).read_text("direct_url.json")
    except importlib_metadata.PackageNotFoundError as error:
        raise RuntimeError(
            f"Required distribution {distribution_name!r} is not installed"
        ) from error
    if not raw:
        raise RuntimeError(
            f"{distribution_name!r} lacks direct_url.json; install the preregistered git commit"
        )
    try:
        commit = json.loads(raw)["vcs_info"]["commit_id"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"{distribution_name!r} does not record an immutable VCS commit"
        ) from error
    return _full_git_sha(commit, field=f"installed {distribution_name} revision")


class EsmcAdapter(TransformerResidueAdapter):
    """Use ESM-C only through the preregistered Biohub Transformers fork."""

    def __init__(self, settings: dict[str, Any], device: Any) -> None:
        model_name = str(settings.get("model_name", ""))
        if model_name not in _SUPPORTED_REPOS:
            raise ValueError(
                "EsmcAdapter only supports the frozen official Biohub checkpoints; "
                f"observed {model_name!r}"
            )
        if settings.get("model_loader") != "masked_lm":
            raise ValueError("EsmcAdapter requires model_loader='masked_lm'")

        self.transformers_code_revision = _full_git_sha(
            settings.get("transformers_code_revision"),
            field="transformers_code_revision",
        )
        installed_revision = _installed_vcs_revision("transformers")
        if installed_revision != self.transformers_code_revision:
            raise RuntimeError(
                "Installed Biohub Transformers code differs from the preregistered commit: "
                f"installed={installed_revision}, required={self.transformers_code_revision}"
            )
        self.installed_transformers_code_revision = installed_revision
        super().__init__(settings, device)
