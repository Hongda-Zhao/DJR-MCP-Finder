# Frozen protocol

## Purpose

Estimate whether replacing the v0 H1/H2 encoder (ESM-C 6B) with the v0.1 candidate
(ESM-2 3B) improves remote-component retrieval or supervised detection, while
showing exactly where the present dataset is too weak to answer a strict
ultra-remote question.

## Data partition

- Train split only: 6,634 records in five globally frozen component folds.
- For evaluation fold `k`, the next fold is calibration and the remaining three
  folds are fit/reference folds.
- No component may cross fit/reference, calibration, or evaluation roles in a cycle.
- Validation and Test prediction counts must remain zero.

## Method layers

1. **Controlled encoder/readout:** maximum cosine to the exact same fit-fold DJR or
   viral MCP positive reference IDs.
2. **Task-adapted detector:** identical H1/H2 classifier family, hyperparameters,
   training labels, folds, seeds, and thresholding rule; only the embedding changes.
3. **Classical context:** BLASTP, DIAMOND ultra-sensitive, MMseqs2, component HMM,
   PSI-BLAST, and family HMM scores are reused without refitting or rescoring.

PSI-BLAST and family HMM receive more task-specific information than controlled
pairwise methods and remain descriptive secondary comparators.

## Threshold and endpoints

- Each method/fold threshold is locked using all eligible calibration negatives at
  target specificity 99.5%, with source- and component-balanced weights.
- The threshold is applied unchanged to the evaluation fold and every difficulty
  stratum. No stratum-specific recalibration is allowed.
- Encoder endpoint: component/source-balanced normalized partial AUROC over
  `FPR in [0, 0.005]`. It is suppressed rather than interpolated when any
  source-balanced independent negative-component unit is larger than 0.005.
- Detector endpoint: component-balanced sensitivity at the locked threshold,
  accompanied by actual evaluation specificity. A sensitivity gain cannot be called
  matched-specificity improvement when the specificity gate fails.
- Uncertainty for descriptive strata is a paired evaluation-component bootstrap
  with the calibration threshold fixed. It does not include calibration uncertainty.
  A paired delta is not called matched-specificity improvement unless both v0 and
  v0.1 meet actual 99.5% specificity in all five evaluation folds.

## Difficulty strata

| Stratum | Definition | Status |
|---|---|---|
| Component holdout | All held-out positive components | Primary development generalization; not automatically ultra-remote |
| Low-coverage stress | Best evaluation-cycle BLAST hit has qcov <80% | Descriptive, BLAST-defined proxy |
| Twilight identity | qcov >=80% and 20% <= identity <30% | Descriptive, BLAST-defined |
| Identity <20%, any coverage | Best BLAST identity <20% | Exploratory case series |
| Strict ultra-remote proxy | qcov >=80% and identity <20% | Exploratory case series only |

The best BLAST hit is chosen by maximum bit score from the permissive E-value 1000
search already frozen in the parent benchmark. A no-hit subset is deliberately not
used as a headline because defining a cohort by a compared method's failure creates
selection bias against that method.

## Evidence needed for a formal ultra-remote claim

- Independent stratifier not included as a scored competitor.
- At least 100 positive independent components overall and at least 20 per fold.
- At least 600 calibration-negative components per source/fold is preferred for a
  defensible 99.5% specificity gate.
- External lockbox calibration and Test; no tuning after labels or scores are opened.
