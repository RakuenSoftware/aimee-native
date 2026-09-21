# Local sparse memory: implementation and validation status

Date: 2026-09-20. **Research slice only. No demonstrated architectural speedup
at equivalent Aimee quality. Do not use these results to justify deployment.**

The native consumption POC remains successful. That is separate from proving
that this local reader preserves Aimee's memory capabilities. Matching two
returned facts does not establish equivalent retrieval or governance.

## Corrections to the performance interpretation

The original approximately 4.71 s local / 6.59 s remote runs used different
returned memory sets and bank placement. They are not a controlled performance
comparison. The 0.142 ms local / 221.270 ms remote lookup medians also compare a
small lexical image with a different Aimee corpus and capability set.

A subsequent controlled **delivery profiling** experiment matched every query,
returned fact content, encoded memory hash, prompt, generated token, and RAM
bank setting, using one frozen Qwen process. It still does **not** compare
functionally equivalent memory systems. Its timing difference must not be
presented as an architectural advantage. User review explicitly rejected that
interpretation. Greater RAM/disk use is acceptable; loss of Aimee capabilities
is not.

## Implemented slice

`server-go/modules/memory/sparse` provides immutable content-addressed records,
lexical postings, exact namespaces and revision references, layered general →
optional KB → server manifests, explicit scoped suppressions, aliases/redirects,
versioned links, time/lifecycle checks, deltas, atomic publication, pinned
readers, and artifact import/export. The CLI is `aimee-memory-image`.

The PostgreSQL exporter currently exports memory rows from one authorized
scope. It preserves other row fields as opaque metadata; this is **not the same
as enforcing their semantics**. It does not export the entire entity graph,
conflict/provenance side tables, canonicalization decisions, episodes, semantic
indexes, or Aimee's complete recall policy. The local reader is lexical-v1, not
a fully expanded Aimee graph. Model delivery separately encodes returned content
with frozen Qwen; it is not a compact compiled engram implementation.

Live native checks used two existing Aimee user memories and small synthetic
general/KB fixtures. Both direct-general and KB-enriched image paths passed
structural tests. Qwen returned `oolong;Lima` from the local image, combined
three origins as `basalt;matte;oolong`, then consumed the published KB update as
`basalt; satin; oolong` without restarting Qwen. These establish connectivity
and generation switching for the slice, not full knowledgebase parity.

## Larger image probe

These are **within-backend diagnostic measurements**, not equivalent-work
comparisons against Aimee. Corpus: deterministic synthetic configuration facts,
one alias each; 100 queries per family per size, single reader, four families
(exact ID, natural wording, alias, missing). Payload/index pages were recently
written and may be cached. No cold-SSD claim is made. Raw samples, source hashes,
resource reports, and image digests are in the linked artifacts.

| Records | Image bytes | Reader RSS (KiB) | Build seconds | Reader open seconds | Exact ID median ms | Natural query correct |
|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 720,966 | 10,728 | 0.050483 | 0.011736 | 0.026588 | 100/100 |
| 10,000 | 7,225,476 | 30,880 | 0.353029 | 0.061092 | 0.022553 | 0/100 |
| 100,000 | 73,980,746 | 211,412 | 3.240580 | 0.674081 | 0.019908 | 0/100 |
| 1,000,000 | 758,634,200 | 2,323,028 | 40.144857 | 9.078631 | 0.032034 | 0/100 |

All exact-ID, alias, and missing-ID probes returned the expected result. At
10K and above, all natural queries failed with `lexical candidate budget
exceeded; refine query`: common words produce more than 8,192 candidates.
These are failures, not successful low-latency searches. The 1M input JSON is
352,819,144 bytes; build peak RSS was 4,936,856 KiB. These memory/storage costs
are observations, not rejection criteria.

