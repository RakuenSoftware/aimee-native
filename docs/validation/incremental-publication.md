# Live Aimee publication and reusable native records

2026-09-21. Research implementation, using the disposable Aimee stack on `.253`
and the existing frozen Qwen runtime. No production organization data was used.

## Implemented boundary

The model-independent `aimee-memory-publish` service reads exact approved memory
IDs from Aimee's actual `user_memories` table in a read-only repeatable-read
transaction. The experiment changes these records through Aimee's existing
memory HTTP API, not by substituting an adapter fixture response. The database
connection uses verified TLS and a SELECT-only role. Credentials stay outside the
model sandbox and evidence archive.

The server-owned `MemoryReleasePolicy` lives in Aimee's execution-policy module.
It binds a recipient, actual Unix peer UID, exact public base digest, namespace,
scope, approved record IDs, expiration, and either a pinned revision or explicit
permission to follow that ID's updates. An additional ID needs a new release
rule. Search permission alone does not authorize exporting all memory. This is
an implemented narrow release policy; it does not integrate every existing
organization membership/tenancy policy or authorize arbitrary graph/episode data. The initial exact-ID release is capped
at 4,096 personal records to match the restricted upstream operation.

The publisher reconciles selected source rows once a second and pushes NDJSON
transactions over a persistent authenticated Unix connection. This is server
push with source polling, **not a database changefeed**. `follow-published` also
supports the existing authenticated HTTPS transport. The receiver keeps its
resume cursor and last good snapshot in a publisher-private directory, stages
transactions privately, verifies their target digest, and atomically switches
model-visible CURRENT. Immediately before commit, a separate authenticated HEAD
request rechecks the publisher’s current approval for that exact generation; a
revocation during staging cannot be overridden by an older queued frame. A gap or malformed update cannot commit. Disconnection
withdraws model-facing delivery; reconnect can restore from a heartbeat without
retransmitting records. Missing source history requires a complete authorized
snapshot.

Transactions contain changed canonical records, removals, and sparse cue changes.
The unchanged general record data/index is reused. This does not yet eliminate
large manifest reconstruction, validation or lookup-index rebuilding. Publisher
history has no automatic compaction policy yet.

A policy change causes withdrawal before replacement compilation. Native requests
check the generation before every forward step and before returning the answer.
If the generation changes or disappears, the active request fails and must be
retried; the adapter does not rebuild Qwen's state or silently mix generations.
Ordinary content mutations become visible when their replacement generation
commits, not at the instant of the source write; the measured publication lag
below is therefore also a staleness window. Permission changes use the separate
withdrawal barrier. Already emitted output or knowledge retained by a recipient
cannot be retracted. Research traces deliberately preserve historical synthetic
answers and are not part of the claim that obsolete KB snapshot bytes are removed.
This path currently returns non-streaming model answers.

## Native encoding coherence

Independent record encodings remain opt-in (`--enable-record-encoding` plus
`memory_encoding_granularity=record`). CPU K/V cache keys include the actual
serialized memory tokens, canonical namespace/ID/revision, and encoding mode.
The model and tokenizer stay fixed for the process lifetime. On a publication
change, a current canonical content hash and exact identity must prove each record
unchanged before its cached encoding is retained. Changed/removed records and
joint-bank encodings are invalidated. No adapter training, inference-time learning,
or domain-specific selection was introduced.

This cache is in-process. It is not persisted across model restarts, precomputed
for all 249K objects, or a learned engram writer. Aimee owns canonical identity,
deduplication, supersession and selection. The local layer consumes their results;
it does not independently solve contradictions or merge semantically similar text.

Memory is not added to the main conversation: reported memory prompt tokens are
zero. The frozen encoder separately tokenizes selected canonical memory to derive
native attention K/V. This is not token-free encoding of knowledge.

## Remote fallback

A local miss still reaches the real Aimee restricted lexical-search ingress.
This is the existing bounded record operation, not a claim that every Aimee
hybrid/graph/episode retrieval path has been exported. A privileged
Rust gateway binds that read to the current recipient snapshot, supplies an exact
ID restriction, requires Aimee's restriction receipt, and checks returned canonical
content/revision before forwarding it. This narrows independently authenticated
Aimee access; a local image does not grant upstream rights. A generation change
during the remote call fails closed. Unapproved records and opaque response fields
are not forwarded. Richer Aimee response families still need explicit release
codecs; this implementation must not silently claim full Aimee parity.

## Validation

The live mutation run used **249,105 public objects** plus two initially approved
synthetic Aimee memories. **8/8 native answers passed**, with zero memory tokens
in the conversation prompt. All seven composition runs had exactly identical main
prompt token IDs. The eighth question checks the surviving public record after
removing personal release permissions. These are focused functional observations,
not a statistical accuracy or throughput benchmark.

| Native request | New record encodes | Retained / invalidated on generation change | Answer | End-to-end seconds |
|---|---:|---:|---|---:|
| baseline-cold | 3 | 0 / 0 | `6115;oolong;Lima` | 8.115912 |
| baseline-warm | 0 | 0 / 0 | `6115;oolong;Lima` | 5.518247 |
| after-update | 1 | 2 / 1 | `6115;jasmine;Lima` | 37.890786 |
| update-warm | 0 | 0 / 0 | `6115;jasmine;Lima` | 5.043720 |
| after-delete | 0 | 2 / 1 | `6115;jasmine;unknown` | 37.037142 |
| after-supersession | 1 | 1 / 1 | `6115; mint; unknown` | 37.622054 |
| after-replacement-approval | 1 | 1 / 1 | `6115;chamomile;unknown` | 41.069471 |
| unrelated-after-narrowing | 0 | 1 / 1 | `6115` | 37.552480 |

