**English** | [简体中文](README.cn.md)

# DJR-MCP Finder

[![CI](https://github.com/Hongda-Zhao/DJR-MCP-Finder/actions/workflows/ci.yml/badge.svg)](https://github.com/Hongda-Zhao/DJR-MCP-Finder/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Release](https://img.shields.io/github/v/release/Hongda-Zhao/DJR-MCP-Finder?display_name=tag)](https://github.com/Hongda-Zhao/DJR-MCP-Finder/releases)

**Detect double-jelly-roll major capsid proteins from protein FASTA files with a frozen,
three-stage protein-language-model classifier.** DJR-MCP Finder is intended for virologists and
bioinformaticians who need an auditable first-pass screen for DJR proteins, viral
morphogenesis-associated DJRs, and two supported viral phyla.

> **Recommended release:** the frozen **model V0** in [`user-inference-v0/`](user-inference-v0/).
> It accepts protein FASTA and writes tabular predictions, run metadata, and checksums. It does not
> train or retune the model.

## From FASTA to an auditable result

```mermaid
flowchart LR
    A["Protein FASTA"] --> B["Pinned ESM-C 6B embeddings"]
    B --> H1{"H1: DJR?"}
    H1 -- "No" --> N["non_djr"]
    H1 -- "Yes" --> H2{"H2: VMA-associated?"}
    H2 -- "No" --> D["djr_non_vma"]
    H2 -- "Yes" --> H3{"H3: supported phylum?"}
    H3 --> P1["vma::Nucleocytoviricota"]
    H3 --> P2["vma::Preplasmiviricota"]
    H3 --> U["vma::unknown/other"]
```

`vma::unknown/other` is a reject option after a sequence passes H1 and H2; it is not a general
unknown-virus or out-of-distribution detector.

## Quick start: CPU-only checks

A laptop can install the formal V0 package, run its contract tests, validate FASTA, and inspect the
frozen bundle without downloading ESM-C or PyTorch:

```bash
git clone https://github.com/Hongda-Zhao/DJR-MCP-Finder.git
cd DJR-MCP-Finder/user-inference-v0

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

python -m pytest -q
djrmcp-predict validate-fasta examples/synthetic_example.faa
djrmcp-predict model-info
```

The commands assume a Linux or macOS shell; native Windows has not been validated. For a
non-editable install, replace `-e '.[dev]'` with `'.[dev]'`.

## Full V0 prediction: NVIDIA workstation

The validated full-inference path uses Linux x86_64, Docker, the NVIDIA Container Toolkit, and a
CUDA GPU with at least 24 GB memory recommended. Build and run from the formal V0 package:

```bash
cd /path/to/DJR-MCP-Finder/user-inference-v0
bash workstation/build.sh

bash workstation/run_user_fasta.sh \
  examples/synthetic_example.faa \
  run_output/sample \
  0
```

`0` is the physical GPU index. The first prediction downloads the pinned ESM-C 6B checkpoint;
later runs reuse the cache and support `DJRMCP_OFFLINE=1`. The measured V0 peak was about 13.05 GB
allocated, while CPU mode loads roughly 25 GB of float32 weights and is not a routine deployment
path.

## Output example

Each run creates `predictions.tsv`, `run_metadata.json`, and `CHECKSUMS.sha256`. This shortened,
illustrative view shows the decision path; the real TSV also records sequence metadata, raw scores,
all probabilities, warnings, and gate states.

| protein_id | H1 DJR probability | H2 VMA probability | H3 prediction | final_prediction |
| --- | ---: | ---: | --- | --- |
| candidate_001 | 0.997 | 0.981 | Nucleocytoviricota | `vma::Nucleocytoviricota` |
| cellular_djr_002 | 0.994 | 0.082 | not_reached | `djr_non_vma` |
| background_003 | 0.006 | 0.021 | not_reached | `non_djr` |

The numbers above demonstrate the output schema and are not benchmark results. See the
[`user-inference-v0` guide](user-inference-v0/README.md) for the complete input/output contract and
the [`Docker deployment guide`](user-inference-v0/workstation/README.md) for caches, offline runs,
devices, and host paths.

## Choose the right path

| Goal | Start here | Environment |
| --- | --- | --- |
| Validate FASTA or inspect the frozen model | [`user-inference-v0/`](user-inference-v0/) | Python 3.10+, CPU |
| Run formal model V0 predictions | [V0 workstation guide](user-inference-v0/workstation/README.md) | Linux x86_64, Docker, NVIDIA GPU |
| Evaluate the unreleased mixed-encoder candidate | [`user-inference-v0.1/`](user-inference-v0.1/) | Python 3.12+, two isolated model runtimes |
| Audit or reproduce the research workflow | [`WORKFLOW_V0.md`](WORKFLOW_V0.md) | Site archives, databases, software stack, and HPC resources |

V0.1 is post-freeze development evidence and does not replace formal model V0. The complete
research workflow cannot be reproduced from the compact checkout alone.

## Documentation

- [Formal V0 user guide](user-inference-v0/README.md)
- [Docker/NVIDIA deployment](user-inference-v0/workstation/README.md)
- [Frozen V0 model card](user-inference-v0/src/djrmcp_predict/assets/project-v0-esmc6b-r1/MODEL_CARD.md)
- [Complete workflow and evidence boundary](WORKFLOW_V0.md)
- [Concise scientific report](PROJECT_V0_FINAL_REPORT.md)
- [V0.1 development candidate](user-inference-v0.1/README.md)
- [Citation metadata](CITATION.cff)

## Scientific status and limitations

The formal release remains **all ESM-C 6B**. Schema 5, PLM-versus-classical, and ultra-remote
analyses are post-freeze Train/Validation evidence: none opens the protected Test split or changes
model V0. Current scores are calibrated under the development-data distribution, not
prevalence-adjusted probabilities for natural proteomes. Large-scale discovery still requires
independent false-positive assessment and structural/manual validation.

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
