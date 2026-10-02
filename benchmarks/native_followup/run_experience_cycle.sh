#!/bin/bash
set -euo pipefail
cd /opt/aimee-memory-lab/aimee-qwen
lab=/opt/aimee-memory-lab
while systemctl is-active --quiet aimee-gemma-learning-arms; do sleep 5; done
test -f "$lab/task-learning-gemma-feedback-a5-eval/DONE"
root="$lab/experience-five-gemma-r1"
python3 benchmarks/native_followup/experience_cycle.py init "$root" "$lab/task-transfer-plan-r1"
for round in 1 2 3 4 5; do
 python3 benchmarks/native_followup/experience_cycle.py prepare "$root" "$round"
 python3 benchmarks/native_followup/gemma_tasks.py "$root/r$round-plan" "$root/r$round-gemma-training" --disabled-only
 # Cross-model contribution only; Qwen is not a five-round evaluation target.
 python3 benchmarks/native_followup/qwen_tasks.py "$root/r$round-plan" "$root/r$round-qwen-training" --disabled-only
 python3 benchmarks/native_followup/experience_cycle.py select "$root" "$round"
 python3 benchmarks/native_followup/publish_tasks.py "$root/r$round-plan" "$root/r$round-selected" "$root/r$round-source"
 python3 benchmarks/native_followup/gemma_tasks.py "$root/r$round-source" "$root/r$round-eval"
 python3 benchmarks/native_followup/verify.py "$root/r$round-source" "$root/r$round-eval" > "$root/r$round-summary.json"
 python3 benchmarks/native_followup/analyze_learning_arm.py "$root/r$round-plan" "$root/r$round-source" "$root/r$round-eval" > "$root/r$round-diagnostics.json"
 if test "$round" -gt 1; then
  python3 - "$root/r$((round-1))-summary.json" "$root/r$round-summary.json" <<'CHECK'
import json,sys
old,new=[json.load(open(p))['groups']['all']['native_correct'] for p in sys.argv[1:]]
if new<old:raise SystemExit('STOP: regression; preserve for analysis')
CHECK
 fi
done
date -u > "$root/DONE"
