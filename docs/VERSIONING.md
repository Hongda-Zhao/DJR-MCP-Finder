# Versioning and naming contract

This project has software releases, Python distributions, scientific models, and frozen artifact
bundles. They change on different schedules, so one number cannot safely represent all four.

## Canonical layers

| Layer | Format | Example | Changes when |
| --- | --- | --- | --- |
| Repository/software release | `vMAJOR.MINOR.PATCH` | `v0.1.0` | The GitHub software release changes |
| Python distribution | PEP 440 version | `djrmcp-user-inference==0.1.0` | That installable package changes |
| Scientific model | `model-v<scientific line>[-candidate]` | `model-v0`, `model-v0.1-candidate` | Frozen model identity or evidence status changes |
| Bundle revision | `<model-id>-<encoder>-rN` | `model-v0-esmc6b-r1` | Exported files or packaging revision changes |
| Data curation | `data-curation-vN` | `data-curation-v3` | Dataset construction contract changes |

Use lowercase machine IDs in metadata and prose labels such as **Model V0** only for display.
`V0.1` without the `candidate` qualifier is prohibited for the current mixed-encoder system because
it has not passed prospective external confirmation.

## Current mapping

| Component | Version / ID | Status |
| --- | --- | --- |
| GitHub repository | `v0.1.0` | Released |
| Research pipeline distribution | `djrmcp-finder==0.1.0` | Alpha software |
| Formal inference distribution | `djrmcp-user-inference==0.1.0` | Packages `model-v0` |
| Candidate inference distribution | `djrmcp-user-inference-v01==0.2.1` | Engineering revision for `model-v0.1-candidate` |
| Formal bundle | `model-v0-esmc6b-r1` | Released, frozen |
| Candidate bundle | `model-v0.1-mixed-r1` | External confirmation required |

The candidate package version `0.2.1` is not a claim that the scientific model is released as
V0.2. It is a PEP 440 engineering revision of a separate distribution. Package versions are not
downgraded or forced to equal the repository tag.

## Machine-readable authority

[`release-manifest.json`](../release-manifest.json) is the sole compact mapping across these layers.
`python scripts/check_project_metadata.py` verifies that it agrees with every `pyproject.toml`,
runtime `__version__`, `py.typed` marker, bundle `release.json`, and scientific status field.

Do not place a second copy of a package version in `__init__.py`. Runtime code reads installed
distribution metadata through `importlib.metadata`; an uninstalled source checkout reports
`0.0.0.dev0` rather than pretending to be a release.

## Change rules

### Repository release

Use Semantic Versioning:

- PATCH: backward-compatible engineering or packaging fix;
- MINOR: backward-compatible capability or new packaged model candidate;
- MAJOR: incompatible public CLI, output-schema, or package API change.

Update the repository version and tag in `release-manifest.json`, update `CHANGELOG.md`, pass
`make check`, merge to `main`, and create an annotated matching tag.

### Python distribution

Change only the distribution that changed. Update its `pyproject.toml` and matching entry in
`release-manifest.json`. Use PEP 440 prereleases such as `0.3.0rc1` for package-level release
candidates. Never infer scientific evidence status from a package version.

### Scientific model

A new model ID requires a frozen model card, complete bundle metadata and checksums, declared
evidence status, and the scientific release gates in `WORKFLOW_V0.md`. Engineering refactors that
preserve all frozen parameters do not create a new model ID.

### Bundle revision

Increment `rN` when exported files or non-model bundle metadata change while model behavior remains
identical. If classifier weights, thresholds, routing, or encoders change, create a new scientific
model identity instead of hiding the change in a bundle revision.

## Tag release gate

The release workflow accepts only tags matching the manifest's repository tag. It builds and
validates wheels and sdists for all three distributions, then attaches them to the GitHub Release.
PyPI upload is intentionally disabled until package names are reserved and Trusted Publishing is
configured with a protected GitHub environment.

## 中文摘要

仓库 release、Python 包、科学模型和 bundle revision 是四个不同层次。软件发布使用 SemVer；
Python distribution 使用 PEP 440；正式模型写作 `model-v0`；当前 mixed-encoder 必须完整写作
`model-v0.1-candidate`；bundle 使用 `rN` 表示不改变模型身份的导出修订。所有映射由
`release-manifest.json` 集中维护并由 CI 校验。
