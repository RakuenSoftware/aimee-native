# Local-first Aimee decisions and native-state reuse — 2026-09-20

This follows the user's revised architecture: a persistent published general
knowledgebase with optional KB/server overlays, Aimee fallback for unclear
results, and all learning and semantic decisions remaining in Aimee. The model
and adapter are read-only. Canonical semantic objects, evidence, relationships,
identity and validity remain authoritative in Aimee; model-native projections
are disposable derivatives, never the knowledge itself.

## Implemented boundary

- Optional published exact-request read contracts preserve complete real Aimee
  responses. Query, limit, authority, scope grants, expiry and source revisions
  must match. Unsupported requests call the actual Aimee search endpoint.
- Each new published generation withdraws prior contracts unless explicitly
  republished, even if original source records were not changed. Requests pin
  generations; active-request revocation is not implemented.
- A bounded RAM cache reuses frozen-Qwen native states only after an eligible
  read. No adapter training, local semantic learning or model-authorized writes.
  This cache currently preserves complete jointly encoded banks, not independent
  per-object projections or a portable multi-model latent format.
- The model service runs as `aimee-native` with a read-only image. A separate
  root-owned gateway holds Aimee credentials and accepts only search. The model
  cannot read those credentials or invoke write routes. A separate publisher
  owns generation changes. Writable runtime caches/traces are outside the KB.

## Experiment and limits

Frozen Qwen3.8-27B, dual Radeon 7900 XTX, the existing weight-only int8 research
runtime, synchronous profiling enabled, one serial service for all arms.
Remote reads use the existing mTLS Aimee endpoint through the development SSH
tunnel; that endpoint closes each response connection despite keepalive. The
remote timings include this deployed path, not just Aimee database execution.
Improving the remote transport could reduce the local-read advantage.
The prompt asks for the same two existing Aimee research facts; memory content
is separately encoded into native attention states, never appended to the main
prompt. No production memory mutations were performed. The experimental model service
and credential gateway were stopped after measurements to release resources.

Four randomized arms separate remote/local read cost from fresh/reused native
encoding. Two complete warmup blocks precede ten measured blocks. Complete
per-read Aimee responses, query strings, bank hashes, prompt token IDs and
output token IDs are compared, not merely answer correctness. All raw samples
and traces are retained.

The image contains 100,000 synthetic general records plus two real Aimee facts,
but only seven exact read requests were prepublished. This is intentionally a
repeated-working-set measurement, **not** 100,000-memory semantic coverage or a
representative local hit rate. The image occupies about 23 MiB on disk; the
current native bank cache occupies 2,621,440 bytes (2.5 MiB) in RAM. Files may be
OS-cached; no cold-SSD or concurrency claim is made.

The publisher's one-hour expiry is an operator-controlled research bound, not
an authority-issued freshness lease. Automatic Aimee mutation/invalidation
publication is not wired. Therefore this is not proof of production freshness,
full graph contraction/deduplication/contradiction parity, or model-independent
knowledge consumption. Those responsibilities stay in Aimee; safe publication
must integrate with its mutation lifecycle before deployment.

## Measured repeated-working-set results

Ten measured requests per arm, after warmup. All 40 requests returned
`oolong;Lima`. Complete recall responses and main/native model input and output
signatures were identical across all 40; this comparison does not substitute a
weaker local search algorithm for Aimee's decisions.

| Read source / native encoding | Median answer time | Median TTFT | Remote calls per request |
|---|---:|---:|---:|
| Remote / fresh | 4.888813 s | 1.516263 s | 7 |
| Remote / reused RAM states | 4.395079 s | 1.029906 s | 7 |
| Published local / fresh | 3.364257 s | 1.086706 s | 0 |
| Published local / reused RAM states | 2.866663 s | 0.590454 s | 0 |

For this repeated working set, local reads plus state reuse reduce the median
answer time by 2.022150 seconds (41.36%) versus remote reads plus fresh encoding.
Against remote reads with the same encoding reuse, the reduction is 1.528415
seconds (34.78%). This is conditional on all seven requests being locally
covered; it is not an expected overall deployment speedup.

Remote search occupies a median 1.493918 seconds per answer across seven calls;
published local searches occupy 0.001384 seconds with fresh encoding. Fresh
native encoding costs approximately 0.495 seconds per answer. Encoding reuse
removes that pass while preserving the same native inputs. These are separately
measured medians, so their differences need not add exactly to median totals.

## Unpublished query

Reversing the question to ask for city before drink changes the native read
requests. All 12 measured requests (three per arm, after warmup) returned
`Lima; oolong`, with identical complete recall/input/output signatures across
arms. Every local-first read missed its exact contract and reached real Aimee:
42 fallback calls across six measured local-first requests, zero local hits.
The model did not publish its new queries or responses into the knowledgebase.

Aimee supplied an additional third record during native recall. Both remote and
local-first paths retained it. With fresh encoding, this required two encoding
passes per answer. Median times were 5.473382 seconds remote and 5.481600 seconds
local-first; with state reuse they were 4.490279 and 4.440292 seconds. Three
samples per arm are only a functional fallback check, not a tail estimate or
evidence that falling back makes Aimee faster.

## Publication withdrawal

The publisher created generation 2 with no read contracts, retaining the
canonical records and upstream general image. All 12 measured follow-up
requests returned `oolong;Lima`, with identical complete recall/input/output
signatures across arms. Every local-first request now made seven actual Aimee
reads: 42 fallbacks and zero local hits across six measured requests. Existing
RAM states remained reusable only after those reads.

Median answer times were 4.939243 seconds remote versus 4.882901 seconds
local-first with fresh encoding, and 4.414982 versus 4.459260 seconds with reuse.
These small three-sample groups validate withdrawal and fallback, not a speed
advantage. This tests publication withdrawal, not production Aimee deletion or
contradiction mutation propagation. The research image is left at generation 2
with local read contracts withdrawn.

Across the three experiments, all 64 measured answers were correct for their
respective prompts, and all within-experiment complete signatures matched.
This remains two question forms about two target facts, not 64 independent
knowledge tasks or a broad quality benchmark.

## Validation

Go sparse/CLI race tests and vet passed. The Python suite ran 27 tests
successfully, including frozen tiny-model logit equality with encoding reuse,
fresh eligible reads before reuse, empty replies, changed content, cache limits,
local miss/fallback, and generation withdrawal. These are structural checks,
not evidence of broad pretrained-model accuracy.

Eight live access-boundary checks passed: image manifest modification, image
object creation, credential reads, gateway store/publication routes, extra
write parameters and CLI publication were denied; ordinary Aimee reads worked.

An initial 48-request run failed because ROCm attempted to write its runtime
cache under the reader account's nonexistent home. These failed samples are
retained and excluded from timing results. The research account's home was
changed to its writable runtime cache directory; KB permissions stayed read-only.

## Artifacts

[Raw samples, summaries, traces and checks](artifacts/aimee-local-first-2026-09-20/).
Drivers: `benchmarks/local_memory/local_first_qwen.py`,
`summarize_local_first.py`, `publish_recall.py`, and `withdraw_recall.py`.
