# Portable V0.1 development-candidate deployment

This directory deploys the mixed-encoder V0.1 candidate without changing the
formal V0 directory, image, or cache. V0.1 remains a Train-CV-nominated
development candidate that requires prospective external confirmation.

## Isolation contract

```text
checkout         <repository>/user-inference-v0.1
base image       djrmcp-user-inference:v0
candidate image  djrmcp-user-inference:v0.1
cache            djrmcp-v01-hf-cache
entrypoint       djrmcp-predict-v01
```

The image is derived from the checksum-verified formal V0 image. It reuses the
validated V0 CUDA/PyTorch/NumPy and ESM-C environment, then adds only a small
ESM-2 Transformers overlay and the compiler support required by Triton's first
GPU forward pass. The two Transformers distributions stay isolated:

```text
/opt/djrmcp-esm2  H1/H2: facebook/esm2_t36_3B_UR50D@476b6399..., float16
/opt/djrmcp-venv  H3:    Biohub/ESMC-6B@45b0fa5d..., bfloat16
```

The ESM-2 environment uses Transformers 5.14.1 with its overlay dependencies
pinned; the ESM-C environment uses the Biohub fork at
`ef32577f55da19a4989cd7b22e004dc43a4998cb`. Both environments share the
immutable V0 NumPy 2.5.1 and PyTorch 2.13.0 installation. The controller first
embeds all exact-unique input sequences with ESM-2 3B. It releases that worker,
then starts ESM-C 6B only for sequences that pass both H1 and H2. Thus a
single-GPU run does not keep both checkpoints resident at once.

The frozen benchmark peaks were approximately 5.95 GB for ESM-2 3B and 15.0 GB
for ESM-C 6B. A CUDA GPU with at least 24 GB and native BF16 support is
recommended. CPU inference is not the validated workstation path.

## Build

```bash
cd /path/to/DJR-MCP-Finder/user-inference-v0.1
bash workstation/build.sh
```

The build first verifies that `djrmcp-user-inference:v0` still has the exact
validated image identity. It never retags or modifies that image. It then
verifies both Python environments and the checksum-bearing candidate bundle.
It creates the independent `djrmcp-v01-hf-cache` volume, but it does not
download either checkpoint and is not an end-to-end inference validation.

The script resolves the build context from its own location, so it can also be
invoked by absolute path from another working directory. Its portable settings
are environment variables:

```text
DJRMCP_DOCKER                      Docker executable (default: docker)
DJRMCP_BASE_IMAGE                 V0 base image tag
DJRMCP_EXPECTED_BASE_IMAGE_ID     required base ID; set to an empty string only
                                  for an intentionally compatible local rebuild
DJRMCP_IMAGE                      candidate output image tag
DJRMCP_CACHE_SOURCE               named volume or absolute host cache directory
DJRMCP_DOCKER_GPUS                complete Docker --gpus value (for example all,
                                  device=0, or device=GPU-...)
```

`DJRMCP_DOCKER_BIN` is accepted as a backward-compatible alias when
`DJRMCP_DOCKER` is unset.

`DJRMCP_GPU` remains a shorthand for the device selected by the default
`DJRMCP_DOCKER_GPUS=device=$DJRMCP_GPU`. The exact validated V0 image ID remains
the default gate. Disabling only that identity gate does not disable the pinned
package, CUDA, model-bundle, or release checksum checks.

## Run user FASTA

Use physical GPU 0:

```bash
bash workstation/run_user_fasta.sh \
  examples/synthetic_example.faa \
  run_output/sample \
  0
```

Use `1` as the final argument for the second GPU. The first inference downloads
the immutable ESM-2 checkpoint. ESM-C is downloaded only when at least one
sequence reaches H3. Both are then reused from `djrmcp-v01-hf-cache`. Inputs and
outputs remain at the paths supplied by the caller. The default large cache is
a Docker named volume; set `DJRMCP_CACHE_SOURCE` to an absolute host directory
when an explicit cache location is preferred.

After both checkpoints have been cached, require a network-independent rerun:

```bash
DJRMCP_OFFLINE=1 bash workstation/run_user_fasta.sh \
  examples/synthetic_example.faa \
  run_output/sample_offline \
  0
```

This disables the container network, sets the Hugging Face/Transformers offline
environment, and passes the CLI `--offline` flag to both isolated workers.

The output directory contains:

```text
predictions.tsv
run_metadata.json
CHECKSUMS.sha256
```

Existing standard result files are not overwritten. The wrapper verifies the
output checksum manifest before returning success.

## Deployment validation

The final image passed a checksum-bound 12-protein Train-derived fixture on
2026-07-29. Four records reached H3. Online and `--network none` offline runs
each matched the frozen golden predictions with zero label, routing, or
probability differences. Exact original host, image, input, output, revision,
GPU-memory, and checksum evidence is retained as historical metadata in
`VALIDATION.json`; that host is not required for this deployment.

This establishes engineering reproduction, not prospective scientific external
confirmation. Do not retag this image as `v0` or mount
`djrmcp-esmc6b-cache`; both wrappers explicitly refuse those formal-V0 names.
