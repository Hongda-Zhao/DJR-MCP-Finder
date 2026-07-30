**English** | [简体中文](README.cn.md)

# DJR-MCP Finder — User Inference V0

This standalone directory packages the frozen DJR-MCP Finder project V0 as an inference tool for
user-supplied protein FASTA files. It does not train models, change temperatures or thresholds,
read the historical Test split, or alter the main project release identity.

```text
protein FASTA
  -> pinned ESM-C 6B embedding
  -> frozen H1/H2/H3 linear heads
  -> frozen H1 -> H2 -> H3 gate
  -> predictions.tsv + run_metadata.json + CHECKSUMS.sha256
```

## Output semantics

There are exactly five final output labels:

```text
non_djr
djr_non_vma
vma::Nucleocytoviricota
vma::Preplasmiviricota
vma::unknown/other
```

`vma::unknown/other` means only that a sample passed H1/H2 but could not be assigned reliably to
either of the two known H3 phyla. It is not a detector for arbitrary unknown viruses or global
out-of-distribution data.

## Installation

Basic checks and unit tests do not download ESM-C:

```bash
cd /path/to/DJR-MCP-Finder/user-inference-v0
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

Real inference requires the pinned Biohub Transformers revision and PyTorch:

```bash
python -m pip install -e '.[inference]'
```

A CUDA GPU with at least 24 GB of memory is recommended. In the frozen benchmark, measured peak
memory for ESM-C 6B was about 15.0 GB. CPU mode loads about 25 GB of float32 weights and has not
been validated as a routine path.

## Usage

First validate the input and model package on CPU:

```bash
djrmcp-predict validate-fasta proteins.faa
djrmcp-predict model-info
```

Then run inference:

```bash
djrmcp-predict predict proteins.faa \
  --outdir run_output/my_sample \
  --device cuda
```

You can also use the complete wrapper, which checks the FASTA and model, runs inference, and
verifies the result checksums in sequence:

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
bash "${checkout}/scripts/run_user_fasta.sh" proteins.faa run_output/my_sample cuda
```

The wrapper locates the checkout from its own path, so it need not be launched from the repository
root. It prefers `.venv/bin/python` inside the checkout and otherwise uses `python3`. The runtime
and paths can be overridden explicitly:

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
DJRMCP_PYTHON=/path/to/venv/bin/python \
DJRMCP_CACHE_DIR=/path/to/huggingface-cache \
DJRMCP_DEVICE=cuda \
bash "${checkout}/scripts/run_user_fasta.sh" proteins.faa run_output/my_sample
```

`DJRMCP_DEVICE` defaults to `cuda` and can be set explicitly to `auto` or `cpu`; the third
positional argument takes precedence. `DJRMCP_OFFLINE=1` switches the wrapper to offline mode.
See [`workstation/README.md`](workstation/README.md) for Docker/NVIDIA deployment and configurable
image, cache volume, GPU, and UID/GID settings.

The first run downloads the pinned `Biohub/ESMC-6B` revision from Hugging Face. Once the cache is
populated, network access can be disabled:

```bash
djrmcp-predict predict proteins.faa \
  --outdir run_output/my_sample \
  --device cuda \
  --offline
```

The output directory contains:

```text
predictions.tsv    H1/H2/H3 scores, gate states, and final label for each input protein
run_metadata.json  input/model SHA256, environment, hardware, thresholds, runtime, and interpretation boundary
CHECKSUMS.sha256   integrity checks for the two result files
```

Existing results are not overwritten by default. Use `--overwrite` only when you explicitly want
to replace the standard output files; writes still use temporary files followed by an atomic
rename.

## Input contract

- FASTA IDs must be non-empty and unique; the complete header is retained.
- Sequences are converted to uppercase. The 20 standard amino acids seen during training and `X`
  are accepted.
- Empty sequences, gaps, stop symbols, other ambiguous residues, and apparently nucleotide-only
  FASTA files fail closed.
- Identical sequences with different IDs are embedded once, then restored to their original order.
- Sequences outside the 130–2906 aa training range are still evaluated but receive an
  out-of-domain warning.
- Long sequences always use the frozen 1022-aa window / 511-aa stride and are never silently
  truncated.

## Frozen contract

- ESM-C 6B: `Biohub/ESMC-6B@45b0fa5d7fb06faefbd5e3b89bdcef35d564e79a`
- Transformers: `Biohub/transformers@ef32577f55da19a4989cd7b22e004dc43a4998cb`
- Embedding: residue mean followed by overlapping-window mean, 2560 dimensions
- Classifier input: a float16 storage-precision round trip matching training
- H1/H2 gate: probability `>=` the frozen threshold
- H3 reject: output `unknown/other` when the maximum probability is `<` the frozen threshold

The three sklearn joblib files were exported as checksum-verified NumPy weights; public inference
does not deserialize pickle. `PARITY_REPORT.json` records parity against the original joblib files
over all 11,060 frozen ESM-C embeddings. See `environment/REFERENCE_ENVIRONMENT.md` for the
reference software and hardware environment used for the original embeddings.

## Scientific boundary

The current ESM-C 6B model has no new prospective external Test. Output probabilities are frozen,
calibrated model scores under the development-data distribution, not prevalence-adjusted posterior
probabilities in natural proteomes. Large-scale discovery requires independent false-positive
assessment, same-source challenge sets, and structural/manual validation.

This directory currently has no project-level `LICENSE`, so it grants no permission to copy,
modify, or redistribute the package. Before any formal public release, code and data/classifier-head
licensing must be determined and citation information added.
