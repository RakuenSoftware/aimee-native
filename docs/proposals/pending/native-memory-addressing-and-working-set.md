> Final repair completion: [4 October validation](../../validation/native-memory-completion-20261004.md) closes the four remaining gaps for the matching BF16 instruction profile. Earlier INT8 failures remain unchanged and unpromoted.

> The earlier completion assessment is superseded: its 75/96 quality result left a native-consumption defect unresolved. The complete hybrid-state follow-up below closes that defect only after its new gates pass. Historical evidence remains unchanged.

# Native memory addressing and bounded working sets

Status: implementation and scoped evaluation complete; complete-state gates passed.
Date: 2026-10-02; final repair validation 2026-10-04.

## Problem and intended behaviour

A model can consume external knowledge through native attention states, while
selection still depends on a user-message query or lexical reconstruction from
attention addresses. These are different interfaces and must be measured separately.
The system should discover relevant knowledge when reasoning needs it, deliver a
bounded working set, and preserve canonical identity, revision and release authority.

The objective is better task quality per unit of retrieval, preparation and
consumption cost. A large durable archive does not require a large active bank.
Bounded native consumption does not imply constant archive search or constant
ordinary conversation attention.

## Existing mechanisms and evidence limits

The integration already has native key/value delivery, separate conversation
caches, token and device-byte limits, versioned record encodings, selective reuse,
and prepared-bank admission. Local named-address lookup has been evaluated as the
archive grows. Selection, encoding/cache handling and activation have some timing
coverage. These measurements do not yet form a matched benchmark for semantic
addressing, decode scheduling and end-to-end archive scaling.

The research runtime reconstructs lexical spans from attention scores and can
retrieve during decode. The serving plugin selects before generation from the
latest user message. Their scheduling, selection and preparation differences
must be explicit experimental conditions rather than pooled results.

## Contracts

### Native addressing

An address request identifies the model/representation version, layer and
positional treatment, request step, publication binding, candidate budget and
requested scope supplied by the trusted host. Candidate generation is distinct
from eligibility and final selection. A miss or uncertain result can invoke a
bounded fallback; a denial cannot be converted into a fallback permission.

Returned knowledge carries canonical namespace, identity and immutable revision.
Model-specific representations derive from those records and never own their
authority. Router replacement may change the mapping without changing identity.
No hidden-state vector is assumed to be a semantic search embedding by default.

### Active working set

Define separate server-controlled limits for candidate count, active records,
memory positions, device bytes, newly activated positions, retrieval interval and
total request retrieval work. Record-count limits alone do not bound native cost.
Preserve complete selected records; overflow is explicit. Replacement/retention
policy belongs to the memory owner, not to an adapter that silently drops facts.
Pinned request banks and reusable caches have separate budgets and lifetimes.

### Measurement

Every experiment specifies model/checkpoint, selector, schedule, archive size,
context size, active-position budget, encoding granularity and cache condition. Store exact source-trace
hashes and externally scored task outcomes. Separate failures from successful
request timing distributions; failed requests remain in coverage and quality counts.

Measure addressing, source selection, encoding/cache bookkeeping, activation and
incremental native attention cost separately. Nested timings are not additive.
CPU dispatch timing is not completed GPU time. Missing measurements remain unknown,
including absent events, rather than becoming zero. Never estimate attention cost
by subtracting unrelated end-to-end runs.

Correct record selection and correct final answers are separate outcomes. Expected
records are externally supplied revision-bound references; self-reported selection
is not an oracle. For multi-hop tasks, distinguish cumulative discovery from the
final active working set. Benchmark labels and sealed answers never enter learning.

## Delivery sequence

### Phase 1: baseline measurement and trace audit

Implement a dependency-free offline auditor for experiment manifests and existing
native traces. Keep conditions separate, expose timing sample coverage, classify
selection/consumption failures, count unchanged-bank retrievals, and report source
hashes. Incomplete conditions or malformed evidence fail visibly. The auditor
does not launch models, mutate memory, or infer unmeasured GPU costs.

Then extend runtime instrumentation where coverage is absent: addressing time,
active-bank positions/bytes, activation, synchronized consumption microbenchmarks,
and failed-request durations. Preserve exact selection and attention semantics.
The first deliverable is this proposal plus the manifest/auditor and its tests.

### Phase 2: retrieval scheduling controls

Compare preload-only, existing decode retrieval and deterministic bounded refresh
using the same selector and memory budget. A refresh policy may consider address
change and explicit unresolved cues; it must define a retry interval and maximum
calls. Preserve generation checks and invalidation on skipped retrieval steps.
Offline replay describes potential calls avoided only: generated trajectories
change when reads are skipped, so replay cannot establish answer quality.

