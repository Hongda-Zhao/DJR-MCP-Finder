**English** | [简体中文](README.cn.md)

# DJR-MCP Finder — project V0

DJR-MCP Finder is a three-stage protein classification tool. The current formal release remains
**all ESM-C 6B**. The subsequent schema 5, PLM-versus-classical, and ultra-remote analyses are
post-freeze development evidence from Train/Validation; none opens the protected Test split or
changes V0 or its user inference package.

```text
data-curation V3 -> 11,060 representatives -> component-safe split
 -> 14-model Train-CV + Validation gates -> frozen all ESM-C 6B (V0)
                                            |
                                            +-> schema 5 family robustness
                                            +-> internal homology benchmarks
                                            +-> unreleased V0.1 candidate
```

## Frozen V0

- Data: 560 VMA-DJRs, 500 cellular DJRs, 5,000 HardNeg proteins, and 5,000 background proteins.
- Split: Train/Validation/Test = **6,634 / 2,212 / 2,214**. Exact-sequence, source,
  component, and MMseqs2 relationships were merged before splitting; residual qualifying
  cross-split edges = **0**.
- Model selection: 14 representation models shared a Train-only five-fold component map. The
  composite score was `S = 0.60·H1 AP + 0.30·H2 AP + 0.10·H3 macro-F1`; after the three-head
  Validation gates and paired one-SE rule, ESM-C 6B was selected (`S=0.997145`).

| Head | Task | Classifier | Temperature | Threshold |
| --- | --- | ---: | ---: | ---: |
| H1 | DJR / non-DJR | alpha=`1e-5` | 1168.1537298613255 | 0.9687754839244975 |
| H2 | VMA-DJR / cellular DJR | C=`0.01` | 0.8241381150130028 | 0.9639353725025007 |
| H3 | two known phyla + reject | C=`10` | 4.2474179687096845 | 0.7126488980564439 |

H2 runs only after H1 classifies a protein as DJR; H3 runs only after H2 classifies it as
VMA-DJR. H3 `unknown/other` rejects a forced assignment to Nucleocytoviricota or
Preplasmiviricota; it is not a general unknown-virus detector.

## Current evidence hierarchy

| Evidence | Status | What it can answer | What it cannot answer |
| --- | --- | --- | --- |
| 14-model benchmark | frozen development selection | which all-one-encoder system was selected as V0 | external generalization |
| schema 5 Amendment D | 20/20 gates PASS | robustness of eight models/nine cascades on family members from the same four sources | independent Test performance or feedback into model selection |
| PLM vs classical V0 | internal cross-fit PASS | differences between PLM retrieval and classical search on Train components | external superiority |
| ultra-remote V0/V0.1 | PASS; formal claim blocked | V0.1 behavior on internal holdouts and low-coverage stress strata | a formal `<20% identity` conclusion |
| prospective/external Test | **not run** | — | release-grade generalization of V0/V0.1 |

### Schema 5: a mixed candidate worth external confirmation

The nine mixed candidates were preregistered and ranked only by existing Train-CV results; the
four-source robustness analysis did not rerank them. The current nominee is **H1/H2 ESM-2 3B +
H3 ESM-C 6B** (`S=0.997645`), with `0/4` Holm-corrected source warnings relative to all-6B. This
does not establish four-source non-inferiority or equivalence:

| System | Viral | Cellular | Background | Matched HardNeg | Always-on / worst-case s·seq⁻¹ |
| --- | ---: | ---: | ---: | ---: | ---: |
| frozen all ESM-C 6B | 0.9536 | 0.8791 | 0.9948 | 0.9978 | 0.059531 / 0.059531 |
| mixed nominee | 0.9537 | 1.0000 | 0.9985 | 0.9998 | 0.023524 / 0.083055 |

The nominee recovers 52/69 viral strict clusters, fewer than the 55/69 recovered by all-6B; it
also requires a second encoder for sequences that reach H3. Its formal status is only
`recommended_for_external_confirmation`, with `released_v0_change_permitted=0`.

### PLM versus classical: internal results do not support higher ESM-C cosine sensitivity

The benchmark uses cyclic 3-fit/1-calibration/1-evaluation component cross-fitting on the 6,634
Train records. The values below are fold-macro component AP / sensitivity at a threshold
calibrated to a 99.5% specificity target:

| Method | H1 | H2 |
| --- | ---: | ---: |
| ESM-C 6B cosine | 0.8719 / 0.7340 | 0.9861 / 0.9306 |
| BLASTP | 0.9392 / 0.8692 | 0.9829 / 0.9443 |
| DIAMOND ultra | 0.9406 / 0.9025 | 0.9806 / 0.9317 |
| MMseqs2 | 0.9319 / 0.8805 | 0.9751 / 0.9119 |
| component-HMMER | 0.9542 / 0.9016 | 0.9911 / 0.9569 |
| ESM-2 650M cosine, contextual | 0.9515 / 0.8954 | 0.9965 / 0.9977 |

