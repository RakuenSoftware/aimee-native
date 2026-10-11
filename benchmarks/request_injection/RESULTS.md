# Completed injection-point experiment, 11 October 2026

All 2,592 responses completed on the RTX 5080. The fixed main fixture has
24 twelve-turn episodes, 72 distinct record versions, three initial history
lengths and three fresh-process repetitions. Weights and active state are
CUDA resident; no offload is used. The maximum recorded allocator reservation
is 11,114,905,600 bytes. The mechanism test passes direct target-position RoPE
comparison and immutable-checkpoint checks.

| Arm | Selected correct | Withdrawal correct | Old-code echoes | Unrelated correct |
|---|---:|---:|---:|---:|
| Persistent text | 369/432 | 72/216 | 144/216 | 216/216 |
| Removed text | 432/432 | 216/216 | 0/216 | 216/216 |
| Native at injection | 432/432 | 216/216 | 0/216 | 216/216 |

Counts repeat 144 selected and 72 withdrawal/unrelated turns three times.
Quality counts are identical across processes. The unrelated probes are
simple instruction-following controls; these data are not a broad distraction
benchmark. All arms receive identical instructions expiring earlier memory.
Private questions/answers are replaced by the same public notices, isolating
record retention from output-mediated influence.

Native attachment medians are 2.83, 2.87 and 3.32 ms for 128, 1,024 and 4,096
initial history tokens. Paired complete-turn savings versus removed text,
including generation and cleanup, are 22.38, 23.92 and 27.99 ms. Median first-logit
latencies are 27.18/27.73/36.80 ms native and 49.65/51.05/67.13 ms removed text.
Removing text also retains unaffected earlier history; no artificial history
rebuild is charged to that control.

Native uses 45,954 task/public-notice prefill tokens, versus 57,726 in each text
arm, and adds 5,886 preparation tokens once per bank/process. Preparing three
banks takes a median 86–87 ms per episode. Complete twelve-turn cost including
that preparation is 41.67/71.36/77.94 ms lower than removed text. Shared initial
history prefill, model loading and forensic hashing are excluded from these
incremental delivery costs.

This is a single-record default-RoPE attention implementation. It is not a
Gemma deployment, recurrent-state composition result or a new production
authorization test. Detachment discards memory-dependent task state and rebuilds
clean notices; it cannot erase information an application retains in public
outputs. Existing multi-record composition failures are unaffected.

Exact raw inputs, outputs, frozen sources and failed/development attempts remain
in `/mnt/pve/backup/aimee-experiments/request-injection-20261011-r1` on `.253`.
The paired audit is in `results/main-r1-audit.json`; the manuscript repository
contains exact copies of completed main receipts for reviewer access.