Run full-model paired tasks before promoting any scheduling policy. Measure missed
necessary reads, redundant reads, discovery delay and final task outcomes.

### Phase 3: candidate routing

Compare latest-message selection, attention-to-span selection, deterministic
partition routing and a small optional learned candidate router. Use oracle-selected
records to diagnose the consumption ceiling. Prototype learned routing separately
from the untrained production adapter. Eligibility and final selection stay with
the memory authority.

Evaluate pre/post positional representations, layers, head aggregation and pooling.
Route to bounded candidates or partitions with their own retrieval limits. Treat
abstention and fallback as measured behaviour. Train using development relevance
and verified downstream outcomes; do not just imitate existing retrieval errors.

### Phase 4: representation reuse and compression

Measure independent record reuse under working-set churn, revisions and model
replacement. Only then investigate compact derived blocks. Bind them to source
revisions, encoder identity, applicability and invalidation dependencies. Evaluate
exact numbers/names, multi-record composition and corrections alongside gist recall.
Independent encoding and compression require quality checks; numerical or semantic
equivalence is not assumed.

### Phase 5: proposed writes

Investigate a native proposal signal only after read-path results justify it.
Produce inspectable candidate content tied to source spans, outcomes and parent
revisions. The authority validates, resolves conflicts and publishes accepted
knowledge. Compare proposal precision and capture cost with textual proposals.
Hidden-state confidence never supplies factual authority or mutation permission.

## Evaluation matrix and decision gates

Vary archive size, conversation length and active-bank budget independently.
Use nested archives with unchanged target identities plus new distractors; record
query distributions and index/startup cost. Include paraphrases, aliases, ambiguous
entities, missing knowledge, multi-record composition, temporal changes, deletion,
contradictory sources, poisoning attempts and permission withdrawal.

Hold prompts, model revision, decoding and scoring constant in paired comparisons.
Record cold preparation, warm activation and resident reads separately. For
consumption overhead, use matched token workloads or controlled attention kernels;
different generated answer lengths are not equivalent compute.

Promote a change only when matched evidence improves task quality or cost without
unacceptable regressions, stale-revision use or authority violations. Set concrete
quality/cost tolerances before each run rather than selecting thresholds afterward.
Publish achieved coverage, fallback work and maintenance/training cost. Partial
runs support partial conclusions only; archive-scale and lifelong-learning claims
require corresponding evidence.

## Ownership and first implementation scope

Native contracts, runtime integration and experiments belong in the integration
repository. Canonical knowledge, eligibility, authorization and mutations belong
to the memory authority. This programme does not add a competing policy engine.

The initial implementation was the phase-1 offline measurement slice. Research-runtime
instrumentation follows it. Learned routing, scheduling policies, training campaigns
and deployment are later deliverables, not claims attached to an offline audit.

## Initial implementation evidence

The baseline auditor, manifest contract and usage guide are implemented under
`benchmarks/native_addressing/`. Twelve tests passed, including missing/partial
timings, malformed evidence, condition separation, failure attribution, source
hashes and refusal to overwrite reports.

A read-only compatibility audit consumed 42 archived native requests and retained
all 42 external passing scores. It found 360 unchanged-bank retrieval events,
complete encoding/cache timing for 21 requests, and no source-selection timing in
those historical traces. Exact conditions yielded 42 groups, so this exercise is
schema/coverage validation, not an aggregate latency comparison. Unchanged-bank
events are scheduling research opportunities, not demonstrated safe skips.

## Research-runtime instrumentation — 2026-10-03

The runtime now measures native addressing wall time and attempts, complete recall
duration, and post-recall active records/positions/logical K/V bytes with lifetime
peaks. Both successful and failed request traces expose these metrics; failed
requests also expose total elapsed time. Empty/rejected selections and unchanged
banks now carry explicit timing coverage. Admission failures remain visible without
guessing unavailable substage costs. Existing prepared-load metrics remain distinct.

Addressing time includes bank preparation and host readback and overlaps other
stages. Encoded bytes are logical across native layers, not device residency.
Telemetry does not change selection, refresh cadence, authority checks or attention
math. The auditor validates the new scopes while continuing to accept older traces.
GPU attention-cost microbenchmarks and serving-plugin telemetry remain outstanding
before the phase-1 measurement contract is complete.

Validation passed 15 auditor tests, 50 Rust library tests and the serving-binary
compile check. The archived 42-request compatibility audit still retains its
original outcomes and reports historical telemetry as missing. See
`benchmarks/native_addressing/VALIDATION.md` for the checked source hashes,
measurement limits and raw test evidence. No live latency or quality gain is
claimed by this instrumentation slice.

