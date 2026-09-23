#!/bin/bash
set -euo pipefail
cd /opt/aimee-memory-lab/aimee-qwen
lab=/opt/aimee-memory-lab
for model in gemma qwen; do
  if test "$model" = gemma; then
    rounds='3 4 5'
    previous_training="$lab/task-repeat-gemma-a2-training"
    previous_eval="$lab/task-repeat-gemma-a2-eval"
    previous_source="$lab/task-repeat-gemma-a2-source"
  else
    rounds='2 3 4 5'
    previous_training="$lab/task-transfer-qwen-training-r1"
    previous_eval="$lab/task-transfer-qwen-eval-r1"
    previous_source="$lab/task-transfer-qwen-source-r1"
  fi
  for attempt in $rounds; do
    prefix="$lab/task-gated-$model-a$attempt"
    if test "$model" = gemma && test "$attempt" -eq 3; then
      # Replay the exact recorded proposals: isolate the new acceptance gate.
      plan="$lab/task-repeat-gemma-a3-plan"
      training="$lab/task-repeat-gemma-a3-training"
    else
      extra=()
      if test -f "$previous_source/selected-procedures.json"; then extra=(--accepted-source "$previous_source"); fi
      plan="$prefix-plan"
      training="$prefix-training"
      python3 benchmarks/native_followup/prepare_retry.py "$lab/task-transfer-plan-r1" "$previous_training" "$previous_eval" "$plan" "$attempt" "${extra[@]}"
      python3 "benchmarks/native_followup/${model}_tasks.py" "$plan" "$training" --disabled-only
    fi
    python3 benchmarks/native_followup/publish_tasks.py "$plan" "$training" "$prefix-source" --validated-previous "$previous_source"
    python3 "benchmarks/native_followup/${model}_tasks.py" "$prefix-source" "$prefix-eval"
    python3 benchmarks/native_followup/verify.py "$prefix-source" "$prefix-eval" > "$prefix-summary.json"
    python3 - "$previous_eval" "$prefix-eval" <<'CHECK'
import json,sys
from pathlib import Path
def score(p):
 rows=[json.loads(x) for x in (Path(p)/'results.jsonl').read_text().splitlines()]
 return sum(bool(r['correct']) for r in rows if r['enabled'])
before,after=map(score,sys.argv[1:]);print(json.dumps(dict(previous_correct=before,current_correct=after)),flush=True)
if after<before:raise SystemExit('STOP: native task success declined; preserve results for analysis')
CHECK
    previous_training="$training"
    previous_eval="$prefix-eval"
    previous_source="$prefix-source"
  done
done
date -u > "$lab/task-gated-retries-DONE"
