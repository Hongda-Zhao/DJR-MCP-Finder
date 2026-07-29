#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
docker_bin="${DJRMCP_DOCKER:-${DJRMCP_DOCKER_BIN:-docker}}"
base_image="${DJRMCP_BASE_IMAGE:-djrmcp-user-inference:v0}"
image_name="${DJRMCP_IMAGE:-djrmcp-user-inference:v0.1}"
cache_source="${DJRMCP_CACHE_SOURCE:-${DJRMCP_CACHE_VOLUME:-djrmcp-v01-hf-cache}}"
docker_gpus="${DJRMCP_DOCKER_GPUS:-device=${DJRMCP_GPU:-0}}"
protected_v0_image="${DJRMCP_PROTECTED_V0_IMAGE:-djrmcp-user-inference:v0}"
protected_v0_cache="${DJRMCP_PROTECTED_V0_CACHE_SOURCE:-djrmcp-esmc6b-cache}"
expected_base_image_id="${DJRMCP_EXPECTED_BASE_IMAGE_ID-sha256:88be8ff60b222875dae45bb7eaf4940d653893f2b22d289bc2d5e7cd6974a7b6}"
container_uid="${DJRMCP_UID:-$(id -u)}"
container_gid="${DJRMCP_GID:-$(id -g)}"

if ! command -v "${docker_bin}" >/dev/null 2>&1; then
    echo "Docker command is unavailable: ${docker_bin}" >&2
    exit 2
fi
if [[ -z "${docker_gpus}" ]]; then
    echo "DJRMCP_DOCKER_GPUS must not be empty" >&2
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
if [[ "${image_name}" == "${base_image}" || "${image_name}" == "${protected_v0_image}" ]]; then
    echo "refusing to overwrite a V0 base/protected image tag: ${image_name}" >&2
    exit 2
fi
if [[ "${cache_source}" == "${protected_v0_cache}" ]]; then
    echo "refusing to reuse the protected V0 cache source: ${cache_source}" >&2
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

if ! observed_base_image_id="$("${docker_bin}" image inspect "${base_image}" --format '{{.Id}}')"; then
    echo "required V0 base image is missing: ${base_image}" >&2
    exit 2
fi
if [[ -n "${expected_base_image_id}" && "${observed_base_image_id}" != "${expected_base_image_id}" ]]; then
    echo "V0 base image identity differs from the validated base; refusing build" >&2
    echo "expected=${expected_base_image_id}" >&2
    echo "observed=${observed_base_image_id}" >&2
    echo "Set DJRMCP_EXPECTED_BASE_IMAGE_ID='' only for an intentionally compatible rebuild." >&2
    exit 2
fi

"${docker_bin}" build \
    --file "${project_root}/workstation/Dockerfile" \
    --build-arg "BASE_IMAGE=${base_image}" \
    --build-arg "DJRMCP_UID=${container_uid}" \
    --build-arg "DJRMCP_GID=${container_gid}" \
    --tag "${image_name}" \
    "${project_root}"

if [[ "${cache_source}" != /* ]]; then
    "${docker_bin}" volume inspect "${cache_source}" >/dev/null 2>&1 \
        || "${docker_bin}" volume create "${cache_source}" >/dev/null
fi

"${docker_bin}" run --rm \
    --volume "${cache_source}:/models/huggingface" \
    --entrypoint sh \
    "${image_name}" \
    -c 'test -w "$HOME" && test -w /models/huggingface && marker=/models/huggingface/.djrmcp-write-test.$$ && : > "$marker" && rm -f "$marker"'

"${docker_bin}" run --rm \
    --gpus "${docker_gpus}" \
    --entrypoint /opt/djrmcp-esm2/bin/python \
    "${image_name}" \
    -c 'import numpy, torch, transformers; assert numpy.__version__ == "2.5.1"; assert torch.__version__.split("+")[0] == "2.13.0"; assert torch.version.cuda == "13.0"; assert transformers.__version__ == "5.14.1"; assert transformers.__file__.startswith("/opt/djrmcp-esm2/"); assert numpy.__file__.startswith("/opt/djrmcp-venv/"); assert torch.__file__.startswith("/opt/djrmcp-venv/"); assert torch.cuda.is_available(); print({"environment": "esm2", "torch": torch.__version__, "transformers": transformers.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0)})'

"${docker_bin}" run --rm \
    --gpus "${docker_gpus}" \
    --entrypoint /opt/djrmcp-venv/bin/python \
    "${image_name}" \
    -c 'import json; from importlib import metadata; import numpy, torch, transformers; payload=json.loads(metadata.distribution("transformers").read_text("direct_url.json")); assert payload["vcs_info"]["commit_id"] == "ef32577f55da19a4989cd7b22e004dc43a4998cb"; assert numpy.__version__ == "2.5.1"; assert torch.__version__.split("+")[0] == "2.13.0"; assert torch.version.cuda == "13.0"; assert transformers.__version__ == "4.57.6"; assert numpy.__file__.startswith("/opt/djrmcp-venv/"); assert torch.__file__.startswith("/opt/djrmcp-venv/"); assert transformers.__file__.startswith("/opt/djrmcp-venv/"); assert torch.cuda.is_available(); print({"environment": "esmc", "torch": torch.__version__, "transformers": transformers.__version__, "transformers_revision": payload["vcs_info"]["commit_id"], "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0)})'

"${docker_bin}" run --rm "${image_name}" model-info >/dev/null

printf 'image=%s\nbase_image=%s\nbase_image_id=%s\nuid=%s\ngid=%s\ncache_source=%s\ndocker_gpus=%s\nesm2_python=%s\nesmc_python=%s\nstatus=environment_ready\n' \
    "${image_name}" \
    "${base_image}" \
    "${observed_base_image_id}" \
    "${container_uid}" \
    "${container_gid}" \
    "${cache_source}" \
    "${docker_gpus}" \
    "/opt/djrmcp-esm2/bin/python" \
    "/opt/djrmcp-venv/bin/python"

printf '%s\n' \
    'A real dual-encoder smoke run is still required; build.sh does not download checkpoints.'
