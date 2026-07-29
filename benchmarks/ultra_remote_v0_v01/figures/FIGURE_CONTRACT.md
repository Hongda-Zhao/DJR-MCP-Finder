# Figure contract

Core conclusion: The v0.1 encoder change can be estimated on component-held-out and
BLAST-defined difficult proteins, but the present strict <20% identity cohort is too
small for an ultra-remote superiority claim.

- Figure archetype: quantitative grid with a dominant paired-delta panel.
- Target/output: manuscript/report figure; editable SVG and PDF, 600-dpi TIFF and
  preview PNG.
- Backend: Python (matplotlib only).
- Final size: 180 mm wide, approximately 145 mm high.
- Panel a: paired v0.1 minus v0 sensitivity deltas for all holdouts, the 20–30%
  identity twilight layer, and low-coverage stress, with 95% descriptive bootstrap CI.
- Panel b: absolute sensitivity of selected PLM and classical methods in the
  low-coverage stress stratum, using calibration-fold-locked thresholds.
- Panel c: normalized partial AUROC at FPR <=0.005 on all component-held-out rows.
  Endpoints without adequate per-source negative-component resolution are omitted.
- Panel d: independent-component counts versus pre-frozen adequacy thresholds.
- Statistics: paired component bootstrap only when total n >=30 and each fold n >=5;
  no CI or superiority inference for strict <20% strata.
- Source data: every plotted point must be present in `figures/source_data/`.
- Reviewer risk: BLAST-derived strata are method-conditioned; actual evaluation
  specificity may miss the 99.5% target; H2 has one evaluation fold with only one
  negative component; current benchmark is Train-only development evidence.
  Open symbols mark paired deltas where either system misses the actual specificity
  gate; fixed-threshold bootstrap intervals exclude calibration uncertainty.
