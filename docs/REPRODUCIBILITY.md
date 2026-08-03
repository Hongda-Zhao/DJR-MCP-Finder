# Reproducibility levels and archive boundary

**English** | [简体中文](REPRODUCIBILITY.cn.md) | [日本語](REPRODUCIBILITY.ja.md)

[Documentation map](README.md) | [Repository README](../README.md) |
[Scientific evidence](SCIENTIFIC_EVIDENCE.md)

“Reproducible” means three different things in this project: verifying the public checkout,
repeating a user prediction with public model checkpoints, or replaying the research workflow with
frozen archives and portable Python entrypoints. The requirements are intentionally stated
separately; the original PBS launchers are historical replay evidence, not the public default.

## Scope at a glance

| Level | Public checkout alone? | What it reproduces | Additional requirements |
| --- | --- | --- | --- |
| A — Checkout verification | Yes | Metadata, documentation, tests, FASTA validation, bundle identity, and package builds | Python 3.12+ and declared dependencies |
| B — Public user inference | No | A real V0 or V0.1 prediction from a user FASTA | Pinned public checkpoint(s); validated/recommended workstation path: Linux, Docker, and a CUDA GPU |
| C — Archive-backed scientific replay | No | Dataset construction, embeddings, model selection, and internal benchmark workflows | Frozen private archives/databases, checksums, Python, and versioned tools such as MMseqs2; HPC only for optional historical launcher replay |
| Protected Test evaluation | No | Administrator-authorized preregistered Test run | Protected ledger and separate authorization; archives and HPC are not sufficient |

The compact GitHub repository does not redistribute all original databases, model checkpoints,
large embeddings, logs, TIFF files, or historical run outputs.

## Level A — Verify the public checkout

The following path checks the code and frozen package contracts without downloading either large
encoder or requiring a GPU:

```bash
cd /path/to/DJR-MCP-Finder
python3.12 -m venv .venv
source .venv/bin/activate

make setup
make metadata docs-check lint test smoke
```

`make smoke` runs FASTA validation and `model-info`; it is not a prediction. To include wheel/sdist
construction and every local CI-equivalent gate, run:

```bash
make check
```

The canonical target definitions are in the repository [`Makefile`](../Makefile). A passing Level A
verification establishes that the checkout and compact bundles are internally consistent; it does
not establish biological accuracy or external generalization.

## Level B — Repeat a public user prediction

User inference does not require the private research archive.

It also does not require PBS, `qsub`, or an HPC scheduler. PBS is not part of either public
prediction interface.

The validated and recommended workstation path is Linux + Docker + a CUDA GPU. Both packages also
expose explicit automatic/CPU device modes, but the high-memory CPU fallback is not covered by the
formal workstation validation and should not be treated as the reference reproducibility path.