For H1, the paired delta confidence intervals for ESM-C cosine versus all four classical anchors
are negative. For H2 and the end-to-end endpoint, the intervals cross zero and are limited by
low-FPR resolution for singleton components. This is a representation-retrieval comparison, not
evidence about the external performance of the frozen supervised V0 tool. The validator
independently recomputes point estimates but did not independently rerun all 10,000 bootstrap
replicates.

### Ultra-remote: V0.1 shows a signal, but the formal conclusion is blocked

V0.1 changes only the H1/H2 encoder to ESM-2 3B; H3 remains ESM-C 6B. On the Train-only component
holdout, H1 encoder sensitivity improves by `+0.197` relative to V0; the BLAST-defined `qcov<80%`
stress stratum improves by `+0.260` (95% CI 0.206–0.317). However, the H1 supervised detector
improves by only `+0.017`, while the H2 and end-to-end detector changes are zero. Every paired
system misses the actual 99.5% specificity target in at least one fold. The strict
`qcov≥80%, identity<20%` stratum contains only one independent positive component, so the status
is `PASS_WITH_FORMAL_ULTRA_REMOTE_BLOCKED_BY_SAMPLE_SIZE`.

## Current release boundary

Historical Test results apply only to ESM-2 650M. All ESM-C 6B, the schema 5 nominee, and V0.1
remain `not_evaluated`. The current release can therefore support claims about component-safe
dataset construction, development benchmarks, the frozen V0 tool, and clearly labelled internal
stress tests. It cannot support claims that V0.1 has replaced V0, that PLMs outperform classical
methods on external data, or that the tool can generally detect unknown viruses.

## Authoritative entry points

- `WORKFLOW_V0.md`: the single complete workflow and evidence-boundary document.
- `PROJECT_V0_FINAL_REPORT.md`: the current concise scientific report.
- `results/validation_family_robustness_v0_schema5_mixed_heads/`: formal compact schema 5 results.
- `results/figures/project_v0/validation_family_robustness_v0_schema5_head_focus/`: read-only
  publication-figure companion.
- `benchmarks/plm_vs_classical_v0/`: compact internal PLM/classical benchmark.
- `benchmarks/ultra_remote_v0_v01/`: compact V0/V0.1 development audit.
- [`user-inference-v0/`](user-inference-v0/): formal frozen all-ESM-C-6B user FASTA inference package.
- [`user-inference-v0.1/`](user-inference-v0.1/): mixed-encoder V0.1 candidate inference package;
  it does not replace V0.

## Running the research workflow from another location

The GitHub checkout may live at any path. Active shell/PBS entry points that are not independently
frozen by a scientific checksum first read `DJRMCP_PROJECT_ROOT`; otherwise they locate the
repository from the script location (and may also use `PBS_O_WORKDIR` under PBS). A local Python
environment can be selected with `DJRMCP_VENV_ROOT`. Example variables are provided in
[`.env.example`](.env.example).

The historical absolute paths retained in `configs/`, benchmark `config/`,
`FULL_ARTIFACT_POINTER.json`, validation records, and reports are frozen provenance or archive
locators from the original gds2 system. They must not be batch-replaced. To rerun the workflow,
first generate a site-local copy outside the scientific-checksum scope:

```bash
export DJRMCP_PROJECT_ROOT="$(pwd -P)"
export DJRMCP_ARCHIVE_ROOT=/absolute/path/to/checksum-bound-archives
export DJRMCP_DATABASE_ROOT=/absolute/path/to/frozen-input-databases
export DJRMCP_SOFTWARE_ROOT=/absolute/path/to/versioned-HPC-software
export DJRMCP_VENV_ROOT=/absolute/path/to/project-python-environment

python scripts/render_portable_config.py \
  configs/v0_dataset.json \
  build/local-configs/v0_dataset.json

DJRMCP_DATASET_CONFIG="$PWD/build/local-configs/v0_dataset.json" \
  bash scripts/build_v0_dataset.sh
```

The same tool supports YAML and the two compact benchmark JSON configurations; `--map OLD=NEW`
adds finer prefix mappings. It fails closed by default: if the generated configuration still
contains an unmapped historical operational root, no output is written, and the input is never
overwritten. Each rerun should still restore the complete archive described by its README and
place generated site configuration outside checksum scope rather than editing the frozen config
in place. Schema 5 Amendment D deliberately preserves
`legacy_schema4_numerical_operator.venv_root` because it is part of the exact numerical replay
contract. A full Amendment-D replay still requires the original validated environment to be
mounted; that provenance field must not be disguised as a local path. The production Test ledger
is likewise fixed in the original administrator registry, and a public checkout has no override
entry point.

This portable GitHub package parameterizes documentation and active entry points and strengthens
checksum verification before model deserialization. The top-level, schema 5 source, and two
compact benchmark source-bundle checksum manifests were refreshed accordingly. Model heads,
release parameters, frozen configurations, numerical results, and their internal artifact
checksums are unchanged; the original gds2 version remains preserved in dated archives and their
provenance records.

Full run outputs, logs, databases, TIFF files, old figures, and development-candidate code remain
in dated checksum-bound archives under the historical `/aptmp/hongda/DJRMCP_Develope/` location.
That path is a provenance record, not a requirement for a GitHub checkout. The active repository
contains only the compact core needed for interpretation and audit.
