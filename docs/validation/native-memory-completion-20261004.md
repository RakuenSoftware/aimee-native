# Complete hybrid native serving and checkpoint repairs

Completion recorded: 4 October 2026. Runs are individually timestamped in the evidence. This follows the earlier native-addressing and
complete-prefix studies and closes their four implementation/validation gaps for
the matching BF16 serving profile. Historical evidence and failed experimental
scores are retained unchanged.

The supported path combines a publication-bound, bounded canonical selection with
an offline complete prefix: attention K/V, convolution history and FP32 recurrent
state. Conversation positions start after the prefix; private request state is
initialized from the immutable seeds, preserved during decode and reseeded after
preemption. Closed system framing binds instructions into the prepared prefix and
requires the same context at admission. Serving never encodes memory.

## Gates

The independent completion audit passes. The frozen matrix passes **192/192**
answers: 48 tasks × three native conversation lengths (144) plus 48 text controls.
Eight development probes and four scored concurrency observations also pass,
for **204/204** retained scored observations. The 48 task IDs contain 47 distinct
questions: two declared missing-entity tasks intentionally share the same question,
answer and empty selection. The audit checks the declared multiplicity.

That quality producer retains its `failed` status because its initial workload did
not actually preempt; correctness scores alone do not establish recomputation.
The subsequent **current-source integration gate passes**, separately: empty-catalogue
startup activates all eighteen published banks, two mixed native/plain answers and
one republished answer are correct, and every negative admission control passes.
Two mechanical continuations request exactly forty tokens at 32/78 prior turns;
they are explicitly excluded from answer-quality denominators. The workload forces
one observed preemption and **192 recurrent seed events against 144 initial events**,
demonstrating the extra forty-eight-layer reseed.

Two final admission guards are covered by the current integration and unit tests:
install hybrid hooks even when startup has no publications, and reject convolution
cache dtype mismatches before writing any cache. The supported BF16 path performs
no silent convolution conversion. The quality matrix preceded these guards; its
consumer and runner source bytes are retained separately, and the unchanged
supported-profile arithmetic is not presented as a fresh rerun of that matrix.

The earlier generic-instruction BF16 run is retained as a failed diagnostic:
132/134 completed answers, including native Merisol/Osreth outpost failures at
sixteen turns. Merisol's matched text control also fails at sixteen turns but
passes at forty-eight. A development comparison fixes that text answer with the
general instruction to resolve named entities across different descriptive nouns
without inventing identity or connections. An alternative lookup-cue context does
not fix it and is declined.

The new consumption profile freezes that general instruction for all tasks before
the fresh set is evaluated. It is prepared once, binds its context digest, and uses
the same instructions in native and text controls. Eight development probes cover
the two known failures in both representations at sixteen/forty-eight turns. No
per-task answer instructions, authoritative identities or silent text fallback are
introduced. The historical prompts and failed scores are unchanged.

The frozen tasks include the original questions, the previously failing implicit
alias holdout and fresh implicit aliases. The source facts contain no newly
asserted alias identities. The real published reader selected exactly the expected
canonical records for all 48 tasks from 100,018 physically verified public records.
The matrix is native at 0/16/48 prior turns plus paired text controls at zero turns;
it is distinct from the older INT8 online/prepared three-schedule research gate.

The final research binary also passes the full **64-layer checkpoint replay and
withdrawal gate**. Over real published-reader facts and controlled source transitions,
a changed native bank gives bit-identical replayed outputs and convolution/recurrent
state to a clean forward. Withdrawal rejects the next forward and clears native and
conversation caches plus the position offset. This controlled probe uses INT8 row
weights to test exact state transitions; it does not promote INT8 alias quality or
claim a production authorization test.

Checkpoint identity binds immutable revision, tokenizer bytes, configuration,
encoder precision and positional profile. Same-architecture revision/tokenizer
changes reject derived state. Live control tests check wrong instructions,
withdrawal, wrong-revision admission, removal of all publications and recovery
through republishing. Publication withdrawal blocks new admissions; it does not
claim immediate cancellation of an already executing request.

