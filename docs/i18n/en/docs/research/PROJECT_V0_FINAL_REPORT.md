<!-- i18n-mirror: non-authoritative translation; source=docs/research/PROJECT_V0_FINAL_REPORT.md -->

> **Translation note:** This translation is for reading only; the frozen Chinese source is authoritative.

# DJR-MCP Finder project V0: final concise report

## One-sentence conclusion

Project V0 used data-curation V3 to construct 11,060 representative proteins and froze **all ESM-C
6B** after a component-safe split and a 14-model Train/Validation development process. Subsequent
analysis found that ESM-2 3B produced a stronger internal candidate signal for H1/H2, but the mixed
system, PLM-vs-classical, and ultra-remote results are not an external Test and are not sufficient
to replace V0.

## 1. Frozen primary release

| Item | Frozen value |
| --- | --- |
| Data | 560 VMA-DJR + 500 cellular DJR + 5,000 HardNeg + 5,000 background |
| split | Train 6,634 / Validation 2,212 / Test 2,214 |
| Leakage control | exact/source/component/MMseqs2 relations merged; residual qualifying cross-split edge=0 |
| benchmark | 14 models; shared Train-only 5-fold component map |
| Selection rule | three-Head Validation gate + composite score + paired one-SE |
| released model | all ESM-C 6B, `S=0.997145` |

| Head | classifier | temperature | threshold |
| --- | ---: | ---: | ---: |
| H1: DJR / non-DJR | alpha=`1e-5` | 1168.1537298613255 | 0.9687754839244975 |
| H2: VMA / cellular DJR | C=`0.01` | 0.8241381150130028 | 0.9639353725025007 |
| H3: two known phyla + reject | C=`10` | 4.2474179687096845 | 0.7126488980564439 |

H3 `unknown/other` rejects a forced classification; it does not discover arbitrary unknown viruses.
The historical Test was used only for ESM-2 650M; the Test status of all ESM-C 6B is
`not_evaluated`.

## 2. Schema 5 mixed-head conclusion

Schema 5 compares 8 homogeneous systems on the same matched Validation-family cohort. Before this
round of results was viewed, the mixed search was limited to:

```text
H1=H2 in {ESM-2 650M, ESM-2 3B, ESM-C 6B}
H3    in {ESM-C 300M, ESM-C 600M, ESM-C 6B}
```

Candidates are ranked only by the existing Train-CV `S`; four-source robustness is not pooled and
does not participate in reranking, but produces only Holm-corrected source warnings. The nominee is
**H1/H2 ESM-2 3B + H3 ESM-C 6B**:

| system | Train-CV `S` | always-on s·seq⁻¹ | worst-case s·seq⁻¹ |
| --- | ---: | ---: | ---: |
| mixed nominee | **0.997645** | **0.023524** | 0.083055 |
| frozen all ESM-C 6B | 0.997145 | 0.059531 | **0.059531** |

| source | nominee expected path (95% CI) | strict clusters | all-6B expected path |
| --- | ---: | ---: | ---: |
| viral | 0.9537 (0.9131–0.9872) | 52/69 | 0.9536 |
| cellular | 1.0000 (1.0000–1.0000) | 43/43 | 0.8791 |
| background | 0.9985 (0.9963–1.0000) | 997/1,000 | 0.9948 |
| matched HardNeg | 0.9998 (0.9995–1.0000) | 381/382 | 0.9978 |

There are `0/4` warnings relative to all-6B, but this is not proof of four-source
non-inferiority/equivalence. The nominee's viral strict clusters are below the all-6B value of
55/69, and the H3 worst case requires running a second encoder. Schema 5 independent validation is
20/20 gates PASS; Test=0; training, recalibration, threshold adjustment, and release-feedback
operations are all 0. Its formal status is `recommended_for_external_confirmation`, not released
V0.1.

## 3. PLM and classical homology retrieval: internal cross-fit

The completed `plm_vs_classical_v0` uses 6,634 Train records and the existing component folds,
cyclically performing 3 folds fit/reference + 1 fold calibration + 1 fold evaluation. Both
Validation and Test prediction rows are 0.

The controlled retrieval track gives all methods the same fold-specific positive references. The
table below reports fold-macro component AP / sensitivity at calibration-target 99.5%
source-balanced specificity:

| method | H1 | H2 | VMA end-to-end |
| --- | ---: | ---: | ---: |
| ESM-C 6B cosine | 0.8719 / 0.7340 | 0.9861 / 0.9306 | 0.9528 / 0.9301 |
| BLASTP | 0.9392 / 0.8692 | 0.9829 / 0.9443 | 0.9544 / 0.9401 |
| DIAMOND ultra | 0.9406 / 0.9025 | 0.9806 / 0.9317 | 0.9497 / 0.9317 |
| MMseqs2 | 0.9319 / 0.8805 | 0.9751 / 0.9119 | 0.9317 / 0.9078 |
| component-HMMER | 0.9542 / 0.9016 | 0.9911 / 0.9569 | 0.9660 / 0.9569 |
| ESM-2 650M cosine, contextual | 0.9515 / 0.8954 | 0.9965 / 0.9977 | 0.9906 / 0.9859 |

