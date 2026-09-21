# Independent native record encodings

Follow-up: [live incremental publication and cross-generation retention](incremental-publication.md)
now implement the stream/cache transition that remained pending in this experiment.
The observations below describe the earlier run unchanged.

Date: 2026-09-21. This is the encoding-reuse part of the
[Aimee-driven incremental update direction](../proposals/pending/incremental-kb-updates.md),
not an implementation of that network stream.

## Change

The opt-in Rust path separately encodes each selected canonical record using the
same frozen Qwen model. It preserves each raw CPU K/V record and composes their
positions as disjoint slices before the prompt at native attention reads. No
projection training, memory selection rule, textual prompt insertion, or main
conversation-cache rebuilding was added. Separate memory content is still
internally tokenized by the frozen encoder.

Cache keys bind publication, canonical namespace/ID/revision, exact encoder
input, encoding format and granularity. Working-set growth reuses existing record
encodings. The bounded shared LRU also permits reuse across different working sets
within one publication. The cache is in RAM, not a persistent projection store.
The existing joint encoder remains the default; enabling the server flag is
required before a client can request record mode.

Publication changes and withdrawal still clear the whole shared cache. Selective
retention across knowledge updates requires a complete, validated publication
change set. The current polling/full-snapshot publisher does not supply that yet.
This experiment must not be reported as successful streaming publication or as
selective invalidation of a live authorization change.

## Experiment

The unchanged 249,105-object approved public image and existing two synthetic
personal Aimee records were used on `.253`. Frozen INT8 Qwen, the same content
encoding, corrected memory positions, prompts, greedy decoding, limits and
attention-driven recall were used in both modes. No production memory was used.

Seven distinct questions cover drink, city, two planet values, neutron/proton
mass difference, and two three-memory compositions mixing the public KB with
Aimee's personal records. Each mode runs them with the shared cache disabled,
then filling the shared cache, then fully warm: 21 generations per mode, not 21
independent questions. In fill runs, drink/city singletons precede composition,
allowing reuse across working sets to be observed. Full raw traces are retained.

## Results and validation

**21/21 answers passed in each mode.** All 21 paired runs had identical prompt
token IDs, identical preload record references and identical final record
references. Both three-memory compositions passed cold, filling and warm. No
memory facts were inserted into the generation prompt.

Five endpoint controls passed: omitted granularity uses the bank default; both
native-disabled modes answer `unknown` with zero recall/encoding/native reads;
unknown and non-string granularities are rejected. The complete release Rust
suite passed **14 tests**, including the actual tokenizer fixture, disjoint
positions through growth/reordering, unchanged raw cached keys, changed
revision/content misses, publication isolation, LRU budget and withdrawal.
The non-Torch local suite also passed (8 tests; actual tokenizer exercised in the
remote full suite).

[Raw results and comparison](artifacts/record-cache-2026-09-21/comparison.json),
[full generations](artifacts/record-cache-2026-09-21/results.jsonl),
[endpoint controls](artifacts/record-cache-2026-09-21/controls.json), and
[raw traces](artifacts/record-cache-2026-09-21/traces/) are retained with source
archives and binary hashes.

## Measured encoding work

When the neutron/proton question discovers a second record during decode, the
joint encoder processes 58 tokens and then the enlarged 166-token bank: **224
encoder input tokens**. Independent encoding processes the initial 58 tokens and
then **only the new 112-token record**, reusing the first record: **170 tokens**.
The independently assembled bank includes an additional per-record header; it is
not claimed to be token-for-token identical to joint encoder input. Both answers
are `1.29333251`.

After drink and city were cached separately, each new three-memory composition
needed **one** new record encode and **two** record-cache hits. The joint baseline
needed **two** complete-bank encodes for each of those queries. Both returned the
correct port, `oolong`, and `Lima`.

| Cache-fill composition | Joint encoder/cache time | Independent encoder/cache time |
|---|---:|---:|
| `3584; oolong; Lima` | 1075.360703 ms | 494.176995 ms |
| `6115; oolong; Lima` | 978.998890 ms | 487.724069 ms |

These are single observed encoder/cache timings, not end-to-end speedup claims.
With neither reusable fact cached, independent three-record encoding instead
needed three model passes and took about 1.47 seconds versus about 0.98–1.06
seconds for the joint baseline. Fully warm joint-bank reuse already avoids
encoding; independent encoding does not improve that property. Mode blocks were
not randomized, the GPU host is shared, and endpoint controls overlapped the end
of the warm block. No production-throughput conclusion follows.

## Scope and next implementation boundary

The tests establish reuse when an admitted working set grows, plus cache identity
invalidation for changed payload/revision and isolation between publications.
They do not establish a production Aimee stream, persistence across restarts,
model-wide generalization, or live selective invalidation across generations.

Next, Aimee needs to publish authorized record changes/removals and dependency
invalidations with a durable predecessor/commit contract. Then the local KB can
apply those transactions and selectively evict derived encodings. Current source
deltas cannot simply be distributed: their historical graph can include records
that the recipient is not authorized to receive.