- **Preferred experimental candidate:** follow the [Model V0.1 Candidate user guide](../user-inference-v0.1/README.md)
  and [fresh-clone workstation setup](../user-inference-v0.1/workstation/README.md#fresh-clone-setup).
  The first prediction downloads ESM-2; ESM-C is downloaded when at least one sequence reaches H3.
- **Released baseline:** follow the [Model V0 user guide](../user-inference-v0/README.md) and
  [V0 workstation setup](../user-inference-v0/workstation/README.md). Its first prediction downloads
  the pinned ESM-C checkpoint.

Both paths produce `predictions.tsv`, `run_metadata.json`, and `CHECKSUMS.sha256`. A later
network-disabled run is possible only after every checkpoint required by that input path has been
cached. Repeating user inference verifies a frozen model/runtime path; it does not replay the
training data, model selection, or benchmarks.

## Level C — Replay the archive-backed research workflow

Full replay requires resources that are not present in the public checkout:

- checksum-matching source databases and compact/full artifact archives;
- model embeddings and raw benchmark ledgers referenced by frozen configs and, where present,
  `FULL_ARTIFACT_POINTER.json` files;
- the recorded Python, CUDA, MMseqs2, and other versioned software environments;
- sufficient local or HPC compute for the chosen stage. PBS/HPC is required only when deliberately
  replaying an original checksum-bound benchmark launcher.

### Localize historical paths

Historical absolute paths in frozen configuration remain provenance. Generate a site-local copy
rather than editing the frozen input:

```bash
cd /path/to/DJR-MCP-Finder

export DJRMCP_PROJECT_ROOT="$(pwd -P)"
export DJRMCP_ARCHIVE_ROOT=/absolute/path/to/checksum-bound-archives
export DJRMCP_DATABASE_ROOT=/absolute/path/to/frozen-input-databases
export DJRMCP_SOFTWARE_ROOT=/absolute/path/to/versioned-HPC-software
export DJRMCP_VENV_ROOT=/absolute/path/to/project-python-environment

python3 scripts/render_portable_config.py \
  configs/v0_dataset.json \
  build/local-configs/v0_dataset.json
```

These variables are local resource locators, not download URLs or credentials. The renderer rewrites
declared path prefixes; it does not download files or prove that mapped resources exist. The mapped
inputs must already be present and match the frozen checksums.

### Run the portable Python research entrypoints

Dataset construction requires Python and MMseqs2, but not PBS or Environment Modules. The runner
refuses to overwrite an existing output directory, so use explicit paths that do not yet exist:

```bash
python3 scripts/run_v0_dataset.py \
  --config build/local-configs/v0_dataset.json \
  --work-dir build/replay/v0-interim \
  --output-dir build/replay/v0-processed

python3 scripts/run_postsplit_integrity_audit.py --help
```

The second command lists the explicit manifests, FASTA inputs, and output directories required by
the portable post-split audit. Both runners accept `--python` and `--mmseqs` overrides and otherwise
use local executables. Benchmark replay still requires archived embeddings and ledgers referenced
by frozen configs and, where present, `FULL_ARTIFACT_POINTER.json`. Checksum-bound
`benchmarks/*/pbs/` launchers are optional historical HPC replay evidence, not ordinary entrypoints;
they remain untouched so the frozen evidence bundles retain their identity.

## Frozen provenance and integrity

- Historical paths under `/aptmp/hongda/DJRMCP_Develope/` and recorded hosts are provenance or
  archive locators, not runtime requirements for ordinary user inference.
- Frozen model bundles verify their `CHECKSUMS.sha256` before loading classifier heads.
- User predictions include `CHECKSUMS.sha256` for outputs and run metadata.
- Compact benchmark and release evidence retain their owning checksum manifests.
- Model checkpoints are downloaded from pinned upstream identities and are not redistributed here.
- Checksums establish content identity, not authorship or secure transport.

Do not batch-replace historical paths inside frozen configs, validation records, reports, or
artifact pointers. In particular, `legacy_schema4_numerical_operator.venv_root` belongs to the exact
Amendment-D numerical replay contract. Changing a notice or model-card file inside a frozen bundle
requires refreshing that bundle's checksum manifest and rerunning `model-info`. Changing weights,
thresholds, routing, or encoders requires a new scientific model identity under
[`VERSIONING.md`](VERSIONING.md).

## Protected Test boundary

The repository contains a selected-only Test runner, but a public checkout or path override cannot
grant access. The production ledger is fixed in the external administrator registry and rejects
overrides; a run still requires registry permission plus authorization for the frozen inputs and
workflow. Possessing the archive, software stack, or HPC access does not by itself authorize a Test
run.

## Reproducibility entry points

- [Complete scientific workflow](research/WORKFLOW_V0.md)
- [Scientific evidence and claim boundary](SCIENTIFIC_EVIDENCE.md)
- [Formal V0 reference environment](../user-inference-v0/environment/REFERENCE_ENVIRONMENT.md)
- [Candidate reference environment](../user-inference-v0.1/environment/REFERENCE_ENVIRONMENT.md)
- [Formal V0 workstation validation](../user-inference-v0/workstation/VALIDATION.json)
- [Candidate workstation validation](../user-inference-v0.1/workstation/VALIDATION.json)
- [Repository release manifest](../release-manifest.json)