The complete eighteen-bundle storage gate verifies all recurrent checksums and
base/positioned metadata. Thirty-six entries share eighteen digest-named payloads:
2,788,687,872 stored bytes versus 5,577,375,744 entry-summed bytes, saving exactly
2,788,687,872 bytes (50%, about 2.60 GiB). All eighteen serving exports hardlink
those payloads on the same filesystem, adding no recurrent copies. Cross-filesystem
exports retain a self-contained, byte-identical copy. This saving concerns immutable
storage; evolving request-private state still consumes additional memory.

## Executed configuration and evidence

One RTX 5080 ran the full 64-layer, 27B BF16 checkpoint: sixteen full-attention
layers and forty-eight GDN layers. The serving runtime is vLLM 0.30.0,
Torch 2.13.0/CUDA 13.0, Python 3.12.14. The model revision is
`1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`. Eager synchronous V1, FP32
Mamba caches, stock Triton GDN prefill and stock sampling were used. CPU offload
is 40 GiB, pageable and restricted to matrix projections. Native limits are
8 GiB host and 512 MiB device; the validation service has a 56 GiB host-memory
cap and no swap. The retained quality run uses a ten-block KV override. The final mechanical
preemption gate uses eleven blocks (ten usable), growing concurrent prompts
across the actual 784-token attention page boundary.
Maximum conversation length is 2,048 and maximum concurrent requests is two.

This configuration demonstrates correctness on a 16 GiB GPU through substantial
host weight transfers. It is not a low-latency or throughput certification.
Native byte/position limits exclude ordinary conversation caches and model weights.
Runtime checkpoint binding trusts the configured immutable revision pin; installed
weights must correspond to it.

Final validation: **67 executed Rust tests** (62 library, four binary and one
separately executed actual-CUDA equivalence test), **62 serving tests without skips**,
and **35 offline Python tests**. Earlier Go race coverage is retained; the final
serving guards do not change the Go authority implementation. The independent
audit checks exact answers and canonical selections, coverage, instruction identity,
publication controls, actual preemption and extra recurrent seeds. Both final model
services exited successfully, the owned fixture service was stopped and the RTX 5080
returned to idle (2 MiB allocated, 0% utilization).

Evidence: [`20261004-native-context-5080-completion`](../../benchmarks/native_addressing/evidence/20261004-native-context-5080-completion/).
Its `raw.tar.gz` contains 645 text/source/metadata members and has SHA-256
`c2971757e5aff58eec198d11b0df00e8356a036277fa8d2d2ec80cc89e6b7721`.
All sixty previously recorded evidence files retain their original hashes.

The source/binary provenance distinguishes final research code from earlier probes
and retained quality-consumer sources. All eighteen instruction-bound bundles were
freshly prepared with the final research binary. Compatible recovered Cargo/native support was
used for the research build. The portable C++ bridge was rebuilt from the exact
baseline HEAD implementation using its current `runtime_ops` import. Earlier
startup errors and unsuccessful framing candidates remain separate evidence.
No checkpoint tensors, prepared payloads, compiled binaries or private signing
material are included in the repository evidence.

## Decision

Retain the matching BF16 complete-hybrid serving path under its explicit tested
consumption contract. Its instruction profile is `complete-hybrid-entity-resolution-system-v1`. Retain bounded canonical selection, exact prepared reuse, scheduling
controls, independent authority checks and separate stage telemetry. The INT8
research implicit-alias gate remains failed and unpromoted; the BF16 result does
not isolate precision as the cause because its runtime and kernels also differ.
The learned-router prototype remains unpromoted, and lossy state/native writes
remain declined. Arbitrary model families, arbitrary aliases, immediate in-flight
revocation, production multi-tenant deployment and constant-time semantic archive
search are not established by these tests.


The [subsequent INT8 retest](native-memory-int8-20261004.md) passes 432/432
answers under this explicit instruction contract. Its historical failed INT8
scores remain unchanged; the retest records its separate research runtime and
capacity adjustment rather than attributing the earlier failures purely to precision.