## First-cycle closure — 2026-10-03

The read-path controls, separate serving telemetry, controlled GPU cost benchmark,
query-state diagnostic export and candidate-only fitted-router prototype are now
implemented and evaluated. The paired schedule campaign completed 60 full-model
requests; the independent oracle/native-disabled control completed another 20.
The original broad evaluation matrix is not claimed complete.

All three schedules retained 14/20 passing outcomes on the small public fixture.
Preload-only reduced source calls from 96 to 20; bounded refresh reduced them to
52. No material answer-latency improvement was established. The unresolved
multi-record questions passed with oracle-selected native banks, identifying
selection/discovery rather than native consumption as their failure.

The predeclared learned-routing configuration found only 3/6 held-out targets and
failed its gate. Exploratory alternatives cannot replace that primary result
without a new holdout. The prototype remains separate from the untrained adapter.
The useful changes retained from this cycle are explicit contracts, bounded
retrieval controls, truthful stage measurement and exact governed record reuse.

The representation/write prerequisites are unmet. This cycle explicitly declines
a new lossy representation and a native proposed-write path; it does not leave
them scheduled for automatic implementation. Broader semantic archive scaling,
model-family/quantization robustness and production promotion require new evidence.
See `benchmarks/native_addressing/RESULTS.md` for the full decisions, limitations,
exact source/trace evidence and validation. Production defaults are unchanged.

## Implementation and evaluation completion — 2026-10-03

The first-cycle closure above was insufficient to close this programme. The
completion study integrates publication-bound addressing with the actual published
reader, adds explicitly publisher-approved complete candidate bundles, measures
real archives through 1,000,006 records and a separate 100,006-partition catalog,
and evaluates native discovery and consumption on extended full-model tasks.

Warm owner-selected two-record access remains approximately 24–30 microseconds in
these archive/catalog probes; opening the largest archive takes 48 seconds.
Startup, index maintenance and unknown-query fallback are explicitly excluded from
any constant-cost claim. Bound candidate selection and active consumption rather
than promising archive-independent semantic search.

The actual reader provides every required canonical record in 96/96 model requests.
All 60 original task/conversation/schedule combinations pass, including 18 multi-hop
cases. Additional paraphrase/alias questions expose native consumption failures:
total exact-answer quality is 75/96. This fails the broad quality promotion gate,
while all three schedules retain identical outcomes with fewer source calls.
The bounded router/address interface remains explicit and experimental.

Revision, deletion, expiry, alias punctuation, ambiguous names, invalid hints,
unapproved records, poisoned receipts, address mismatch, withdrawal and publication
delta delivery have executable regression coverage. The authority's existing core
policy remains the authorization dependency; no new policy engine or learned
adapter is introduced. Legacy images and default schedules retain their behaviour.

Phase decisions are closed: measurement and bounded schedules are implemented;
owner-controlled candidate expansion and address contracts are implemented and
measured; the optional learned router fails its gate; exact representation reuse
is retained; a new lossy representation and native write channel are declined
because their prerequisites are unmet. These negative decisions do not authorize
future automatic implementation. No broad semantic search, lifelong learning or
universal model-family quality claim follows from these experiments.

The results report records the serving-family/weight-profile checks, raw evidence,
per-feature promotion decisions and remaining scientific limits. This completion
means the proposed implementation and evaluation have been carried out, not that
every tested hypothesis succeeded or every future research question is solved.

## Complete state for hybrid native memory

The attention-only interface omitted state produced by the model's linear
attention layers. A complete native prefix must contain every attention bank,
convolution history and recurrent state produced by the same frozen encoder pass.
It must retain FP32 recurrence, correct layer placement, ordered canonical source
records and model/profile identity. Treat this as lossless derived state, never
as an authoritative memory store.

Each request receives private recurrence copies. It may reuse immutable encoded
prefixes but cannot mutate them through decoding. If an authorized working set
changes during a request, rebuild the observed conversation against its new
complete prefix rather than mixing old recurrence with new attention banks.
Bound and report that replay separately; it performs no new source reads and
must check the publication before and after execution.

Offline preparation must publish the complete state atomically with checksummed
metadata, and serving must reject missing or incomplete profiles without encoding.
Attention-only artifacts retain their old identities and compatibility. A native
profile explicitly declares which model states it carries; another runtime's
attention-only success is not evidence for a hybrid profile.

