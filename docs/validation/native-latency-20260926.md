# Native activation and preparation latency follow-up

This follow-up optimizes the existing private-preview path without changing
encoding, selected records, positions, trained weights, or attention semantics.
The exact bytes and complete working sets remain the correctness criteria.

## Changes

Rust now prepares the tensor-parallel read plan once, retains the admitted file
handle, and reads this rank's disjoint extents directly into one pinned staging
buffer through a bounded four-thread I/O pool. The GPU bridge performs one
completed transfer and creates segment views into the allocation. It previously
allocated and synchronously transferred each K/V segment separately. The I/O pool
is initialized during admission. There are no file opens, stat calls, hashes or
content checks in activation, and no disk operations in resident attention.

The private preparation service keeps the CPU model and tokenizer resident across
jobs. Every request still creates its own fresh KV cache, uses all selected
records in their approved order, and publishes through Rust. The existing SSH
boundary now forwards to a same-UID Unix service. Preparation and authorization
cache keys are unchanged. This does not imply arbitrary token IDs can be expanded
into model-specific memory without computation.

## Matched activation measurements

Exact compiled baseline image: r13. Optimized image: `gemma-packed-r3`, image ID
`1490fc750447f8b3c1b4aa79390ee85096e4552ffbc1afd1c332ee579e34abcf`.
Same source files, GPU, rank 0 of two ranks and BF16 memory tensors. Cold samples
run in fresh processes and verify zero OS-resident source pages before timing;
warm samples verify all source pages resident. GPU/allocator setup and integrity
admission are outside the measured interval for both paths. The optimized path's
pinned allocator is primed using unrelated zeros, not the target bank. Timings
include completed GPU transfer and view creation. Cold n=8, warm n=50 per cell.

| Bank | Condition | Baseline median | Optimized median | Reduction |
|---|---|---:|---:|---:|
| 3 records, 53 positions | Cold | 26.15 ms | 5.69 ms | 78.3% |
| 3 records, 53 positions | Warm | 6.94 ms | 1.82 ms | 73.8% |
| 32 records, 586 positions | Cold | 123.02 ms | 51.95 ms | 57.8% |
| 32 records, 586 positions | Warm | 31.89 ms | 21.16 ms | 33.7% |

Optimized p95 values are 6.51/1.99 ms for the small cold/warm bank and
62.05/21.80 ms for the large bank. With eight cold samples, the nearest-rank p95
is the maximum; this is an engineering comparison, not a precise tail guarantee.
All 96 K/V segments were byte-identical after GPU transfer. Rust tests also cover
both partitioned and replicated KV heads and old-inode retention across atomic
replacement. Resident lookup remains sub-microsecond; it is not cold activation.

The small bank reads 9,551,872 bytes per rank from an 18,239,700-byte source file.
The wide bank reads 105,611,264 bytes per rank from a 201,627,944-byte source file.
The wide engineering profile has larger host/device budgets than the default
private-preview profile. These are exact prepared states, not 424-byte token-ID
inputs. The measured cold path still does **not** meet the microsecond target.

## Preparation measurements

Three complete synthetic working sets, including a reversed order and changed
facts, produced exactly matching index metadata and payload hashes through the
one-shot and resident compilers. The first one-shot request took 33.62 seconds;
subsequent one-shot requests took 15.59 and 15.73 seconds. Resident requests took
8.70, 8.21 and 8.14 seconds. This is a small controlled preparation comparison,
not a general inference-speed claim. The first one-shot value must not be used as
the steady-state baseline. Persistent model residency consumes host RAM.

An exploratory CPU-thread sweep retained identical tensors but did not establish
a better stable setting: 8 threads were slower; 16 threads ranged from 6.95 to
24.92 seconds. The deployed worker therefore retains the 12-thread setting.