The initial cold request encodes three records. Changing one fact encodes only
that record. Deleting the city encodes nothing; Qwen returns `unknown` for it.
Supersession and explicit approval of a new identity each encode one record.
Narrowing the policy retains the unrelated public encoding and encodes nothing.

| Publication event | Stream bytes | Upserts / removals | Cue edits | Receiver apply seconds | Source-write-to-publication seconds |
|---|---:|---:|---:|---:|---:|
| update-publication | 2,327 | 1 / 0 | 4 | 112.213797 | 159.569595 |
| delete-publication | 1,717 | 0 / 1 | 2 | 111.842746 | 157.529396 |
| replacement-approved | 2,470 | 1 / 1 | 4 | 115.799117 | 179.610235 |
| authorization-narrowed | 1,733 | 0 / 1 | 2 | 117.510078 | 182.359227 |

The supersession delta separately measured 2,324 stream bytes and 116.771285
seconds receiver apply time. Its driver was resumed after correcting a source-ID
assumption, so the recorded 77.071968-second wait is **not** total source-write lag.

The key remaining bottleneck is substantial: ordinary update/deletion took about
158–160 seconds to publish; release-policy replacements took about 180–182 seconds.
First reads after a generation change took 37–41 seconds because large reader and
gateway indexes are reopened. The warm repeat after updating took 5.043720 seconds.
Small network deltas do **not** currently imply fast local generation application.

For ordinary updates, 267,391,712 bytes were reused by hard link, but approximately
148 MB of changed routing/manifests and small record objects were still copied
locally. A policy change deliberately withdraws the old model-visible image, so
restoring that image copied approximately 415 MB locally even though the stream
sent only a few KB. Repeated full-image validation/index reconstruction and large
routing manifests need incremental replacement before claiming production speed.

Aimee's current server-placement `supersede` operation returned the **same ID**
with new content/revision. The adapter followed that canonical identity. A separate
new record (ID 1002) remained absent and did not advance the image until explicitly
approved. This is not evidence that the server API created a KB supersession chain.
The same-key update confirms the source upsert decision; full semantic deduplication,
contradiction resolution, and lineage remain Aimee responsibilities and were not
reimplemented or exhaustively validated by this record-release slice.

Physical scans found no withheld canary, obsolete drink value, deleted city, or
narrowed personal record in the corresponding delivered snapshots. Historical
research traces remain archived deliberately. Unit tests additionally verify a
cue-only transaction sends no record payloads and retains both unchanged values.

Test drivers are in `benchmarks/incremental_kb/`. Initial setup failures and failed
model traces are retained separately from successful results. The first baseline
failed on an absent fallback socket. The supersession probe initially used invalid
HTTP field names, then needed correction for Aimee's observed same-ID behavior;
neither is counted as a native memory answer failure.

[Raw mutation results, source archives and checks](artifacts/incremental-publication-2026-09-21/)
include the complete API responses, canonical references and exact prompt IDs.

Component coverage includes policy identity/scope/expiry, owner-only policy files,
symlink/trailing-document rejection, selected-ID export, exact delta reconstruction,
removal/replay/gap/integrity handling, sparse cue edits, truncated/oversized/invalid
stream withdrawal, durable reconnect, canonical remote egress, and selective cache
retention. Existing native positional and composition regression tests still run.


## Disconnect, revocation and final checks

- Model UID could not read the private policy or write the delivered image.
- Graceful consumer disconnect removed delivery in **0.161864 seconds**.
- Reconnect restored the identical generation using a **108-byte heartbeat**, no
  record retransmission. Full restoration still took **54.579632 seconds**, with
  **38.170149 seconds** of receiver apply work and 415,439,744 bytes copied locally.
- During a long native request, withdrawal removed the image in **0.803641 seconds**.
  The request had reached native step **66**. It returned HTTP **502**, with no
  answer; the failed trace is retained. The delivery directory then contained
  **zero record files**.
- The first in-flight probe requested 700 tokens, exceeding the runtime's existing
  512-token maximum, and was rejected before generation. That failed probe remains
  archived. The corrected 512-token probe above is the actual withdrawal result.

Final Go race suites passed for sparse memory, execution policy, publisher,
image CLI, and memory. The complete Rust release suite passes **16 tests** using
its actual tokenizer. Formatting and Python probe syntax checks also pass.

The final Go consumer/publisher binaries include the fresh pre-commit approval
check and persistent policy-change marker; the reconnect/withdrawal run exercised
those binaries. Mutation runs preceded that last hardening step. A final small
Rust cleanup also drops shared cached encodings immediately when an active
request's generation check fails (in addition to dropping the active bank and
rejecting output). Its focused release test passes; the full-Qwen withdrawal
measurement used the preceding binary, which already aborted that request and
invalidated the shared cache on the next request. Binary hashes distinguish the
executed revisions; final source archives are labeled separately.

These are single observations on a shared research host. No production throughput
or zero-lag revocation claim follows. The next performance work is to reuse
immutable general routing/index state and validate only changed objects, while
retaining the fresh approval check. It must not weaken recipient release rules.


The research release is left inactive, its model-visible image withdrawn, and
its temporary model/publisher/consumer/gateway services stopped. The prior
restricted-read ingress in the disposable Aimee stack was restored. No production
service was changed. Final release binaries are built on `.253`; command files,
final state, hashes and private-free evidence are archived here.
