#!/bin/bash
set -euo pipefail
cd /opt/aimee-memory-lab/aimee-qwen
lab=/opt/aimee-memory-lab
python3 benchmarks/native_followup/prepare_tasks.py "$lab/task-transfer-plan-r1" "$lab/general10k-source-r1/image"
python3 benchmarks/native_followup/gemma_tasks.py "$lab/task-transfer-plan-r1" "$lab/task-transfer-gemma-training-r1" --disabled-only
python3 benchmarks/native_followup/publish_tasks.py "$lab/task-transfer-plan-r1" "$lab/task-transfer-gemma-training-r1" "$lab/task-transfer-gemma-source-r1"
python3 benchmarks/native_followup/gemma_tasks.py "$lab/task-transfer-gemma-source-r1" "$lab/task-transfer-gemma-eval-r1"
python3 benchmarks/native_followup/qwen_tasks.py "$lab/task-transfer-plan-r1" "$lab/task-transfer-qwen-training-r1" --disabled-only
python3 benchmarks/native_followup/publish_tasks.py "$lab/task-transfer-plan-r1" "$lab/task-transfer-qwen-training-r1" "$lab/task-transfer-qwen-source-r1"
python3 benchmarks/native_followup/qwen_tasks.py "$lab/task-transfer-qwen-source-r1" "$lab/task-transfer-qwen-eval-r1"

python3 benchmarks/native_followup/verify.py "$lab/general10k-source-r1" "$lab/general10k-gemma-r1" > "$lab/general10k-gemma-summary.json"
python3 benchmarks/native_followup/verify.py "$lab/general10k-source-r1" "$lab/general10k-qwen-r1" > "$lab/general10k-qwen-summary.json"
python3 benchmarks/native_followup/verify.py "$lab/task-transfer-gemma-source-r1" "$lab/task-transfer-gemma-eval-r1" > "$lab/task-transfer-gemma-summary.json"
python3 benchmarks/native_followup/verify.py "$lab/task-transfer-qwen-source-r1" "$lab/task-transfer-qwen-eval-r1" > "$lab/task-transfer-qwen-summary.json"
python3 benchmarks/native_followup/provenance.py "$lab/task-transfer-plan-r1/execution-provenance.json"
date -u > "$lab/native-followup-r1-DONE"