A 100-record delta at 1M contained 32,628 input bytes. Building it took
9.357534 s, publication validation 9.301477 s, and a new reader's first query
including open 9.326177 s. The old pinned reader retained revision 1 and the
new reader saw revision 2. Small delta size does not imply cheap generation
switching: the current implementation reconstructs metadata for the whole view.

## Isolated Aimee service probe

A fresh, separate Compose project ran the deployed Aimee application image
`aimee:0.4.4-probe-fix-20260917`. Production memory and schema were untouched.
Canonical synthetic facts match the image generator; aliases/vectors were not
loaded. Fixture rows were bulk loaded directly into the disposable database,
so this is not an ingestion/learning benchmark. Requests used the **actual
Aimee `/v1/memory/search` HTTP route over its Unix socket**. Times exclude network
and TLS and therefore represent a lower bound for external deployment.

This is the standalone server's user-memory path, not a complete KB/graph
quality benchmark. The image and Aimee scale runs use separately drawn queries
from the same families; they are not per-query paired timing samples.

The default and indexed Aimee arms use identical queries and application
behavior. The indexed arm adds PostgreSQL GIN indexes on key/content trigrams
and the existing full-text expression. No application retrieval policy changes.
Ten queries per family is exploratory; it cannot establish tail-latency SLAs.

| Records | Default natural-query median ms | Indexed natural-query median ms | Indexed natural-query correct |
|---:|---:|---:|---:|
| 1,000 | 61.874499 | 65.160360 | 10/10 |
| 10,000 | 147.620199 | 56.661461 | 10/10 |
| 100,000 | 556.827529 | 55.656713 | 10/10 |
| 1,000,000 | 5,007.576903 **error responses** | 58.218204 | 10/10 |

At 1M the default arm hit the service deadline in all 30 probes; those timings
are not successful retrieval latency. The indexed arm passed all 30 (exact,
natural, missing). This demonstrates why an untuned external baseline must not
be used to justify a new architecture. It does not establish complete Aimee
quality for either arm.

## Native delivery profiling, not a design comparison

Ten measured randomized pairs after two warm-up pairs. Same loaded frozen
Qwen3.8-27B, placement, adapter, request, limit=2, preload plus native recall,
RAM bank, and greedy decoding. Every run returned `oolong;Lima`, with 74 prompt
tokens, 6 generated tokens, 40 separately encoded memory tokens, one encoding,
7 searches, and 96 native bank reads. No memory tokens were added to the
main prompt. Every per-call query and returned fact body matched across each
pair; see `payload-match.json`.

Opt-in synchronized wall profiling drains GPU work at stage boundaries on both
arms. These are diagnostic research-runtime timings, not production throughput.

| Mean seconds per request | Local lexical reader | Remote Aimee |
|---|---:|---:|
| Total client-observed answer time | 3.368650 | 4.916091 |
| First generated token | 1.092841 | 1.523325 |
| All 7 searches combined | 0.001167 | 1.517277 |
| Separate memory encoding | 0.495539 | 0.494732 |
| Bank copies to model devices | 0.009078 | 0.012000 |
| Bank copies to host | 0.001475 | 0.001321 |
| Attention-query translation | 0.005098 | 0.004985 |
| Remaining server work, including Qwen inference and profiling overhead | 2.854246 | 2.883879 |

The observed 1.547441 s difference (31.48% of remote time) controls delivered
payloads only. **It does not control memory-system capabilities and is invalid
as evidence that the proposed local architecture is faster at equal quality.**
The approximately 2.85 s remainder was not decomposed into individual model
kernels and must not be described as a measured pure decode cost.

Connection reuse was requested in the controlled remote arm. A separate
25-call probe showed that the endpoint closes the connection after each
response: 25 connections were opened. No persistent-connection optimization
benefit has been demonstrated. This remains a baseline optimization opportunity.

## Quality acceptance status

A speed claim is blocked until the same authoritative snapshots, mutations,
scopes, evidence requirements, and queries have been evaluated against both
backends. Additional RAM/disk use is expected for graph expansion and is not
by itself a failure.

