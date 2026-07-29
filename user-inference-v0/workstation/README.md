# Portable Docker deployment

The Docker wrappers locate the `user-inference-v0` checkout from the script
location, so they can be invoked from any working directory. Input and output
paths remain on the host. The immutable ESM-C 6B checkpoint is cached in a
configurable named Docker volume.

A CUDA run requires Docker with NVIDIA Container Toolkit support and a GPU with
about 15 GB of free memory; 24 GB or more is recommended. CPU inference can be
selected explicitly, but it loads roughly 25 GB of float32 weights and is not a
validated routine deployment path.

## Configuration

The wrappers have portable defaults and accept these environment overrides:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJRMCP_DOCKER` | `docker` | Docker-compatible executable |
| `DJRMCP_BASE_IMAGE` | `ubuntu:24.04` | Base image used by `build.sh` |
| `DJRMCP_IMAGE` | `djrmcp-user-inference:v0` | Locally built image tag |
| `DJRMCP_CACHE_VOLUME` | `djrmcp-esmc6b-cache` | Named Hugging Face cache volume |
| `DJRMCP_DEVICE` | `cuda` | Runtime device: `auto`, `cuda`, or `cpu` |
| `DJRMCP_GPU` | `0` | Physical GPU index exposed to the container |
| `DJRMCP_GPU_CHECK` | `1` | Set to `0` only to skip the CUDA preflight |
| `DJRMCP_OFFLINE` | `0` | Set to `1` for network-disabled cached inference |
| `DJRMCP_UID` / `DJRMCP_GID` | host IDs | Container user/group for bind-mounted outputs |

Changing the base image or dependency pins creates a deployment distinct from
the historical validation record and requires fresh validation.

## Build

Set `checkout` to the downloaded directory; no fixed host path is required:

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
bash "${checkout}/workstation/build.sh"
```

The build preserves the validated default of running a CUDA preflight. To build
the image on a host where Docker cannot expose an NVIDIA GPU, skip only that
preflight explicitly:

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
DJRMCP_GPU_CHECK=0 \
bash "${checkout}/workstation/build.sh"
```

The build verifies the packaged frozen model bundle and creates the configured
cache volume. It does not download the ESM-C checkpoint.

## Run user FASTA

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
DJRMCP_DEVICE=cuda DJRMCP_GPU=0 \
bash "${checkout}/workstation/run_user_fasta.sh" \
  /absolute/path/proteins.faa \
  /absolute/path/run_output/sample
```

The optional third argument overrides `DJRMCP_GPU`. The first prediction run
downloads the pinned `Biohub/ESMC-6B` revision into `DJRMCP_CACHE_VOLUME`; later
runs reuse it. For an already populated cache, require network-independent use:

```bash
checkout=/path/to/DJR-MCP-Finder/user-inference-v0
DJRMCP_OFFLINE=1 DJRMCP_DEVICE=cuda DJRMCP_GPU=0 \
bash "${checkout}/workstation/run_user_fasta.sh" \
  /absolute/path/proteins.faa \
  /absolute/path/run_output/sample_offline
```

The host output directory contains `predictions.tsv`, `run_metadata.json`, and
`CHECKSUMS.sha256`. Existing standard output files are not overwritten, and the
wrapper verifies the checksum manifest before returning success.

## Historical deployment validation

An earlier deployment passed an end-to-end GPU smoke test on 2026-07-27. The
frozen 6.352B-parameter checkpoint used 13,047,401,984 peak allocated GPU bytes
and produced checksum-valid outputs for `examples/synthetic_example.faa`.
Exact image, runtime, input, and output evidence is retained in
`VALIDATION.json` as historical metadata. Its original host alias and deployment
path are provenance only, not instructions or requirements for this checkout.

Rebuilding after the portability edits produces a new image identity; rerun the
GPU smoke test before treating that rebuilt image as independently validated.
