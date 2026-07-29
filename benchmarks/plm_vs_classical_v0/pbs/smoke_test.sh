#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="${DJRMCP_PROJECT_ROOT:-${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd -P)}}"
BENCHMARK_ROOT="${PROJECT_ROOT}/benchmarks/plm_vs_classical_v0"
VENV_ROOT="${DJRMCP_VENV_ROOT:-${VENV_ROOT:-$PROJECT_ROOT/.venv-v0}}"
CONFIG_PATH="${DJRMCP_PLM_CONFIG:-$BENCHMARK_ROOT/config/benchmark.json}"

cd "${PROJECT_ROOT}"
source "${DJRMCP_MODULE_INIT:-/usr/share/Modules/init/bash}"
module purge
module load Python/3.11.7
module load blast+/2.17.0 diamond/2.2.4 mmseqs2/18-8cc5c mafft/7.526 hmmer/3.4
test -x "$VENV_ROOT/bin/python"
export PATH="${VENV_ROOT}/bin:${PATH}"
export VIRTUAL_ENV="${VENV_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}/src:${BENCHMARK_ROOT}/scripts:${PYTHONPATH:-}"

python -m py_compile "${BENCHMARK_ROOT}"/scripts/*.py
python -m unittest discover -s "${BENCHMARK_ROOT}/tests" -v
python "${BENCHMARK_ROOT}/scripts/preflight_tools.py" \
    --config "${CONFIG_PATH}"
python "${BENCHMARK_ROOT}/scripts/prepare_inputs.py" \
    --config "${CONFIG_PATH}"
