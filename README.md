**English** | [简体中文](docs/repository/README.cn.md) | [日本語](docs/repository/README.ja.md)

[![CI](https://github.com/Hongda-Zhao/DJR-MCP-Finder/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Hongda-Zhao/DJR-MCP-Finder/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Hongda-Zhao/DJR-MCP-Finder?display_name=tag&sort=semver&label=release&color=2ea44f)](https://github.com/Hongda-Zhao/DJR-MCP-Finder/releases/tag/v0.1)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

# DJR-MCP Finder

DJR-MCP Finder screens protein FASTA files for double-jelly-roll major capsid protein (DJR-MCP) candidates. It reports scores and a final label for each protein, with phylum assignments to Nucleocytoviricota or Preplasmiviricota where supported.

- [Model V0.1 Candidate](user-inference-v0.1/README.md) is the preferred experimental candidate for exploratory screening. It uses ESM-2 3B for DJR/MCP screening and the frozen V0 ESM-C 6B head for phylum classification.
- [Model V0](user-inference-v0/README.md) is the released, frozen baseline. It uses ESM-C 6B throughout and remains supported.

Both versions still await independent external validation.

## Prediction workflow

![DJR-MCP Finder prediction workflow](docs/assets/readme/readme_workflow.svg)

The three stages identify DJR candidates (H1), distinguish MCPs from other DJR proteins (H2), and assign a supported viral phylum or return `unknown/other` (H3). See the user guides above for each version's computation path.

## Quick start

Recommended environment: Linux, Docker, NVIDIA Container Toolkit, and a CUDA GPU with at least 24 GB of memory and BF16 support. Ordinary FASTA prediction does not require an HPC scheduler.

```bash
git clone https://github.com/Hongda-Zhao/DJR-MCP-Finder.git
cd DJR-MCP-Finder/user-inference-v0
bash workstation/build.sh

cd ../user-inference-v0.1
DJRMCP_EXPECTED_BASE_IMAGE_ID='' bash workstation/build.sh

bash workstation/run_user_fasta.sh \
  /absolute/path/to/proteins.faa \
  run_output/my_sample \
  0
```

Build V0 first: V0.1 uses its Docker image as a base. The empty `DJRMCP_EXPECTED_BASE_IMAGE_ID` skips the historical image-ID check after a local rebuild; version, environment, and checksum checks remain active.

The first prediction downloads the pinned model checkpoints.

## Output

Results are saved in:

```text
run_output/my_sample/
├── predictions.tsv
├── run_metadata.json
└── CHECKSUMS.sha256
```

`predictions.tsv` records each protein's scores, stage decisions, and final label. Illustrative V0.1 rows (selected columns):

| protein_id | head1_djr_probability | head2_mcp_probability | head3_prediction | final_prediction |
| --- | ---: | ---: | --- | --- |
| candidate_001 | 0.997 | 0.981 | Nucleocytoviricota | `mcp::Nucleocytoviricota` |
| cellular_djr_002 | 0.994 | 0.082 | not_reached | `djr_non_mcp` |
| background_003 | 0.006 | NA | not_reached | `non_djr` |

The five labels are `non_djr`, `djr_non_mcp`, `mcp::Nucleocytoviricota`, `mcp::Preplasmiviricota`, and `mcp::unknown/other`. The last means that a sequence passed H1/H2 but could not be assigned reliably to either supported phylum; it does not establish a new or unknown virus.

These are screening results and need structural or manual follow-up. Scores are not adjusted for prevalence in natural samples, and large screens need an independent assessment of false positives.

## Model evaluation

The development dataset contains 11,060 proteins after removal of exact duplicate sequences, split into Train (6,634), Validation (2,212), and Test (2,214). The results below use only Train, with the same five folds for both models and no component shared across folds. Values are mean ± standard error.

| Train-only five-fold CV | Model V0 | Model V0.1 Candidate |
| --- | ---: | ---: |
| H1 AP | `0.9985 ± 0.0003` | `0.9993 ± 0.0004` |
| H2 AP | `1.0000 ± 0.0000` | `1.0000 ± 0.0000` |
| H3 known-phylum macro-F1 | `0.9806 ± 0.0095` | `0.9806 ± 0.0095` |
| Composite score `S` | `0.9971 ± 0.0009` | `0.9976 ± 0.0010` |

`S = 0.60 × H1 AP + 0.30 × H2 AP + 0.10 × H3 macro-F1`. V0.1 has a slightly higher mean H1 AP; H2 AP is equal, and H3 reuses the same model. These development results guided candidate selection and do not establish a statistically significant advantage or external performance.

Data composition, the 14-encoder comparison, and further evaluation are in the [scientific evidence](docs/SCIENTIFIC_EVIDENCE.md) documentation.

## Documentation

- [User guides](user-inference-v0.1/README.md) for Model V0.1 Candidate and [Model V0](user-inference-v0/README.md)
- [Reproducibility](docs/REPRODUCIBILITY.md): released data, models, and research workflows
- [Code architecture](docs/ARCHITECTURE.md) and [full documentation index](docs/README.md)

## Citation and license

If you use DJR-MCP Finder in research, cite [`CITATION.cff`](CITATION.cff) and report the model version used.

Project-authored code and documentation are available under the [MIT License](LICENSE).
