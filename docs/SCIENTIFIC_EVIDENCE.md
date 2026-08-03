**English** | [简体中文](SCIENTIFIC_EVIDENCE.cn.md) | [日本語](SCIENTIFIC_EVIDENCE.ja.md)

# Scientific evidence and interpretation boundary

[Documentation map](README.md) | [Repository README](../README.md) |
[Reproducibility](REPRODUCIBILITY.md)

This page answers four questions in order: which result to use, what the core numbers show, how
strong the evidence is, and what the project cannot yet claim. It summarizes rather than replaces
the frozen protocols and result files.

## Which result should I use?

| Scientific result | Encoder system | Current status | Recommended use |
| --- | --- | --- | --- |
| **Model V0.1 Candidate** (`model-v0.1-candidate`) | ESM-2 3B for H1/H2; ESM-C 6B for H3 | `recommended_for_external_confirmation` | **Preferred current result for new screening** |
| **Model V0** (`model-v0`) | ESM-C 6B for H1/H2/H3 | Released and frozen | Formal reproducible baseline and supported fallback |

“Preferred” describes the current screening path and Train-CV nomination. It does not mean that
Model V0.1 Candidate has passed a prospective external Test or replaced Model V0. Model V0 remains
a primary scientific result, not a deprecated version.

## Core development numbers

The two tables below come from different Train-only development protocols. Compare V0 with V0.1
only within the same row; do not compare values across the two tables.

### Shared five-fold Train-CV nomination

| Metric ↑ | Model V0 | Model V0.1 Candidate |
| --- | ---: | ---: |
| Composite score `S` (mean ± SE) | `0.9971 ± 0.0009` | **`0.9976 ± 0.0010`** |

For both models, `S = 0.60·H1 AP + 0.30·H2 AP + 0.10·H3 macro-F1`. The displayed uncertainty is the
sample standard deviation of the five shared-fold scores divided by `sqrt(5)`, not a confidence
interval. The released V0 snapshot was H1 AP `0.998 ± 0.000`, H2 AP `1.000 ± 0.000`, and H3
known-class macro-F1 `0.981 ± 0.010` (means ± SE). Bold marks the nominated candidate, not a
statistical-significance claim.

### Separate cyclic component-holdout audit

| All-component sensitivity (descriptive; fold-locked) | Positive components (n) | Model V0 | Model V0.1 Candidate |
| --- | ---: | ---: | ---: |
| H1 encoder DJR readout | 392 | `0.728` | `0.925` |
| H1 operational detector | 392 | `0.978` | `0.995` |
| End-to-end MCP cascade | 209 | `0.914` | `0.914` |

Each cycle uses three fit folds, the next fold for calibration, and one evaluation fold. A separate
threshold is calibrated for every method, task, and cycle at the nominal 99.5% specificity target,
then applied unchanged to that cycle's evaluation fold. Within a component, record detections are
averaged; the table then gives every held-out component equal weight across all five evaluation
folds. This is the aggregation used by the audit's paired all-component report.

The largest descriptive difference is at H1 encoder readout. It becomes smaller after fitting and
applying the task-adapted detector under the frozen protocol, and the audit observes no end-to-end
MCP sensitivity difference. H3 is unchanged between the two systems and was excluded from this
audit.

### Why 0.800 appeared

The frozen outputs contain two valid but different component-level summaries of the same
end-to-end detections, plus a record-pooled contrast:

| Aggregation | Model V0 | Model V0.1 Candidate | Meaning |
| --- | ---: | ---: | --- |
| Equal-fold macro | `0.800` | `0.800` | Mean of fold sensitivities `1/0/1/1/1` |
| All held-out components | `0.913876` | `0.913876` | `191/209` components detected; all-component table above |
| All held-out records | `0.645833` | `0.645833` | `217/336` records detected; not the component estimand |

The folds contained `47/18/47/49/48` positive components. Equal-fold averaging therefore gave the
18-component second fold 20% of the final value, whereas the all-component estimate gave each of
the 209 components equal weight. The earlier README called `0.800` simply “sensitivity,” which hid
this distinction.

