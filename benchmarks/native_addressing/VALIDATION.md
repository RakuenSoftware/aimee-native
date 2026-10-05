# Initial validation — 2 October 2026

Implementation baseline: integration checkout commit
`0ebdc4fed2ed02a1290a2d9af9c7e86207af6452`.

The standard-library test suite passed 12 tests. It covers unit conversion,
source-byte hashing, content-free reports, incomplete event timing, absent GPU
timing, runtime failures, distinct conditions and repeated tasks, external quality
labels, observed capacity violations, invalid numbers, duplicate evidence,
required dimensions and exclusive mode-0600 output creation.

A read-only smoke audit joined 42 completed requests from the historical
`docs/validation/artifacts/record-cache-2026-09-21/results.jsonl` with their original
trace files. Outcome scores came from `pass_` in the existing results, not from
model answers or this auditor. Selection scores were left unknown because equality
between two selected banks is not an independent relevance oracle.

The manifest separated bank/record encoding, disabled/fill/warm cache conditions,
exact prompt lengths and repeat identity. It declared the archived 249,105 public
records plus two synthetic personal records and the recorded 2,048-position limit.
The model label identifies the archived frozen INT8 run; this smoke check is not a
new full-checkpoint provenance or accuracy experiment.

Results: 42 requests, 42 exact-condition groups, 42 externally scored correct,
360 `bank_unchanged` events, zero complete selection-timing requests, and 21
complete encoding/cache-timing requests. The remaining timings were withheld as
incomplete rather than reconstructed from absent events. Addressing, activation
and GPU consumption remained unmeasured. Each group's single request does not
support a tail-latency or comparative scaling conclusion.

The generated smoke manifest and report reside in the temporary development
directory; original experiment files were neither changed nor copied into the
implementation. No model, runtime policy, production memory or deployment was changed.

## Research-runtime instrumentation — 3 October 2026

The next slice adds addressing wall-time/attempts, complete recall duration and
post-recall working-set peaks to the Rust research adapter. Successful and failed
request traces expose a versioned metric object; failed traces also include total
elapsed time. Empty and rejected selection paths explicitly did no encoding.
Unchanged-bank reads measure equality/bookkeeping, and later admission failures
retain total recall duration without invented stage measurements. Existing
prepared loading remains a separately measured operation.

The auditor now reads complete recall duration and validates the metric schema,
scopes, current-versus-peak consistency and failed-attempt counts. It keeps new
post-recall position coverage distinct from old encoding-event observations.
Addressing includes preparation and host readback; logical tensor bytes exclude
copies, caches, staging and allocator overhead. Neither is a GPU-kernel-cost or
physical-residency claim.

Validation:

- Python auditor: **15/15 tests passed**.
- Rust library: **50/50 tests passed**, including five new telemetry regressions,
  existing publication/invalidation checks, disjoint native positions and native
  tensor integrity. The final run set the existing checkpoint-tokenizer fixture
  environment variable so its optional token-slot assertions were exercised.
- Serving binary: `cargo check --release --locked --offline --bin aimee-qwen`
  passed with the Torch feature enabled.
- Archived compatibility: the original 42 requests still retain all 42 external
  passing scores and 360 unchanged-bank events. Historical metric coverage stays
  zero rather than being inferred from the new schema.
- `git diff --check` passed.

Rust validation used a separate source snapshot, Rust 1.98.1 and the established
native Torch compatibility setup on the research container. CPU-only tests ran
with two compute threads and reused existing build dependencies. No serving
process, model deployment, authority record or production memory was modified.
The checked snapshot's adapter and serving-source hashes match the local changes:

```text
45e5c67a9f4cc4c5b5a1ef4810461f263aefd86e216fb2005049b617e0739bc3  src/adapter.rs
522f7efb4a49468a88c02bfabb8f26ffd2adc0377b39c49f49e3e9845506d4fc  src/main.rs
```

