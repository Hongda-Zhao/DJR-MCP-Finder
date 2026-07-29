"""Content-addressed lifecycle registry for the one permitted Project-V0 Test.

The production manifest is special-cased deliberately: its lifecycle state lives
outside the active project tree at a fixed administrator-managed location.  A
content identity claim is created before authorization, so copying or archiving
the project tree, changing relative paths, changing a result-output path, or
renaming a state directory cannot create a second workflow authorization.

Deleting or modifying the fixed external registry with administrator privileges
is outside the workflow threat model.  Ordinary production code has no override
for its location.  Non-production manifests retain a caller-supplied temporary
state directory so unit and integration tests remain hermetic.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


PRODUCTION_MANIFEST_SHA256 = (
    "94aa5aff80a18367d36c06fb2f51155f3b52bd8fff4b5be2aa682d891ab84dc7"
)
PRODUCTION_LEDGER_REGISTRY_ROOT = Path(
    "/aptmp/hongda/DJRMCP_Develope/"
    "test-ledger-registry/project-v0__database-v3-560"
)
PRODUCTION_LEDGER_MODE = "canonical_production_fixed_external_registry"
PRODUCTION_PROJECT_NAME = "DJR-MCP-Finder"
PRODUCTION_COHORT_ID = "project-v0__data-curation-v3-560"

# These values identify storage locations, not the frozen scientific contract.
# Excluding them makes the identity invariant to project copies, relative/absolute
# spelling and result-root changes.  Their concrete values remain checksum-bound
# in the authorization and are independently checked before inference.
_LOCATION_ONLY_PATH_KEYS = {
    "v0_manifest",
    "v0_fasta",
    "embedding_output",
    "result_output",
    "benchmark_embedding_root",
    "benchmark_embedding_overrides",
    "benchmark_result_root",
    "test_state_dir",
    "benchmark_cv_fold_map",
    "benchmark_cv_fold_metadata",
    "known_output",
    "dataset_output",
}
_LOCATION_ONLY_MODEL_KEYS = {"reuse_embedding", "reuse_result"}

_SELECTION_ROW_FIELDS = (
    "model_id",
    "selectable",
    "selected",
    "raw_cv_rank",
    "composite_score",
    "composite_fold_scores",
    "val_head1_average_precision",
    "val_head1_fpr_at_95pct_recall",
    "val_head2_macro_f1",
    "val_head3_macro_f1",
    "validation_gate_failures",
    "within_one_paired_se",
    "paired_fold_deltas_vs_best_selectable_cv",
    "paired_delta_se_vs_best_selectable_cv",
    "tie_break_rank",
    "permissive_license",
    "gpu_seconds_per_sequence",
    "speed_tie_break_eligible",
    "speed_tie_break_status",
    "timing_comparability_key",
)

_LIFECYCLE_BASENAMES = {
    "TEST_SELECTION_AUTHORIZATION.json",
    "TEST_EVALUATION_RESERVED.json",
    "TEST_EVALUATION_RECEIPT.json",
}


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def benchmark_config_contract(config: dict[str, Any]) -> dict[str, Any]:
    """Return the location-invariant scientific part of a benchmark config."""

    contract = deepcopy(config)
    contract.pop("test_selection_authorization", None)
    paths = contract.get("paths")
    if isinstance(paths, dict):
        for key in _LOCATION_ONLY_PATH_KEYS:
            paths.pop(key, None)
    models = contract.get("benchmark", {}).get("models")
    if isinstance(models, dict):
        for spec in models.values():
            if isinstance(spec, dict):
                for key in _LOCATION_ONLY_MODEL_KEYS:
                    spec.pop(key, None)
    return contract


def benchmark_config_contract_sha256(config: dict[str, Any]) -> str:
    return canonical_sha256(benchmark_config_contract(config))


def selection_decision_sha256(summary: dict[str, Any]) -> str:
    """Hash selection semantics while excluding report and filesystem locations."""

    rows = summary.get("models")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise RuntimeError("Benchmark summary lacks model rows for Test identity")
    payload = {
        "schema_version": summary.get("schema_version"),
        "weights": summary.get("weights"),
        "validation_regression_tolerance": summary.get(
            "validation_regression_tolerance"
        ),
        "tie_rule": summary.get("tie_rule"),
        "tie_break_order": summary.get("tie_break_order"),
        "speed_tie_break_policy": summary.get("speed_tie_break_policy"),
        "candidate_model_ids": summary.get("candidate_model_ids"),
        "selected_model_id": summary.get("selected_model_id"),
        "highest_selectable_cv_model_id": summary.get(
            "highest_selectable_cv_model_id"
        ),
        "models": [
            {field: row.get(field) for field in _SELECTION_ROW_FIELDS}
            for row in rows
        ],
        "candidate_artifact_hashes": summary.get("candidate_artifact_hashes"),
    }
    return canonical_sha256(payload)


def content_identity_payload(
    *,
    config: dict[str, Any],
    manifest_sha256: str,
    fasta_sha256: str,
    selection_decision_sha256: str,
    weights: dict[str, float],
    candidate_model_ids: list[str],
    selected_model_id: str,
    selected_candidate_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Build schema-2 identity using content and selection, never filesystem paths."""

    project = config.get("project", {})
    return {
        "schema_version": 2,
        "project_name": project.get("name"),
        "project_version": project.get("version"),
        "manifest_sha256": manifest_sha256,
        "model_input_fasta_sha256": fasta_sha256,
        "benchmark_config_contract_sha256": benchmark_config_contract_sha256(config),
        "selection_decision_sha256": selection_decision_sha256,
        "weights": weights,
        "candidate_model_ids": candidate_model_ids,
        "selected_model_id": selected_model_id,
        "selected_candidate_evidence": selected_candidate_evidence,
    }


