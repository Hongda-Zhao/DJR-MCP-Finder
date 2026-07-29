# INTERNAL CROSS-FITTED DEVELOPMENT BENCHMARK — NOT AN EXTERNAL TEST

This is an internal cyclic component-cross-fitted development comparison, not an external superiority claim.
The headline is fixed in advance: ESM-C 6B cosine retrieval is compared separately with each registered classical anchor; no post-hoc best baseline is selected.

## Empirical resolution audit

The endpoint remains frozen at 99.5% specificity, but its empirical resolution is reported separately rather than being treated as unconditional low-FPR evidence.

| Task | Sensitivity inference status | Zero-FP granularity cycles | Singleton calibration sources | Singleton evaluation sources | Low-positive-component folds |
|---|---|---|---|---|---|
| h1_djr | DESCRIPTIVE_PAIRED_COMPONENT_BOOTSTRAP | 1,2,3,4,5 | none | none | none |
| h2_vma_conditional | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED | 1,2,3,4,5 | cycle 2 / cal fold 3: cellular_djr_none 62/1 records/components | fold 3: cellular_djr_none 62/1 records/components | fold 2: 119/18 records/components |
| vma_end_to_end | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED | 1,2,3,4,5 | cycle 2 / cal fold 3: cellular_djr_none 62/1 records/components | fold 3: cellular_djr_none 62/1 records/components | fold 2: 119/18 records/components |

In particular, fold 3 contains 62 cellular-DJR negative records but only one global component. In cycle 2 this is the H2 calibration source: each row carries 1/62 of the negative mass, so 99%, 99.5%, and 99.9% all require zero empirical false positives. The same source is a single independent negative component when fold 3 is evaluated.
A one-component fold/source stratum has bootstrap multiplicity fixed at one. Its between-component calibration/evaluation variation is therefore not estimable; affected sensitivity delta intervals are conditional on that observed component. Fold 2 also has only 18 independent VMA-positive components (119 records), so fold ranges and component counts must accompany aggregate values.

## Controlled primary comparisons

AP is the macro-average of five evaluation-fold component-balanced AP values. Sensitivity uses each cycle's dedicated calibration fold at 99.5% source-balanced specificity; its interval is the paired global-component bootstrap delta interval, subject to the resolution status above.

| Task | Classical anchor | ESM-C cosine AP | Anchor AP | AP delta (95% CI) | ESM-C sensitivity | Anchor sensitivity | Sensitivity delta (95% CI) | Sensitivity status |
|---|---|---:|---:|---:|---:|---:|---:|---|
| h1_djr | blastp | 0.8719 | 0.9392 | -0.0672 (-0.0998, -0.0347) | 0.7340 | 0.8692 | -0.1353 (-0.1899, -0.0523) | DESCRIPTIVE_PAIRED_COMPONENT_BOOTSTRAP |
| h1_djr | diamond_ultra | 0.8719 | 0.9406 | -0.0687 (-0.1024, -0.0345) | 0.7340 | 0.9025 | -0.1686 (-0.2170, -0.0979) | DESCRIPTIVE_PAIRED_COMPONENT_BOOTSTRAP |
| h1_djr | mmseqs_s7.5 | 0.8719 | 0.9319 | -0.0600 (-0.0932, -0.0256) | 0.7340 | 0.8805 | -0.1466 (-0.2034, -0.0722) | DESCRIPTIVE_PAIRED_COMPONENT_BOOTSTRAP |
| h1_djr | hmmer_component | 0.8719 | 0.9542 | -0.0823 (-0.1119, -0.0521) | 0.7340 | 0.9016 | -0.1676 (-0.2236, -0.1023) | DESCRIPTIVE_PAIRED_COMPONENT_BOOTSTRAP |
| h2_vma_conditional | blastp | 0.9861 | 0.9829 | +0.0032 (-0.0102, +0.0211) | 0.9306 | 0.9443 | -0.0138 (-0.0599, +0.0307) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| h2_vma_conditional | diamond_ultra | 0.9861 | 0.9806 | +0.0054 (-0.0112, +0.0268) | 0.9306 | 0.9317 | -0.0011 (-0.0479, +0.0434) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| h2_vma_conditional | mmseqs_s7.5 | 0.9861 | 0.9751 | +0.0109 (-0.0051, +0.0303) | 0.9306 | 0.9119 | +0.0187 (-0.0367, +0.0685) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| h2_vma_conditional | hmmer_component | 0.9861 | 0.9911 | -0.0050 (-0.0194, +0.0102) | 0.9306 | 0.9569 | -0.0263 (-0.0712, +0.0179) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| vma_end_to_end | blastp | 0.9528 | 0.9544 | -0.0017 (-0.0328, +0.0334) | 0.9301 | 0.9401 | -0.0100 (-0.0557, +0.0343) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| vma_end_to_end | diamond_ultra | 0.9528 | 0.9497 | +0.0031 (-0.0294, +0.0398) | 0.9301 | 0.9317 | -0.0015 (-0.0471, +0.0439) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| vma_end_to_end | mmseqs_s7.5 | 0.9528 | 0.9317 | +0.0211 (-0.0140, +0.0600) | 0.9301 | 0.9078 | +0.0223 (-0.0300, +0.0746) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |
| vma_end_to_end | hmmer_component | 0.9528 | 0.9660 | -0.0132 (-0.0427, +0.0203) | 0.9301 | 0.9569 | -0.0267 (-0.0708, +0.0197) | CONDITIONAL_COMPONENT_BOOTSTRAP_RESOLUTION_LIMITED |

