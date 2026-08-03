<!-- i18n-mirror: non-authoritative translation; source=docs/research/WORKFLOW_V0.md -->

> **Translation note:** This translation is for reading only; the frozen Chinese source is authoritative.

# DJR-MCP Finder project V0: complete workflow

Status: the primary release, **all ESM-C 6B, is frozen**. Schema 5 Amendment D is the current
broadest four-source auxiliary analysis of eight models and mixed Heads; schema 4 is retained as
the two-model continuity baseline. Neither robustness analysis is an independent Test, and neither
can feed back into V0.

```text
data-curation V3 -> project V0
 -> 11,060 representatives
 -> component-safe Train / Validation / Test
 -> 14-model shared Train-CV
 -> Validation calibration + gates + paired one-SE
 -> freeze all ESM-C 6B
 -> user inference release
 -> post-freeze schema 4 / schema 5 diagnostics (read-only)
```

## 1. Three cascade Heads

```text
protein
 └─ H1: DJR?
     ├─ no  -> non_djr
     └─ yes -> H2: viral morphogenesis-associated?
               ├─ no  -> cellular DJR / none
               └─ yes -> H3: known phylum or reject
```

| Head | Training scope | Task | Primary development metric |
| --- | --- | --- | --- |
| H1 | All proteins | DJR / non-DJR | AP |
| H2 | DJR | VMA-DJR / cellular DJR | AP; Validation also checks macro-F1 |
| H3 | Two sufficiently sampled VMA phyla | Nucleocytoviricota / Preplasmiviricota + reject | known-class macro-F1 |

The 560 VMA-DJR records for H3 consist of 415 Nucleocytoviricota, 117 Preplasmiviricota, 26
Produgelaviricota, and 2 literature-unclassified records. The first two classes, totaling 532
records, participate in known-class fitting; the remaining 28 records are used only as reject
diagnostics. `unknown/other` means “do not force into either known class”; it does not mean discovery
of a new virus or new phylum.

## 2. Data and component-safe split

| source set | representatives | H1 | H2 |
| --- | ---: | --- | --- |
| VMA-DJR data-curation V3 | 560 | positive | positive |
| cellular DJR | 500 | positive | negative |
| hard non-DJR | 5,000 | negative | N/A |
| background non-DJR | 5,000 | negative | N/A |
| total | **11,060** | — | — |

Upstream V3 contains 564 official cluster rows; exact-sequence deduplication leaves 560 modeling
positives. The version mapping is always `data-curation V3 -> project V0`.

Before splitting, the transitive closure of the following relations is taken:

1. normalized exact-identical sequence;
2. the same source cluster;
3. an existing legacy/global component;
4. a qualifying MMseqs2 relation with identity≥30% and bidirectional coverage≥80%.

Each complete component may enter only one split:

| split | records | DJR / non-DJR | VMA-DJR |
| --- | ---: | ---: | ---: |
| Train | 6,634 | 634 / 6,000 | 336 |
| Validation | 2,212 | 212 / 2,000 | 112 |
| Test | 2,214 | 214 / 2,000 | 112 |

The full graph contains 27,427 nodes and 9,262 global components containing modeling
representatives; quarantined model representatives=0 and full-search residual qualifying
cross-split edges=0. This gate reduces the risk of strong-homology leakage, but it does not prove
the absence of remote homology below 30% identity.

## 3. 14-model benchmark

All models read the same manifest, split, and Train-only `global_component_id` 5-fold map.
Checkpoint revision, precision, window, stride, pooling, and checksum are fixed. Long sequences
must be processed with sliding windows covering their full length; padding and special tokens are
not included in the residue mean.

```text
S = 0.60 * CV H1 raw-score AP
  + 0.30 * CV H2 raw-score AP
  + 0.10 * CV H3 known-class macro-F1
```

The Validation gate requires that no Head decline by more than 0.01 relative to the fresh ESM-2
650M baseline. After the gate, a paired one-SE rule is applied to shared folds; speed is used as a
final cost criterion only when its definition is fully comparable.

