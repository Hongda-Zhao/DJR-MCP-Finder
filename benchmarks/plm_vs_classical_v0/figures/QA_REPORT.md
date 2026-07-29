# Figure QA report

Status: **PASS**.

## Scientific and data integrity

- The visualization is bound to validated `summary.json` and `validation.json` artifacts with status `PASS`.
- All 27 method–task primary-metric rows and all 12 pre-registered paired comparisons are present exactly once.
- The paired panels use the reported point estimates and percentile 95% intervals from 10,000 paired global-component bootstrap replicates; no P value or Holm field is plotted.
- The low-coverage panel contains all 18 controlled method–task rows from the `best_local_qcov_lt80` stratum.
- No record, method, task, fold or interval was sampled or excluded for plotting convenience.
- Secondary/resource-augmented, metadata-augmented and operational tracks remain visually and textually separated from controlled comparisons.

## Source preflight

The strict static preflight reports 14 PASS, 0 WARN and 0 FAIL findings: valid Python syntax, Python-only backend, editable SVG/PDF text settings, sans-serif fonts, minimum detected text size 5.2 pt, no unsafe rainbow map, SVG/PDF/TIFF exports, 600 dpi raster output, 183 mm figure width, no detected sampling or simulated data, and no unguarded logarithmic transform.

## Export and visual inspection

- Main figure: 183 × 215 mm; PNG/TIFF 4320 × 5070 pixels at 600 dpi; SVG/PDF retain editable text.
- Supplementary figure: 183 × 86 mm; PNG/TIFF 4320 × 2040 pixels at 600 dpi; SVG/PDF retain editable text.
- PDF page sizes are 518.4 × 608.4 pt and 518.4 × 244.8 pt, respectively.
- The main and supplementary PNGs were inspected at original resolution after export. Panel labels, task labels, method labels, confidence intervals, legends, color bars and footnotes are visible without overlap or clipping.
- The main SVG contains 151 `<text>` nodes and the supplementary SVG contains 44; PDF inspection shows embedded Arial TrueType/CIDFontType2 fonts.
- White backgrounds, restrained non-rainbow palettes and marker shapes keep the figures interpretable beyond color alone.

## Statistical and reviewer caveats carried into the figure

- The 99.5% value is a calibration-fold target, not an assumed evaluation specificity; realized evaluation specificity is shown explicitly.
- H2/end-to-end intervals are displayed with open markers and labelled conditional/resolution-limited because one negative source/fold has one independent component.
- The low-query-coverage panel is descriptive, not a global evolutionary-distance analysis or a matched-specificity superiority test.
- The benchmark remains internal and Train-only; Validation/Test prediction counts are zero.

## Image-integrity statement

No microscopy, photographs, gels or other raster observations are used. Raster files are direct 600 dpi renders of vector/data graphics; no local contrast adjustment, selective masking, compositing or image reuse is involved.