def project_data_cohort_id(
    *, config: dict[str, Any], manifest_sha256: str
) -> str:
    """Return a selection-independent project/data cohort identifier.

    The canonical production identifier is deliberately fixed in code.  In
    particular, it does not inherit ``project.version`` because that field also
    describes benchmark/metric revisions which must not create another Test
    entitlement for the same frozen cohort.
    """

    if manifest_sha256 == PRODUCTION_MANIFEST_SHA256:
        return PRODUCTION_COHORT_ID
    project = config.get("project", {})
    if not isinstance(project, dict):
        raise RuntimeError("Benchmark config project section must be a mapping")
    explicit = project.get("data_cohort_id", project.get("cohort_id"))
    if explicit is not None:
        if not isinstance(explicit, str) or not explicit.strip():
            raise RuntimeError("project data/cohort identifier must be a non-empty string")
        return explicit.strip()
    name = project.get("name")
    version = project.get("version")
    if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
        raise RuntimeError(
            "Non-production config must define project.name/project.version or "
            "an explicit project.data_cohort_id"
        )
    return f"{name}::{version}"


def cohort_identity_payload(
    *, config: dict[str, Any], manifest_sha256: str, fasta_sha256: str
) -> dict[str, Any]:
    """Build the immutable cohort identity without any model-selection fields."""

    project = config.get("project", {})
    project_name = (
        PRODUCTION_PROJECT_NAME
        if manifest_sha256 == PRODUCTION_MANIFEST_SHA256
        else (project.get("name") if isinstance(project, dict) else None)
    )
    return {
        "schema_version": 1,
        "project_name": project_name,
        "project_data_cohort_id": project_data_cohort_id(
            config=config, manifest_sha256=manifest_sha256
        ),
        "manifest_sha256": manifest_sha256,
        "model_input_fasta_sha256": fasta_sha256,
    }


def production_locations(identity: str) -> tuple[Path, Path, Path]:
    root = PRODUCTION_LEDGER_REGISTRY_ROOT.resolve()
    state_dir = root / "states" / identity
    claim_path = root / "identity_claims" / f"{identity}.json"
    return root, state_dir, claim_path