The complete-state experiment freezes the plain-content joint-prefix profile
before testing fresh public facts. Its gate requires all exact answers and all
required canonical records across every-step, preload-only and bounded-refresh
schedules, online and strictly prepared serving, and conversations up to 48 prior
turns. Architectural equivalence, corruption, byte budgets, immutable reuse,
prepared misses and working-set replay have executable regressions.

The complete implementation now passes 480/480 exact-answer and canonical-selection
cases across online and strict prepared paths. Strict prepared serving performs
zero encoding. Active recurrence is explicitly bounded and reported separately
from attention; immutable prepared recurrence has a substantial storage cost.
The initial implicit-alias holdout remains failed at 135/144. A separate fresh
explicit-identity fixture passes; its result does not erase the implicit failure.
These outcomes close the proposed engineering/evaluation work with documented
limits, not a promise of general semantic or cross-runtime equivalence.

The initial fixture's text-memory control passes 16/16, including the native-failing
alias. This retains a native implicit-inference limitation and prevents claiming
that absent explicit identity facts were its sole cause. The complete profile
remains an explicit research opt-in; broad quality promotion is declined.

## Preserve the complete prefix's coordinates and instruction context

Bind a complete native prefix to the caller's system instructions as well as its
canonical source records. Encode one closed system message containing those
instructions followed by the approved facts; consume only the subsequent
conversation through the ordinary token path. A miss keeps the ordinary system
message. Prepared identity includes the instruction digest, so a different caller
context cannot silently reuse the same prefix.

Keep complete-prefix attention keys at their original positions `0..M-1` and
start conversation positions at `M`. Conversation cache length still counts only
conversation tokens. This avoids a second rotary transform of already rounded
memory keys. A bank change requires replay with the replacement prefix's position
offset, private convolution history and FP32 recurrent state. Publication failure
discards both native state and the conversation cache before returning an error.

Serving runtimes must implement the same contract explicitly: offset positions
before rotary projection, initialize the correct physical request's recurrence
only on initial prefill or recomputation, preserve evolving state on subsequent
chunks and decode, and retain the ordinary path for publication-free requests.
An attention-only integration cannot stand in for these checks. The initial
complete serving profile uses eager synchronous execution with FP32 recurrence.

Publish immutable recurrence by its content digest. Multiple attention placement
entries may reference the same lossless payload; request state remains private.
Charge raw host storage, partition copies, device residency and staging separately.
Validate actual physical file counts and bytes as well as logical entry totals.

Validate accelerator-specific execution on the requested hardware. If weights
exceed device capacity, keep selected matrix weights on the host while executing
their projections on the accelerator. Record the placement and transfer overhead;
do not treat an accelerator switch or successful small-model test as a completed
full-checkpoint quality gate.

## Bind serving identity and bound model loading

A derived native prefix must match the configured immutable checkpoint revision,
its tokenizer digest, its configuration digest and its encoder weight profile.
Matching layer geometry alone is insufficient. Apply this check in frontend
admission, worker initialization and replacement publication admission, before
reserving or installing a prefix.

Separate final device capacity from transient host loading capacity. On a small
accelerator, pageable host weights with explicit per-layer transfers can avoid
large pinned-memory reservations. Make this a declared placement option and
record the resulting transfer cost. Run checkpoint validation under a finite
host-memory limit and a timeout so a failed load remains confined to the test.
Keep the recurrent prefill backend explicit and use an installed supported
backend; successful attention-only startup does not validate recurrent kernels.


### Bind the consumption contract into derived state

Selection and factual identity are separate from the model's permitted inference.
An approved lookup cue selects records; it does not assert a new entity identity.
A long-context comparison found a question that failed under both native and text
memory with generic instructions. A general instruction permitting named-entity
resolution across descriptive nouns corrected the development text case; adding
lookup-cue metadata alone did not. Such observations justify a separately frozen
consumption profile, not rewriting canonical facts or relabeling prior scores.

Prepare the complete prefix with its caller-owned instructions, bind their digest
into every derived-state key and publication, reject a different context, and
consume the already encoded system role exactly once. Evaluate native and text
under the same fixed contract, retain negative old profiles, and reserve fresh
questions for the final matrix. Instructions, model precision/runtime, source
selection and factual grounding are independent experimental dimensions.


The [matching-contract INT8 retest](../../validation/native-memory-int8-20261004.md)
now passes 432/432 answers across online native, text controls and strict-prepared
native consumption. The explicit instruction-bound profile passes in both evaluated
precision paths; earlier INT8 contract failures stay recorded and unpromoted.
The INT8 study adjusts host matrix residency to finish on the 5080, verifies four
replays and all request traces, and leaves model arithmetic and canonical facts
unchanged. This does not promote a different quantized serving engine.
