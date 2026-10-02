#!/bin/bash
set -euo pipefail
cd /opt/aimee-memory-lab/aimee-qwen
lab=/opt/aimee-memory-lab
root=$lab/native-text-20260924-r1
mkdir "$root"
# Gates are outside the scored cohort. Neither model's outputs alter fixtures.
python3 benchmarks/native_vs_text/run_gemma.py "$lab/general10k-source-r1" "$root/gemma-smoke" --limit 6 --smoke
for kind in procedures personal general; do
 case "$kind" in
 procedures) source=$lab/experience-five-gemma-r1/r5-source; filter=();;
 personal) source=$lab/native-scale-r2; filter=(--source-type personal);;
 general) source=$lab/general10k-source-r1; filter=();;
 esac
 python3 benchmarks/native_vs_text/run_gemma.py "$source" "$root/gemma-$kind" "${filter[@]}"
done
python3 benchmarks/native_vs_text/run_qwen.py "$lab/general10k-source-r1" "$root/qwen-smoke" --smoke
for kind in procedures personal general; do
 case "$kind" in
 procedures) source=$lab/experience-five-gemma-r1/r5-source; filter=();;
 personal) source=$lab/native-scale-r2; filter=(--personal);;
 general) source=$lab/general10k-source-r1; filter=();;
 esac
 python3 benchmarks/native_vs_text/run_qwen.py "$source" "$root/qwen-$kind" "${filter[@]}"
done
date -u > "$root/DONE"
