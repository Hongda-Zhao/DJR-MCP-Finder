# DJR-MCP Finder documentation

[Repository README](../README.md) | [中文 README](../README.cn.md)

The repository landing page explains what the tool does and gets a new user to a validated result.
This directory holds engineering, scientific, and reproducibility detail that should not compete
with that first-use path.

## Start by role

| Reader | Start here | Then read |
| --- | --- | --- |
| FASTA-screening user | [Formal V0 user guide](../user-inference-v0/README.md) | [Docker/NVIDIA deployment](../user-inference-v0/workstation/README.md) |
| Scientist interpreting results | [Scientific evidence and limitations](SCIENTIFIC_EVIDENCE.md) | [Frozen V0 model card](../user-inference-v0/src/djrmcp_predict/assets/project-v0-esmc6b-r1/MODEL_CARD.md) |
| Researcher reproducing the study | [Reproducibility guide](REPRODUCIBILITY.md) | [Complete workflow](../WORKFLOW_V0.md) |
| Software contributor | [Contributing guide](../CONTRIBUTING.md) | [Architecture](ARCHITECTURE.md) |
| Maintainer preparing a release | [Versioning and naming](VERSIONING.md) | [Changelog](../CHANGELOG.md) |
| Security reporter | [Security policy](../SECURITY.md) | [Third-party notices](../THIRD_PARTY_NOTICES.md) |

## Source-of-truth map

- [`release-manifest.json`](../release-manifest.json) is the machine-readable mapping among the
  repository release, Python distribution versions, scientific model IDs, and bundle revisions.
- [`WORKFLOW_V0.md`](../WORKFLOW_V0.md) is the complete scientific workflow and evidence boundary.
- [`PROJECT_V0_FINAL_REPORT.md`](../PROJECT_V0_FINAL_REPORT.md) is the concise scientific report.
- [`Makefile`](../Makefile) defines canonical contributor commands.
- [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) and
  [`.github/workflows/release.yml`](../.github/workflows/release.yml) define automated gates.

The compact GitHub checkout does not contain every original database, checkpoint, log, or HPC
output. Missing archived inputs are documented as prerequisites rather than silently reconstructed.
