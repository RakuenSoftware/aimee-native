# Publication latency: immutable base and small personal overlays

2026-09-21. The five publication optimizations are implemented. On the same
249,105-record public KB on `.253`, an ordinary real Aimee update published in
**2.689332 s**, compared with **159.569595 s** in the preceding implementation.
The subsequent native Qwen answer took **6.008780 s**, compared with **37.890786 s**.
All eight native-answer checks passed, including update, deletion, supersession,
replacement approval, and authorization narrowing.

This is a publication and reader-reuse improvement. It does not establish a
new comparison against remote Aimee retrieval, improve Qwen's reasoning speed,
or expand the local codec to reproduce every Aimee decision.

## Implemented changes

1. **Validation is separate from retrieval-index construction.** Publisher,
   delta receiver, and installer validate objects and routing without constructing
   the large phrase index. Serving builds that index lazily once. Cue validation
   decodes each canonical record once, rather than again for every alias.
2. **The public base is immutable.** Serving format 2 keeps the original approved
   general manifest, data, indexes, and routing. A separately bound server layer
   contains only personal records and cues. Publication delta version 2 can reuse
   the complete base by digest. Legacy format-1 snapshots remain readable.
3. **Verified objects are reused with integrity checks.** The process cache checks
   device, inode, size, modification time, and change time. A replacement or any
   metadata change requires SHA-256 verification. Reused pinned data inodes are
   checked too. A hash-looking filename is not sufficient. Cached parsing never
   replaces the source release policy or final authenticated HEAD check before
   the staged directory becomes visible.
4. **Readers reuse the public index across generations.** Each new reader has a
   small personal map and references the existing base. It does not clone the
   public record map, canonical-identity map, or phrase index. Lookup combines
   base and personal matches before ambiguity, longest-match, and budget checks.
   Unchanged native encodings remain reusable through the existing exact
   canonical-reference/content-hash protocol.
5. **Private history is compacted in the background.** Personal layers are already
   compact snapshots; they do not accumulate a replay chain. A background worker
   retains bounded resume checkpoints and removes unreachable private history
   objects. Defaults: 64 checkpoints, one-minute interval. The live compaction
   test used two checkpoints and a one-second interval. An expired cursor receives
   the existing full-snapshot fallback. The current generation is always retained.

These changes are in the sibling Aimee repository's model-independent sparse
image reader/compiler and publication CLI. Qwen integration, experiments, and
this report remain here. No adapter training or Rust inference changes were needed.

## Measurements

Host: `.253`, dual Radeon 7900 XTX, the existing frozen Qwen research runtime.
Corpus: the unchanged 249,105 public records / 800,470 cues, plus two initially
released synthetic personal records from the disposable Aimee stack. The public
base occupies **415,439,227 bytes**. Source mutations use the actual Aimee memory
HTTP API; source export uses the existing read-only database connection and
server-owned exact-ID release policy.

| Measurement | Previous implementation | Optimized |
|---|---:|---:|
| Ordinary update: mutation start → visible CURRENT | 159.569595 s | 2.689332 s |
| Ordinary update: receiver apply | 112.213797 s | 1.028213 s |
| Ordinary update: locally copied bytes | 148,050,082 | 2,610 |
| Ordinary update: locally reused bytes | 267,391,712 | 415,439,227 |
| Ordinary update: stream bytes | 2,327 | 2,068 |
| First native answer after update | 37.890786 s | 6.008780 s |
| Deletion: mutation start → visible CURRENT | 157.529396 s | 1.697198 s |
| Replacement approval → visible CURRENT | 179.610235 s | 3.752576 s |
| Authorization narrowing → visible CURRENT | 182.359227 s | 6.004218 s |
| Consumer restart → restored CURRENT | 54.579632 s | 11.885671 s |

Supersession published in **1.674213 s**. Warm native composition after the update
was **5.003778 s**, with zero new encodings. The first composition response with
cold native encodings was **11.786352 s**; model weight loading is excluded.

A separate six-update sequence measured **1.805484–3.071974 s**, median
**2.522549 s**, mean **2.427205 s**. This sequence ran while Qwen weights were
loading; the mutation/answer sequence above ran after model readiness. Each
measurement includes the actual API mutation, source polling, compilation,
transport, validation, and publication. Polling remains one second. These are
small research samples, not production percentiles or a randomized A/B study.

