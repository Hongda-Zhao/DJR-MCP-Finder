from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _launchers() -> list[Path]:
    paths = [*ROOT.joinpath("pbs").glob("*.pbs")]
    paths.extend(ROOT.joinpath("scripts").glob("*.pbs"))
    paths.extend(ROOT.joinpath("scripts").glob("*.sh"))
    paths.extend(ROOT.joinpath("benchmarks").glob("*/pbs/*.pbs"))
    paths.extend(ROOT.joinpath("benchmarks").glob("*/pbs/*.sh"))
    return sorted(set(paths))


def test_operational_launchers_do_not_embed_legacy_user_paths() -> None:
    launchers = _launchers()
    assert launchers
    for path in launchers:
        source = path.read_text(encoding="utf-8")
        assert "/aptmp/hongda" not in source, path
        assert "/lab/hongda" not in source, path
        assert "hongda-133" not in source, path


def test_primary_launchers_expose_portable_roots_and_config_overrides() -> None:
    expected = {
        "scripts/build_v0_dataset.sh": (
            "DJRMCP_PROJECT_ROOT",
            "DJRMCP_DATASET_CONFIG",
        ),
        "scripts/run_benchmark_metric_revision_1_gds2.pbs": (
            "DJRMCP_PROJECT_ROOT",
            "DJRMCP_VENV_ROOT",
            "DJRMCP_BENCHMARK_CONFIG",
        ),
        "scripts/run_validation_family_robustness_v0_schema4.pbs": (
            "DJRMCP_PROJECT_ROOT",
            "DJRMCP_ARCHIVE_ROOT",
            "DJRMCP_SCHEMA4_CONFIG",
        ),
        "scripts/run_validation_family_robustness_v0_schema5_mixed_heads.pbs": (
            "DJRMCP_PROJECT_ROOT",
            "DJRMCP_ARCHIVE_ROOT",
            "DJRMCP_SCHEMA5_CONFIG",
        ),
        "benchmarks/plm_vs_classical_v0/pbs/submit_pipeline.sh": (
            "DJRMCP_PROJECT_ROOT",
            "DJRMCP_VENV_ROOT",
            "DJRMCP_PLM_CONFIG",
        ),
        "benchmarks/ultra_remote_v0_v01/pbs/run_benchmark.pbs": (
            "DJRMCP_PROJECT_ROOT",
            "DJRMCP_VENV_ROOT",
            "DJRMCP_ULTRA_CONFIG",
        ),
    }
    for relative, variables in expected.items():
        source = (ROOT / relative).read_text(encoding="utf-8")
        for variable in variables:
            assert variable in source, (relative, variable)


def test_schema4_launcher_binds_config_write_paths_before_execution() -> None:
    source = (
        ROOT / "scripts/run_validation_family_robustness_v0_schema4.pbs"
    ).read_text(encoding="utf-8")
    assert "launcher/config analysis-root mismatch" in source
    assert "launcher/config write-path mismatch" in source
    assert source.index("schema4_path_preflight=PASS") < source.index(
        "score_validation_family_robustness_v0_schema4.py"
    )


def test_submit_pipeline_propagates_custom_module_initializer() -> None:
    source = (
        ROOT / "benchmarks/plm_vs_classical_v0/pbs/submit_pipeline.sh"
    ).read_text(encoding="utf-8")
    assert "DJRMCP_MODULE_INIT=${DJRMCP_MODULE_INIT}" in source


def test_pbs_workdir_fallbacks_fail_closed_on_non_project_directories() -> None:
    for path in _launchers():
        source = path.read_text(encoding="utf-8")
        if "PBS_O_WORKDIR" in source:
            assert "pyproject.toml" in source, path


def test_configured_venvs_are_checked_before_path_precedence() -> None:
    for path in _launchers():
        source = path.read_text(encoding="utf-8")
        if 'export PATH="${VENV_ROOT}/bin:${PATH}"' in source or (
            'export PATH="$VENV_ROOT/bin:$PATH"' in source
        ):
            normalized = source.replace("${VENV_ROOT}", "$VENV_ROOT")
            assert "$VENV_ROOT/bin/python" in normalized, path
            assert normalized.index("$VENV_ROOT/bin/python") < normalized.index(
                "export PATH="
            ), path
