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
| **Model V0.1 Candidate** | ESM-2 3B for H1/H2; ESM-C 6B for H3 | Recommended for external confirmation | **Preferred current result for new screening** |
| **Model V0** | ESM-C 6B for H1/H2/H3 | Released and frozen | Formal reproducible baseline and supported fallback |

“Preferred” describes the current screening path and Train-CV result. It does not mean that
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

## Evidence hierarchy

| Evidence | Status | What it can answer | What it cannot answer |
| --- | --- | --- | --- |
| 14-model V0 selection | Frozen development selection | Which all-one-encoder system was selected as Model V0 | External generalization |
| Four-source family-robustness analysis | All 20 predefined checks passed | Post-selection consistency of eight models and nine cascades on family members from the same four sources | Independent Test performance, equivalence, or feedback into model selection |
| PLM versus classical V0 | Internal cross-fit checks passed | Retrieval differences on Train components under the declared information budgets | External superiority |
| Low-similarity V0/V0.1 audit | Internal checks passed; formal claim blocked | Descriptive behavior on internal holdouts and low-coverage stress strata | A formal `<20% identity` conclusion |
| Prospective external Test | **Not run** | — | Release-grade generalization of Model V0 or Model V0.1 Candidate |

## What these results do not establish

- Neither Model V0 nor Model V0.1 Candidate has a new prospective external Test.
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
| Viral DJR-MCP | 560 | Gold 65 plus Silver 495; positive-source details are shown below |
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
| Silver | 495 | 436 MetaVR proteins; 18 GenBank candidates; 41 literature-derived candidates |

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

| Phylum | Class | Order / terminal taxon | Gold | Silver | Total |
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

The public [dataset contract](../configs/v0_dataset.json),
[dataset checksum manifest](../data/processed/v0/CHECKSUMS.sha256), and
[post-split audit checksums](../results/postsplit_integrity_v0/CHECKSUMS.sha256) provide compact,
machine-readable provenance for the same frozen dataset and audit.

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

### Model V0.1 Candidate: selection and trade-offs

Nine encoder combinations were compared using only existing Train-CV results. The four-source
robustness analysis served as a consistency check and did not rerank them. Model V0.1 Candidate
uses ESM-2 3B for H1/H2 and ESM-C 6B for H3 (`S=0.997645`), with no Holm-corrected source warnings
relative to Model V0. This does not establish four-source non-inferiority or equivalence.

| System | Viral | Cellular | Background | Matched HardNeg | Always-on / worst-case GPU s·seq⁻¹ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Model V0 (all ESM-C 6B) | 0.9536 | 0.8791 | 0.9948 | 0.9978 | 0.059531 / 0.059531 |
| Model V0.1 Candidate | 0.9537 | 1.0000 | 0.9985 | 0.9998 | 0.023524 / 0.083055 |

The four source columns are full-expected-path member accuracies, not one pooled score. Model V0.1
Candidate recovers 52/69 viral strict clusters, fewer than the 55/69 recovered by Model V0, and
requires a second encoder for sequences reaching H3. It remains recommended for external
confirmation and does not replace the released Model V0.

### Ultra-remote development audit

On the Train-only all-component holdout, H1 encoder sensitivity differs by `+0.197` for V0.1
relative to V0. The BLAST-defined `qcov<80%` stress stratum differs by `+0.260` (95% CI
0.206–0.317). The H1 operational detector differs by only `+0.017`, while the H2 and end-to-end MCP
cascade differences are zero. Because at least one evaluation fold misses the target specificity
and the strict ultra-remote stratum contains only one independent positive component, these results
are descriptive and do not support a formal ultra-remote claim.

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
2. [Published result map](../results/README.md) and
   [V0 figure collection](../results/figures/project_v0/README.md).
3. [V0/V0.1 audit report](../benchmarks/ultra_remote_v0_v01/results/REPORT.md),
   [all-component sensitivities](../benchmarks/ultra_remote_v0_v01/results/stratum_sensitivity.tsv),
   [paired comparisons](../benchmarks/ultra_remote_v0_v01/results/paired_v0_v01.tsv).
4. [PLM versus classical benchmark](../benchmarks/plm_vs_classical_v0/).
5. [Concise scientific report](research/PROJECT_V0_FINAL_REPORT.md).
6. [Complete workflow and protocol boundary](research/WORKFLOW_V0.md).
