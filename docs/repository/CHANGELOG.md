# Changelog

All notable engineering changes to DJR-MCP Finder are documented here. Scientific evidence
amendments remain governed by their frozen protocols and checksum manifests.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Repository releases use
concise `MAJOR.MINOR` labels; installable Python distributions retain their independent PEP 440
versions.

## [Unreleased]

## [0.2] - 2026-09-28

### Added

- Train-only short-sequence benchmark with component-disjoint cross-fitting, verified reuse of
  existing embeddings, paired truncation preparation and original-length evaluation.
- MCP-positive length statistics for 560 curated positives, including 336 Train positives;
  held-out splits are inspected for lengths only and are not scored.
- English benchmark figures and aggregate source tables for <250, 250–299, 300–349,
  350–399, 400–449, 450–499 and ≥500 aa. V0.1 detects 331/336 Train MCPs, with
  0/6,298 observed false positives; paired truncation performance remains pending.
- Opt-in `djrmcp-predict-v02-preview`: inputs <250 aa receive
  `mcp_unreliable_short_sequence`, `NA` scores and no model execution. Inputs ≥250 aa
  use frozen V0.1 unchanged. This label means abstention, not MCP-negative.
- Trilingual V0.2 policy/design documentation and a homepage performance table with
  denominators, evidence limitations and the English overview figure.

### Changed

- Repository software release advances to `v0.2`; research distribution to `0.2.0` and
  candidate inference distribution to `0.3.0`. Formal V0 distribution remains `0.1.0`.
- Citation metadata and version mappings now describe software v0.2. Scientific model IDs,
  frozen weights, calibration and bundles remain unchanged; no scientific Model V0.2 was trained.
- The main length figure omits the repetitive FP column and retains overall FP in its caption.

### Validation

- 236 core, 33 formal V0 and 69 candidate inference tests pass locally (338 total).
- Documentation, metadata, critical Ruff checks and all three wheel/sdist checks pass.
- New short-input routing tests exercise boundaries, mixed order, skipped models, invalid
  FASTA, unchanged baseline scores, checksum failures and overwrite behavior.

### Earlier engineering changes since v0.1


### Added

- A layered `docs/` information architecture and a machine-readable release manifest.
- A stable top-level directory-function map in all three landing-page languages.
- Unified `make setup/test/lint/smoke/build/check` contributor commands.
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
- Auxiliary landing-page translations, the changelog, and repository-level third-party notices
  now live under `docs/repository/`; the root retains only the primary English Markdown README.

### Removed

- Standalone contribution and security policy pages were removed from the public documentation
  surface; issue and pull-request templates remain available under `.github/`.

## [0.1] - 2026-07-30

### Added

- First formal GitHub release with the frozen `model-v0` user-inference package.
- Bilingual landing README, MIT license, citation metadata, third-party notices, and baseline CI.

[Unreleased]: https://github.com/Hongda-Zhao/DJR-MCP-Finder/compare/v0.2...HEAD
[0.2]: https://github.com/Hongda-Zhao/DJR-MCP-Finder/compare/v0.1...v0.2
[0.1]: https://github.com/Hongda-Zhao/DJR-MCP-Finder/releases/tag/v0.1
