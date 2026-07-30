# Contributing to DJR-MCP Finder

Thank you for improving the software, documentation, or reproducibility of DJR-MCP Finder. The
released model and the development candidate have different evidence status, so every change must
preserve that distinction.

## Development setup

The complete contributor environment requires Python 3.12 or newer because it includes the V0.1
candidate package. Full model inference is not required for normal tests.

```bash
git clone https://github.com/Hongda-Zhao/DJR-MCP-Finder.git
cd DJR-MCP-Finder
python3.12 -m venv .venv
source .venv/bin/activate
make setup
```

For a smaller environment, use `make setup-core`, `make setup-v0`, or `make setup-v01`.

## Canonical checks

```bash
make lint          # critical Python correctness rules
make test          # core + formal V0 + V0.1 candidate tests
make smoke         # CPU-only FASTA and frozen-bundle validation
make package-check # wheel/sdist metadata and content checks
make check         # complete local CI-equivalent gate
```

Run one test with its explicit path, for example:

```bash
python -m pytest -q tests/test_cli.py::test_release_command
```

## Change rules

- Do not use candidate evidence to modify or relabel the released `model-v0` bundle.
- Do not edit checksum-bound scientific artifacts without updating the owning manifest and running
  the relevant integrity validator.
- Keep historical provenance paths intact; use the portable configuration renderer for local paths.
- Update `release-manifest.json` and `docs/VERSIONING.md` together when a software, package, model,
  or bundle identifier changes.
- Add an entry under `[Unreleased]` in `CHANGELOG.md` for user-visible engineering changes.
- Never commit model checkpoints, secrets, raw datasets, generated caches, or local environments.

## Pull requests

1. Create a focused branch from current `main`.
2. Add or update tests and documentation with the change.
3. Run the narrowest relevant checks, then `make check` before requesting review.
4. Complete the pull-request template, including scientific-boundary and checksum questions.
5. Wait for all GitHub Actions checks to pass before merging.

Prefer small commits with imperative summaries such as `Add candidate package smoke check`. Direct
pushes to `main` are discouraged; branch protection and required checks must be configured by a
repository administrator to enforce this policy.

## Bug reports and feature requests

Use the repository's structured GitHub issue forms. Include a minimal FASTA or synthetic example
when possible, remove sensitive sequence data, and never attach credentials or private database
contents. Security vulnerabilities follow [`SECURITY.md`](SECURITY.md), not public issues.

## Release changes

Software releases use `vMAJOR.MINOR.PATCH` tags. Model identities and bundle revisions use the
separate scheme in [`docs/VERSIONING.md`](docs/VERSIONING.md). The release workflow builds all three
distributions and attaches validated wheels and sdists to the matching GitHub Release; it does not
publish to PyPI until Trusted Publishing is configured explicitly.
