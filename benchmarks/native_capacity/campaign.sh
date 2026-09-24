#!/bin/bash
set -euo pipefail
cd /opt/aimee-memory-lab/aimee-qwen
lab=/opt/aimee-memory-lab
prior=$lab/native-text-20260924-r1
while systemctl is-active --quiet aimee-native-text-campaign.service; do sleep 30; done
test -f "$prior/DONE"
root=$lab/native-capacity-20260924-r1
mkdir "$root"
cp benchmarks/native_capacity/source-provenance.json "$root/source-provenance.json"
python3 benchmarks/native_capacity/run_gemma.py "$prior/personal-source" "$root/personal-smoke" --smoke
python3 benchmarks/native_capacity/run_gemma.py "$lab/general10k-source-r1" "$root/general-smoke" --smoke
python3 benchmarks/native_capacity/run_gemma.py "$prior/personal-source" "$root/personal" --limit 625
python3 benchmarks/native_capacity/run_gemma.py "$lab/general10k-source-r1" "$root/general" --limit 625
date -u > "$root/DONE"
