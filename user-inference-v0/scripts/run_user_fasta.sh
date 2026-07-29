#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo "usage: $0 INPUT.faa OUTPUT_DIR [auto|cuda|cpu]" >&2
    exit 2
fi

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
input_fasta="$1"
output_dir="$2"
device="${3:-${DJRMCP_DEVICE:-cuda}}"
cache_dir="${DJRMCP_CACHE_DIR:-}"
offline_value="${DJRMCP_OFFLINE:-0}"

case "${device}" in
    auto|cuda|cpu)
        ;;
    *)
        echo "device must be auto, cuda, or cpu" >&2
        exit 2
        ;;
esac

if [[ -n "${DJRMCP_PYTHON:-}" ]]; then
    python_bin="${DJRMCP_PYTHON}"
elif [[ -x "${project_root}/.venv/bin/python" ]]; then
    python_bin="${project_root}/.venv/bin/python"
else
    python_bin="python3"
fi

offline_args=()
case "${offline_value}" in
    0|false|FALSE|no|NO)
        ;;
    1|true|TRUE|yes|YES)
        offline_args+=(--offline)
        ;;
    *)
        echo "DJRMCP_OFFLINE must be 0/1, true/false, or yes/no" >&2
        exit 2
        ;;
esac

cache_args=()
if [[ -n "${cache_dir}" ]]; then
    cache_args+=(--cache-dir "${cache_dir}")
fi

# Always execute the package and frozen assets from this checkout.  Dependency
# imports still come from DJRMCP_PYTHON, .venv, or the caller's python3.
export PYTHONPATH="${project_root}/src${PYTHONPATH:+:${PYTHONPATH}}"
run_cli=("${python_bin}" -m djrmcp_predict.cli)

"${run_cli[@]}" validate-fasta "${input_fasta}"
"${run_cli[@]}" model-info
"${run_cli[@]}" predict "${input_fasta}" \
    --outdir "${output_dir}" \
    --device "${device}" \
    "${cache_args[@]}" \
    "${offline_args[@]}"
(
    cd "${output_dir}"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum -c CHECKSUMS.sha256
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 -c CHECKSUMS.sha256
    else
        echo "sha256sum or shasum is required to verify output checksums" >&2
        exit 2
    fi
)
