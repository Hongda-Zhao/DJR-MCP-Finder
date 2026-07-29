# Benchmark visualization contract

Core conclusion: ESM-C 6B cosine retrieval does not provide a general sensitivity gain over controlled classical anchors; ESM2-650M shows an exploratory end-to-end VMA signal that requires external matched-specificity validation.

Figure archetype: quantitative grid.

Target journal/output: full-width manuscript or technical-report figure; editable SVG and PDF plus high-resolution PNG and LZW-compressed TIFF.

Backend: Python (matplotlib), used exclusively for drawing and export.

Final size: main figure 183 × 215 mm; supplementary figure 183 × 86 mm.

Panel map:

- a: absolute fold-macro component-balanced average precision for all nine methods and three tasks.
- b: absolute fold-macro sensitivity at thresholds selected for 99.5% specificity on held-out calibration folds.
- c: pre-registered paired ESM-C-minus-classical AP differences with 95% component-bootstrap intervals.
- d: pre-registered paired ESM-C-minus-classical sensitivity differences with 95% component-bootstrap intervals.
- e: observed evaluation-fold specificity for the six controlled methods, making calibration-to-evaluation drift visible.
- Supplementary a: descriptive sensitivity in the BLAST local-query-coverage <80% stratum.
- Supplementary b: method/task no-hit fractions.

Evidence hierarchy:

- Hero evidence: paired-difference forest plots in panels c and d.
- Validation evidence: absolute metric matrices in panels a and b.
- Controls/robustness: achieved specificity in panel e; coverage/distance diagnostics in the supplementary figure.

Statistics needed: five-fold macro estimands; 10,000 paired global-component bootstrap replicates; percentile 95% intervals; no bootstrap P values or multiplicity-adjusted claims.

Source data needed: `metrics_primary.tsv`, `paired_deltas.tsv`, `distance_strata.tsv`, `validation.json`, and `summary.json` from the validated benchmark release.

Image-integrity notes: all 27 primary-metric rows and all 12 registered paired comparisons are used. No method, task, fold, or interval is omitted. Secondary/resource-augmented and operational tracks are labelled rather than pooled with the controlled headline.

Reviewer risks:

- This is an internal Train-only cross-fitted development benchmark, not an external test.
- The 99.5% value is a calibration-fold target; evaluation specificity is measured and shown separately.
- H2 and end-to-end sensitivity intervals are conditional because one negative source/fold contains 62 records but one independent component.
- PSI-BLAST, family-grouped HMMER, and supervised ESM-C use different information budgets.
- BLAST local query coverage is a descriptive alignment stratum, not a global evolutionary distance.
