# Versioning and naming contract

[Documentation map](README.md) | [Repository README](../README.md) |
[Release manifest](../release-manifest.json)

This project has software releases, Python distributions, scientific models, frozen artifact
bundles, and data-curation versions. They change on different schedules, so one number cannot
safely represent all of them.

## The short answer

| Name visible to a user | Machine identity | Meaning |
| --- | --- | --- |
| **Model V0.1 Candidate** | `model-v0.1-candidate` | Preferred current screening result; prospective external confirmation still required |
| **Model V0** | `model-v0` | Released, frozen scientific baseline and supported fallback |
| Repository release `v0.1` | `repository_release.tag` | Version of the GitHub software release, not a scientific model claim |
| Candidate package `0.2.1` | `djrmcp-user-inference-v01==0.2.1` | Engineering revision of the candidate inference distribution, not “Model V0.2” |

Machine metadata and evidence records must always use the complete scientific ID
`model-v0.1-candidate`. Human-facing navigation may use the shorter **V0.1** only when the adjacent
table or sentence explicitly states that it is a candidate awaiting external confirmation. The
formal display name is **Model V0.1 Candidate**.

Preferring Model V0.1 Candidate for new screening does not make it a formally confirmed model and
does not deprecate Model V0.

## Canonical layers

| Layer | Format | Example | Changes when |
| --- | --- | --- | --- |
| Repository/software release | `vMAJOR.MINOR` | `v0.1` | The GitHub software release line changes |
| Python distribution | PEP 440 version | `djrmcp-user-inference==0.1.0` | That installable package changes |
| Scientific model | `model-v<scientific line>[-candidate]` | `model-v0`, `model-v0.1-candidate` | Frozen model identity or evidence status changes |
| Bundle revision | `<model-id>-<encoder>-rN` | `model-v0-esmc6b-r1` | Exported files or packaging revision changes |
| Data curation | `data-curation-vN` | `data-curation-v3` | Dataset construction contract changes |

Use lowercase machine IDs in metadata and the formal display names above in scientific prose.

## Current mapping

| Component | Version / ID | Status |
| --- | --- | --- |
| GitHub repository | `v0.1` | Released software snapshot |
| Research pipeline distribution | `djrmcp-finder==0.1.0` | Alpha software |
| Formal inference distribution | `djrmcp-user-inference==0.1.0` | Packages `model-v0` |
| Candidate inference distribution | `djrmcp-user-inference-v01==0.2.1` | Engineering revision for `model-v0.1-candidate` |
| Formal bundle | `model-v0-esmc6b-r1` | Released and frozen |
| Candidate bundle | `model-v0.1-mixed-r1` | External confirmation required |

The candidate package version `0.2.1` is not a claim that the scientific model is released as
V0.2. Package versions are not downgraded or forced to equal the repository tag.

## Machine-readable authority

[`release-manifest.json`](../release-manifest.json) is the sole compact mapping across these layers.
The command below verifies that it agrees with every `pyproject.toml`, runtime version source,
`py.typed` marker, bundle `release.json`, and scientific status field:

```bash
python scripts/check_project_metadata.py
```

Do not place a second copy of a package version in `__init__.py`. Runtime code reads installed
distribution metadata through `importlib.metadata`; an uninstalled source checkout reports
`0.0.0.dev0` rather than pretending to be a release.

## Change rules

### Repository release

Repository releases use a concise `MAJOR.MINOR` label. Backward-compatible capability and packaged
candidate changes increment MINOR; incompatible public CLI, output-schema, or package API changes
increment MAJOR. Patch-level engineering revisions remain visible in the Python distribution and
bundle versions rather than creating a third repository-release component.

Update the repository version and tag in `release-manifest.json`, update `CHANGELOG.md`, pass
`make check`, merge to `main`, and create an annotated matching tag.

### Python distribution

Change only the distribution that changed. Update its `pyproject.toml` and matching entry in
`release-manifest.json`. Use PEP 440 prereleases such as `0.3.0rc1` for package-level release
candidates. Never infer scientific evidence status from a package version.

### Scientific model

A new model ID requires a frozen model card, complete bundle metadata and checksums, declared
evidence status, and the scientific release gates in [`WORKFLOW_V0.md`](research/WORKFLOW_V0.md).
Engineering refactors that preserve all frozen parameters do not create a new model ID.

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

仓库 release、Python 包、科学模型和 bundle revision 是不同层次。当前正式显示名为
**Model V0.1 Candidate**，机器 ID 必须写作 `model-v0.1-candidate`；它是新筛查的当前优先结果，
但仍需 prospective external confirmation。**Model V0**（`model-v0`）仍是已发布、冻结的正式
基线。仓库 tag `v0.1` 与 candidate package `0.2.1` 都不是科学模型证据状态。所有映射由
`release-manifest.json` 集中维护并由 CI 校验。
