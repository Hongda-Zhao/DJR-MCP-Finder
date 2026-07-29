from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "render_portable_config.py"
SPEC = importlib.util.spec_from_file_location("render_portable_config", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


def test_longest_prefix_mapping_and_provenance_preservation() -> None:
    value = {
        "project": "/aptmp/hongda/DJR-MCP-Finder/results",
        "archive": "/aptmp/hongda/DJRMCP_Develope/frozen",
        "database": "/aptmp/hongda/database/source.faa",
        "legacy_schema4_numerical_operator": {
            "venv_root": (
                "/aptmp/hongda/DJRMCP_Develope/frozen/.venv-v0"
            )
        },
    }
    mappings = renderer.normalize_mappings(
        [
            (renderer.LEGACY_PROJECT_ROOT, "/checkout"),
            (renderer.LEGACY_ARCHIVE_ROOT, "/storage/archive"),
            (renderer.LEGACY_DATABASE_ROOT, "/storage/database"),
        ],
        [],
    )

    observed = renderer.remap_value(value, mappings)

    assert observed["project"] == "/checkout/results"
    assert observed["archive"] == "/storage/archive/frozen"
    assert observed["database"] == "/storage/database/source.faa"
    assert observed["legacy_schema4_numerical_operator"]["venv_root"] == (
        "/aptmp/hongda/DJRMCP_Develope/frozen/.venv-v0"
    )
    assert renderer.unmapped_legacy_paths(observed) == []


def test_environment_mapping_defaults_project_to_checkout(tmp_path: Path) -> None:
    observed = renderer.environment_mappings(
        {
            "DJRMCP_ARCHIVE_ROOT": str(tmp_path / "archive"),
            "DJRMCP_DATABASE_ROOT": str(tmp_path / "database"),
        },
        default_project_root=tmp_path / "checkout",
    )

    assert (renderer.LEGACY_PROJECT_ROOT, str(tmp_path / "checkout")) in observed
    assert (renderer.LEGACY_ARCHIVE_ROOT, str(tmp_path / "archive")) in observed
    assert (renderer.LEGACY_DATABASE_ROOT, str(tmp_path / "database")) in observed


def test_main_refuses_unmapped_legacy_path(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    destination = tmp_path / "output.json"
    source.write_text(
        json.dumps({"input": "/aptmp/hongda/database/input.faa"}),
        encoding="utf-8",
    )

    try:
        renderer.main([str(source), str(destination)])
    except renderer.RenderError as exc:
        assert "DJRMCP_*_ROOT" in str(exc)
    else:
        raise AssertionError("unmapped legacy database path must fail closed")
    assert not destination.exists()


def test_main_writes_generated_copy_and_keeps_source_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    destination = tmp_path / "local" / "output.json"
    original = json.dumps(
        {"project_root": renderer.LEGACY_PROJECT_ROOT, "threshold": 0.95},
        indent=2,
    ) + "\n"
    source.write_text(original, encoding="utf-8")

    assert renderer.main([str(source), str(destination)]) == 0

    assert source.read_text(encoding="utf-8") == original
    rendered = json.loads(destination.read_text(encoding="utf-8"))
    assert rendered["project_root"] == str(renderer.repository_root())
    assert rendered["threshold"] == 0.95
