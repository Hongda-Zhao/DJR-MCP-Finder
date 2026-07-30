**English** | [简体中文](README.cn.md)

# Ultra-remote benchmark: v0 versus v0.1

This is a separate, fail-closed development audit. It does not modify the released
`plm_vs_classical_v0` benchmark and it does not open Validation or Test.

This active directory is the compact publication/checksum core.  It retains the
protocol, configuration, code, compact results, small reproduction contracts,
figure source data, and PNG/PDF/SVG outputs.  Row-level diagnostics, logs, and the
TIFF export remain checksum-bound in the complete archive named by
`FULL_ARTIFACT_POINTER.json`; no data were deleted.

## What is actually compared

| Layer | v0 | v0.1 candidate | Fair comparison |
|---|---|---|---|
| H1/H2 encoder | ESM-C 6B | ESM-2 3B | Same positive reference IDs, maximum cosine |
| H1/H2 detector | ESM-C 6B + frozen classifier family | ESM-2 3B + the same classifier family | Same cyclic 3-fit/1-calibration/1-evaluation folds and hyperparameters |
| H3 phylum head | ESM-C 6B | The same ESM-C 6B | Excluded: unchanged and not a homology-detection endpoint |

The cosine layer asks whether the representation itself retrieves held-out
components. The supervised layer asks whether the operational H1/H2 detector can
use that representation. Classical tools retain their original frozen scores and
information-budget labels from the parent benchmark.

## Ultra-remote boundary

The current data contain only one positive independent component with best BLAST
query coverage at least 80% and identity below 20%. Therefore that stratum is a
case series, not an inferential benchmark. `qcov < 80%` has adequate counts for a
descriptive stress test but is a low-coverage proxy, not proof of ultra-remote
homology. Its definition also comes from BLAST, one of the compared methods, so it
cannot support a formal claim that another method is superior to BLAST.

A release-grade ultra-remote benchmark remains reserved for an external lockbox
whose labels and distance strata are frozen independently of every compared method,
preferably from structure or experimental/manual evidence.

## Verify the compact core

```bash
cd /path/to/DJR-MCP-Finder/benchmarks/ultra_remote_v0_v01
sha256sum -c CHECKSUMS.sha256
```

`results/validation.json` is the frozen successful full-validator record.  The
active validator is not replayable from this compact tree because the original
row-level score ledger and TIFF contract are archive-only.  The GitHub `pbs/`
launcher is a portable replay template, not a standalone runner.  For exact
scoring, rendering, and validation replay, follow `FULL_ARTIFACT_POINTER.json`
and restore its `full_v1` tree first.  The ultra scripts
also consume parent PLM inputs, query scores, and classical receipts, so restore
the PLM tree named by `../plm_vs_classical_v0/FULL_ARTIFACT_POINTER.json` to its
recorded active path as well.  The visualization manifest records the compact
rendering outputs and source-data checksums.

After restoring those archives on another system, generate a local config from
the repository root with `scripts/render_portable_config.py`, set
`DJRMCP_ULTRA_CONFIG` to that copy, and set `DJRMCP_PROJECT_ROOT`,
`DJRMCP_ARCHIVE_ROOT`, and `DJRMCP_VENV_ROOT`.  The checked-in JSON remains the
immutable record of the original gds2 run.