Ranking metrics must use the raw `decision_function`. The old Figure 1a used sigmoid probability to
calculate AP. Saturation to exact 0/1 incorrectly produced `0.857107`; the raw-score AP for the same
ESM-2 650M fold predictions is `0.997917`. This is a numerical correction, not new data or new
biological evidence.

| model | rank | `S` | gate |
| --- | ---: | ---: | --- |
| **ESM-C 6B** | 1 | **0.997145** | PASS / selected |
| ESM-2 3B | 2 | 0.994873 | PASS |
| ESM-C 300M | 3 | 0.993444 | PASS |
| ESM-2 650M | 8 | 0.990376 | baseline PASS |

The complete 14-model table is at `results/model_benchmark_v0_metric_revision_1/model_comparison.tsv`.

## 4. Calibration, frozen parameters, and the Test boundary

Temperature changes only the probability scale, not the raw-score ordering. The H1 threshold
maximizes MCC on Validation, and H2 maximizes macro-F1; the H3 reject threshold uses only known
Validation classes, targeting known acceptance near 0.95. Rare/unclassified records do not
participate in H3 threshold selection.

| Head | classifier | temperature | decision/reject threshold |
| --- | ---: | ---: | ---: |
| H1 | alpha=`1e-5` | 1168.1537298613255 | 0.9687754839244975 |
| H2 | C=`0.01` | 0.8241381150130028 | 0.9639353725025007 |
| H3 | C=`10` | 4.2474179687096845 | 0.7126488980564439 |

The historical 2,214-record Test was opened only for ESM-2 650M. Numerical trace-back of the same
frozen prediction gives H1 AP=0.998068, AUROC=0.999724, and FPR@95% recall=0; these values cannot be
attached to ESM-C 6B. The current all-6B system and every schema 5 candidate have
`test_status=not_evaluated`. A new prospective/external Test must be opened once, only after its
protocol is frozen.

## 5. HardNeg source recovery

The historical four-batch DAG used for V0 has been fully replayed from frozen inputs:

```text
172,346 raw
 -> 42,266 strict rows / 42,264 unique
 -> 36,138 Tier1 members
 -> 10,880 representatives
 -> 10,878 H1-negative pass + 2 quarantine
 -> 5,000 selected
```

All 93/93 search units were verified; the A/B member maps agree; retained representatives, selected
artifacts, and reconstructed results are byte-identical or semantically equivalent; G0–G6 are 7/7
PASS, with status `FULL_OPERATIONAL_RECOVERY_PASS`. The later six-batch expansion containing 57,708
Tier1 / 18,819 representatives is a separate exploration and is not part of V0.

The recovery results provide matched members only for selected HardNeg clusters. They do not change
the 11,060 representatives, split, model, parameters, or Test. The older 5,878 pass-but-unselected
representatives are historical unpaired sensitivity and must not be presented as selected-cluster
members.

## 6. Schema 4: two-model continuity baseline

Schema 4 establishes a four-source, applicable-Head matched-family baseline for frozen all-6B and
ESM-2 650M:

| source | legal clusters / members / blocks | all-6B full path | ESM-2 650M |
| --- | ---: | ---: | ---: |
| viral | 69 / 13,054 / 32 | 0.9536 | 0.9325 |
| cellular | 43 / 391 / 12 | 0.8791 | 0.9997 |
| background | 1,000 / 3,000 / 893 | 0.9948 | 0.9974 |
| selected HardNeg | 382 / 3,478 / 237 | 0.9978 | 1.0000 |

The four sources are not pooled into a total score. Statistics use equal dependence
block→source cluster→member weighting, fixed seed 20260724, and 10,000 paired bootstrap replicates.
Negative-only sources report only specificity/FPR and do not calculate AP, AUROC, or F1. Every 95%
CI for a member−representative delta includes 0; the main weakness of all-6B is cellular H1.

