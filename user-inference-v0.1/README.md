**English** | [简体中文](README.cn.md)

# DJR-MCP Finder — User Inference for Model V0.1 Candidate

This directory accepts user-supplied protein FASTA files and returns predictions from the frozen
V0.1 mixed-encoder candidate:

```text
FASTA -> ESM-2 3B -> H1 -> H2 -> [passing sequences only] ESM-C 6B -> H3
```

This is an engineering candidate with status `recommended_for_external_confirmation`. It is not a
formal V0.1 confirmed by an independent external Test and does not replace the released V0.

The workstation package completed online and fully network-disabled reruns on 12 proteins on
2026-07-29. Both runs matched the frozen golden standard with zero label mismatches and zero
probability delta. Original host, image, and GPU details are retained as historical validation
evidence in `workstation/VALIDATION.json`; they are not runtime requirements. V0.1 is the scientific
candidate version, while Python wheel version `0.2.1` identifies its engineering package revision.

| Layer | Identifier |
| --- | --- |
| Scientific model | `model-v0.1-candidate` (not released as a formal model) |
| Frozen bundle revision | `model-v0.1-mixed-r1` |
| Python distribution | `djrmcp-user-inference-v01==0.2.1` |
| CLI | `djrmcp-predict-v01` |

The full `candidate` qualifier is required. See the repository
[versioning contract](../docs/VERSIONING.md) for why the scientific and package versions differ.

## Workstation usage

Docker is recommended. The image isolates the two incompatible Transformers environments and
releases GPU memory between them:

```bash
cd /path/to/DJR-MCP-Finder/user-inference-v0.1
bash workstation/build.sh

bash workstation/run_user_fasta.sh \
  examples/synthetic_example.faa \
  run_output/sample \
  0
```

The defaults use independent resources:

```text
base image       djrmcp-user-inference:v0
candidate image  djrmcp-user-inference:v0.1
cache            djrmcp-v01-hf-cache
GPU              device=0
```

The scripts resolve the checkout from their own location, so they can be invoked from any working
directory. Input and output paths may be relative or absolute. Common Docker settings can be
overridden with environment variables:

```bash
export DJRMCP_BASE_IMAGE=local/djrmcp-user-inference:v0
export DJRMCP_IMAGE=local/djrmcp-user-inference:v0.1
export DJRMCP_CACHE_SOURCE=/absolute/path/to/huggingface-cache
export DJRMCP_DOCKER_GPUS=all
export DJRMCP_DOCKER=docker
```

`DJRMCP_CACHE_SOURCE` may name either a Docker volume or an absolute host directory; the default
remains a separate named volume. By default, the build verifies the historically validated V0 base
image ID. If V0 was rebuilt locally from the same compatible frozen environment and therefore has
a different image ID, you may explicitly use
`DJRMCP_EXPECTED_BASE_IMAGE_ID='' bash workstation/build.sh` after verifying its provenance.
Version, CUDA, Transformers, and candidate-bundle checks still run. See
[`workstation/README.md`](workstation/README.md) for other options.

A CUDA GPU with at least 24 GB and native BF16 support is recommended. Historical peaks were about
5.95 GB for ESM-2 3B and 15.0 GB for ESM-C 6B; the two models are never resident simultaneously.
If no sequence passes H1/H2, the H3 worker is not started.

## CLI

Input and bundle checks do not require a GPU:

```bash
djrmcp-predict-v01 validate-fasta proteins.faa
djrmcp-predict-v01 model-info
```

When both frozen Python environments have already been configured:

```bash
export DJRMCP_ESM2_PYTHON=/path/to/esm2-venv/bin/python
export DJRMCP_ESMC_PYTHON=/path/to/esmc-venv/bin/python

djrmcp-predict-v01 predict proteins.faa \
  --outdir run_output/sample \
  --device cuda
```

You can also use the wrapper in the checkout directly. It prefers `DJRMCP_PYTHON`, then
`.venv/bin/python` inside the checkout, and finally `python3`, while retaining the validated CUDA
default. To request automatic device selection or CPU, pass `auto`/`cpu` explicitly or set
`DJRMCP_DEVICE`:

```bash
DJRMCP_PYTHON=/path/to/controller-python \
DJRMCP_ESM2_PYTHON=/path/to/esm2-venv/bin/python \
DJRMCP_ESMC_PYTHON=/path/to/esmc-venv/bin/python \
DJRMCP_CACHE_DIR=/path/to/huggingface-cache \
bash scripts/run_user_fasta.sh proteins.faa run_output/sample auto
```

After the cache has been populated, add the CLI option `--offline` or set
`DJRMCP_OFFLINE=1` for the wrapper. The output directory contains:

```text
predictions.tsv
run_metadata.json
CHECKSUMS.sha256
```

Final labels are `non_djr`, `djr_non_mcp`, `mcp::Nucleocytoviricota`,
`mcp::Preplasmiviricota`, or `mcp::unknown/other`. The final category means only that a sequence
passed H1/H2 but could not be assigned reliably to either of the two known H3 phyla. It is not a
general unknown-virus or out-of-distribution detector.

The Head-2 score column is `head2_mcp_probability`; new run metadata uses output schema version 3.

## Input and frozen contracts

- FASTA IDs must be non-empty and unique; the 20 standard amino acids and `X` are accepted.
- Identical sequences are embedded once; the output restores the original IDs and order.
- Sequences outside 130–2906 aa can still be evaluated but receive an out-of-training-domain warning.
- Long sequences are covered completely with a 1022-aa window / 511-aa stride and are not truncated.
- H1/H2 use `facebook/esm2_t36_3B_UR50D@476b639...` in FP16.
- H3 uses `Biohub/ESMC-6B@45b0fa5...` in BF16 and runs only on gate-through sequences.
- Classifier heads are checksum-verified, pickle-free NPZ files; the wheel contains no sklearn joblib.
- Raw scores, probabilities, and threshold decisions have exact parity across both frozen sets of
  11,060 embeddings.

Every run records SHA256 hashes for the input, models, classifier heads, routed subset, runtime
environment, and outputs. Probabilities are calibrated model scores under the development-data
distribution, not prevalence-adjusted posteriors for natural samples.

## Development checks

The V0.1 Python package requires Python 3.12 or newer because it pins NumPy 2.5.1. CPU-only
contract tests do not download the large models:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

See `environment/REFERENCE_ENVIRONMENT.md` for the frozen environments and release boundary.

## License

This development-candidate package and its original bundled linear classifier heads are released
under the [MIT License](LICENSE). ESM-2 and ESM-C checkpoints are downloaded separately and retain
their upstream terms; see the
[release-specific third-party notice](src/djrmcp_predict_v01/assets/project-v0.1-mixed-r1/THIRD_PARTY_NOTICES.md)
and repository-level [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md). Prospective external
confirmation remains outstanding.
