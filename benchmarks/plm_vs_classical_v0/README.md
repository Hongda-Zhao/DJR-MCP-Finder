**English** | [简体中文](README.cn.md)

# PLM versus classical remote-homology benchmark

> **INTERNAL CROSS-FITTED DEVELOPMENT BENCHMARK — NOT AN EXTERNAL TEST**

This active directory is the compact publication/checksum core.  It retains the
frozen protocol, configuration, code, compact result tables, validation record,
figure source data, and PNG/PDF/SVG outputs.  Inputs, raw receipts, search
databases, logs, row-level ledgers, and TIFF exports remain checksum-bound in the
complete archive identified by `FULL_ARTIFACT_POINTER.json`; no data were deleted.

This directory compares the project protein-language-model (PLM) system with
sequence and profile-search baselines on the frozen DJR-MCP-Finder Train split.
It never evaluates the protected Test split.  The five existing
`global_component_id` folds are reused in a cyclic 3/1/1 design.  For every
cycle, three folds build the database/model, one disjoint fold calibrates the
operating threshold, and one disjoint fold is evaluated.  Calibration and
evaluation share exactly the same database/model without entering fitting.

The benchmark has two deliberately separate tracks:

1. **Controlled retrieval:** ESM-C/ESM-2 maximum cosine similarity, BLASTP,
   DIAMOND, MMseqs2, HMMER, and PSI-BLAST use the same fold-specific positive
   reference IDs.
2. **Operational supervised system:** ESM-C 6B embeddings are fitted with the
   project's frozen H1/H2 classifier settings.  This track is not used to
   attribute gains solely to PLM representations because it also learns from
   labelled negatives.

The three endpoints are DJR detection (H1), VMA versus cellular DJR (H2), and
end-to-end VMA detection.  Fold-macro component-balanced AP and calibrated sensitivity
at 99.5% source-balanced specificity are primary.  The 99.9% endpoint is
reported only as resolution-limited secondary evidence.

A pre-aggregation audit also found that fold 3's 62 cellular-DJR negatives are
one component. Affected H2/end-to-end low-FPR sensitivity intervals are retained
but explicitly labelled conditional and resolution-limited; see `PROTOCOL.md`.
The score-independent counts and leakage checks are recorded in
`DATA_AUDIT.md`.

## Verify the compact core

```bash
cd /path/to/DJR-MCP-Finder/benchmarks/plm_vs_classical_v0
sha256sum -c CHECKSUMS.sha256
```

`results/validation.json` is the frozen successful full-validator record.  The
compact copy intentionally cannot replay the full validator or search pipeline,
because their raw inputs and receipts are archive-only.  The GitHub `pbs/`
launchers are portable replay templates, but they are not standalone runners:
for an exact end-to-end replay, follow `FULL_ARTIFACT_POINTER.json` and restore
its `full_v1` tree before submission.  Do not reinterpret this compact source
checksum as a full-pipeline or scientific-result checksum.

See `PROTOCOL.md` for the frozen scientific contract and
`config/benchmark.json` for machine-readable paths, checksums, parameters, and
tool versions.

For a restored full archive on another system, keep the checked-in config as
provenance and generate a runtime copy from the repository root:

```bash
python scripts/render_portable_config.py \
  benchmarks/plm_vs_classical_v0/config/benchmark.json \
  build/local-configs/plm_vs_classical_v0.json
```

Set `DJRMCP_PROJECT_ROOT`, `DJRMCP_ARCHIVE_ROOT`, `DJRMCP_SOFTWARE_ROOT`, and
`DJRMCP_VENV_ROOT` first, then pass the generated path as `DJRMCP_PLM_CONFIG`.
The PBS launchers resolve the checkout from those variables (or their own
location/`PBS_O_WORKDIR`) instead of requiring the historical gds2 project path.

The headline controlled track never mixes the supervised classifier with
retrieval tools.  Supervised ESM-C, metadata-grouped HMMs, and iterative
PSI-BLAST are reported in explicitly labelled supplementary tracks.
