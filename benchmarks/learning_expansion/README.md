# Native consumption and retained-learning expansion

This campaign extends the completed request-injection experiment. It does not
reuse the withdrawn independent multi-record composition result.

The first runnable study crosses 100, 250, 500, 1,000 and 2,000 serialized
memory tokens with 0, 1,024 and 4,096 additional public-history tokens. Each
24-turn episode has six revisioned records and two selected uses per record,
withdrawal probes and unrelated two-digit addition. Persistent context retains
record blocks; removed text and native retain the same unaffected public-history
checkpoint and reconstruct the same public completion notice. Native attaches
one independently prepared bank after history, with no BOS in the memory block.
History token counts always include the actual system/chat prefix separately.

The pilot has four episodes, 288 responses. The frozen main has thirty episodes
(two value positions per size/history cell), three rotated process repetitions
and 6,480 responses. Repeats do not create independent tasks. BF16 is a separate
profile from the original FP32 study; weights and active state must fit on the
RTX 5080. Padding tests size pressure, not dense-document comprehension.

The queue waits for the occupied GPU, runs FP32/BF16 mechanism tests, then the
pilot, coverage/accounting checks and main repetitions. It never kills another
job. Source and main/pilot fixtures are frozen before the pilot is read. An
incomplete/failed run remains in its own directory and is not pooled.

All output: `/mnt/pve/backup/aimee-experiments/learning-expansion-20261011-r3`.
No large output or model download goes to the host root filesystem. Use the
pinned clean-release Python environment and local frozen Qwen checkpoint.

Accounting separates bank preparation, initial history, memory text prefill,
task prefill, decode and cleanup. The attention metric is causal query-key pairs
across layers, verified against the counters; it is not FLOPs or a kernel
profile. Actual checkpoint bytes are checked against layout. Byte-seconds are
stage-endpoint proxies, not complete integration of all live allocations.
One-second GPU power samples accompany each process; forensic hashing, load and
idle time must be separated before any energy-per-task headline.

Window headroom is logged; a 24-turn run that never reaches the limit does not
prove a window-saturation boundary. A separate boundary experiment and fixed
VRAM concurrency sweep remain on the roadmap. No free-request/mid-generation
access, deployment-learning gain or small-versus-large cost crossover is inferred
from this synthetic pressure study.
