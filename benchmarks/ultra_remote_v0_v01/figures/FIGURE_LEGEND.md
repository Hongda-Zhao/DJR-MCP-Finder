# Figure legend

**Figure | DJR-MCP Finder v0 versus v0.1 remote-component development audit.**
**a,** Paired component-balanced sensitivity difference (v0.1 minus v0) for the raw
encoder cosine layer and task-adapted detector on all component holdouts, the
BLAST-defined 20–30% identity twilight layer, and the BLAST-defined qcov <80%
low-coverage stress layer. Thresholds were locked separately for each method, task,
and evaluation cycle on its calibration fold at nominal 99.5% specificity. Error
bars are 95% paired evaluation-component bootstrap intervals with fixed thresholds;
they exclude calibration uncertainty. **b,** Absolute component-balanced sensitivity
in the low-coverage stress layer. Marker shape denotes H1 DJR, conditional H2 VMA,
or VMA end-to-end. **c,** Source- and component-balanced normalized partial AUROC at
FPR <=0.005 on all H1 component holdouts. H2 and end-to-end endpoints are omitted
because one or more negative sources lack independent-component resolution at 0.5%
FPR. **d,** Positive independent-component counts for strict identity <20%, identity
<20% at any coverage, 20–30% twilight, low-coverage stress, and all holdouts. Dotted
and dashed lines show the pre-frozen descriptive (n=30) and formal ultra-remote
(n=100) minima. Open symbols indicate that v0 or v0.1 missed actual 99.5%
specificity in at least one evaluation fold, so deltas are descriptive rather than
matched-specificity improvement. All analyses use Train-only cyclic component
crossfit; BLAST-derived strata are method-conditioned and are not formal evidence
that another method is superior to BLAST.

Source data: `paired_delta.tsv`, `low_coverage_sensitivity.tsv`, `low_fpr_pauc.tsv`,
and `sample_sufficiency.tsv` under `figures/source_data/`.
