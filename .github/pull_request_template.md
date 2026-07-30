## Summary

<!-- What changed, for whom, and why? -->

## Scope

- [ ] Research pipeline
- [ ] Formal `model-v0` inference
- [ ] `model-v0.1-candidate` inference
- [ ] Documentation/community files
- [ ] Packaging or release automation

## Validation

<!-- List the exact commands and results. Prefer make targets. -->

- [ ] `make lint`
- [ ] relevant tests
- [ ] relevant smoke checks
- [ ] `make package-check` when packaging metadata or bundled files changed
- [ ] all GitHub Actions checks are green

## Scientific and release boundary

- [ ] The change does not silently alter frozen encoders, heads, thresholds, routing, or evidence status.
- [ ] Any checksum-bound file change updates its owning checksum manifest.
- [ ] `release-manifest.json`, `docs/VERSIONING.md`, and `CHANGELOG.md` agree when an identifier or version changes.
- [ ] User-facing claims remain within `docs/SCIENTIFIC_EVIDENCE.md`.

## Security and data

- [ ] No secrets, private sequences, checkpoints, raw datasets, caches, or generated environments are included.
- [ ] New input, path, deserialization, and overwrite behavior has an explicit safety review.

## Reviewer notes

<!-- Residual risk, intentionally deferred work, or manual GitHub/PyPI configuration. -->
