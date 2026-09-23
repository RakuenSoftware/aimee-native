#!/bin/bash
set -euo pipefail
cd /opt/aimee-memory-lab/aimee-qwen
lab=/opt/aimee-memory-lab
# Author cancelled Qwen; require completed Gemma baseline before new branches.
test -f "$lab/task-gated-gemma-a5-eval/DONE"
for model in gemma; do
 for arm in feedback reasoning combined; do
  if test "$model" = gemma; then
   previous_training="$lab/task-repeat-gemma-a2-training"
   previous_eval="$lab/task-repeat-gemma-a2-eval"
   previous_source="$lab/task-repeat-gemma-a2-source"
  else
   previous_training="$lab/task-gated-qwen-a2-training"
   previous_eval="$lab/task-gated-qwen-a2-eval"
   previous_source="$lab/task-gated-qwen-a2-source"
  fi
  for attempt in 3 4 5; do
   prefix="$lab/task-learning-$model-$arm-a$attempt"
   python3 benchmarks/native_followup/prepare_learning_arm.py "$lab/task-transfer-plan-r1" "$previous_training" "$previous_eval" "$previous_source" "$prefix-plan" "$attempt" "$arm"
   learning_flags=();publish_flags=()
   if test "$arm" != feedback; then learning_flags=(--reasoning);publish_flags=(--final-line);fi
   python3 "benchmarks/native_followup/${model}_learning.py" "$prefix-plan" "$prefix-training" --disabled-only "${learning_flags[@]}"
   python3 benchmarks/native_followup/publish_tasks.py "$prefix-plan" "$prefix-training" "$prefix-source" --validated-previous "$previous_source" "${publish_flags[@]}"
   python3 "benchmarks/native_followup/${model}_tasks.py" "$prefix-source" "$prefix-eval"
   python3 benchmarks/native_followup/verify.py "$prefix-source" "$prefix-eval" > "$prefix-summary.json"
   python3 benchmarks/native_followup/analyze_learning_arm.py "$lab/task-transfer-plan-r1" "$prefix-source" "$prefix-eval" > "$prefix-diagnostics.json"
   python3 - "$previous_eval" "$prefix-eval" <<'CHECK'
import json,sys
from pathlib import Path
def score(p):return sum(bool(r['correct']) for r in map(json.loads,(Path(p)/'results.jsonl').read_text().splitlines()) if r['enabled'])
if score(sys.argv[2])<score(sys.argv[1]):raise SystemExit('STOP: score declined; analyze before continuing')
CHECK
   previous_training="$prefix-training";previous_eval="$prefix-eval";previous_source="$prefix-source"
  done
 done
done
date -u > "$lab/task-learning-arms-DONE"
