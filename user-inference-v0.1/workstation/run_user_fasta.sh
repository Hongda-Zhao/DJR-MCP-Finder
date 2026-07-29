#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo "usage: $0 INPUT.faa OUTPUT_DIR [GPU_SELECTOR]" >&2
    exit 2
fi

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
invocation_dir="$(pwd -P)"
docker_bin="${DJRMCP_DOCKER:-${DJRMCP_DOCKER_BIN:-docker}}"
image_name="${DJRMCP_IMAGE:-djrmcp-user-inference:v0.1}"
cache_source="${DJRMCP_CACHE_SOURCE:-${DJRMCP_CACHE_VOLUME:-djrmcp-v01-hf-cache}}"
input_argument="$1"
output_argument="$2"
gpu_selector="${3:-${DJRMCP_GPU:-0}}"
docker_gpus="${DJRMCP_DOCKER_GPUS:-device=${gpu_selector}}"
offline_value="${DJRMCP_OFFLINE:-0}"
protected_v0_image="${DJRMCP_PROTECTED_V0_IMAGE:-djrmcp-user-inference:v0}"
protected_v0_cache="${DJRMCP_PROTECTED_V0_CACHE_SOURCE:-djrmcp-esmc6b-cache}"

if [[ ! -f "${project_root}/pyproject.toml" ]]; then
    echo "cannot locate the user-inference-v0.1 checkout: ${project_root}" >&2
    exit 2
fi
if ! command -v "${docker_bin}" >/dev/null 2>&1; then
    echo "Docker command is unavailable: ${docker_bin}" >&2
    exit 2
fi
if [[ "${image_name}" == "${protected_v0_image}" ]]; then
    echo "refusing to run the V0.1 wrapper with the formal V0 image tag" >&2
    exit 2
fi
if [[ "${cache_source}" == "${protected_v0_cache}" ]]; then
    echo "refusing to write the formal V0 cache volume" >&2
    exit 2
fi
if [[ "${cache_source}" == /* ]]; then
    mkdir -p "${cache_source}"
    cache_source="$(cd "${cache_source}" && pwd -P)"
    if [[ "${cache_source}" == "/" ]]; then
        echo "refusing to use / as the cache source" >&2
        exit 2
    fi
fi
if [[ ! -f "${input_argument}" ]]; then
    echo "input FASTA does not exist: ${input_argument}" >&2
    exit 2
fi
if [[ -z "${docker_gpus}" ]]; then
    echo "DJRMCP_DOCKER_GPUS must not be empty" >&2
    exit 2
fi
offline_docker_args=()
offline_predict_args=()
case "${offline_value}" in
    0|false|FALSE|no|NO)
        ;;
    1|true|TRUE|yes|YES)
        offline_docker_args+=(
            --network none
            --env HF_HUB_OFFLINE=1
            --env TRANSFORMERS_OFFLINE=1
            --env HF_DATASETS_OFFLINE=1
        )
        offline_predict_args+=(--offline)
        ;;
    *)
        echo "DJRMCP_OFFLINE must be 0/1, true/false, or yes/no" >&2
        exit 2
        ;;
esac

input_parent="$(cd "$(dirname "${input_argument}")" && pwd -P)"
input_fasta="${input_parent}/$(basename "${input_argument}")"

case "${output_argument}" in
    /*) output_path="${output_argument}" ;;
    *) output_path="${invocation_dir}/${output_argument}" ;;
esac
output_parent_candidate="$(dirname "${output_path}")"
output_name="$(basename "${output_path}")"
if [[ "${output_name}" == "." || "${output_name}" == ".." ]]; then
    echo "refusing unsafe output directory: ${output_argument}" >&2
    exit 2
fi
if [[ "${output_path}" == "/" || "${output_parent_candidate}" == "/" ]]; then
    echo "refusing to mount / as the output parent; choose a nested output path" >&2
    exit 2
fi
if [[ -e "${output_path}" && ! -d "${output_path}" ]]; then
    echo "output path exists and is not a directory: ${output_path}" >&2
    exit 2
fi
mkdir -p "${output_parent_candidate}"
output_parent="$(cd "${output_parent_candidate}" && pwd -P)"
if [[ "${output_parent}" == "/" ]]; then
    echo "refusing to mount / as the output parent; choose a nested output path" >&2
    exit 2
fi
output_path="${output_parent}/${output_name}"
if [[ -L "${output_path}" ]]; then
    echo "refusing a symbolic-link output directory: ${output_path}" >&2
    exit 2
fi
if [[ -e "${output_path}" && ! -d "${output_path}" ]]; then
    echo "output path exists and is not a directory: ${output_path}" >&2
    exit 2
fi

# FASTA validation is CPU-only and runs before either checkpoint is loaded.
"${docker_bin}" run --rm \
    "${offline_docker_args[@]}" \
    --volume "${input_fasta}:/input/proteins.faa:ro" \
    "${image_name}" \
    validate-fasta /input/proteins.faa

# The controller uses ESM-2 3B for H1/H2, releases it, and starts the ESM-C
# worker only for exact-unique sequences that pass both gates.
"${docker_bin}" run --rm \
    --gpus "${docker_gpus}" \
    --ipc=host \
    "${offline_docker_args[@]}" \
    --volume "${cache_source}:/models/huggingface" \
    --volume "${input_fasta}:/input/proteins.faa:ro" \
    --volume "${output_parent}:/output" \
    "${image_name}" \
    predict /input/proteins.faa \
    --outdir "/output/${output_name}" \
    --device cuda \
    "${offline_predict_args[@]}"

(
    cd "${output_path}"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum -c CHECKSUMS.sha256
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 -c CHECKSUMS.sha256
    else
        echo "sha256sum or shasum is required to verify output checksums" >&2
        exit 2
    fi
)
