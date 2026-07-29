from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from conftest import rewrite_checksums
from djrmcp_predict_v01.release import load_release


CANONICAL_RELEASE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "djrmcp_predict_v01"
    / "assets"
    / "project-v0.1-mixed-r1"
)


def test_canonical_candidate_bundle_loads_strictly() -> None:
    release = load_release(CANONICAL_RELEASE)

    assert release.release_id == "project-v0.1-candidate-esm2-3b-esmc-6b-user-inference"


def test_strict_loader_rejects_self_consistent_scientific_mutation(tmp_path: Path) -> None:
    copied = tmp_path / "mutant"
    shutil.copytree(CANONICAL_RELEASE, copied)
    release_path = copied / "release.json"
    payload = json.loads(release_path.read_text(encoding="utf-8"))
    payload["heads"]["head1"]["threshold"] = 0.123
    release_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    rewrite_checksums(copied)

    with pytest.raises(RuntimeError, match="canonical V0.1 candidate"):
        load_release(copied)


def test_release_rejects_unbound_rogue_file(tmp_path: Path) -> None:
    copied = tmp_path / "rogue"
    shutil.copytree(CANONICAL_RELEASE, copied)
    (copied / "rogue.joblib").write_bytes(b"not trusted")

    with pytest.raises(ValueError, match="does not exactly cover"):
        load_release(copied)


def test_schema2_release_loads_pickle_free_mixed_heads(tiny_release: Path) -> None:
    release = load_release(tiny_release, strict_candidate=False)
    values = np.asarray([[2.0, -1.0, 0.5]], dtype=np.float32)

    assert release.release_id == "tiny-v0.1-mixed-release"
    assert tuple(release.encoders) == ("esm2_3b", "esmc_6b")
    assert release.heads["head1"].encoder_id == "esm2_3b"
    assert release.heads["head2"].encoder_id == "esm2_3b"
    assert release.heads["head3_phylum"].encoder_id == "esmc_6b"
    assert release.heads["head1"].decision_function(values).tolist() == [2.0]
    assert release.heads["head2"].decision_function(values).tolist() == [-1.0]


def test_checksum_tamper_fails_before_loading(tiny_release: Path) -> None:
    target = tiny_release / "heads" / "head1.npz"
    target.write_bytes(target.read_bytes() + b"tamper")

    with pytest.raises(RuntimeError, match="checksum mismatch"):
        load_release(tiny_release, strict_candidate=False)


def test_unsafe_checksum_path_is_rejected(tiny_release: Path) -> None:
    (tiny_release / "CHECKSUMS.sha256").write_text(
        "0" * 64 + "  ../escape\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="not safe"):
        load_release(tiny_release, strict_candidate=False)


def test_checksum_manifest_must_bind_release_json(tiny_release: Path) -> None:
    manifest = tiny_release / "CHECKSUMS.sha256"
    retained = [
        line
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if not line.endswith("  release.json")
    ]
    manifest.write_text("\n".join(retained) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not bind release.json"):
        load_release(tiny_release, strict_candidate=False)


def test_wrong_head_encoder_binding_fails_closed(tiny_release: Path) -> None:
    release_path = tiny_release / "release.json"
    payload = json.loads(release_path.read_text(encoding="utf-8"))
    payload["heads"]["head3_phylum"]["encoder_id"] = "esm2_3b"
    release_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    rewrite_checksums(tiny_release)

    with pytest.raises(ValueError, match="head3_phylum must bind to esmc_6b"):
        load_release(tiny_release, strict_candidate=False)


def test_head_dimension_must_match_its_encoder(tiny_release: Path) -> None:
    release_path = tiny_release / "release.json"
    payload = json.loads(release_path.read_text(encoding="utf-8"))
    payload["encoders"]["esmc_6b"]["dimension"] = 4
    release_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    rewrite_checksums(tiny_release)

    with pytest.raises(ValueError, match="dimension differs from encoder esmc_6b"):
        load_release(tiny_release, strict_candidate=False)


@pytest.mark.parametrize(
    "mutation, message",
    [
        (("release_status", "promoted"), "status"),
        (("released_v0_unchanged", False), "preserve the formal V0"),
    ],
)
def test_candidate_boundary_cannot_be_silently_promoted(
    tiny_release: Path, mutation: tuple[str, object], message: str
) -> None:
    release_path = tiny_release / "release.json"
    payload = json.loads(release_path.read_text(encoding="utf-8"))
    payload[mutation[0]] = mutation[1]
    release_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    rewrite_checksums(tiny_release)

    with pytest.raises(ValueError, match=message):
        load_release(tiny_release, strict_candidate=False)


def test_frozen_encoder_precision_contract_is_enforced(tiny_release: Path) -> None:
    release_path = tiny_release / "release.json"
    payload = json.loads(release_path.read_text(encoding="utf-8"))
    payload["encoders"]["esm2_3b"]["compute_precision"] = "bfloat16"
    release_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    rewrite_checksums(tiny_release)

    with pytest.raises(ValueError, match="transformer_residue/float16"):
        load_release(tiny_release, strict_candidate=False)