[Raw final Rust test output](evidence/runtime-tests-20261003.txt) is retained.
The native-library loader emitted two startup file-path warnings before the test
harness; all tests completed successfully. No live full-model quality or latency
experiment was run. GPU consumption measurement, serving-plugin instrumentation
and retrieval-scheduling controls remain subsequent implementation work.

## Completed first implementation/evaluation cycle — 3 October 2026

See [RESULTS.md](RESULTS.md) for the final controls, paired full-model results,
oracle/native-disabled controls, negative learned-router gate, reuse decision,
GPU cost measurement and explicit compression/write decisions. The earlier
instrumentation-only limitations above describe the earlier snapshot, not the
completed cycle. Broader production and semantic archive-scaling claims remain
unproven. Raw evidence is retained in `evidence/20261003/`.

## Completion validation — 3 October 2026

The completion snapshot adds the real published-reader router, signed/released
bundle validation, typed native address protocol and opt-in Rust transport envelope.
The owner-approved routing data is content-addressed with the publication. Reader
queries resolve canonical records at the requested time; temporal expiry cannot
invalidate the unrelated routing catalog. Tip routes are explicitly republished.

`go test -race ./memory/... ./cmd/...` passes on Go 1.26.7, including core authority
integration and new native protocol/bundle regressions. The isolated snapshot also
contains the public seed corpus needed by existing command tests. The initial
missing-corpus test attempt is an environment failure, not a suppressed result.

The updated Rust library passes 55 tests with the actual checkpoint tokenizer,
and its release serving binary builds. The offline Python suite passes 22 tests.
The real-reader model campaign completes 96 requests at 100,006 published records:
96 correct required-record selections, 75 correct answers, zero added memory prompt
tokens. All 60 original cases pass. The expanded exact-answer gate fails and is
retained; defaults are not promoted on the basis of that failure.

Separate real-reader archives contain 1,006/10,006/100,006/1,000,006 records with six
routes; another 100,006-record case grows the catalog to 100,006 routes. Each records
build/open/cold-route cost separately from 1,000 warm canonical-selection samples.
This is public synthetic exact-address performance, not production semantic search.

Evidence is retained separately under `evidence/20261003-completion/`; first-cycle
artifacts and their hashes are unchanged. Source snapshots distinguish executed
runtime/reader/package source from later formatting and documentation changes.
Failed model/serving startup attempts are retained separately from scored quality:
one model startup exhausted GPU memory, and one serving startup used a policy-only
library without the portable runtime exports. Neither produced scored requests.
Successful validation uses an isolated owned server and the correct portable build;
no unrelated service, authoritative record or production deployment is changed.

Current-source serving validation passes both BF16 and Q8 profiles, 72 requests
each (36 native and 36 text controls), at 0/16/48 preceding turns. All 144 answers
pass. Actual worker metrics show enabled host-stage counters and successful bank
activation/cache samples. Static-catalog operation leaves selection-RPC counters
absent. These checks reuse existing synthetic prepared states and do not certify
the new router for that model family or fresh production policy/preparation.

The current portable client and plugin pass 35 admission/cache/state/telemetry/
control tests. The recorded portable build uses Python 3.12 headers and
`--no-default-features --features vllm-portable`; policy-only `vllm-client` builds
are suitable for unit tests but lack the runtime activation exports required by
live serving. Source snapshots and binary digests distinguish these builds.

Independent streaming verification confirms every archive's physical record count
and manifest/data/index SHA256 values, including all 1,000,006 published records.
The measured model trace digests and working-set peaks were checked after transfer.
The final content hashes and decision file are in the completion evidence directory.

## Complete hybrid prefix validation

The follow-up preserves the attention-only studies above and adds full hybrid
prefix state. The executed frozen-model runtime passes **60 Rust library tests**,
including contiguous-prefix equivalence through prefill/decode, immutable
recurrence reuse, changing-bank conversation replay without extra source reads,
lossless mixed-dtype prepared loading, corrupt sidecars, incomplete/lossy state,
strict prepared misses and recurrent byte limits. The extended auditor/router
suite passes **24 tests**, including unknown historical recurrence metrics and
rejection of partial or inconsistent recurrence/replay metrics.