The second-fold zero was a calibration-resolution cliff; it does not mean that the 119 MCP
positives ranked below the conditional-H2 calibration negatives. For both models, their H1 and H2
raw scores exceeded the corresponding calibration-negative maxima. The H2-negative calibration
subset nevertheless contained 62 records from only one independent component, so empirical-tail
evidence saturated at `log10(63) = 1.7993405494535817`. At the cascade endpoint, 12 V0 and 15 V0.1
calibration negatives shared that saturated score; each source- and component-balanced tied block
had mass `0.007199` and `0.008380`, respectively—above the allowed `0.005`. The frozen conservative
`score >= threshold` rule therefore moved the threshold to the next floating-point value,
`1.7993405494535819`, and rejected the entire tie. Thus the `0.800` calculation is internally
reproducible, but it is unsuitable as an unqualified public recall value.

This clarification and alternative aggregation were checked against the full archived row ledgers
recorded by the [V0 parent pointer](../benchmarks/plm_vs_classical_v0/FULL_ARTIFACT_POINTER.json) and the
[V0/V0.1 audit pointer](../benchmarks/ultra_remote_v0_v01/FULL_ARTIFACT_POINTER.json). The V0 parent
ledger matched SHA-256 `d21bf8534a04b98a11f7502ce275dc6ff346b43d4433ba5551c223e77d904fdb`;
the V0.1 ledger matched
`b27a96a9ea7c26ab2c47ae2b3a7d5156cb775a9eab935a6cd17a87caed6ed2fa`. Independent recalculation
reproduced every displayed fold threshold, fold
sensitivity, evaluation specificity, and the all-component values above. The archive manifests
matched SHA-256 `6273f88a618726046162f9e83cbfb447602796c0e9bb7d68af92440faf023ab7`
(V0 parent benchmark) and
`dcd33fa981f4064a027e9d27a184cba947bfd16f3c2c85030e0288d509215384` (V0/V0.1 audit).

## Evidence hierarchy

| Evidence | Status | What it can answer | What it cannot answer |
| --- | --- | --- | --- |
| 14-model V0 selection | Frozen development selection | Which all-one-encoder system was selected as Model V0 | External generalization |
| Schema 5 Amendment D | 20/20 gates PASS | Post-selection consistency of eight models and nine cascades on family members from the same four sources | Independent Test performance, equivalence, or feedback into model selection |
| PLM versus classical V0 | Internal cross-fit PASS | Retrieval differences on Train components under the declared information budgets | External superiority |
| Ultra-remote V0/V0.1 audit | PASS; formal claim blocked | Descriptive behavior on internal holdouts and low-coverage stress strata | A formal `<20% identity` conclusion |
| Prospective external Test | **Not run** | — | Release-grade generalization of Model V0 or Model V0.1 Candidate |

## What these results do not establish

- Neither Model V0 nor Model V0.1 Candidate has a new prospective external Test.
- Historical Test results apply only to ESM-2 650M, not to the all-ESM-C-6B V0 system, the Schema 5
  nominee, or Model V0.1 Candidate.
- Every paired fold-calibrated system misses the intended 99.5% specificity in at least one
  evaluation fold; the sensitivity differences are therefore descriptive, not matched-specificity
  improvements.
- The BLAST-defined strict `qcov≥80%, identity<20%` stratum contains one independent positive
  component—too few for a formal ultra-remote conclusion.
- H3 is not a V0.1 improvement: both systems use the same ESM-C 6B H3 model.
- The evidence does not show that Model V0.1 Candidate has replaced Model V0 or that PLMs outperform
  classical methods on external data.
- `mcp::unknown/other` rejects a forced assignment to two supported phyla. It is not a general
  unknown-virus or out-of-distribution detector.

## Detailed evidence

### Released Model V0

- Data: 560 viral MCP-DJRs, 500 cellular DJRs, 5,000 HardNeg proteins, and 5,000 background
  proteins.

#### Development sample composition

The frozen development dataset contains **11,060 exact-sequence-unique representative proteins**.
The compact inventory and expandable taxonomy table below form the public sample list reproduced
from slide 5 of `Design-0728.pptx`. The 11,060-row build manifest is intentionally not distributed
in this repository because it contains local source-dataset paths; the public record instead uses
aggregate counts and checksum-bound evidence artifacts.

| Dataset group | N | Composition and construction |
| --- | ---: | --- |
| Viral DJR-MCP | 560 | Gold 65 plus Silver_R3 495; positive-source details are shown below |
| Cellular DJR | 500 | GH172/DUF2961 64; PHM/PAM 290; PNGase F 85; SIDT/SID-1/ChUP 56; DeCLIC-like DJR NTD 5 |
| Hard non-DJR | 5,000 | Structure-supported, β-sheet-rich viral and cellular non-DJR decoys expanded from the PPT's 36-seed construction set |
| Background non-DJR | 5,000 | Swiss-Prot representatives retained after sequence-, HMM-, and structure-relatedness exclusion against the other three groups |
| **Total** | **11,060** | Exact-sequence-unique representatives before the frozen component-safe split |