## Other controlled-primary PLM comparator

This controlled PLM comparator is not substituted for a registered classical anchor.

| Method | Task | Fold-macro component AP (fold range) | Sensitivity@99.5% (fold range) |
|---|---|---:|---:|
| esm2_650m_cosine | h1_djr | 0.9515 (0.9152–0.9744) | 0.8954 (0.8371–0.9432) |
| esm2_650m_cosine | h2_vma_conditional | 0.9965 (0.9827–1.0000) | 0.9977 (0.9894–1.0000) |
| esm2_650m_cosine | vma_end_to_end | 0.9906 (0.9639–1.0000) | 0.9859 (0.9400–1.0000) |

## Resource-augmented secondary

PSI-BLAST uses iterative positive-database enrichment and remains secondary.

| Method | Task | Fold-macro component AP (fold range) | Sensitivity@99.5% (fold range) |
|---|---|---:|---:|
| psiblast_longest_seed_positiveDB_3iter | h1_djr | 0.9705 (0.9365–0.9958) | 0.9493 (0.8958–0.9894) |
| psiblast_longest_seed_positiveDB_3iter | h2_vma_conditional | 0.9982 (0.9913–1.0000) | 0.9750 (0.9574–1.0000) |
| psiblast_longest_seed_positiveDB_3iter | vma_end_to_end | 0.9899 (0.9685–1.0000) | 0.9750 (0.9574–1.0000) |

## Metadata-grouped secondary

Family-grouped HMMER uses frozen grouping metadata and remains secondary.

| Method | Task | Fold-macro component AP (fold range) | Sensitivity@99.5% (fold range) |
|---|---|---:|---:|
| hmmer_family | h1_djr | 0.9971 (0.9915–1.0000) | 0.9957 (0.9890–1.0000) |
| hmmer_family | h2_vma_conditional | 0.9994 (0.9971–1.0000) | 0.9806 (0.9444–1.0000) |
| hmmer_family | vma_end_to_end | 0.9931 (0.9829–1.0000) | 0.9806 (0.9444–1.0000) |

## Operational supervised descriptive only

The supervised ESM-C system learns from labelled negatives and is not primary-eligible.

| Method | Task | Fold-macro component AP (fold range) | Sensitivity@99.5% (fold range) |
|---|---|---:|---:|
| esmc6b_supervised | h1_djr | 0.9945 (0.9846–0.9999) | 0.9753 (0.8923–1.0000) |
| esmc6b_supervised | h2_vma_conditional | 1.0000 (1.0000–1.0000) | 1.0000 (1.0000–1.0000) |
| esmc6b_supervised | vma_end_to_end | 0.8723 (0.6297–0.9792) | 0.8000 (0.0000–1.0000) |

PSI-BLAST is resource-augmented secondary evidence, family-grouped HMMER is metadata secondary evidence, and supervised ESM-C is operational descriptive evidence only.
Pooled raw AP is retained only as a secondary diagnostic. The 99.9% ladder is `RESOLUTION_LIMITED_SECONDARY`, and FP-per-million is not estimable from this cohort.
Uncertainty for both primary metrics used 10,000 paired global-component replicates. Only delta 95% intervals are reported; no bootstrap sign fraction is presented as a P value and no Holm adjustment is generated.
Source-specific calibration/evaluation checks, distance strata, approximate MDE, profile construction, reference contracts, and runtime receipts are in the accompanying TSV files.