The initial real Aimee/SSH check, using a fresh test cache and all three approved
canaries, matched the prior compiler's index and payload exactly. It took 42.32
seconds while GPU model startup was running on the host; the subsequent cache hit
was 10.78 ms. This overlapping-load observation is retained separately and is not
used to claim an isolated preparation improvement. With the GPU experiments
stopped, two fresh real Aimee/SSH preparations took **9.30 and 9.11 seconds**;
cache hits took **10.58 and 10.95 ms**. Both fresh runs matched the previous
compiler's entire index and payload hash. A fresh cache directory forced each
compile without evicting production cache entries or changing source records.

A paired isolated comparison using those same 45-token canary contents gave
**16.87/18.24 seconds** for one-shot preparation and **9.08/8.98 seconds** for the
resident worker, with execution order reversed for the second pair. That is a
48.6% reduction in the two-sample medians (17.55 to 9.03 seconds), with identical
outputs. This small sample supports the startup-amortization improvement, not a
tail-latency guarantee or a claim that new preparation is now sub-second.

## Rejected attempt

The first packed implementation gathered slices through mmap and applied a
sequential-access hint. It reduced the small warm case but regressed cold latency:
37.06 ms for the small bank and 624.17 ms for the wide bank. It was not promoted.
The explicit retained-file parallel read path replaced it. Both attempts' raw
records are preserved; the regression was not discarded from the evidence.

## Validation and release status

See [raw evidence](artifacts/native-latency-20260926/). The intermediate r2 image
passed **592/592** engineering answers: 240 each for BF16 and Q8 (matrix,
concurrency and streaming), plus 112 in the 32-record Q8 suite. Final review
changed the Rust destination type to `MaybeUninit<u8>` so newly allocated pinned
buffers are only treated as initialized after successful reads. This preserves
the bytes without adding a zero-fill pass. The final r3 image is validated
separately on the shipped Q8 profile; r2's BF16 results are not relabelled as r3
results. Final r3 passed **352/352** Q8 engineering answers (240 in the
standard suite and 112 in the 32-record suite). All 32 records were encoded and
delivered together; the wider suite includes two- and three-record questions.
Rust's 21 tests and the 17 private-service tests passed. Final signed
client and release results follow below.


## Signed private-preview deployment

The final image is pinned as
`192.168.0.126:5445/aimee-native@sha256:04b6a77fa315fb60dca4bd15fcc27b20df29c2b252c4c45854c3b6aa1373ae53`.
Private-preview sequence 3 has manifest SHA-256
`96f492dd4e69c30b1f05277413ebedbe3372d2f4ba482d9e45c8c3b3269a8f99`.
The unchanged normal launcher installed it using signature and artifact checks.
The separately marked fresh candidate passed 2/2 live Aimee answers, and the
normal signed update passed another 2/2. Rollback to sequence 2 passed 2/2
using current memory, retained high-water sequence 3, and sequence 3 was restored
as the final active installation. This gives 6/6 signed lifecycle answers.
Both GPU test runtimes were stopped afterward. The private CPU compiler is enabled on
the preparation host; the Aimee core deployment and its authorization boundary
were not modified by this follow-up.

No encoder or publisher was added to the client. The consumer export audit
passed, dependencies were unchanged, and the earlier private-preview disclosure
and redistribution limits remain in force. Cold-path measurement is a release
gate with disclosed bounds, not a claim that the microsecond target passed.

## Remaining performance work

The aggregate timings do not attribute every microsecond to storage, staging,
DMA, synchronization or tensor-view construction. Those components need separate
measurements before selecting the next optimization. The current exact-state
path still transfers 9.55 MB or 105.61 MB per rank in these cases. A smaller
intermediate representation must demonstrate both faster reconstruction and
unchanged memory behavior before replacing it. Moving preparation or activation
ahead of a request may reduce visible latency, but must be reported separately
from an actual reduction in cold activation cost.

Persistent CPU residency removes repeated startup, not the model computation for
a new working set. Fresh preparation remains seconds. This follow-up does not
claim completion of the microsecond cold-application target.
