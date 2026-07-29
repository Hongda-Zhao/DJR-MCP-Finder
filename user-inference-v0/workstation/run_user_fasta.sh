#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo "usage: $0 INPUT.faa OUTPUT_DIR [GPU_INDEX]" >&2
    exit 2
fi

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
docker_bin="${DJRMCP_DOCKER:-docker}"
image_name="${DJRMCP_IMAGE:-djrmcp-user-inference:v0}"
cache_volume="${DJRMCP_CACHE_VOLUME:-djrmcp-esmc6b-cache}"
device="${DJRMCP_DEVICE:-cuda}"
input_argument="$1"
output_argument="$2"
gpu_index="${3:-${DJRMCP_GPU:-0}}"
offline_value="${DJRMCP_OFFLINE:-0}"

if [[ ! -f "${project_root}/pyproject.toml" ]]; then
    echo "cannot locate the user-inference-v0 checkout root" >&2
    exit 2
fi
if [[ -z "${image_name}" || -z "${cache_volume}" ]]; then
    echo "DJRMCP_IMAGE and DJRMCP_CACHE_VOLUME must be non-empty" >&2
    exit 2
fi
if [[ ! -f "${input_argument}" ]]; then
    echo "input FASTA does not exist: ${input_argument}" >&2
    exit 2
fi
if [[ ! "${gpu_index}" =~ ^[0-9]+$ ]]; then
    echo "GPU_INDEX must be a non-negative integer" >&2
    exit 2
fi
case "${device}" in
    auto|cuda|cpu)
        ;;
    *)
        echo "DJRMCP_DEVICE must be auto, cuda, or cpu" >&2
        exit 2
        ;;
esac

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
        )
        offline_predict_args+=(--offline)
        ;;
    *)
        echo "DJRMCP_OFFLINE must be 0/1, true/false, or yes/no" >&2
        exit 2
        ;;
esac

device_docker_args=()
if [[ "${device}" != "cpu" ]]; then
    device_docker_args+=(--gpus "device=${gpu_index}" --ipc=host)
fi

input_parent="$(cd "$(dirname "${input_argument}")" && pwd -P)"
input_fasta="${input_parent}/$(basename "${input_argument}")"
output_parent_argument="$(dirname "${output_argument}")"
output_name="$(basename "${output_argument}")"
case "${output_name}" in
    ""|.|..|/)
        echo "refusing unsafe output directory: ${output_argument}" >&2
        exit 2
        ;;
esac
if [[ "${output_parent_argument}" == "/" ]]; then
    echo "refusing to mount / as the output parent; choose a nested output path" >&2
    exit 2
fi
mkdir -p "${output_parent_argument}"
output_parent="$(cd "${output_parent_argument}" && pwd -P)"
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

"${docker_bin}" volume inspect "${cache_volume}" >/dev/null 2>&1 \
    || "${docker_bin}" volume create "${cache_volume}" >/dev/null

"${docker_bin}" run --rm \
    "${offline_docker_args[@]}" \
    --volume "${input_fasta}:/input/proteins.faa:ro" \
    "${image_name}" \
    validate-fasta /input/proteins.faa

"${docker_bin}" run --rm \
    "${device_docker_args[@]}" \
    "${offline_docker_args[@]}" \
    --volume "${cache_volume}:/models/huggingface" \
    --volume "${input_fasta}:/input/proteins.faa:ro" \
    --volume "${output_parent}:/output" \
    "${image_name}" \
    predict /input/proteins.faa \
    --outdir "/output/${output_name}" \
    --device "${device}" \
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