The cellular-DJR and HardNeg construction summaries use non-viral structural expansion with
`qTM > 0.7` and `LDDT > 0.5`. The repository contains the final 5,000-row HardNeg inventory and
checksum-pins its upstream metadata, but it does not include a compact row-by-row inventory of the
36 PPT seed families; that seed count is therefore a construction note rather than a fully
repository-auditable list.

| Viral evidence tier | N | Sources |
| --- | ---: | --- |
| Gold | 65 | 15 experimental PDB structures; 49 RefSeq-annotated MCPs; 1 isolated-virus GenBank MCP with virion-proteomics support |
| Silver_R3 | 495 | 436 MetaVR proteins; 18 GenBank candidates; 41 literature-derived candidates |

For the MetaVR and RefSeq/GenBank Silver candidates, the PPT records high viral confidence, HMM
support (`E < 0.1`, bit score `> 10`), length `> 200 aa`, separation from Gold clusters, and
structural similarity to PDB Golds (`qTM ≥ 0.60`, `tTM ≥ 0.60`, `LDDT ≥ 0.50`).

The positive catalog covers the following phylum-level groups:

| Positive taxonomy | N |
| --- | ---: |
| Nucleocytoviricota | 415 |
| Preplasmiviricota | 117 |
| Produgelaviricota | 26 |
| Literature-only, unclassified | 2 |
| **Total** | **560** |

<details>
<summary>Order / terminal-taxon sample list from the PPT</summary>

| Phylum | Class | Order / terminal taxon | Gold | Silver_R3 | Total |
| --- | --- | --- | ---: | ---: | ---: |
| Nucleocytoviricota | Megaviricetes | Algavirales | 25 | 161 | 186 |
| Nucleocytoviricota | Megaviricetes | Imitervirales | 9 | 122 | 131 |
| Nucleocytoviricota | Megaviricetes | Mamonoviridae† | 1 | 0 | 1 |
| Nucleocytoviricota | Megaviricetes | Pimascovirales | 7 | 55 | 62 |
| Nucleocytoviricota | Mriyaviricetes | Yaraviridae† | 1 | 18 | 19 |
| Nucleocytoviricota | Pokkesviricetes | Asfuvirales | 2 | 8 | 10 |
| Nucleocytoviricota | Pokkesviricetes | Chitovirales | 1 | 5 | 6 |
| Preplasmiviricota | Aquintoviricetes | Archintovirales | 2 | 6 | 8 |
| Preplasmiviricota | Pharingeaviricetes | Rowavirales | 1 | 2 | 3 |
| Preplasmiviricota | Polintoviricetes | Amphintovirales | 2 | 2 | 4 |
| Preplasmiviricota | Tectiliviricetes | Kalamavirales | 2 | 3 | 5 |
| Preplasmiviricota | Virophaviricetes | Divpevirales | 0 | 1 | 1 |
| Preplasmiviricota | Virophaviricetes | Lavidavirales | 3 | 5 | 8 |
| Preplasmiviricota | Virophaviricetes | Mividavirales | 1 | 5 | 6 |
| Preplasmiviricota | Virophaviricetes | Priklausovirales | 2 | 80 | 82 |
| Produgelaviricota | Ainoaviricetes | Lautamovirales | 1 | 0 | 1 |
| Produgelaviricota | Belvinaviricetes | Atroposvirales | 1 | 0 | 1 |
| Produgelaviricota | Belvinaviricetes | Belfryvirales | 1 | 0 | 1 |
| Produgelaviricota | Belvinaviricetes | Coyopavirales | 0 | 1 | 1 |
| Produgelaviricota | Belvinaviricetes | Vinavirales | 3 | 19 | 22 |
| Literature-only | Unclassified | *Abadenavirae*-like<sup>*</sup> | 0 | 2 | 2 |

† ICTV terminal family without an assigned order. The asterisk marks a literature-only working
clade rather than an ICTV MSL41 order. Each SHA-256-identical protein is counted once; the PPT
assigns four cross-order aliases to their catalog-designated primary taxon for this display.

</details>

The [split summary](../data/processed/v0/split_summary.json),
[dataset contract](../data/processed/v0/v0_dataset.json), and
[source-file checksums](../data/processed/v0/source_files.tsv) provide the compact machine-readable
provenance for the same frozen dataset.