Independent validation for schema 4 is PASS: 22 endpoints were recomputed consistently,
predictions=92,844, expected paths=39,846, HardNeg H2/H3=0, and Test=0. It now serves as schema 5's
checksum-bound continuity baseline, not as the latest broadest conclusion.

## 7. Schema 5: eight models and mixed Heads

### 7.1 Fixed design

Schema 5 uses the same legal four-source cohort as schema 4. The expensive expansion is restricted
to the 8 models from the original 14-model benchmark that satisfy the fixed candidate boundary:
ESM-2 650M/3B, ESM-C 300M/600M/6B, ProtT5-XL-U50, ProstT5, and ESM3-open 1.4B.

The first layer consists of 8 homogeneous systems; the second contains only 9 preregistered mixed
candidates:

```text
H1=H2 in {ESM-2 650M, ESM-2 3B, ESM-C 6B}
H3    in {ESM-C 300M, ESM-C 600M, ESM-C 6B}
```

H1/H2 share an encoder; the second H3 encoder is called only after the H1→H2 route reaches the viral
path. No arbitrary 8³ combinations were searched. Candidate ordering uses only the existing shared
Train-CV `S`; robustness checks only source-specific inferiority warnings relative to all-6B, with
Holm correction within each source.

### 7.2 Homogeneous results

| system | viral | cellular | background | matched HardNeg |
| --- | ---: | ---: | ---: | ---: |
| ESM-2 650M | 0.9325 | 0.9997 | 0.9974 | **1.0000** |
| ESM-2 3B | 0.8949 | **1.0000** | 0.9985 | 0.9998 |
| ESM-C 300M | 0.9060 | 0.9620 | 0.9907 | 0.9988 |
| ESM-C 600M | 0.9063 | 0.8790 | 0.9966 | **1.0000** |
| ESM-C 6B | 0.9536 | 0.8791 | 0.9948 | 0.9978 |
| ProtT5-XL-U50 | 0.9084 | 0.7960 | 0.9991 | 0.9958 |
| ProstT5 | 0.9078 | 0.9877 | 0.9989 | **1.0000** |
| ESM3-open 1.4B | **0.9685** | 0.8885 | 0.9989 | **1.0000** |

No homogeneous model wins across all four sources. The trade-offs among sources are real and must
not be hidden by a post hoc mean.

### 7.3 Mixed nominee and cost

| candidate | Train-CV `S` | always-on s·seq⁻¹ | worst-case s·seq⁻¹ |
| --- | ---: | ---: | ---: |
| **H1/H2 ESM-2 3B + H3 ESM-C 6B** | **0.997645** | **0.023524** | 0.083055 |
| all ESM-C 6B | 0.997145 | 0.059531 | **0.059531** |
| H1/H2 ESM-2 650M + H3 ESM-C 6B | 0.996813 | **0.007405** | 0.066935 |

nominee=`h12_esm2_3b__h3_esmc_6b`:

| source | expected path (95% CI) | strict clusters |
| --- | ---: | ---: |
| viral | 0.9537 (0.9131–0.9872) | 52/69 |
| cellular | 1.0000 (1.0000–1.0000) | 43/43 |
| background | 0.9985 (0.9963–1.0000) | 997/1,000 |
| matched HardNeg | 0.9998 (0.9995–1.0000) | 381/382 |

There are `0/4` Holm-corrected warnings relative to all-6B, but this is not proof of four-source
non-inferiority/equivalence. Viral strict clusters are below the all-6B value of 55/69, and the H3
worst case requires two encoders. The formal status is only
`recommended_for_external_confirmation`; `released_v0_change_permitted=0`.

### 7.4 H3 boundary

The nominee's H3 is identical to all-6B: Nucleocytoviricota F1=0.9792 and Preplasmiviricota
F1=1.0000; Produgelaviricota reject=6/7 (2 parents/blocks), and
literature-unclassified=1/1 (1 parent, with no estimable CI). The two groups must remain separate;
pooled 7/8 is only a secondary diagnostic.

