#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="${DJRMCP_PROJECT_ROOT:-${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd -P)}}"
CONFIG="${DJRMCP_DATASET_CONFIG:-${CONFIG:-$PROJECT_ROOT/configs/v0_dataset.json}}"
WORK_DIR="${WORK_DIR:-$PROJECT_ROOT/data/interim/v0}"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_ROOT/data/processed/v0}"
THREADS="${NCPUS:-8}"

cd "$PROJECT_ROOT"
if ! type module >/dev/null 2>&1; then
  source "${DJRMCP_MODULE_INIT:-/usr/share/Modules/init/bash}"
fi
module load Python/3.11.7
module load mmseqs2/18-8cc5c

if [[ -e "$OUTPUT_DIR" ]]; then
  echo "Refusing to overwrite existing V0 output: $OUTPUT_DIR" >&2
  exit 2
fi

python3 scripts/build_v0_dataset.py prepare \
  --config "$CONFIG" \
  --work-dir "$WORK_DIR"

mkdir -p "$WORK_DIR/mmseqs"

mmseqs easy-cluster \
  "$WORK_DIR/component_input.faa" \
  "$WORK_DIR/mmseqs/global" \
  "$WORK_DIR/mmseqs/tmp" \
  --min-seq-id 0.30 \
  -c 0.80 \
  --cov-mode 0 \
  --cluster-mode 1 \
  --threads "$THREADS"

# easy-cluster is a fast seed graph, but its greedy/prefilter path can miss
# qualifying cross-split edges.  Add a sensitive all-vs-all search and union
# every 30%-identity/80%-bidirectional-coverage edge before assigning splits.
mmseqs easy-search \
  "$WORK_DIR/component_input.faa" \
  "$WORK_DIR/component_input.faa" \
  "$WORK_DIR/mmseqs/full_search.tsv" \
  "$WORK_DIR/mmseqs/full_search_tmp" \
  -s 7.5 \
  --min-seq-id 0.30 \
  -c 0.80 \
  --cov-mode 0 \
  --max-seqs 50000 \
  --format-output 'query,target,pident,qcov,tcov,alnlen,evalue,bits' \
  --threads "$THREADS"

python3 scripts/build_v0_dataset.py finalize \
  --config "$CONFIG" \
  --work-dir "$WORK_DIR" \
  --cluster-tsv "$WORK_DIR/mmseqs/global_cluster.tsv" \
  --search-tsv "$WORK_DIR/mmseqs/full_search.tsv" \
  --output-dir "$OUTPUT_DIR"

echo "V0 dataset completed: $OUTPUT_DIR"