The actual checkpoint probe shows a complete joint-content prefix passing all
16 development tasks. Joint content, keyed, JSON and chat-framed attention-only
variants do not close the quality gap; the complete-state profile was frozen
before the new held-out tasks. Model matrices, preparation checks and final hash
verification are recorded in the subsequent results and evidence section.

Executed Rust sources are retained separately from the final formatted sources.
Formatting and explanatory comments do not change the tested model/cache behavior.
The checkpoint revision and original shard-verification evidence remain those of
the completion study; no checkpoint tensors or prepared state payloads are stored
in repository evidence.

The four final matrices pass **480/480** exact answers and canonical selections.
The independent summary verifies every trace hash and exact Cartesian coverage,
matching online/prepared answers and the same executed binary across all cells.
All 240 strict prepared traces record zero encoding; all 480 record zero memory
prompt tokens. The original implicit-alias matrix remains a failed 135/144 gate.
The new explicitly grounded holdout is a separate fixture and outcome.

The implicit fixture's subsequent zero-turn text control passes 16/16, including
the native-failing alias; native implicit-inference quality remains a documented
limitation. Independent verification checks every prepared attention entry range
and every recurrent sidecar against its recorded SHA256 and exact byte size.
Only metadata/hash reports are retained locally, not the derived tensor payloads.


## 4 October: full-checkpoint repair completion

The [final completion report](../../docs/validation/native-memory-completion-20261004.md) supersedes earlier assessments of the four
remaining repairs for the matching BF16 consumption profile. All 192 frozen matrix
answers, eight development checks and four retained concurrency answers pass.
The quality producer's preemption-coverage failure remains recorded; a separate
current-source integration passes initial empty publication, three scored answers,
all publication controls and actual preemption with recurrent reseeding. Its two
forced continuations are mechanical tests, not scored QA. Full-checkpoint replay
and withdrawal cleanup pass. Immutable recurrent sharing saves 2.60 GiB (50%).

Final checks: 67 executed Rust tests, 62 serving tests without skips and 35 offline
Python tests. Evidence and executed-source identities are retained in
[`evidence/20261004-native-context-5080-completion/`](evidence/20261004-native-context-5080-completion/).
The INT8 implicit-alias failures and unpromoted learned router remain separate
research results; this completion does not assert production readiness or arbitrary
model/alias support.


## 4 October: matching-contract INT8 retest

The [INT8 consumption report](../../docs/validation/native-memory-int8-20261004.md)
records **432/432** exact answers: online native 144/144, matched text 144/144,
and strict-prepared native 144/144 at zero/sixteen/forty-eight prior turns.
The independent audit verifies every trace, source content, instructions, canonical
selection and zero encoding in all prepared observations. Online/prepared native
answers agree in every paired case. Merisol/Osreth outpost failures do not reproduce
under the current instruction profile.

The initial placement hits GPU OOM on the first forty-eight-turn text control
after 193 correct answers. Those exact traces remain retained; eight additional
matrix layers are stored on CPU for the continuation, with unchanged CUDA layer
arithmetic and four separately checked replay observations. This capacity failure
is not an incorrect answer. Recurrent sharing saves 2.60 GiB (50%), checksums pass,
forty offline Python tests pass, and the GPU is idle after completion.

Evidence: [`evidence/20261004-int8-consumption/`](evidence/20261004-int8-consumption/).
The historical 135/144 failed gate remains valid for its older contract; this
finite retest does not certify other quantization formats or INT8 vLLM serving.

## Dedicated model-plugin release

The [dedicated model-plugin validation](../../docs/validation/native-memory-serving-and-model-plugins-20261004.md) records three isolated Rust-adapter plugins, actual quantized
Gemma 12B/26B execution and complete-prefix Qwen FP8 serving. It preserves
the earlier INT8, BF16 and failed-attempt evidence as separate profiles.
