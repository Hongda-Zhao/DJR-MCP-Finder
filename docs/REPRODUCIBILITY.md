# Research reproducibility and archive boundary

The GitHub repository is a compact, portable audit and inference checkout. It does not redistribute
all original databases, model checkpoints, large embeddings, logs, TIFF files, or historical run
outputs. Complete replay therefore requires the checksum-bound archives and environments described
by [`WORKFLOW_V0.md`](research/WORKFLOW_V0.md).

## Portable checkout

Active shell and PBS entry points that are not independently frozen by a scientific checksum read
`DJRMCP_PROJECT_ROOT`; otherwise they locate the repository from the script location and may use
`PBS_O_WORKDIR` under PBS. `DJRMCP_VENV_ROOT` selects a local Python environment. Example variables
are in [`.env.example`](../.env.example).

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

The renderer also supports YAML, compact benchmark JSON configurations, and explicit
`--map OLD=NEW` prefix mappings. It fails closed if an unmapped historical operational root remains,
does not overwrite the input, and writes site-local configuration outside scientific checksum scope.

## Frozen provenance

Historical absolute paths in `configs/`, benchmark configuration, validation records, reports, and
`FULL_ARTIFACT_POINTER.json` are provenance or archive locators from the original system. They must
not be batch-replaced. In particular,
`legacy_schema4_numerical_operator.venv_root` is part of the exact Amendment-D numerical replay
contract. A full replay still requires the validated environment to be mounted; changing the string
would disguise provenance rather than improve portability.

The production Test ledger is fixed in the original administrator registry and has no public
checkout override. No engineering command in this repository opens the protected Test split.

## Integrity model

- Frozen model bundles verify their `CHECKSUMS.sha256` before loading classifier heads.
- User outputs include `CHECKSUMS.sha256` for predictions and metadata.
- Compact benchmark and release evidence retains its owning checksum manifest.
- Model checkpoints are downloaded from pinned upstream identities and are not redistributed here.
- Checksums establish content identity, not authorship or secure transport.

Changing a notice or model-card file inside a frozen bundle requires refreshing that bundle's own
checksum manifest and rerunning `model-info`. Changing weights, thresholds, routing, or encoders
requires a new scientific model identity under [`VERSIONING.md`](VERSIONING.md).

## What can be reproduced locally

| Activity | Compact checkout only | Additional requirements |
| --- | --- | --- |
| Unit and contract tests | Yes | Python dependencies |
| FASTA validation and bundle inspection | Yes | Formal or candidate package environment |
| Formal V0 inference | No | Pinned ESM-C checkpoint and compatible GPU/runtime |
| V0.1 candidate inference | No | Isolated ESM-2 and ESM-C runtimes plus checkpoints |
| Full data reconstruction and benchmark replay | No | Frozen archives, databases, software stack, and HPC resources |
| Protected Test evaluation | No | Administrator-controlled ledger and preregistered authorization |

## Historical locations

Paths under `/aptmp/hongda/DJRMCP_Develope/` and other recorded hosts remain historical validation
or archive locations, not runtime requirements for a GitHub checkout. New local runs should use the
portable environment variables and rendered configuration above.

## Reproducibility entry points

- [Complete scientific workflow](research/WORKFLOW_V0.md)
- [Formal V0 reference environment](../user-inference-v0/environment/REFERENCE_ENVIRONMENT.md)
- [Candidate reference environment](../user-inference-v0.1/environment/REFERENCE_ENVIRONMENT.md)
- [Formal V0 workstation validation](../user-inference-v0/workstation/VALIDATION.json)
- [Candidate workstation validation](../user-inference-v0.1/workstation/VALIDATION.json)
- [Repository release manifest](../release-manifest.json)
