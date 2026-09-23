#!/bin/bash
set -euo pipefail
cd /opt/aimee-memory-lab/aimee-qwen
lab=/opt/aimee-memory-lab
while systemctl is-active --quiet aimee-matched-transfer; do sleep 10; done
test -f "$lab/matched-transfer-r1/DONE"
root="$lab/native-extensions-r1"
mkdir "$root"
# Independent task family: same frozen candidates, own-only versus shared.
p="$root/structured-plan"
python3 benchmarks/native_followup/prepare_extensions.py structured "$p" 2026092401 "$lab/general10k-source-r1/image"
python3 benchmarks/native_followup/gemma_tasks.py "$p" "$root/structured-gemma-learning" --disabled-only
python3 benchmarks/native_followup/qwen_tasks.py "$p" "$root/structured-qwen-learning" --disabled-only
for arm in own shared; do
 python3 benchmarks/native_followup/prepare_extensions.py structured-select "$p" "$root/structured-gemma-learning" "$root/structured-qwen-learning" "$root/structured-$arm-selected" "$arm"
 python3 benchmarks/native_followup/publish_tasks.py "$p" "$root/structured-$arm-selected" "$root/structured-$arm-source"
 python3 benchmarks/native_followup/gemma_exact.py "$root/structured-$arm-source" "$root/structured-$arm-eval"
 python3 benchmarks/native_followup/verify_exact.py "$root/structured-$arm-source" "$root/structured-$arm-eval" > "$root/structured-$arm-summary.json"
done
# One-round component comparisons from precisely the same saved plateau.
old="$lab/experience-five-gemma-r1"
for arm in baseline history observations transfer contributor combined; do
 p="$root/ablation-$arm"
 python3 benchmarks/native_followup/prepare_extensions.py ablation "$p-plan" "$old" "$arm"
 python3 benchmarks/native_followup/gemma_tasks.py "$p-plan" "$p-gemma-learning" --disabled-only
 donor=()
 if test "$arm" = contributor || test "$arm" = combined; then
  python3 benchmarks/native_followup/qwen_tasks.py "$p-plan" "$p-qwen-learning" --disabled-only
  donor=("$p-qwen-learning")
 fi
 python3 benchmarks/native_followup/prepare_extensions.py ablation-select "$p-plan" "$old" "$p-gemma-learning" "$p-selected" "${donor[@]}"
 python3 benchmarks/native_followup/publish_tasks.py "$p-plan" "$p-selected" "$p-source"
 python3 benchmarks/native_followup/gemma_tasks.py "$p-source" "$p-eval"
 python3 benchmarks/native_followup/verify.py "$p-source" "$p-eval" > "$p-summary.json"
done
# Fixed three replications; finish every round, including regressions, for unbiased reporting.
for seed in 2026092402 2026092403 2026092404; do
 p="$root/replication-$seed"
 python3 benchmarks/native_followup/prepare_extensions.py seed "$p-fixture" "$seed" "$lab/general10k-source-r1/image"
 python3 benchmarks/native_followup/experience_cycle.py init "$p" "$p-fixture" "Seed${seed}Birch"
 for round in 1 2 3 4 5; do
  python3 benchmarks/native_followup/experience_cycle.py prepare "$p" "$round"
  python3 benchmarks/native_followup/gemma_tasks.py "$p/r$round-plan" "$p/r$round-gemma-training" --disabled-only
  python3 benchmarks/native_followup/qwen_tasks.py "$p/r$round-plan" "$p/r$round-qwen-training" --disabled-only
  python3 benchmarks/native_followup/experience_cycle.py select "$p" "$round"
  python3 benchmarks/native_followup/publish_tasks.py "$p/r$round-plan" "$p/r$round-selected" "$p/r$round-source"
  python3 benchmarks/native_followup/gemma_tasks.py "$p/r$round-source" "$p/r$round-eval"
  python3 benchmarks/native_followup/verify.py "$p/r$round-source" "$p/r$round-eval" > "$p/r$round-summary.json"
 done
 date -u > "$p/DONE"
done
python3 benchmarks/native_followup/compare_workflows.py "$lab/matched-transfer-r1/own-eval" "$lab/matched-transfer-r1/shared-eval" > "$root/matched-transfer-comparison.json"
python3 benchmarks/native_followup/compare_workflows.py "$root/structured-own-eval" "$root/structured-shared-eval" > "$root/structured-comparison.json"
for arm in history observations transfer contributor combined; do
 python3 benchmarks/native_followup/compare_workflows.py "$root/ablation-baseline-eval" "$root/ablation-$arm-eval" > "$root/ablation-$arm-comparison.json"
done
for seed in 2026092402 2026092403 2026092404; do
 python3 benchmarks/native_followup/compare_workflows.py "$root/replication-$seed/r1-eval" "$root/replication-$seed/r5-eval" > "$root/replication-$seed-comparison.json"
done
date -u > "$root/DONE"