## 8. Schema 5 integrity

- result status=`complete_eight_model_nine_candidate_four_source`; independent validation **20/20 gates PASS**, with 289 endpoints recomputed consistently;
- 18 new materialization receipts + 6 reuse attestations = 24/24;
- schema 4's 92,844 keys and 464,220 numeric strings exactly replay under the frozen Python 3.11.7/four-thread numerical operator, with numeric/semantic/derived-decision mismatches=0;
- single-model predictions=371,376; system predictions=789,174; expected paths=338,691; bootstrap rows=680,000; Test records=0;
- Amendment D is byte-identical to Amendment C for 7 formal contract artifacts including predictions, thresholds, CV scores, and candidate order; H3 subgroup endpoints were independently recomputed from the frozen manifest;
- compact result 17/17 checksum PASS; original a–e figure package 11/11 PASS. The active primary figure uses the read-only head-focus companion: top release 4/4 and in-directory 13/13 checksum PASS; 56 Head endpoints, 32 path cells, 9 recipes, and 4 nominee diagnostics agree field-for-field with the formal results and create no new scientific conclusion.

Failure closure, numerical-operator, and display-contract details for Amendments A–D are retained in
`VALIDATION_FAMILY_ROBUSTNESS_V0_SCHEMA5_MIXED_HEADS_PROTOCOL.md` and are not repeated in the primary
workflow.

## 9. Completed internal PLM-vs-classical benchmark

### 9.1 Design and fairness boundary

This benchmark uses only the 6,634 frozen Train records. Five existing `global_component_id` folds
cyclically serve as 3-fit/reference, 1-calibration, and 1-evaluation. The reference/profile/model in
a given cycle does not read calibration or evaluation data. Both Validation and Test prediction
rows are 0.

The three tasks are H1 DJR detection, H2 VMA|DJR, and VMA end-to-end. In the controlled primary
track, ESM-C 6B cosine, BLASTP, DIAMOND, MMseqs2, and component-HMMER share the same positive
reference IDs; ESM-2 650M is a separate controlled PLM context. PSI-BLAST, metadata-family HMM, and
supervised ESM-C refitted in each outer fold belong to different supplementary/operational tracks
and are not mixed into the controlled headline.

Primary metrics are the macro-average of component-balanced AP across the five evaluation folds,
and evaluation sensitivity after selecting a 99.5% specificity-target threshold on an independent
calibration fold. 99.9% is only `RESOLUTION_LIMITED_SECONDARY`; FP-per-million is not estimable.

### 9.2 Formal internal results

| method | H1 AP / sens. | H2 AP / sens. | VMA e2e AP / sens. |
| --- | ---: | ---: | ---: |
| ESM-C 6B cosine | 0.8719 / 0.7340 | 0.9861 / 0.9306 | 0.9528 / 0.9301 |
| BLASTP | 0.9392 / 0.8692 | 0.9829 / 0.9443 | 0.9544 / 0.9401 |
| DIAMOND ultra | 0.9406 / 0.9025 | 0.9806 / 0.9317 | 0.9497 / 0.9317 |
| MMseqs2 | 0.9319 / 0.8805 | 0.9751 / 0.9119 | 0.9317 / 0.9078 |
| component-HMMER | 0.9542 / 0.9016 | 0.9911 / 0.9569 | 0.9660 / 0.9569 |
| ESM-2 650M cosine, context | 0.9515 / 0.8954 | 0.9965 / 0.9977 | 0.9906 / 0.9859 |

For ESM-C cosine versus the four classical anchors, every H1 AP and sensitivity delta 95% CI is
negative; every preregistered H2 and e2e CI crosses 0. This does not support the claim that “ESM-C
cosine retrieval is more sensitive than classical tools.” Nor is it equivalent to external
performance of the frozen supervised V0 classifier.

### 9.3 Validation and limitations

