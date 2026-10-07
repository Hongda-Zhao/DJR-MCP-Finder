"""Scientific-boundary checks for the published exclusion experiment."""
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "topology_evidence", ROOT / "scripts/validate_topology_exclusion_evidence.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_published_evidence_is_internally_consistent():
    result = MODULE.validate(MODULE.DEFAULT_ROOT)
    assert result["status"] == "PASS"


@pytest.mark.parametrize("change,message", [
    ("test_count", "Test rows or split counts changed"),
    ("test_evaluated", "experimental/Test boundary violated"),
    ("cv_score", "published CV score does not match fold scores"),
])
def test_rejects_scientific_boundary_changes(tmp_path, change, message):
    root = tmp_path / "evidence"
    shutil.copytree(MODULE.DEFAULT_ROOT, root)
    path = root / "retraining/RESULTS_SUMMARY.json"
    summary = json.loads(path.read_text())
    if change == "test_count":
        summary["data_counts"]["split_counts"]["test"] -= 7
    elif change == "test_evaluated":
        summary["test_predictions_or_metrics_computed"] = True
    else:
        summary["models"][0]["CV_H3_macro_F1"] = 0.5
    path.write_text(json.dumps(summary))
    # Exercise semantic checks independently of the inventory checksum gate.
    with pytest.raises(ValueError, match=message):
        MODULE.validate(root, check_hashes=False)
