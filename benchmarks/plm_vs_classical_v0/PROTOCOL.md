# Frozen protocol: PLM versus classical remote homology

## Scope and claim boundary

This is an internal method-development comparison.  It may establish what was
observed under component-cross-fitting on project data; it cannot establish
external superiority.  Validation was used during earlier model development,
and the protected Test split is out of scope.  PLM pretraining exposure is not
fully knowable, so equal task-specific references do not imply equal total
pretraining information.

## Cohort and leakage control

- Cohort: the 6,634 records in the frozen Train split.
- Outer folds: the existing five-fold map keyed by `global_component_id`.
- For evaluation fold *k*, calibration is fold `k mod 5 + 1`; the remaining
  three folds are the only fitting/reference data.
- Calibration and evaluation use the identical fitted model/reference/profile,
  and neither can enter fitting, an MSA, or PSSM iteration.
- No component may occur in both query and reference within a fold.
- BLASTP, DIAMOND, MMseqs2, cosine retrieval, HMMER, and PSI-BLAST share the
  identical reference-ID manifest for a task and fold.
- HMM MSAs and PSI-BLAST enrichment databases contain reference IDs only.
- Validation and Test records are not accepted as queries, references, profile
  members, threshold-fitting rows, or metric rows.

## Tasks

| ID | Positive | Negative | Eligible rows | Reference set |
|---|---|---|---|---|
| `h1_djr` | viral VMA + cellular DJR | hard + background non-DJR | all Train | outer-Train DJR |
| `h2_vma_conditional` | viral VMA | cellular DJR | Train DJR only | outer-Train VMA |
| `vma_end_to_end` | viral VMA | cellular DJR + hard + background | all Train | outer-Train VMA |

## Methods

- `esmc6b_cosine` and `esm2_650m_cosine`: maximum cosine to an outer-Train
  positive reference; mean embeddings are fixed project artifacts.
- `blastp`: maximum bit score, BLAST+ 2.17.0.
- `diamond_ultra`: maximum bit score, DIAMOND 2.2.4 `--ultra-sensitive`.
- `mmseqs_s7.5`: maximum bit score, MMseqs2 18-8cc5c, sensitivity 7.5,
  one iteration.
- `hmmer_component`: maximum full-sequence HMM bit score; one Train-only model
  per positive global component.  Singleton models are retained and counted.
- `hmmer_family`: the same score, using Train-only metadata groups.  This is
  reported separately because curated grouping supplies extra supervision.
- `psiblast_longest_seed_positiveDB_3iter`: one deterministic longest seed per positive component,
  at most three iterations against the outer-Train positive-only database,
  inclusion E-value 0.002, without per-subject HSP truncation during enrichment,
  then frozen-PSSM search of calibration and evaluation folds.
- `esmc6b_supervised`: H1/H2 models refitted per outer fold with the project's
  frozen settings.  End-to-end scores combine nested-cross-fitted empirical H1
  and H2 negative-tail evidence by their minimum.

No-hit is a legitimate score of negative infinity.  Tool or parser failure is
missing/NA and invalidates formal aggregation.

## Metrics and weighting

### Internal low-FPR endpoint amendment

Section 12 reserves 99.9% specificity for a future sufficiently powered
external benchmark.  The present internal cohort cannot resolve that endpoint
reliably (especially H2 with only 298 cellular negatives), so protocol V0
pre-registers 99.5% as its internal primary and retains 99.9% only as
`RESOLUTION_LIMITED_SECONDARY`.  This amendment does not alter the future
external endpoint.

### Pre-aggregation empirical-resolution audit

A score-independent audit of the frozen folds found an additional H2
limitation. Fold 3 contains 62 cellular-DJR negative records but only one
`global_component_id` (`V0GC_96fb96e7e076c167`). When fold 3 calibrates cycle
2, every H2 negative record has weight 1/62 (1.61%), so the 99%, 99.5%, and
99.9% thresholds all require zero empirical false positives. When fold 3 is
evaluated in cycle 3, H2 specificity has only one independent negative
component. Because the component bootstrap retains the sole member of a
stratum with multiplicity one, it cannot estimate between-component variation
for this source.

The frozen 99.5% estimand is not changed post hoc. Instead, affected
sensitivity estimates and paired intervals are labelled conditional and
resolution-limited in the machine-readable output and report. Fold 2 also has
119 VMA-positive records but only 18 positive components; all primary tables
therefore retain fold ranges and record/component counts. These limitations
preclude treating the internal H2 low-FPR endpoint as a stable external
specificity estimate.

Primary metrics are fold-macro component-balanced average precision and sensitivity at
99.5% source-balanced specificity.  A component first receives equal mass and
its records share that mass.  For threshold calibration, negative sources
receive equal mass, then components within source receive equal mass.

Thresholds use only the cycle's dedicated calibration fold, scored against the
same reference/model as the paired evaluation fold.  Inclusive ties are handled conservatively.
Sensitivity is also shown at 99% and at 99.9%; the latter is always labelled
`RESOLUTION_LIMITED_SECONDARY`.  FP-per-million endpoints are not estimable.

Paired uncertainty for both fold-macro component-balanced AP and calibrated
sensitivity uses 10,000 common component resamples across methods.  Every
replicate draws one global component-multiplicity vector and reuses it across
tasks, cycles, methods, and both metrics.  Each method's calibration threshold
is recalculated within that draw.  Paired percentile-bootstrap intervals are
reported descriptively; bootstrap sign fractions are not labelled as
null-hypothesis P values and no family-wise superiority claim is made.

## Stop conditions

Formal summarization fails if any reference checksum/ID contract differs among
controlled methods, a query component leaks into a reference/profile, an
inclusion ledger contains a non-reference ID, Test/Validation prediction rows
are nonzero, a method failure is encoded as no-hit, an expected score is absent,
or 99.9%/FP-per-million is presented as a stable primary estimate.
