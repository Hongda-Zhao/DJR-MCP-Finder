# Scientific evidence and interpretation boundary

This document contains the scientific detail intentionally removed from the repository landing
page. It summarizes the current evidence without changing the authoritative frozen protocols or
results. For the complete workflow, read [`WORKFLOW_V0.md`](research/WORKFLOW_V0.md); for a concise
report, read [`PROJECT_V0_FINAL_REPORT.md`](research/PROJECT_V0_FINAL_REPORT.md).

## Current primary results: V0 and V0.1

The project currently exposes two primary scientific results: the released, all-ESM-C-6B Model V0
and the mixed-encoder Model V0.1 candidate. They are peers in the public project navigation, while
retaining different evidence and release statuses. The sections below preserve those distinctions.

### Released Model V0

- Data: 560 VMA-DJRs, 500 cellular DJRs, 5,000 HardNeg proteins, and 5,000 background proteins.
- Split: Train/Validation/Test = **6,634 / 2,212 / 2,214**. Exact-sequence, source, component, and
  MMseqs2 relationships were merged before splitting; residual qualifying cross-split edges = 0.
- Model selection: 14 representation models shared a Train-only five-fold component map. The
  composite score was `S = 0.60·H1 AP + 0.30·H2 AP + 0.10·H3 macro-F1`; after the three-head
  Validation gates and paired one-SE rule, ESM-C 6B was selected (`S=0.997145`).

| Head | Task | Classifier | Temperature | Threshold |
| --- | --- | ---: | ---: | ---: |
| H1 | DJR / non-DJR | alpha=`1e-5` | 1168.1537298613255 | 0.9687754839244975 |
| H2 | VMA-DJR / cellular DJR | C=`0.01` | 0.8241381150130028 | 0.9639353725025007 |
| H3 | two known phyla + reject | C=`10` | 4.2474179687096845 | 0.7126488980564439 |

H2 runs only after H1 classifies a protein as DJR; H3 runs only after H2 classifies it as VMA-DJR.
H3 `unknown/other` rejects a forced assignment to Nucleocytoviricota or Preplasmiviricota; it is
not a general unknown-virus detector.

## Evidence hierarchy

| Evidence | Status | What it can answer | What it cannot answer |
| --- | --- | --- | --- |
| 14-model benchmark | Frozen development selection | Which all-one-encoder system was selected as Model V0 | External generalization |
| Schema 5 Amendment D | 20/20 gates PASS | Robustness of eight models and nine cascades on family members from the same four sources | Independent Test performance or feedback into model selection |
| PLM versus classical V0 | Internal cross-fit PASS | Differences between PLM retrieval and classical search on Train components | External superiority |
| Ultra-remote V0/V0.1 | PASS; formal claim blocked | Candidate behavior on internal holdouts and low-coverage stress strata | A formal `<20% identity` conclusion |
| Prospective/external Test | **Not run** | — | Release-grade generalization of Model V0 or the candidate |

### Model V0.1 mixed-encoder result

Nine mixed candidates were preregistered and ranked only by existing Train-CV results; the
four-source robustness analysis did not rerank them. The current nominee uses ESM-2 3B for H1/H2
and ESM-C 6B for H3 (`S=0.997645`), with `0/4` Holm-corrected source warnings relative to all-6B.
This does not establish four-source non-inferiority or equivalence.

| System | Viral | Cellular | Background | Matched HardNeg | Always-on / worst-case s·seq⁻¹ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Frozen all ESM-C 6B | 0.9536 | 0.8791 | 0.9948 | 0.9978 | 0.059531 / 0.059531 |
| Mixed nominee | 0.9537 | 1.0000 | 0.9985 | 0.9998 | 0.023524 / 0.083055 |

The nominee recovers 52/69 viral strict clusters, fewer than the 55/69 recovered by all-6B, and it
requires a second encoder for sequences reaching H3. Its status remains
`recommended_for_external_confirmation`, with `released_v0_change_permitted=0`.

## PLM versus classical retrieval

The benchmark uses cyclic 3-fit/1-calibration/1-evaluation component cross-fitting on 6,634 Train
records. Values are fold-macro component AP / sensitivity at a threshold calibrated to a 99.5%
specificity target.

| Method | H1 | H2 |
| --- | ---: | ---: |
| ESM-C 6B cosine | 0.8719 / 0.7340 | 0.9861 / 0.9306 |
| BLASTP | 0.9392 / 0.8692 | 0.9829 / 0.9443 |
| DIAMOND ultra | 0.9406 / 0.9025 | 0.9806 / 0.9317 |
| MMseqs2 | 0.9319 / 0.8805 | 0.9751 / 0.9119 |
| Component-HMMER | 0.9542 / 0.9016 | 0.9911 / 0.9569 |
| ESM-2 650M cosine, contextual | 0.9515 / 0.8954 | 0.9965 / 0.9977 |

For H1, paired delta confidence intervals for ESM-C cosine versus all four classical anchors are
negative. For H2 and the end-to-end endpoint, intervals cross zero and are limited by low-FPR
resolution for singleton components. This compares representation retrieval, not external
performance of the released supervised tool. The validator recomputed point estimates but did not
independently rerun all 10,000 bootstrap replicates.

## Ultra-remote development audit

The candidate changes only the H1/H2 encoder to ESM-2 3B; H3 remains ESM-C 6B. On the Train-only
component holdout, H1 encoder sensitivity improves by `+0.197` relative to V0; the BLAST-defined
`qcov<80%` stress stratum improves by `+0.260` (95% CI 0.206–0.317). The H1 supervised detector
improves by only `+0.017`, while H2 and end-to-end detector changes are zero. Every paired system
misses the actual 99.5% specificity target in at least one fold. The strict
`qcov≥80%, identity<20%` stratum contains only one independent positive component, so the status is
`PASS_WITH_FORMAL_ULTRA_REMOTE_BLOCKED_BY_SAMPLE_SIZE`.

## Current claim boundary

Historical Test results apply only to ESM-2 650M. All ESM-C 6B systems, the Schema 5 nominee, and
the V0.1 candidate remain `not_evaluated` on that Test. The repository supports claims about
component-safe dataset construction, development benchmarks, the frozen Model V0 tool, and clearly
labelled internal stress tests. It does not support claims that the candidate has replaced V0, that
PLMs outperform classical methods on external data, or that the tool generally detects unknown
viruses.

## Authoritative evidence entry points

- [`WORKFLOW_V0.md`](research/WORKFLOW_V0.md): complete workflow and evidence boundary.
- [`PROJECT_V0_FINAL_REPORT.md`](research/PROJECT_V0_FINAL_REPORT.md): concise scientific report.
- [`results/validation_family_robustness_v0_schema5_mixed_heads/`](../results/validation_family_robustness_v0_schema5_mixed_heads/): compact Schema 5 results.
- [`benchmarks/plm_vs_classical_v0/`](../benchmarks/plm_vs_classical_v0/): internal PLM/classical benchmark.
- [`benchmarks/ultra_remote_v0_v01/`](../benchmarks/ultra_remote_v0_v01/): compact development audit.
- [Formal Model V0 package](../user-inference-v0/) and [V0.1 candidate package](../user-inference-v0.1/).
