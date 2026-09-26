# Streaming activation and transient GPU residency

This follows [the Rust runtime release](native-runtime-ownership-20260926.md).
All changes remain in the private aimee-qwen repository. vLLM, model weights,
attention mathematics, record selection and authority policy are unchanged.

## Outcome and scope

Parallel reads and overlap with GPU transfer improve activation, including the
previous wide-bank warm-read regression. Per-upload staging accounting permits
more complete banks to remain resident. The cold microsecond target is **not
met**: the final compiled image measured 3.52 ms for the small bank and 31.40 ms
for the wide bank. Already-resident cache reconciliation measured 8.11–8.22 µs;
that is a different operation and excludes selection, loading and attention.

## Implementation

The owned transport arena keeps its descriptor and RAM index. Four existing Rust
I/O workers read disjoint 1 MiB chunks directly into pinned staging memory. A
completion queue returns each complete range to the caller's thread; the narrow
ATen bridge submits that range on the caller's current GPU stream while other
reads continue. Decoding begins after every range is submitted. No opening,
stat, hashing, content validation or model encoding is added to activation.

The queue preserves byte-range ownership, not record semantics: every selected
bank byte still arrives. Partial reads retry to completion; failures drain/join
all readers and complete submitted GPU work before releasing buffers. The worker
cache is poisoned on failed activation. Rust tests check short reads, complete
range coverage, padding/index bytes and callback thread identity. The existing
read pool is initialized with the admitted rank plan, before activation.

`pipeline_transport: false` retains parallel reads but separates reading from
upload. `lossless_transport: false` selects raw transport. These are diagnostic
and workload controls; the default enables the measured pipeline.

GPU accounting now distinguishes persistent dense bytes from temporary encoded
input. Rust uploads banks sequentially, ordering larger staging requirements
first. The staging charge ends when that upload completes. If the remaining
budget cannot fit encoded staging, that upload uses the same exact bank's raw
representation. It does not evict an otherwise fitting idle bank solely to make
room for compression. Active pins remain protected and rejected dense working
sets leave residency unchanged.

Frontend admission reserves dense bytes; workers enforce the actual per-upload
peak. Frontend size accounting therefore no longer authors unused compressed
transport copies. Each worker uses its own rank plan. An intermediate build's
redundant rank-zero lookup on rank one was corrected before promotion; a real
GPU test now asserts that no second rank plan is created during reconciliation.

## Matched activation measurements

The initial compiled streaming image compared raw transport, parallel compressed
reads, and pipelined compressed reads. Each mode used six fresh-process cold
trials and 30 warm trials on the same dual-7900XTX engineering host. Coldness was
checked with `mincore` on the actual read source. Every run checked all 96 tensor
segments after activation. GPU/runtime warmup, initial integrity admission and
transport authoring are outside activation. Modes ran sequentially, not randomly.
The activation probes time rank zero; full serving tests exercise both ranks.
These figures are not complete TP2 answer latency. They are engineering
measurements, not population latency guarantees.

| Median operation | Raw | Parallel compressed | Pipelined compressed |
|---|---:|---:|---:|
| 3-record cold activation | 5.38 ms | 4.10 ms | 3.53 ms |
| 3-record warm activation | 1.55 ms | 1.46 ms | 1.31 ms |
| 32-record cold activation | 51.37 ms | 37.56 ms | 31.57 ms |
| 32-record warm activation | 15.91 ms | 14.19 ms | 11.54 ms |

Parallel reads alone removed the warm wide-bank regression. Pipelining improved
both cold and warm medians further. A cold wide pipelined trial took 80.51 ms;
all observations remain in the record, and no tail-latency guarantee follows.

The corrected final compiled image repeated pipeline measurements: 3.52/1.25 ms
small cold/warm and 31.40/10.73 ms wide cold/warm. Its native library is byte-for-
byte identical to the initial streaming library; the compiled Python bridge
corrects rank-local accounting. The previous release's separate measurement was
4.06/1.49 ms small and 37.30/17.43 ms wide. Cross-release figures are historical
comparisons; the three-mode table is the matched implementation comparison.

The wide rank still reads 79,484,370 bytes and transfers 80,036,184 bytes including
its RAM index before reconstructing 105,611,264 dense bytes. Overlap hides much
of transfer behind reading, but does not eliminate those bytes. At the measured
throughputs, scheduling improvements cannot turn that cold payload into a
microsecond load. Reaching that target would require avoiding the cold load or
a substantially different exact representation; this work does not claim either.

## Real GPU budget and residency checks

Two complete fixture banks contain 18,743,296 dense bytes per rank. The previous
accounting charged approximately 33.0 MB for both banks and their staging. Under
a 19,791,872-byte budget, the new planner:

- Loads both banks, using compressed transport for one and raw fallback for one.
- Measures a framework-managed GPU allocation peak of 18,743,296 bytes on each GPU.
- Retains both banks through repeated alternating and simultaneous requests,
  with two initial uploads and zero evictions or subsequent uploads.
- Checks all 384 rank/segment combinations against their original tensor bytes.
- Returns framework-managed GPU allocations to baseline after closing the cache and stores.

These allocation checks use the framework allocator counters. They exclude
model/text KV, driver allocations and allocator-reserved capacity, as does the
native payload budget. They are not measurements of total device VRAM.

One thousand already-resident reconciliations per GPU measured median 8.11 and
8.22 µs, with p95 8.30 and 8.33 µs. This includes the compiled Python bridge,
serialization and Rust residency policy. It excludes authority/selection, a cold
load, pointer-table construction, native attention and model generation. Better
retention increases access to this path; it does not redefine cold activation.

## Validation record

The Rust suite passes 33 tests, including transient staging release, raw fallback
without unnecessary eviction, upload order, and streamed read failure handling.
The compiled control suite passes 26 tests. Every BF16 bit pattern is checked on
both GPUs with nondefault streams and raw fallback. The unchanged native library
also completed 100 activation/eviction ownership cycles without retained GPU
allocation. The final image repeats the exact-bit and actual-budget controls.

An intermediate serving run was explicitly interrupted after identifying the
rank-plan issue; it is not counted as final certification. The final image's
serving and signed rollout evidence is recorded separately below.

[Machine-readable evidence](artifacts/native-streaming-20260926/) retains both
compiled activation series, controls, original observations and release checks.

## Final private rollout

The corrected image passed 352/352 serving checks: 240 standard checks and 112
wide-bank checks. Fresh candidate installation, normal signed update and rollback
to sequence 4 each passed two live canary answers (6/6). Sequence 5 was restored
as the final active release, with high-water sequence 5 retained. Its manifest is
`d56c92bfade06bf91ad6cb713d04fe791815b65350f4414f91cd82514554960b`.

The publisher, private compiler, authority and launcher are unchanged. Their prior
preparation and authorization evidence is explicitly retained in the release gates.
GPU test containers are stopped and the Aimee services remain healthy. Public
redistribution is not cleared. No microsecond cold-load claim is made.
