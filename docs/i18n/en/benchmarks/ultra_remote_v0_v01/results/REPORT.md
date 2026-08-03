<!-- i18n-mirror: non-authoritative translation; source=benchmarks/ultra_remote_v0_v01/results/REPORT.md -->

This translation is provided for reading convenience only; the frozen Chinese-language source document is authoritative.

# v0 / v0.1 ultra-remote development evaluation report

## One-sentence conclusion

This analysis can determine whether v0.1 outperforms v0 on **frozen component folds** and the
**BLAST-defined low-coverage stress stratum**, but it cannot establish strict ultra-remote
superiority: the independent positive-component count for `qcov >=80% 且 identity <20%` is
`{'h1_djr': 1, 'h2_vma_conditional': 1, 'vma_end_to_end': 1}`, far below the preregistered
minimum of 100.

## v0.1 relative to v0: all component holdouts

| Task | Encoder sensitivity difference | Supervised-detector sensitivity difference | Encoder specificity | Detector specificity |
| --- | --- | --- | --- | --- |
| h1_djr | +0.197 | +0.017 | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY |
| h2_vma_conditional | +0.049 | +0.000 | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY |
| vma_end_to_end | +0.049 | +0.000 | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY | NOT_MATCHED_SPECIFICITY_DESCRIPTIVE_ONLY |

Differences are v0.1 minus v0. A result is marked as matched only when both systems maintain actual
99.5% specificity in all five evaluation folds; otherwise, the difference is descriptive under a
fixed calibration threshold and cannot be called a matched-specificity improvement. The result
shown here establishes only Train-only component-level generalization, not strict ultra-remote
generalization.

## BLAST-defined low-coverage stress stratum (qcov <80%)

| Task | Comparison layer | Independent components | Sensitivity difference | 95% paired CI |
| --- | --- | --- | --- | --- |
| h1_djr | encoder | 264 | +0.260 | [+0.206, +0.317] |
| h1_djr | task_adapted_detector | 264 | +0.028 | [+0.011, +0.049] |
| h2_vma_conditional | encoder | 100 | +0.062 | [+0.020, +0.112] |
| h2_vma_conditional | task_adapted_detector | 100 | +0.000 | [+0.000, +0.000] |
| vma_end_to_end | encoder | 100 | +0.063 | [+0.020, +0.113] |
| vma_end_to_end | task_adapted_detector | 100 | +0.000 | [+0.000, +0.000] |

This stratum is descriptive only. Low coverage may result from a short homologous segment, domain
fusion, truncation, or true remote relatedness. Moreover, BLAST—the compared method—defines the
stratification, so it cannot support a formal claim that a PLM outperforms BLAST.

## BLAST-defined twilight stratum (qcov >=80%, 20% <= identity <30%)

| Task | Comparison layer | Independent components | Sensitivity difference | 95% paired CI |
| --- | --- | --- | --- | --- |
| h1_djr | encoder | 113 | +0.046 | [+0.013, +0.086] |
| h1_djr | task_adapted_detector | 113 | +0.000 | [+0.000, +0.000] |
| h2_vma_conditional | encoder | 106 | +0.024 | [+0.001, +0.057] |
| h2_vma_conditional | task_adapted_detector | 106 | +0.000 | [+0.000, +0.000] |
| vma_end_to_end | encoder | 106 | +0.025 | [+0.001, +0.057] |
| vma_end_to_end | task_adapted_detector | 106 | +0.000 | [+0.000, +0.000] |

This is the current identity stratum that is closest to remote homology while retaining a useful
sample size. However, it is still BLAST-defined and therefore remains descriptive. The true strict
`<20%` stratum still contains only case-level evidence.

## How to interpret v0 and v0.1

- `esm2_3b_cosine` versus `esmc6b_cosine`: compares only encoder retrieval geometry under the same
  information budget.
- `esm2_3b_supervised` versus `esmc6b_supervised`: uses the same training labels, classifier family,
  hyperparameters, folds, and threshold protocol, and is the fairest comparison of the operational
  H1/H2 detectors.
- H3 is not included: both v0 and v0.1 use the same ESM-C 6B H3, and H3 is a phylum classifier rather
  than a remote-homology detector.
- For any method that fails the 99.5% specificity gate, its sensitivity cannot be called a
  "matched-specificity improvement."

## Conclusions that can and cannot currently be drawn

Can be concluded: component-holdout generalization on the internal development set, low-FPR pAUROC,
and descriptive differences in the low-coverage stress stratum.

Cannot be concluded: improvement on an external Test, structure-confirmed ultra-remote improvement,
or superiority to BLAST after selecting samples by BLAST failure. A formal conclusion requires a
method-independent structure/manual-evidence lockbox, at least 100 positive components, and at least
20 components per fold.
