#!/usr/bin/env bash
set -euo pipefail

MODEL_ID="${1:?usage: run_validation_family_robustness_v0_schema4_workstation.sh MODEL_ID GPU_INDEX PROJECT_ROOT INPUT_ROOT OUTPUT_ROOT}"
GPU_INDEX="${2:?missing physical GPU index}"
PROJECT_ROOT="${3:?missing workstation project root}"
INPUT_ROOT="${4:?missing transferred legal-input root}"
OUTPUT_ROOT="${5:?missing persistent output root}"

if [[ "$MODEL_ID" != "esm2_650m" && "$MODEL_ID" != "esmc_6b" ]]; then
    echo "MODEL_ID must be esm2_650m or esmc_6b" >&2
    exit 2
fi
if [[ "$GPU_INDEX" != "0" && "$GPU_INDEX" != "1" ]]; then
    echo "GPU_INDEX must be 0 or 1" >&2
    exit 2
fi
for value in "$PROJECT_ROOT" "$INPUT_ROOT" "$OUTPUT_ROOT"; do
    if [[ "$value" != /* || "$value" == "/" ]]; then
        echo "All roots must be non-root absolute paths: $value" >&2
        exit 2
    fi
done

RUNTIME_ROOT="${DJRMCP_RUNTIME_ROOT:-/dev/shm/djrmcp_model_benchmark}"
PYTHON="$RUNTIME_ROOT/.venv-esm3/bin/python"
if [[ "$MODEL_ID" == "esm2_650m" ]]; then
    PYTHON="$RUNTIME_ROOT/.venv-bench/bin/python"
fi

cd "$PROJECT_ROOT"
test -x "$PYTHON"
test -f "$INPUT_ROOT/member_manifest.tsv"
test -f "$INPUT_ROOT/member_sequences.faa"
test -f "$INPUT_ROOT/summary.json"
test -f "$INPUT_ROOT/CHECKSUMS.sha256"
(
    cd "$INPUT_ROOT"
    sha256sum -c CHECKSUMS.sha256
)

export CUDA_VISIBLE_DEVICES="$GPU_INDEX"
export HF_HOME="$RUNTIME_ROOT/huggingface"
export PIP_CACHE_DIR="$RUNTIME_ROOT/pip-cache"
export TMPDIR="$RUNTIME_ROOT/tmp"
export PYTHONPATH="$PROJECT_ROOT/src:${PYTHONPATH:-}"
export PYTHONHASHSEED=20260724
mkdir -p "$OUTPUT_ROOT" "$TMPDIR"

OUTPUT_DIR="$OUTPUT_ROOT/hardnegative_matched_${MODEL_ID}"
RECEIPT="$OUTPUT_ROOT/${MODEL_ID}_embedding_receipt.json"
LOG="$OUTPUT_ROOT/${MODEL_ID}_embedding.log"
"$PYTHON" scripts/embed_validation_family_robustness_v0_schema4.py \
    --config configs/validation_family_robustness_v0_schema4.yaml \
    --model-id "$MODEL_ID" \
    --manifest "$INPUT_ROOT/member_manifest.tsv" \
    --fasta "$INPUT_ROOT/member_sequences.faa" \
    --output-dir "$OUTPUT_DIR" \
    --receipt "$RECEIPT" \
    --device cuda >"$LOG" 2>&1

(
    cd "$OUTPUT_DIR"
    sha256sum -c CHECKSUMS.sha256
)
echo "complete model=$MODEL_ID gpu=$GPU_INDEX output=$OUTPUT_DIR receipt=$RECEIPT"
