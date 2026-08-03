# Changelog

All notable engineering changes to DJR-MCP Finder are documented here. Scientific evidence
amendments remain governed by their frozen protocols and checksum manifests.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Repository releases use
concise `MAJOR.MINOR` labels; installable Python distributions retain their independent PEP 440
versions.

## [Unreleased]

### Added

- A layered `docs/` information architecture and a machine-readable release manifest.
- Unified `make setup/test/lint/smoke/build/check` contributor commands.
- Community contribution, security, issue, and pull-request guidance.
- Tag-gated package build and GitHub Release artifact workflow.

### Changed

- Python package metadata now uses SPDX/PEP 639 licensing, complete project URLs, typed-package
  markers, and metadata-backed runtime versions.
- The landing README now focuses on adoption; detailed scientific and reproducibility material
  lives under `docs/`.
- V0.1 is now the preferred current result, while released V0 remains a first-class reproducible
  baseline and fallback; both stay visible with their distinct release statuses.
- Current inference outputs use MCP terminology (`head2_mcp_probability`, `djr_non_mcp`, and
  `mcp::...`); archived benchmark identifiers remain unchanged for reproducibility.
- The landing page now presents the frozen V0 model-selection benchmark before the V0/V0.1
  remote-component development audit and identifies V0.1 as the preferred current result.
- Root-level scientific workflow, report, and robustness protocol documents moved to
  `docs/research/`; a documentation check prevents root Markdown sprawl from returning.

## [0.1] - 2026-07-30

### Added

- First formal GitHub release with the frozen `model-v0` user-inference package.
- Bilingual landing README, MIT license, citation metadata, third-party notices, and baseline CI.

[Unreleased]: https://github.com/Hongda-Zhao/DJR-MCP-Finder/compare/v0.1...HEAD
[0.1]: https://github.com/Hongda-Zhao/DJR-MCP-Finder/releases/tag/v0.1
