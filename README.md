**English** | [简体中文](README.cn.md)

# DJR-MCP Finder

[![CI](https://github.com/Hongda-Zhao/DJR-MCP-Finder/actions/workflows/ci.yml/badge.svg)](https://github.com/Hongda-Zhao/DJR-MCP-Finder/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Release](https://img.shields.io/github/v/release/Hongda-Zhao/DJR-MCP-Finder?display_name=tag)](https://github.com/Hongda-Zhao/DJR-MCP-Finder/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Detect double-jelly-roll major capsid proteins from protein FASTA files with a frozen,
three-stage protein-language-model classifier.** DJR-MCP Finder gives virologists and
bioinformaticians an auditable first-pass screen for DJR proteins, viral
morphogenesis-associated DJRs, and two supported viral phyla.

> **Recommended model:** [`model-v0`](user-inference-v0/) — the released all-ESM-C-6B bundle.
> It accepts protein FASTA and writes predictions, run metadata, and checksums without training or
> retuning the model.

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

`vma::unknown/other` is a reject option after H1 and H2; it is not a general unknown-virus or
out-of-distribution detector.

## Quick start: CPU-only checks

These commands install the formal V0 inference package, run its contract tests, validate a FASTA,
and inspect the frozen bundle without downloading ESM-C or PyTorch:

```bash
git clone https://github.com/Hongda-Zhao/DJR-MCP-Finder.git
cd DJR-MCP-Finder/user-inference-v0

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

python -m pytest -q
djrmcp-predict validate-fasta examples/synthetic_example.faa
djrmcp-predict model-info
```

Native Windows has not been validated. Full inference uses the
[Docker/NVIDIA workstation path](user-inference-v0/workstation/README.md), with a CUDA GPU of at
least 24 GB recommended:

```bash
cd /path/to/DJR-MCP-Finder/user-inference-v0
bash workstation/build.sh
bash workstation/run_user_fasta.sh examples/synthetic_example.faa run_output/sample 0
```

## Output example

Each run creates `predictions.tsv`, `run_metadata.json`, and `CHECKSUMS.sha256`. The rows below are
illustrative schema examples, not benchmark results.

| protein_id | H1 DJR probability | H2 VMA probability | H3 prediction | final_prediction |
| --- | ---: | ---: | --- | --- |
| candidate_001 | 0.997 | 0.981 | Nucleocytoviricota | `vma::Nucleocytoviricota` |
| cellular_djr_002 | 0.994 | 0.082 | not_reached | `djr_non_vma` |
| background_003 | 0.006 | 0.021 | not_reached | `non_djr` |

See the [formal V0 user guide](user-inference-v0/README.md) for the complete input/output contract.

## Releases, models, and packages

These identifiers describe different things and are intentionally not interchangeable:

| Layer | Current identifier | Meaning |
| --- | --- | --- |
| Repository release | [`v0.1.0`](https://github.com/Hongda-Zhao/DJR-MCP-Finder/releases/tag/v0.1.0) | SemVer for the GitHub software release |
| Released scientific model | `model-v0` | Frozen all-ESM-C-6B model in [`user-inference-v0/`](user-inference-v0/) |
| Development candidate | `model-v0.1-candidate` | Mixed-encoder candidate in [`user-inference-v0.1/`](user-inference-v0.1/); does not replace V0 |
| Bundle revision | `model-v0-esmc6b-r1` | Immutable model contents plus export revision |
| Python distribution | for example `djrmcp-user-inference==0.1.0` | PEP 440 version of one installable package |

The complete naming contract and machine-readable mapping are in
[`docs/VERSIONING.md`](docs/VERSIONING.md) and [`release-manifest.json`](release-manifest.json).

## Choose the right path

| Goal | Start here | Environment |
| --- | --- | --- |
| Validate FASTA or inspect the released model | [`user-inference-v0/`](user-inference-v0/) | Python 3.10+, CPU |
| Run formal `model-v0` predictions | [V0 workstation guide](user-inference-v0/workstation/README.md) | Linux x86_64, Docker, NVIDIA GPU |
| Evaluate the unreleased candidate | [`user-inference-v0.1/`](user-inference-v0.1/) | Python 3.12+, two isolated model runtimes |
| Audit the research workflow | [Scientific evidence](docs/SCIENTIFIC_EVIDENCE.md) | Evidence map, metrics, and claim boundary |
| Reproduce from site archives | [Reproducibility guide](docs/REPRODUCIBILITY.md) | Frozen inputs, software, and HPC resources |
| Contribute code or documentation | [`CONTRIBUTING.md`](CONTRIBUTING.md) | Python 3.12+ contributor environment |

## Contributor commands

The root `Makefile` is the canonical local interface:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
make setup
make check
```

Use `make help` to see focused `setup`, `test`, `lint`, `smoke`, `build`, and package-validation
targets. CI calls the same target-level contracts.

## Documentation

- [Documentation map](docs/README.md)
- [Architecture and command inventory](docs/ARCHITECTURE.md)
- [Scientific evidence and limitations](docs/SCIENTIFIC_EVIDENCE.md)
- [Research reproducibility](docs/REPRODUCIBILITY.md)
- [Version and release naming](docs/VERSIONING.md)
- [Citation metadata](CITATION.cff)
- [Changelog](CHANGELOG.md)

## Scientific and licensing boundary

The released ESM-C 6B model has no new prospective external Test. Scores are calibrated under the
development-data distribution, not as prevalence-adjusted probabilities for natural proteomes.
Large-scale discovery requires independent false-positive assessment and structural/manual
validation. See [Scientific evidence](docs/SCIENTIFIC_EVIDENCE.md) before interpreting results.

Project-authored material is released under the [MIT License](LICENSE). External checkpoints,
software, datasets, database content, and trademarks retain their own terms and are not relicensed.
See [third-party notices](THIRD_PARTY_NOTICES.md) and the [security policy](SECURITY.md).
