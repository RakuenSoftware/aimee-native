#!/bin/bash
set -euo pipefail
cd /opt/aimee-memory-lab/aimee-qwen
lab=/opt/aimee-memory-lab
# Start only after the original paired study and its verification have completed.
while systemctl is-active --quiet aimee-task-transfer-r2; do sleep 20; done
test -f "$lab/native-followup-r1-DONE"
for model in gemma qwen; do
  for attempt in 2 3 4 5; do
    if test "$attempt" -eq 2; then
      previous_training="$lab/task-transfer-$model-training-r1"
      previous_eval="$lab/task-transfer-$model-eval-r1"
    else
      previous=$((attempt-1))
      previous_training="$lab/task-repeat-$model-a$previous-training"
      previous_eval="$lab/task-repeat-$model-a$previous-eval"
    fi
    prefix="$lab/task-repeat-$model-a$attempt"
    python3 benchmarks/native_followup/prepare_retry.py "$lab/task-transfer-plan-r1" "$previous_training" "$previous_eval" "$prefix-plan" "$attempt"
    python3 "benchmarks/native_followup/${model}_tasks.py" "$prefix-plan" "$prefix-training" --disabled-only
    python3 benchmarks/native_followup/publish_tasks.py "$prefix-plan" "$prefix-training" "$prefix-source"
    python3 "benchmarks/native_followup/${model}_tasks.py" "$prefix-source" "$prefix-eval"
    python3 benchmarks/native_followup/verify.py "$prefix-source" "$prefix-eval" > "$prefix-summary.json"
  done
done
date -u > "$lab/task-repeat-a2-a5-DONE"
