# Rust activation ownership and exact preparation reuse

This follows [the packed-activation release](native-latency-20260926.md). It fixes
the runtime boundary: Rust owns staging allocation, read orchestration, completed
GPU transfer and tensor-view layout. A small C++ shim calls the installed ATen
runtime. Python makes one activation call and wraps the already-created tensors
for vLLM. No PyTorch implementation, vLLM fork or model encoder is added to the
client. Model loading, tokenization and model execution in the private compiler
continue to use the existing framework APIs.

## Activation profile

The preceding compiled r3 release was measured with six fresh-process cold trials
and 30 warm trials per bank. Cold source page residency was checked; GPU and
allocator setup were excluded. All 96 K/V segments were checked after transfer.
The stage measurements are diagnostic and their separate medians need not sum to
the total median.

| Stage, median | 3-record cold | 32-record cold |
|---|---:|---:|
| Read selected rank data into pinned memory | 4.25 ms | 42.63 ms |
| GPU submission and completion wait | 0.89 ms | 8.22 ms |
| Tensor-view construction | 0.29 ms | 0.31 ms |
| Total activation | 5.77 ms | 51.65 ms |

The Rust-owned prototype measured 5.50/51.73 ms total cold activation. Its tensor
views took 0.15/0.16 ms. Warm totals were 2.04/21.90 ms. These measurements support
the ownership correction and reduced view overhead; they do not establish a
material large-bank activation speedup. The bytes read/transferred remain the
main cost. Device-resident lookup is separate from activation.

The ownership test completed 100 activation/eviction cycles with zero retained
GPU allocation afterward. A tensor remained valid after closing its Rust store,
and released its allocation when its last Python owner was dropped. This checks
the transfer of tensor ownership across the language boundary.

## Preparation reuse boundary

Rust compares the exact token prefix and binds reuse to recipient, authorized
view, model revision, runtime profile, encoding revision and position policy.
Total token length must match because the negative-position convention depends
on that length. A length change cannot silently reuse differently positioned
states. Only the previous complete cache is retained. Unsupported shared-KV,
bidirectional or truncated sliding-window cases use full preparation.

The private model bridge clones the approved prefix into a fresh framework cache,
evaluates only the suffix through the existing backbone API, and publishes all
selected records through the existing Rust publisher. It skips the unused
vocabulary projection. The Rust reuse decision commits only after successful
model evaluation. Every external request still goes through Aimee authorization
and publication; a computational cache is not an authorization cache.

The first 39-token probe reused 34 tokens. Full evaluation took 7.58 seconds and
suffix evaluation 1.04 seconds, with identical bytes across every K/V tensor.
The nine-case comparison passed exact equality of every K/V tensor. Length,
recipient and authorized-view changes correctly reused zero tokens. For a
32-record, 586-token bank, a tail update reused 578 tokens and evaluated eight:
222.94 seconds became 2.86 seconds. Fully fresh wide preparation was 219.94 versus
232.11 seconds; this is no improvement for an arbitrary new bank. The scope/view
binding is deliberately conservative: if publication changes the authorized view,
this optimization does not apply even when some content is unchanged.

## Transport experiment

Whole-segment deduplication found no duplicate K/V segments in either bank.
The lossless format preserves every BF16 bit, including NaNs and signed zero.
CPU decompression was tested twice and was slower than raw activation; those
failed candidates remain in the evidence. The deployed candidate instead uses
small compiled HIP kernels to decode the transport representation on the GPU.
This is representation decoding, not neural encoding or a replacement framework.

Rust authors immutable transport extents at admission, in one worker-owned file
with a retained descriptor and a RAM extent index. Activation performs no file
opening, stat, hashing or content validation. Read failure is still reported.
The original admitted bank remains the fallback if compression, arena capacity,
or the combined dense-plus-staging GPU budget makes coding unsuitable.

| Per-rank measurement | 3 records / 53 positions | 32 records / 586 positions |
|---|---:|---:|
| Dense transfer bytes | 9,551,872 | 105,611,264 |
| Encoded disk extent bytes | 7,198,332 | 79,484,370 |
| Encoded transfer bytes, including RAM index | 7,267,156 | 80,036,184 |
| Raw cold activation | 5.42 ms | 51.72 ms |
| Encoded cold activation | 4.06 ms | 37.30 ms |
| Raw warm activation | 1.66 ms | 16.33 ms |
| Encoded warm activation | 1.49 ms | 17.43 ms |
| Encoded transport preparation, outside activation | 22.80 ms | 234.71 ms |