def production_cohort_claim_path(registry_root: Path, cohort_identity: str) -> Path:
    """Return the append-only claim path shared by all selections of a cohort."""

    return registry_root.resolve() / "cohort_claims" / f"{cohort_identity}.json"


def resolve_test_state_locations(
    *, config: dict[str, Any], manifest_sha256: str, identity: str
) -> tuple[str, Path | None, Path, Path | None]:
    """Resolve lifecycle storage, rejecting production config overrides."""

    paths = config.get("paths", {})
    if manifest_sha256 == PRODUCTION_MANIFEST_SHA256:
        if isinstance(paths, dict) and "test_state_dir" in paths:
            raise RuntimeError(
                "Canonical production Test ledger location is fixed externally; "
                "paths.test_state_dir overrides are forbidden"
            )
        registry_root, state_dir, claim_path = production_locations(identity)
        return PRODUCTION_LEDGER_MODE, registry_root, state_dir, claim_path

    state_value = paths.get("test_state_dir") if isinstance(paths, dict) else None
    if not isinstance(state_value, str) or not state_value:
        raise RuntimeError(
            "Non-production benchmark config must define a temporary paths.test_state_dir"
        )
    return "nonproduction_temporary_state", None, Path(state_value).resolve(), None


def matching_identity_artifacts(registry_root: Path, identity: str) -> list[Path]:
    """Find prior claims/lifecycle markers for an identity, including renamed dirs."""

    root = registry_root.resolve()
    if not root.exists():
        return []
    matches: list[Path] = []
    for path in sorted(root.rglob("*.json")):
        if path.name not in _LIFECYCLE_BASENAMES and path.parent.name != "identity_claims":
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Unreadable production Test ledger artifact: {path}") from exc
        if not isinstance(value, dict):
            raise RuntimeError(f"Invalid production Test ledger artifact: {path}")
        observed = value.get("project_test_identity")
        if observed == identity:
            matches.append(path.resolve())
    return matches


def matching_cohort_artifacts(
    registry_root: Path,
    *,
    cohort_identity: str,
    manifest_sha256: str,
    fasta_sha256: str,
) -> list[Path]:
    """Find new or legacy lifecycle artifacts belonging to a frozen cohort.

    Schema-3 production artifacts predate the cohort key and are linked through
    their manifest/FASTA hashes and then through ``project_test_identity``.  The
    second pass makes an old receipt/reservation visible even though it carries
    only that legacy selection-dependent identity.
    """

    root = registry_root.resolve()
    if not root.exists():
        return []
    records: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(root.rglob("*.json")):
        if (
            path.name not in _LIFECYCLE_BASENAMES
            and path.parent.name not in {"identity_claims", "cohort_claims"}
        ):
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Unreadable production Test ledger artifact: {path}") from exc
        if not isinstance(value, dict):
            raise RuntimeError(f"Invalid production Test ledger artifact: {path}")
        records.append((path.resolve(), value))

    matches: set[Path] = set()
    legacy_selection_identities: set[str] = set()
    for path, value in records:
        if value.get("project_test_cohort_identity") == cohort_identity:
            matches.add(path)
        payloads = (
            value,
            value.get("project_test_cohort_identity_payload"),
            value.get("project_test_identity_payload"),
        )
        same_content = any(
            isinstance(payload, dict)
            and payload.get("manifest_sha256") == manifest_sha256
            and payload.get("model_input_fasta_sha256") == fasta_sha256
            for payload in payloads
        )
        if same_content:
            matches.add(path)
            legacy_identity = value.get("project_test_identity")
            if isinstance(legacy_identity, str) and legacy_identity:
                legacy_selection_identities.add(legacy_identity)

    if legacy_selection_identities:
        for path, value in records:
            if value.get("project_test_identity") in legacy_selection_identities:
                matches.add(path)
    return sorted(matches)