The initial receiver bootstrap applied **274,715,009 transferred bytes** in
**28.727144 s**, copying **415,441,835 bytes** locally. This is receiver apply time,
not a measured end-to-end cold publication time. Cold start is still proportional
to the base size. A restarted consumer must revalidate/reconstruct its process
cache; reconnect is therefore slower than a warm incremental update.

An authorization change still withdraws the complete model-facing directory
before publishing the narrower image. Those transitions copied the public base
again locally (about 415 MB); they are deliberately not reported as 2.6 KB updates.

## Native and authorization checks

- **8/8 native answers passed.** All seven composition runs had identical prompt
  token IDs. Every run reported zero memory tokens in the main conversation.
- Update retained two encodings, invalidated one, and encoded the changed drink once.
- Deletion retained two, invalidated the city, encoded nothing, and answered
  `6115;jasmine;unknown`.
- Supersession returned `mint`, honoring Aimee's observed same-ID/new-revision behavior.
- A newly created record did not publish until explicitly released. After release,
  Qwen returned `chamomile`; unrelated public knowledge remained available.
- Narrowing removed the personal record, retained the public encoding, and needed
  zero new encodings for the public answer.
- Scans found no unapproved canary, deleted fact, or superseded personal content
  in the model-facing image after the corresponding transition.
- The model identity could neither read the private policy nor write the image.
- Consumer disconnect removed CURRENT in **0.050899 s**. Resume used a **108-byte**
  unchanged-generation frame.
- Withdrawal during active native generation removed the image in **0.501604 s**.
  The failed trace reached native step **54**. The request returned HTTP 502 with
  no answer; the withdrawn image contained **zero record files**.

The serving helper now drops its pinned state and cache-owned base leases when
publication becomes unavailable. This supplements the Rust runtime's existing
per-step generation checks and native-cache invalidation. It is not a new local
authorization system.

Persistent encodings remain on CPU/RAM; attention makes temporary device copies.
As before, selected record content is tokenized separately to construct native
K/V states. “Zero memory tokens” means no memory text in the main conversation;
it does not mean the encoding operation never tokenizes content.

## Compaction and regression validation

The live background worker reduced private history from **12 checkpoints / 39
objects** to **2 checkpoints / 9 objects**, removing 30 unreachable objects. CURRENT
was unchanged. No full public-base rewrite was performed.

Go race suites passed for `modules/memory/sparse`, `modules/execution-policy`,
`cmd/aimee-memory-image`, `cmd/aimee-memory-publish`, and `modules/memory`.
New regressions cover base/index sharing, update/removal behavior, base/personal
cue collision and longest-match handling, concurrent reads, recipient isolation,
malformed base reuse, final-check denial, compaction/full reset, and cache tampering.
The tampering checks include restored mtime and a correct replacement path hiding
a corrupted older pinned inode.

Explicit `Verify()` remains exhaustive across base and overlay; normal serving
open reuses the verified base and checks the local overlay. The final executable
successfully verified the full two-layer large image. The audit command took
13.261953 s including cold open, full verification, 148 MB of manifest output,
and test-driver parsing; that number is not a serving latency measurement.

The mutation run and later withdrawal run have separate binary-hash manifests.
The withdrawal build adds cache disposal on publication loss and preserves
inherited remote-context lookup. The final build additionally preserves exhaustive
explicit audits; that audit correction has a focused regression and the full-image
check. The serving validation path is unchanged by that final audit correction.
No Rust code changed; the earlier 16-test Rust result remains in the preceding report.

## Evidence and remaining limits

Raw results, native traces, command arguments, compaction counts, binary hashes,
Go test output, and final state are under
[`artifacts/publication-latency-2026-09-21/`](artifacts/publication-latency-2026-09-21/).
The summary joins timing rows to their consumer events by exact view ID; three
original timing rows observed CURRENT just before their metric line was emitted.
Those original rows are retained unchanged.

Baseline evidence is in [the preceding publication report](incremental-publication.md).
The process caches are bounded to two general readers/manifests. The optimized
format currently supports one explicitly approved general base plus one personal
server overlay; it does not yet generalize the fast path to an organization KB
between those layers. The larger Aimee graph, evidence, episode, and policy codecs
remain outside this exact-record release experiment.

All research services were stopped after testing. The release remains inactive,
CURRENT is absent, model-facing record files are gone, and the prior read-only
bridge in the disposable Aimee stack was restored without modifying its grant.