| Capability | Current evidence | Equivalence status |
|---|---|---|
| Basic native consumption | Live full-Qwen results | Proven for small fixtures |
| Scope, lifecycle, time limits, pinned generations | Structural codec tests | Partial; no full Aimee differential suite |
| Dedupe and graph contraction | Manually supplied redirects work; exporter does not compile `merged_into` or entity contraction | **Not established / exporter incomplete** |
| Contradictions | Explicit scoped suppression replay tested; conflict tables and decisions not exported | **Not established / exporter incomplete** |
| Supersession and retirement | Explicit lifecycle/delta behavior tested | Partial; complete authoritative mutation replay untested |
| Provenance and evidence | Opaque row metadata retained; separate evidence graph absent; adapter encodes content | **Incomplete** |
| Semantic/paraphrase and graph retrieval | Not implemented in local reader | **Incomplete** |
| Natural queries at 10K–1M | Candidate-limit failures | **Fails current implementation** |
| Concurrent serving / cold storage | Not measured | **Not established** |

Required differential cases include:

- Contract duplicates to canonical identities while preserving incoming/outgoing
  relationships, aliases, evidence, and scope. Replay merges and unmerges.
- Preserve unresolved contradictions and Aimee's abstention/qualification;
  replay resolutions without inventing a local winner or leaking scoped rules.
- Replay update, supersede, forget, reject, confidence/evidence changes, and
  temporal expiry. Verify no resurrection after upstream rebases.
- Compare eligible and excluded IDs, revisions, relationship/evidence closure,
  and native answers across ordinary and adversarial queries. Correct answers
  alone cannot conceal forbidden-memory exposure.
- Distinguish a source governor error, export loss, local retrieval error, and
  model-delivery error. The adapter must not become another policy engine.

These are requirements, **not claims that those tests have passed**. The next
useful implementation work is closing the exported-state and recall-policy
coverage gaps, then replaying Aimee's own decisions. More exact-ID microbenchmarks
cannot substitute for this.

## Artifacts and checks

- [Initial artifacts](artifacts/aimee-local-sparse-memory-2026-09-20/)
- [Scale and matched-delivery artifacts](artifacts/aimee-local-scale-2026-09-20/)
- [Benchmark drivers](../../benchmarks/local_memory/)
- Go memory/sparse/CLI race tests and targeted vet passed in initial validation.
- After instrumentation: 21 real-adapter/local-reader tests passed, none skipped.
- Existing repository C-boundary check fails on unrelated ongoing migration
  files; this work did not remove or alter those files.

No commit, production publication, or live Aimee-memory mutation was performed.


## Subsequent agreed direction

The user subsequently selected a persistent local knowledgebase with Aimee
fallback, rather than full local reproduction of Aimee's architecture. General
published knowledge, optional KB enrichment, and server-local updates remain.
All learning and semantic decisions stay in Aimee. The local store applies
published knowledge/decisions and performs lookup; the untrained adapter handles
native translation and delivery. Unclear, missing, stale, or unsupported local
results call Aimee. Corrections and invalidations also propagate proactively.

This changes the next implementation milestone, not the validity of the old
measurements. Quality equivalence must be tested for the **combined local and
Aimee-fallback system**. Complete local coverage is no longer a prerequisite;
unsupported behavior must reach Aimee rather than disappear. The earlier
performance comparison remains invalid. See the updated agreed design in
[the proposal](../proposals/pending/aimee-local-sparse-memory.md).


The agreed model boundary is strictly read-only: no model- or adapter-authorized
knowledge writes, deletions, merges, promotions, or generation publication.
Aimee evaluates changes; a separate Aimee-controlled publisher applies them.
At this earlier checkpoint, separate reader/updater operating-system identities
and write permissions had not been demonstrated. Subsequent enforcement and
local-first reuse tests are recorded in [the follow-up report](aimee-local-first-memory.md);
they do not retroactively validate the earlier comparisons.