- Split: Train/Validation/Test = **6,634 / 2,212 / 2,214**. Exact-sequence, source, component, and
  MMseqs2 relationships were merged before splitting; residual qualifying cross-split edges = 0.
- Selection: 14 representation models shared a Train-only five-fold component map. After the
  three-head Validation gates and paired one-SE rule, ESM-C 6B was selected (`S=0.997145`).

| Head | Task | Classifier | Temperature | Threshold |
| --- | --- | ---: | ---: | ---: |
| H1 | DJR / non-DJR | alpha=`1e-5` | 1168.1537298613255 | 0.9687754839244975 |
| H2 | viral MCP-DJR / cellular DJR | C=`0.01` | 0.8241381150130028 | 0.9639353725025007 |
| H3 | two known phyla + reject | C=`10` | 4.2474179687096845 | 0.7126488980564439 |

H2 runs only after H1 classifies a protein as DJR; H3 runs only after H2 classifies it as a viral
MCP.

### Model V0.1 Candidate nomination and trade-offs

Nine mixed candidates were preregistered and ranked only by existing Train-CV results. The
four-source robustness analysis did not rerank them. The nominee uses ESM-2 3B for H1/H2 and ESM-C
6B for H3 (`S=0.997645`), with `0/4` Holm-corrected source warnings relative to all-6B. This does
not establish four-source non-inferiority or equivalence.

| System | Viral | Cellular | Background | Matched HardNeg | Always-on / worst-case GPU s·seq⁻¹ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Frozen all ESM-C 6B | 0.9536 | 0.8791 | 0.9948 | 0.9978 | 0.059531 / 0.059531 |
| Mixed nominee | 0.9537 | 1.0000 | 0.9985 | 0.9998 | 0.023524 / 0.083055 |

The four source columns are full-expected-path member accuracies, not one pooled score. The nominee
recovers 52/69 viral strict clusters, fewer than the 55/69 recovered by all-6B, and requires a
second encoder for sequences reaching H3. Its status remains `recommended_for_external_confirmation`
with `released_v0_change_permitted=0`.

### Ultra-remote development audit

On the Train-only all-component holdout, H1 encoder sensitivity differs by `+0.197` for V0.1
relative to V0. The BLAST-defined `qcov<80%` stress stratum differs by `+0.260` (95% CI
0.206–0.317). The H1 operational detector differs by only `+0.017`, while the H2 and end-to-end MCP
cascade differences are zero. Because of the specificity and sample-size limitations above, the
formal status is
`PASS_WITH_FORMAL_ULTRA_REMOTE_BLOCKED_BY_SAMPLE_SIZE`.

### PLM versus classical retrieval

This benchmark uses cyclic 3-fit/1-calibration/1-evaluation component cross-fitting on 6,634 Train
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
negative. For H2 and the H1→H2 endpoint, intervals cross zero and are limited by low-FPR resolution
for singleton components. This is a representation-retrieval comparison, not external performance
of the released supervised tool. The validator recomputed point estimates but did not independently
rerun all 10,000 bootstrap replicates.

## Authoritative evidence entry points

1. [Model V0.1 Candidate package](../user-inference-v0.1/) and
   [released Model V0 package](../user-inference-v0/).
2. [Candidate nomination](../results/validation_family_robustness_v0_schema5_mixed_heads/candidate_nomination.tsv)
   and [Train-CV candidate summary](../results/validation_family_robustness_v0_schema5_mixed_heads/train_cv_candidate_summary.tsv).
3. [V0 model-selection figure and provenance](../results/figures/project_v0/model_benchmark_metric_revision_1/).
4. [V0/V0.1 audit report](../benchmarks/ultra_remote_v0_v01/results/REPORT.md),
   [all-component sensitivities](../benchmarks/ultra_remote_v0_v01/results/stratum_sensitivity.tsv),
   [equal-fold method summary](../benchmarks/ultra_remote_v0_v01/results/method_summary.tsv), and
   [paired comparisons](../benchmarks/ultra_remote_v0_v01/results/paired_v0_v01.tsv).
5. [Schema 5 compact results](../results/validation_family_robustness_v0_schema5_mixed_heads/).
6. [PLM versus classical benchmark](../benchmarks/plm_vs_classical_v0/).
7. [Concise scientific report](research/PROJECT_V0_FINAL_REPORT.md).
8. [Complete workflow and protocol boundary](research/WORKFLOW_V0.md).