- validation=PASS; 250,236 query-score rows, 27 primary rows, 12 paired deltas; Test/Validation rows=0;
- point estimates were independently recomputed; `bootstrap_recomputed=false`, and the validator checks only the CI schema, range, order, replicate count, and registry, so this cannot be described as an independent replay of all 10,000 bootstrap replicates;
- fold 3's 62 cellular negatives belong to only one component; fold 2's 119 VMA positives belong to only 18 components, so H2/e2e low-FPR intervals are conditional/resolution-limited;
- equal task-specific references do not eliminate unknown PLM pretraining exposure;
- all 20,424 checksums in the complete original release PASS. The active copy had omitted 3 figure source-data TSVs; after deterministic reconstruction from frozen results, their SHAs agreed item-by-item with the original manifest, restoring a complete compact figure release.

The internal P0/development comparison is complete. A source-component-disjoint external lockbox,
99.9% specificity/FPM, and a more complete PLMSearch/pLM-BLAST/hybrid matrix remain in the
prospective planned state.

## 10. V0/V0.1 ultra-remote development audit

V0.1 changes only the H1/H2 encoder to ESM-2 3B; H3 still uses ESM-C 6B. It reuses the same
Train-only cyclic cross-fit and compares the raw cosine encoder with a task-adapted detector from
the same classifier family.

| endpoint | all holdout Δ(v0.1−v0) | `qcov<80%` | `qcov≥80%, 20–30% identity` |
| --- | ---: | ---: | ---: |
| H1 encoder sensitivity | +0.197 | +0.260 (0.206–0.317) | +0.046 (0.013–0.086) |
| H1 detector sensitivity | +0.017 | +0.028 (0.011–0.049) | 0.000 |
| H2 encoder sensitivity | +0.049 | +0.062 (0.020–0.112) | +0.024 (0.001–0.057) |
| H2 detector sensitivity | 0.000 | 0.000 | 0.000 |

The encoder signal does not translate proportionally into operational-detector gains. Every paired
system misses the actual 99.5% specificity in at least one fold; the minimum-fold specificity of
the V0.1 H2 detector is 0.5426, versus 0.8599 for V0. The strict
`qcov≥80%, identity<20%` stratum has only 1 independent positive component, below the preregistered
threshold of 100 total/20 per fold; BLAST-defined strata also introduce method-conditioned bias.

Validation status is `PASS_WITH_FORMAL_ULTRA_REMOTE_BLOCKED_BY_SAMPLE_SIZE`: the process is PASS,
but matched-specificity, external Test, and formal ultra-remote claims all fail. The V0.1
development workflow must remain isolated from released V0.

## 11. Active files, archives, and execution locations

| role | active path |
| --- | --- |
| frozen model benchmark | `results/model_benchmark_v0_metric_revision_1/` |
| schema 5 compact results | `results/validation_family_robustness_v0_schema5_mixed_heads/` |
| schema 5 publication companion | `results/figures/project_v0/validation_family_robustness_v0_schema5_head_focus/` |
| PLM/classical compact benchmark | `benchmarks/plm_vs_classical_v0/` |
| V0/V0.1 compact audit | `benchmarks/ultra_remote_v0_v01/` |
| frozen model identity | `results/model_benchmark_v0_metric_revision_1/esmc_6b/FROZEN_MODEL_CHECKSUMS.sha256` |
| released user inference V0 | `user-inference-v0/` |
| unreleased user inference V0.1 candidate | `user-inference-v0.1/` |
| portable root research entrypoints | `scripts/run_v0_dataset.py`; `scripts/run_postsplit_integrity_audit.py` |

The following complete schema 5 and schema 4 paths are frozen provenance from the original gds2
generation:

- `/aptmp/hongda/DJRMCP_Develope/project-V0__validation-family-robustness-schema5-mixed-heads__20260728/schema5_v1_amendment_d/`
- `/aptmp/hongda/DJRMCP_Develope/project-V0__validation-family-robustness-schema4__20260728/schema4_v1/`

