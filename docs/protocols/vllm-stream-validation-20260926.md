# Released native runtime: real-model latency validation

The user authorized dual-7900XTX testing on 2026-09-26. CT101 runs the exact
release-5 image `fc1149fc3c58e40dd2e367f97df6e0a0892bd58a3fab9530b47de8b03b427dc4`
with Gemma 4 12B Q8 GGUF, vLLM tensor parallelism 2. No Qwen run is scheduled.

Remote run directory: `/opt/aimee-memory-lab/vllm-stream-validation-20260926`.
The detached `run.py` records progress in `status.json`; each stage has its own
log and original JSON evidence. Stages run sequentially to avoid GPU contention.

1. 336 real HTTP streaming responses: three rounds of 56 question groups paired
   between native and text memory, alternating order. All 32 authorized synthetic
   records are provided in both conditions. Groups query one, two or three facts.
   Record answer correctness, first nonempty content latency, whole-request
   latency, prompt/completion tokens and final per-worker runtime metrics.
2. Small-bank and wide-bank activation probes: each 20 fresh-process cold samples
   and 100 warm samples, plus resident reuse observations. `mincore` verifies
   coldness of the actual read source. Capture native phase profiles and verify
   complete GPU tensor bytes after measurement.

Serving latency includes HTTP, scheduling and model generation; it does not
isolate native activation. First content is not necessarily the first internal
model token. The first native serving request is initially GPU-nonresident;
OS-disk coldness is NOT asserted for serving requests. Only the separately
conditioned activation probes establish disk-cold measurements. Model loading,
publication/encoding and initial admission are outside those activation timings.
Warm serving permits normal runtime caching in both conditions; repeat-round
latency must be reported separately from the first round. This is an engineering
fixture comparison, not a population general-knowledge benchmark or live Aimee
selection/authorization measurement.

Status at launch: running; no new result is claimed yet.

Completed: all stages passed. See the corresponding validation report.
