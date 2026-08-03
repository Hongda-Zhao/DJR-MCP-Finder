**English** | [简体中文](README.cn.md) | [日本語](README.ja.md)

# Results included in Git

This repository tracks only compact, checksum-bound evidence needed to read and
audit the published V0 analyses:

- `figures/project_v0/`
- `validation_family_robustness_v0_schema5_mixed_heads/`
- the small checksum, fold, and comparison files needed by the public-checkout
  validators and `PROJECT_V0_RELEASE_CHECKSUMS.sha256`

Large generated outputs, embeddings, raw intermediate files, and model caches
remain excluded by the root `.gitignore`. Their identities are retained in the
release checksum and provenance records where applicable.

In particular, `data/processed/v0/CHECKSUMS.sha256` and
`postsplit_integrity_v0/CHECKSUMS.sha256` are archive-identity inventories. A
clean Git checkout intentionally does not contain their 38 dataset targets or
15 integrity-audit targets; restore the checksum-bound archive before running
those two manifests with `sha256sum -c`.