These final measurements use the compiled client in the signed sequence-4 image:
six fresh-process cold trials and 30 warm trials per bank and mode. They ran after
our build, deployment and storage-maintenance jobs finished. Earlier source-bridge
measurements remain in `native-runtime-r3`; a wheel build overlapped part of that
earlier series, so the table above uses the later compiled-client series.
Coldness was checked with `mincore` on the actual encoded arena extent or raw
source file, not on a different file. Each run checked all 96 output segments
against the original tensor bytes. The tested path includes Rust allocation,
read, transfer, decode, completion, views and Python object wrapping. Diagnostic
profiling is enabled in this comparison. GPU runtime/allocator warmup, integrity
admission and transport authoring are outside activation; none is free or hidden
inside a microsecond latency claim. Modes ran sequentially rather than randomized.

Encoding is not uniformly faster: the warm wide-bank run regressed from 16.33 to
17.43 ms (about 6.7%). Its host read took 10.56 ms versus 8.39 ms raw; GPU submission
and completion were faster. Raw rank packing uses parallel reads, whereas the
encoded extent uses a bulk read. `lossless_transport: false` retains the raw path
for workloads where this tradeoff is unfavorable. The six cold wide encoded trials
also included a 75.38 ms outlier, dominated by 67.68 ms in the read stage, against
a 37.30 ms median. These small samples do not establish a tail-latency improvement.

The encoded representation reduces PCIe bytes by about 24%; its temporary GPU
input is additional to dense output, and both count against the bank reservation.
This can reduce how many banks fit within a fixed budget. Admission costs and the
additional disk copy belong in total system economics. Already-resident dictionary
lookup was about 0.56 microseconds, but that does not include attention or loading.

The compiled client passed 352/352 serving checks: 240 small-bank checks covering
matched native/text answers, conversation growth, concurrency and streaming, plus
112 wide-bank checks including two- and three-record questions. A separate
six-case compiled-client control checked every BF16 bit pattern, both GPUs,
nondefault streams, explicit raw transport and insufficient-budget fallback.
The first all-pattern fixture was too poorly compressible once its escape index
was counted and correctly fell back to raw; the coded control adds common words
without removing any bit patterns.

The Rust suite passed 29 tests; compiled-plugin control tests passed 26; private
compiler transport tests passed seven. Broad discovery also attempted a private
source-kernel test absent from the binary-only package; that discovery error is
preserved separately. The focused compiled-client test command excludes that
source-only module. GPU serving and exact-byte tests exercise the shipped kernels.

The compiled serving checks are separate from the final isolated activation timings.
Raw fallback receives the constrained-budget serving suite; the wide serving
suite has enough staging headroom to exercise encoded activation on both ranks.

## Remaining limits

Python remains at the vLLM extension boundary for request/batch coordination,
pointer-table metadata and ownership of returned framework objects. The private
compiler still invokes the existing tokenizer/model APIs. Bank staging, storage
reads, transfer, decoding and bank tensor-view construction no longer execute as
Python loops. This is not a claim that the entire vLLM process runs in Rust.

Cold activation still takes milliseconds. A completely new working set still
requires model computation; reuse applies only where its positional and identity
conditions hold. No public-release expansion or universal latency claim follows
from these engineering measurements.

## Evidence

[Machine-readable reports](artifacts/native-runtime-20260926/) retain the stage
profiles, both rejected CPU decoding candidates, GPU prototype results, final
activation measurements, ownership checks and exact CPU reuse comparison.

## Private rollout

The private compiler now enables the Rust reuse planner, with the previous files
and configuration preserved for rollback. Its three-record deployment check took
8.23 seconds for fresh computation, 0.51 seconds for unchanged content with a new
revision, and 1.17 seconds for the tested tail update. These include the compiler
transport and complete publication, unlike the earlier isolated model timings.
The unchanged-content payload hash matched; the update produced a different
payload. Service counters confirmed zero evaluated tokens for the identical case
and prefix reuse for the tail update. These are synthetic service checks, not
new authorization grants.

Private preview sequence 4 is signed and active. Its manifest is
`6734bfc25fef1213808910d823e256f5f21baa294cc8bbbdda4b4436c93a9e4e`.
Fresh candidate installation, normal signed update and rollback to sequence 3
each passed two live canary answers (6/6); sequence 4 was restored afterward.
The signing/installer/authority components were unchanged, and their prior
authority evidence remains explicitly identified in the release gates.
The client carries no private compiler or encoder. Both GPU test runtimes are
stopped; the private compiler and Aimee services remain healthy.

The release origin and client deduplicate verified byte-identical model files
using hard links. Every signed release path and byte remains available, including
older versions; this is storage maintenance, not a latency benchmark change.
