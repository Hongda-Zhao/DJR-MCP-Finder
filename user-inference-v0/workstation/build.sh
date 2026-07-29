#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
docker_bin="${DJRMCP_DOCKER:-docker}"
image_name="${DJRMCP_IMAGE:-djrmcp-user-inference:v0}"
cache_volume="${DJRMCP_CACHE_VOLUME:-djrmcp-esmc6b-cache}"
gpu_index="${DJRMCP_GPU:-0}"
gpu_check_value="${DJRMCP_GPU_CHECK:-1}"
base_image="${DJRMCP_BASE_IMAGE:-ubuntu:24.04}"
container_uid="${DJRMCP_UID:-$(id -u)}"
container_gid="${DJRMCP_GID:-$(id -g)}"

if [[ ! "${gpu_index}" =~ ^[0-9]+$ ]]; then
    echo "DJRMCP_GPU must be a non-negative integer" >&2
    exit 2
fi
if [[ ! "${container_uid}" =~ ^[0-9]+$ || "${container_uid}" == "0" ]]; then
    echo "DJRMCP_UID must be a positive integer (set it explicitly when building as root)" >&2
    exit 2
fi
if [[ ! "${container_gid}" =~ ^[0-9]+$ ]]; then
    echo "DJRMCP_GID must be a non-negative integer" >&2
    exit 2
fi
case "${gpu_check_value}" in
    0|false|FALSE|no|NO)
        gpu_check=0
        ;;
    1|true|TRUE|yes|YES)
        gpu_check=1
        ;;
    *)
        echo "DJRMCP_GPU_CHECK must be 0/1, true/false, or yes/no" >&2
        exit 2
        ;;
esac
if [[ -z "${image_name}" || -z "${cache_volume}" || -z "${base_image}" ]]; then
    echo "DJRMCP_IMAGE, DJRMCP_CACHE_VOLUME, and DJRMCP_BASE_IMAGE must be non-empty" >&2
    exit 2
fi

"${docker_bin}" build \
    --file "${project_root}/workstation/Dockerfile" \
    --build-arg "DJRMCP_BASE_IMAGE=${base_image}" \
    --build-arg "DJRMCP_UID=${container_uid}" \
    --build-arg "DJRMCP_GID=${container_gid}" \
    --tag "${image_name}" \
    "${project_root}"

"${docker_bin}" volume inspect "${cache_volume}" >/dev/null 2>&1 \
    || "${docker_bin}" volume create "${cache_volume}" >/dev/null

if [[ "${gpu_check}" == "1" ]]; then
    "${docker_bin}" run --rm \
        --gpus "device=${gpu_index}" \
        --entrypoint python \
        "${image_name}" \
        -c 'import torch; assert torch.cuda.is_available(); print({"torch": torch.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0)})'
    build_status="ready"
else
    build_status="image_ready"
fi

"${docker_bin}" run --rm "${image_name}" model-info >/dev/null

printf 'image=%s\nbase_image=%s\ncache_volume=%s\ngpu=%s\ngpu_check=%s\nstatus=%s\n' \
    "${image_name}" \
    "${base_image}" \
    "${cache_volume}" \
    "${gpu_index}" \
    "${gpu_check}" \
    "${build_status}"