The PLM benchmark's 7.6GB work/logs/databases and the ultra-remote large work/TIFF are stored in
dated 2026-07-29 checksum-bound archives. Active paths retain only protocols, code, formal summary
tables, validation, PNG/PDF/SVG, and source data.

GPUs are used for encoder embeddings; statistics, checksums, and most validation are CPU tasks. The
two user-facing packages are provided with the GitHub checkout, with the following entry points:

```bash
cd user-inference-v0
bash scripts/run_user_fasta.sh INPUT.faa OUTPUT_DIR cuda

cd ../user-inference-v0.1
bash workstation/run_user_fasta.sh INPUT.faa OUTPUT_DIR GPU_INDEX
```

V0.1 remains a `recommended_for_external_confirmation` candidate package and does not replace V0.
The original `/aptmp/hongda/DJRMCP_Develope/user-inference-V0` and
`hongda-133:/lab/hongda/user-inference-V0` record only historical validation/deployment locations
and are not runtime dependencies of the current checkout. The new analyses did not modify V0's
model, three Heads, temperature, threshold, window, or pooling.

Ordinary user prediction does not depend on PBS, `qsub`, or an HPC scheduler.

### 11.1 Portable paths and frozen provenance

The repository can be checked out at any absolute path. Non-frozen launchers use
`DJRMCP_PROJECT_ROOT`, `DJRMCP_ARCHIVE_ROOT`, `DJRMCP_DATABASE_ROOT`, `DJRMCP_SOFTWARE_ROOT`, and
`DJRMCP_VENV_ROOT`; the default project root is inferred from the script location. Frozen configs retain their original `/aptmp/...` values to preserve provenance
and checksum semantics and must not be edited in place. Use `scripts/render_portable_config.py` to
generate a local JSON/YAML copy, then pass it through the launcher's `*_CONFIG` environment
variable; complete examples are in `README.md` and `.env.example`.

Root dataset construction and post-split integrity auditing are launched by
`scripts/run_v0_dataset.py` and `scripts/run_postsplit_integrity_audit.py`, respectively, without a
scheduler. Checksum-bound launchers under `benchmarks/*/pbs/` are not ordinary runtime entrypoints;
they remain only as optional historical HPC replay evidence and must not be removed from or
rewritten inside their benchmark evidence bundles.

For GitHub packaging, source-level manifests were regenerated for the portable launchers,
documentation, and release allowlist above. This is not a recalculation of scientific results: the
frozen model, thresholds, configs, compact numerical evidence, and internal artifact checksums
remain unchanged; the identity of the original gds2 entry points remains in dated archive
provenance.

Schema-5 Amendment D exact-numeric replay still checks the historical Python/BLAS operator, where
`legacy_schema4_numerical_operator.venv_root` is a provenance contract rather than an ordinary
storage path. A different unattested environment fails closed; this does not affect reading or
validating the compact evidence in the repository. The production Test ledger also remains in a
fixed external administrator registry; a public checkout cannot obtain new Test authorization by
overriding a path.

## 12. Publishable scope and next-version gates

V0 may report the component-safe dataset, 14-model development selection, frozen all-6B tool,
schema 5 family-neighbour robustness, and internal homology comparisons explicitly labelled
Train-only. It may not report all-6B or V0.1 held-out Test performance, external PLM superiority
over classical tools, formal ultra-remote superiority, general unknown-virus detection, or
clinical/diagnostic use.

Before upgrading to V1, freeze:

1. an external lockbox independent of the current Train/Validation family, with distance labels not defined by a compared method;
2. sufficient strict `<20% identity` positive components (total≥100 and per fold≥20);
3. source-specific endpoints, 99.9% specificity/FPM, multiplicity, and power;
4. a one-time Test ledger and accuracy/cost acceptance rules for all-6B and V0.1;
5. permission to modify the released model and user-inference package only after the external gates pass.
