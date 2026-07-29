#!/bin/bash

set -euo pipefail
if [[ "$#" -lt 1 ]]; then
    echo "usage: $0 JOB_ID [JOB_ID ...]" >&2
    exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="${DJRMCP_PROJECT_ROOT:-${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd -P)}}"
BENCHMARK_ROOT="${PROJECT_ROOT}/benchmarks/plm_vs_classical_v0"
VENV_ROOT="${DJRMCP_VENV_ROOT:-${VENV_ROOT:-$PROJECT_ROOT/.venv-v0}}"
cd "${PROJECT_ROOT}"
source "${DJRMCP_MODULE_INIT:-/usr/share/Modules/init/bash}"
module purge
module load Python/3.11.7
test -x "$VENV_ROOT/bin/python"
export PATH="${VENV_ROOT}/bin:${PATH}"
export PYTHONPATH="${BENCHMARK_ROOT}/scripts:${PYTHONPATH:-}"

arguments=()
for job_id in "$@"; do
    arguments+=(--job-id "${job_id}")
done
python "${BENCHMARK_ROOT}/scripts/collect_pbs_resources.py" \
    "${arguments[@]}" \
    --output "${BENCHMARK_ROOT}/work/pbs_job_resources.tsv"
