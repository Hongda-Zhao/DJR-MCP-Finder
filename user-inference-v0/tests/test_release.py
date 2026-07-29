from pathlib import Path

import numpy as np
import pytest

from djrmcp_predict.release import load_release


def test_release_loads_pickle_free_heads(tiny_release: Path) -> None:
    release = load_release(tiny_release)
    x = np.asarray([[2.0, -1.0, 0.5]], dtype=np.float32)
    assert release.release_id == "tiny-test-release"
    assert release.heads["head1"].decision_function(x).tolist() == [2.0]
    assert release.heads["head2"].decision_function(x).tolist() == [-1.0]


def test_checksum_tamper_fails_before_loading(tiny_release: Path) -> None:
    target = tiny_release / "heads" / "head1.npz"
    target.write_bytes(target.read_bytes() + b"tamper")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        load_release(tiny_release)


def test_unsafe_checksum_path_is_rejected(tiny_release: Path) -> None:
    manifest = tiny_release / "CHECKSUMS.sha256"
    manifest.write_text("0" * 64 + "  ../escape\n", encoding="utf-8")
    with pytest.raises(ValueError, match="safe relative path"):
        load_release(tiny_release)

