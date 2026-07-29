#!/bin/bash
# Run this submission controller on the target PBS login node, not as a PBS job.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="${DJRMCP_PROJECT_ROOT:-${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd -P)}}"
BENCHMARK_ROOT="${PROJECT_ROOT}/benchmarks/plm_vs_classical_v0"
VENV_ROOT="${DJRMCP_VENV_ROOT:-${VENV_ROOT:-$PROJECT_ROOT/.venv-v0}}"
CONFIG_PATH="${DJRMCP_PLM_CONFIG:-$BENCHMARK_ROOT/config/benchmark.json}"
test -x "$VENV_ROOT/bin/python"
cd "${PROJECT_ROOT}"

bash "${BENCHMARK_ROOT}/pbs/smoke_test.sh"
PBS_EXPORTS="DJRMCP_PROJECT_ROOT=${PROJECT_ROOT},DJRMCP_VENV_ROOT=${VENV_ROOT},DJRMCP_PLM_CONFIG=${CONFIG_PATH}"
if [[ -n "${DJRMCP_MODULE_INIT:-}" ]]; then
    PBS_EXPORTS="${PBS_EXPORTS},DJRMCP_MODULE_INIT=${DJRMCP_MODULE_INIT}"
fi
PLM_JOB_ID="$(qsub -v "${PBS_EXPORTS}" "${BENCHMARK_ROOT}/pbs/run_plm_stage.pbs")"
CLASSICAL_JOB_ID="$(qsub -v "${PBS_EXPORTS}" "${BENCHMARK_ROOT}/pbs/run_classical_stage.pbs")"
MERGE_JOB_ID="$(qsub -v "${PBS_EXPORTS}" -W "depend=afterok:${CLASSICAL_JOB_ID}" "${BENCHMARK_ROOT}/pbs/run_classical_merge.pbs")"
SUMMARY_JOB_ID="$(qsub -v "${PBS_EXPORTS}" -W "depend=afterok:${PLM_JOB_ID}:${MERGE_JOB_ID}" "${BENCHMARK_ROOT}/pbs/run_summarize_stage.pbs")"

mkdir -p "${BENCHMARK_ROOT}/logs"
SUBMISSION_TMP="${BENCHMARK_ROOT}/logs/submission.tsv.tmp.$$"
{
    printf 'stage\tjob_id\n'
    printf 'plm\t%s\n' "${PLM_JOB_ID}"
    printf 'classical_array\t%s\n' "${CLASSICAL_JOB_ID}"
    printf 'classical_merge\t%s\n' "${MERGE_JOB_ID}"
    printf 'summarize_validate\t%s\n' "${SUMMARY_JOB_ID}"
} > "${SUBMISSION_TMP}"
mv "${SUBMISSION_TMP}" "${BENCHMARK_ROOT}/logs/submission.tsv"
cat "${BENCHMARK_ROOT}/logs/submission.tsv"
