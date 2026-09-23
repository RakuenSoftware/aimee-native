#!/bin/bash
set -euo pipefail
cd /opt/aimee-memory-lab/aimee-qwen
lab=/opt/aimee-memory-lab
old="$lab/experience-five-gemma-r1"
root="$lab/matched-transfer-r1"
test -f "$old/DONE"
python3 benchmarks/native_followup/prepare_matched_transfer.py "$old" "$root"
for arm in own shared; do
 python3 benchmarks/native_followup/publish_tasks.py "$old/r1-plan" "$root/$arm" "$root/$arm-source"
 python3 benchmarks/native_followup/gemma_tasks.py "$root/$arm-source" "$root/$arm-eval"
 python3 benchmarks/native_followup/verify.py "$root/$arm-source" "$root/$arm-eval" > "$root/$arm-summary.json"
done
date -u > "$root/DONE"
