from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "build_v0_dataset.py"
CONFIG = Path(__file__).parents[1] / "configs" / "v0_dataset.json"
SPEC = importlib.util.spec_from_file_location("build_v0_dataset", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


POLICY = {
    "head3": {
        "known_classes": ["Nucleocytoviricota", "Preplasmiviricota"],
        "rare_formal_phyla_as_unknown": ["Produgelaviricota"],
        "unknown_operational_label": "unknown/other",
        "allow_literature_unclassified_as_unknown": True,
    }
}


def _active_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _fixture_source_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    config = _active_config()
    fixture_hashes: dict[str, str] = {}
    source_paths: dict[str, str] = {}
    relocated_root = tmp_path / "relocated_database_copy"
    relocated_root.mkdir()
    for index, source_name in enumerate(MODULE.POSITIVE_SOURCE_KEYS):
        payload = f"canonical-fixture-{index}-{source_name}\n".encode("ascii")
        source_path = relocated_root / f"input-{index}.dat"
        source_path.write_bytes(payload)
        source_paths[source_name] = str(source_path)
        fixture_hashes[source_name] = hashlib.sha256(payload).hexdigest()

    fixture_contract = copy.deepcopy(MODULE.PROJECT_V0_POSITIVE_RELEASE)
    fixture_contract["source_sha256"] = fixture_hashes
    monkeypatch.setattr(MODULE, "PROJECT_V0_POSITIVE_RELEASE", fixture_contract)
    monkeypatch.setattr(MODULE, "POSITIVE_SOURCE_KEYS", tuple(fixture_hashes))
    config["positive_release_contract"] = copy.deepcopy(fixture_contract)
    config["sources"]["viral_vma"] = source_paths
    return config


def test_known_phylum_is_supervised() -> None:
    observed = MODULE.positive_head3_fields(
        {"primary_phylum": "Nucleocytoviricota"}, POLICY
    )
    assert observed["known_mask"] == "1"
    assert observed["unknown_mask"] == "0"
    assert observed["operational_label"] == "Nucleocytoviricota"


def test_rare_formal_phylum_is_unknown_diagnostic() -> None:
    observed = MODULE.positive_head3_fields(
        {"primary_phylum": "Produgelaviricota"}, POLICY
    )
    assert observed["known_mask"] == "0"
    assert observed["unknown_mask"] == "1"
    assert observed["operational_label"] == "unknown/other"
    assert observed["phylum"] == "Produgelaviricota"


def test_literature_only_unclassified_is_not_given_a_fake_phylum() -> None:
    observed = MODULE.positive_head3_fields(
        {
            "taxonomies": "Abadenavirae-like_unclassified_order",
            "primary_taxonomy_authority_scope": (
                "literature_only_unclassified_not_ICTV_MSL41"
            ),
        },
        POLICY,
    )
    assert observed["phylum"] == ""
    assert observed["known_mask"] == "0"
    assert observed["unknown_mask"] == "1"
    assert observed["status"] == "literature_unclassified_unknown_diagnostic"


def test_unreviewed_missing_taxonomy_fails_closed() -> None:
    with pytest.raises(SystemExit):
        MODULE.positive_head3_fields({"taxonomies": "unreviewed"}, POLICY)


def test_active_config_is_bound_to_data_curation_v3_560_and_canonical_hashes() -> None:
    observed = MODULE.validate_project_v0_dataset_contract(_active_config())
    assert observed == MODULE.PROJECT_V0_POSITIVE_RELEASE


def test_data_curation_v2_558_contract_is_rejected() -> None:
    config = _active_config()
    config["upstream_database_release"] = "v2_foldseek_r3"
    config["version_mapping"] = "database V2 -> project V0"
    config["expected_counts"]["viral_vma"] = 558
    config["positive_release_contract"]["database_data_curation_version"] = "V2"
    config["positive_release_contract"]["release_id"] = "v2_foldseek_r3"
    config["positive_release_contract"]["exact_sequence_representatives"] = 558
    with pytest.raises(SystemExit, match="contract mismatch|exactly 560"):
        MODULE.validate_project_v0_dataset_contract(config)


def test_changing_only_expected_positive_count_is_rejected() -> None:
    config = _active_config()
    config["expected_counts"]["viral_vma"] = 559
    with pytest.raises(SystemExit, match="exactly 560"):
        MODULE.validate_project_v0_dataset_contract(config)


def test_changing_configured_canonical_source_hash_is_rejected() -> None:
    config = _active_config()
    config["positive_release_contract"]["source_sha256"]["fasta"] = "0" * 64
    with pytest.raises(SystemExit, match="canonical positive source hash mismatch"):
        MODULE.validate_project_v0_dataset_contract(config)


def test_source_identity_is_content_bound_not_absolute_path_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _fixture_source_config(tmp_path, monkeypatch)
    observed = MODULE.validate_positive_source_identity(config)
    assert observed["source_sha256"] == config["positive_release_contract"][
        "source_sha256"
    ]


def test_changing_source_bytes_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _fixture_source_config(tmp_path, monkeypatch)
    fasta_path = Path(config["sources"]["viral_vma"]["fasta"])
    fasta_path.write_bytes(fasta_path.read_bytes() + b"stale-source\n")
    with pytest.raises(SystemExit, match="positive source content mismatch for fasta"):
        MODULE.validate_positive_source_identity(config)


def test_prepared_v2_source_table_cannot_be_finalized(tmp_path: Path) -> None:
    MODULE.write_tsv(
        tmp_path / "source_files.tsv",
        [
            {"path": f"/relocated/v2/{name}", "bytes": "1", "sha256": "0" * 64}
            for name in MODULE.POSITIVE_SOURCE_KEYS
        ],
        ("path", "bytes", "sha256"),
    )
    with pytest.raises(SystemExit, match="not bound to the canonical V3"):
        MODULE.validate_prepared_positive_source_identity(
            tmp_path, MODULE.PROJECT_V0_POSITIVE_RELEASE
        )
