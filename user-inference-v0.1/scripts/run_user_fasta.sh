#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo "usage: $0 INPUT.faa OUTPUT_DIR [auto|cuda|cpu]" >&2
    exit 2
fi

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ -n "${DJRMCP_PYTHON:-}" ]]; then
    python_bin="${DJRMCP_PYTHON}"
elif [[ -x "${project_root}/.venv/bin/python" ]]; then
    python_bin="${project_root}/.venv/bin/python"
else
    python_bin="python3"
fi
input_fasta="$1"
output_dir="$2"
device="${3:-${DJRMCP_DEVICE:-cuda}}"

if [[ "${device}" != "auto" && "${device}" != "cuda" && "${device}" != "cpu" ]]; then
    echo "device must be auto, cuda, or cpu" >&2
    exit 2
fi
if ! command -v "${python_bin}" >/dev/null 2>&1; then
    echo "Python command is unavailable: ${python_bin}" >&2
    exit 2
fi

export PYTHONPATH="${project_root}/src${PYTHONPATH:+:${PYTHONPATH}}"
cli=("${python_bin}" -m djrmcp_predict_v01.cli)
predict_args=()
if [[ -n "${DJRMCP_CACHE_DIR:-}" ]]; then
    predict_args+=(--cache-dir "${DJRMCP_CACHE_DIR}")
fi
case "${DJRMCP_OFFLINE:-0}" in
    0|false|FALSE|no|NO)
        ;;
    1|true|TRUE|yes|YES)
        predict_args+=(--offline)
        ;;
    *)
        echo "DJRMCP_OFFLINE must be 0/1, true/false, or yes/no" >&2
        exit 2
        ;;
esac

"${cli[@]}" validate-fasta "${input_fasta}"
"${cli[@]}" model-info
"${cli[@]}" predict "${input_fasta}" \
    --outdir "${output_dir}" \
    --device "${device}" \
    "${predict_args[@]}"
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
