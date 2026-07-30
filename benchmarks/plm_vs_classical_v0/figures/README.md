**English** | [简体中文](README.cn.md)

# Benchmark figures

These figures visualize the validated internal cross-fitted benchmark without changing its frozen endpoints or claim boundary.

Regenerate from the benchmark root:

```bash
python figures/plot_benchmark.py
```

Primary outputs:

- `benchmark_summary.svg` — editable primary figure.
- `benchmark_summary.pdf`, `.png` — active review and publication exports; 600-dpi TIFF is in the full archive.
- `benchmark_remote_homology.svg` and PDF/PNG exports — descriptive low-coverage/no-hit diagnostics; TIFF is archive-only.
- `source_data/` — exact plotted rows derived from the validated result tables.
- `visualization_manifest.json` and `CHECKSUMS.sha256` — source bindings and artifact hashes.
- `FIGURE_CONTRACT.md`, `FIGURE_LEGEND.md`, and `QA_REPORT.md` — claim, caption, statistical caveats and final-size audit.

Interpret sensitivity as measured on evaluation folds at thresholds selected to target 99.5% specificity on disjoint calibration folds. It is not an assertion that every evaluation fold achieved 99.5% specificity.
