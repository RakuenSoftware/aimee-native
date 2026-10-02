# SWE native-learning failure and repair validation

The original campaign was stopped after 180 attempt records. Its results are
not evidence of successful learning: native rounds frequently collapsed into
repeated `thought` output instead of executable actions. All original results,
trajectories, experiences and preparation identities remain preserved in the
[private evidence archive](artifacts/swe-diagnosis-20260927/). They are not merged
with subsequent repair runs.

| Original arm | Finished | Resolved | Grader infrastructure failures | Repeated format-error exits |
|---|---:|---:|---:|---:|
| Control | 32 | 2 | 2 | 0 |
| Learning 1, empty memory | 32 | 3 | 0 | 1 |
| Learning 2 | 32 | 2 | 0 | 22 |
| Learning 3 | 28 | 0 | 0 | 18 |
| Learning 4 | 28 | 0 | 0 | 23 |
| Learning 5 | 28 | 1 | 0 | 18 |

The unequal partial denominators must remain visible. These figures do not
estimate an independent effect of learning. A four-minute attempt budget also
ended most baseline attempts before voluntary submission.

## Controlled diagnosis

First-action replays of the first four tasks returned one valid bash block in
all no-memory, text-memory and native-memory conditions. The failure developed
later in the conversation. Replaying the captured histories immediately before
the first format error reproduced the repeated-output failure in Django,
Matplotlib and Seaborn with native memory; the corresponding no-memory and
same-record text-memory responses each contained one valid command.

These are post-hoc debugging probes, not new SWE scores. The same model, saved
conversation, lesson and sampling settings were held fixed across each probe.

| Diagnostic variant | Repeated-output cases among those three |
|---|---:|
| Original native path, BF16 preparation | 3/3 |
| Custom attention with memory contribution disabled | 0/3 |
| Local memory respects the local window, BF16 preparation | 1/3 |
| Original attention, FP32 preparation | 3/3 |
| Local-window correction and FP32 preparation | 0/3 |

The no-memory ablation is only a diagnostic control; it cannot demonstrate
native memory capability. The corrected combination returned one command in
each of the three failing histories. A fourth Astropy history returned two
alternative commands, also observed with text memory; that remains an ordinary
formatting error, not a claim of universal protocol compliance.

The original kernel exposed all negative-position memory keys indefinitely in
local attention layers. The correction applies their trained positional window
to memory as well as text. Global attention layers retain the complete selected
bank at every position. All records remain encoded; none is filtered out to make
the test pass. This changes attention semantics and must be identified as a new
runtime profile. It is not a bit-identical performance optimization.

The diagnostic kernels passed 48 dense-reference comparisons across both GPUs,
both head geometries, both supported block-table strides, three-request batches,
single-query and 17-query chunks, including lengths 1,024 and 1,321. A separate
18-case GPU test covered scrambled text pages, empty and nonempty memory banks,
partial and expired local memory, and logit softcapping. Its largest absolute
BF16 error against the FP32 dense reference was 0.001953125.

## Retaining actual memory consumption

With the corrected combination, a three-record synthetic bank supplied a vault
code, project codename and drink. **All three records were recovered together at
each of five prompt lengths: 33, 833, 1,633, 4,033 and 7,033 tokens.** Native and
text memory each passed 5/5; no memory passed 0/5. Text memory added 46 prompt
tokens per request. This narrow recall gate checks that removing the loop did
not simply disable memory, including beyond the local window. It is not a new
large-scale knowledge or latency benchmark.

## Preparation bottleneck

Resident logs attribute nearly all of the original approximately three-minute
preparations to computation. Response transfer was approximately 0.1–0.2 seconds.
The Threadripper 3970X lacks accelerated BF16 instructions. The private compiler
now supports FP32 computation, exporting BF16 tensors in the same storage format,
under a distinct encoding identity. It does not change the serving model weights.

| Same captured lesson | Original preparation | FP32 preparation |
|---|---:|---:|
| Astropy | 189.0 s | 48.5 s |
| Django | 174.4 s | 37.3 s |
| Matplotlib | 184.2 s | 36.1 s |
| Seaborn | 183.6 s | 30.2 s |

The medians are approximately 183.9 s and 36.7 s (5.0×), with concurrent diagnostic
activity during the FP32 series. Two earlier isolated preparations of the Astropy
lesson took 27.3 s and 24.3 s. These are engineering observations, not controlled
production latency estimates. All four payload sizes stayed unchanged. FP32
requires more model RAM and changes arithmetic; faster computation alone is not
a correctness proof. Seven compiler transport/recovery tests also passed.

Reports now split input readiness, forward computation, BF16 export, Rust
publication and response transport. No model execution or integrity work was
added to the serving hot path. Preparation is still measured in seconds, not
microseconds; it remains separate from loading or applying an existing memory.

## Restart gate and deployment boundary

The runner now records response finish reasons and prompt/response hashes, gives
explicit recovery feedback when a response is truncated, and stops if at least
half of a four-task native group exhausts formatting recovery. It preserves the
failed attempts. A separate run root prevents repaired attempts from inheriting
old scores or trajectories. The original task selection remains frozen.

The wrapper also lost rejected assistant responses from model-visible history:
the parser raises before the upstream agent records the response. The correction
uses the existing exception interface to retain that assistant response before
the error feedback, without executing either of multiple ambiguous actions.
Three protocol tests passed for multiple actions, truncation and a valid command.

Full clean-checkout native replays of the four diagnosed tasks completed with
**zero repeated-format-error exits and zero repeated-output loops**, but **0/4
tasks solved**. All four reached the original wall limit; three had no source
patch. Ordinary format errors occurred and recovered. These replays used the
attention/precision repairs before the rejected-response history fix. They and
the diagnostic probes are development evidence, not held-out evaluation.

A separate calibration now uses the first eight frozen tasks, a 600-second wall
limit, the same 40-step cap, one control and three learning passes (32 attempts).
Every arm gets the same revised budget and protocol. This is a budget calibration
before resuming the 150-task campaign, not a replacement for it. The original
900-attempt campaign remains stopped. The new root is
`/opt/swe-native/calibration-20260927` on CT113; its manifest, results and native
lineage are separate. No improvement or completion is asserted in advance.
Neither diagnosis nor a numerical kernel pass establishes a learning effect.

Only the isolated research engine has the corrected binary bank so far. The
signed release-5 customer image has not been silently replaced or recertified.
The source correction also covers that profile, but a production release remains
gated on the sustained-interaction checks and a new certified artifact. The
original private preparation service has been restored; FP32 experiments use a
separate service and encoding revision.