For ESM-C cosine versus the four classical anchors, every H1 AP and sensitivity delta CI is
negative. The internal results do not support the claim that “ESM-C cosine retrieval is more
sensitive.” The preregistered delta CIs for H2 and end-to-end all cross 0, so no superiority can be
established.

This conclusion has four boundaries:

1. It compares representation retrieval, not the external performance of the frozen supervised V0 tool;
2. the 62 cellular negatives in fold 3 belong to only one component, so the H2/end-to-end low-FPR CI is conditional and resolution-limited;
3. 99.9% specificity is only a resolution-limited secondary endpoint, and FP-per-million is not estimable;
4. the validator independently recalculated point estimates, but `bootstrap_recomputed=false` and the 10,000 bootstrap replicates were not independently rerun.

Numerical benchmark validation=PASS. The original figure bundle was incomplete because 3
source-data TSVs were omitted from the active copy; these tables were reconstructed deterministically
from the frozen results, verified individually against the original `figures/CHECKSUMS.sha256`, and
then included in the compact release.

## 4. V0/V0.1 ultra-remote development audit

The V0.1 candidate changes only the H1/H2 encoder from ESM-C 6B to ESM-2 3B; H3 remains ESM-C 6B.
This audit reuses the same Train-only cyclic component cross-fit and does not open Validation/Test.

| comparison | all component holdout | BLAST-defined `qcov<80%` | `qcov≥80%, 20–30% identity` |
| --- | ---: | ---: | ---: |
| H1 encoder Δ sensitivity | +0.197 | +0.260 (0.206–0.317) | +0.046 (0.013–0.086) |
| H1 supervised detector Δ | +0.017 | +0.028 (0.011–0.049) | 0.000 |
| H2 encoder Δ | +0.049 | +0.062 (0.020–0.112) | +0.024 (0.001–0.057) |
| H2 supervised detector Δ | 0.000 | 0.000 | 0.000 |

The encoder-level signal is markedly stronger than the operational-detector gain. More importantly,
every paired system misses the actual 99.5% specificity in at least one fold, so these are not
matched-specificity improvements. The minimum-fold specificity of the ESM-2 3B H2 detector is only
0.5426, indicating unstable threshold transfer. The strict `qcov≥80%, identity<20%` stratum has only
one independent positive component and no CI, so it cannot support formal ultra-remote inference.

The final status is `PASS_WITH_FORMAL_ULTRA_REMOTE_BLOCKED_BY_SAMPLE_SIZE`: the process and integrity
checks pass, but the scientific-claim gate does not. BLAST-defined distance strata also introduce
method-conditioned bias and cannot support a claim that the PLM outperforms BLAST.

## 5. H3, HardNeg, and scope

The nominee's H3 and V0 both use ESM-C 6B: Nucleocytoviricota F1=0.9792 and Preplasmiviricota
F1=1.0000. Produgelaviricota reject=6/7 (2 parents), and literature-unclassified=1/1 (1 parent).
The two groups can only be reported separately as descriptive results and cannot be pooled as
general unknown-virus detection.

HardNeg source reconstruction has status `FULL_OPERATIONAL_RECOVERY_PASS`; the fourth robustness
source now consists of 3,478 matched members from selected clusters, not the older 5,878
pass-but-unselected representatives.

## 6. Evidence boundary and release decision

| claim | current status |
| --- | --- |
| component-safe data construction and 14-model development selection | Reportable |
| frozen all ESM-C 6B tool | Reportable as a V0 research release |
| schema 5 family-neighbour robustness | Reportable as post-freeze auxiliary evidence |
| PLM/classical Train-only cross-fit | Reportable as an internal development comparison |
| V0.1 low-coverage signal | Reportable as descriptive development evidence |
| all-6B or V0.1 held-out Test performance | **Not reportable; not evaluated** |
| PLM external superiority over classical methods or formal ultra-remote superiority | **Not reportable** |
| clinical/diagnostic or universal unknown-virus detection | **Not reportable** |

V0 can serve as a reproducible research release, a candidate-prioritization tool, and a foundation
for a paper's methods. Before a model upgrade, preregister a source-component-disjoint external
lockbox, method-independent distance labels, sufficient `<20% identity` components, primary
endpoints, specificity/cost gates, and a one-time Test ledger.

## 7. Current authoritative materials

- Complete workflow: `WORKFLOW_V0.md`
- Schema 5 results: `results/validation_family_robustness_v0_schema5_mixed_heads/`
- Publication companion: `results/figures/project_v0/validation_family_robustness_v0_schema5_head_focus/`
- Internal homology benchmark: `benchmarks/plm_vs_classical_v0/`
- V0/V0.1 development audit: `benchmarks/ultra_remote_v0_v01/`
- Frozen user inference: `/aptmp/hongda/DJRMCP_Develope/user-inference-V0`

Complete predictions, bootstrap outputs, search databases, logs, TIFF files, and V0.1 development
code remain in checksum-bound archives under `/aptmp/hongda/DJRMCP_Develope/`; the active directory
retains only the compact evidence core.
