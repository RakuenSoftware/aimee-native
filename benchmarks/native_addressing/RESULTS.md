> The earlier completion assessment is superseded: its 75/96 quality result left a native-consumption defect unresolved. The complete hybrid-state follow-up below closes that defect only after its new gates pass. Historical evidence remains unchanged.

# Native addressing: implementation and evaluation decisions

Date: 2026-10-03. The implementation and evaluation are complete, including
the completion study below. The original first-cycle evidence is preserved.
The research controls and measurement tools are implemented; production defaults
remain unchanged. Experimental gates reject automatic promotion of a learned
router, a new lossy representation, or a native write path.

## What is useful

Make the address/representation contract explicit, keep the active bank bounded,
and measure discovery separately from native consumption. Retrieval cadence is a
real cost control, but repeated reads do not establish better discovery. Preserve
authority-owned selection and exact revision-bound record reuse.

The immediate implementation adds server-controlled preload-only and bounded
refresh schedules, source-call budgets including failures, and an optional total
active-record limit. Existing position/cache/device budgets remain separate.
Overflow refuses complete-record admission rather than silently evicting facts.
Generation checks still run on every forward and before returning an answer.
Legacy cadence remains the default. Failed reads and failed requests retain timing.

Production serving adds opt-in process-lifetime selection-RPC and activation/cache
wall counters through its existing operator-only metrics channel. No query,
publication name, tensor, or record content enters those counters. They do not
measure isolated GPU work. The separate GPU benchmark does that controlled
comparison, with dispatch/queue effects explicitly included.

Bounded diagnostic exports identify layer, query position, pooling and positional
representation. An inverse-rotated FP32 query is labelled separately from a true
pre-rotary projection because the original query has already been rounded.
The separate fitted partition-router prototype emits bounded candidate hints and
explicit abstention. Representation mismatch and deleted partitions require
fallback; candidates cannot authorize or mutate memory.

## Paired full-model scheduling

A frozen 27B checkpoint, INT8 research runtime, identical prompts and greedy
decoding were used for ten public synthetic tasks, repeated twice per condition.
The immutable fixture has six relevant records and 1,000 distractors. Its exact
cue index is a controlled source fixture, not production semantic search or
production authorization. Quality/call-count gates were recorded before execution.

| Schedule | Correct answers | Correct discovery | Source calls | Address attempts |
|---|---:|---:|---:|---:|
| Every step | 14/20 | 14/20 | 96 | 76 |
| Preload only | 14/20 | 14/20 | 20 | 0 |
| Bounded refresh: every 4 steps, at most 8 calls | 14/20 | 14/20 | 52 | 32 |

Preload-only avoided 79.2% of source calls; bounded refresh avoided 45.8%.
Neither introduced an additional wrong answer on these paired tasks. Median
request times were 2,257.8, 2,248.3 and 2,254.6 ms respectively: little observable
end-to-end change. Fixed condition order, mixed first-pass cache state and small
sample size prevent a controlled latency-speedup or general quality claim.

All six direct code questions passed in both repetitions. All three relay-to-
station questions failed in every condition: the second required record was never
discovered. Unknown-information responses passed. An unchanged-bank event is
therefore evidence of redundant work in this fixture, not universal permission to
skip future reads.

Each condition encoded six records and reused twelve record encodings across
requests. Every-step additionally made 72 unchanged-bank reads; bounded refresh
made 30. Peak active positions were 18 and peak logical K/V bytes 1,179,648.
These are a small-bank observation, not physical allocator residency.

## Oracle consumption control

A separate preload-only control supplied externally specified, revision-bound
expected records through the native bank, without adding their text or answers to
the conversation. Native memory passed **10/10**, including the three multi-hop
questions. The paired native-disabled control passed **1/10**, the unknown case.
Selection coverage was 10/10 for the enabled oracle condition.

This identifies discovery as the failure in this fixture. It supports improving
bounded candidate expansion and selection evidence before introducing another
representation. It does not show that an oracle is an implementable selector.

## Learned routing gate

Six development and six distinct held-out query phrasings generated real query
states in a separate memory-free, untimed diagnostic run. Three entity partitions
were represented. The fitted cosine-centroid router was evaluated with a one-
partition budget, score threshold 0.1 and margin threshold 0. Its predeclared
primary configuration was layer 3, inverse-rotated FP32, mean-head pooling.

The primary router hit **3/6** held-out targets and abstained **0/6** times. The
remaining predictions were confidently wrong under this threshold. Deterministic
exact entity-cue routing covers all six held-out prompts. The learned router
fails its predeclared gate and is **not promoted or linked into production**.

The 64 exploratory combinations span 16 native layers, two positional treatments
and two pooling strategies. Hits range from 2/6 to 6/6. Selecting a best variant
on those same held-out examples would invalidate that holdout; no such promotion
is made. This tiny closed-domain dataset does not support model-family,
quantization, open-domain or archive-growth stability claims. Generated fitted
weights remain temporary research artifacts and are excluded from repository evidence.

## Native consumption cost

The current fused serving attention kernel was checked against an independent
FP32 dense reference for 12 cells: text positions 32/512/4,096 crossed with native
positions 0/64/256/1,024. BF16 geometry was 24 query heads, 4 K/V heads and width
256; one decode query; 30 randomized-order matched pairs per cell. The AMD GPU
benchmark records both completed GPU-event intervals and completed wall time.

At 4,096 text positions, median paired GPU increments were approximately 4.0,
13.7 and 54.4 microseconds for 64, 256 and 1,024 native positions. One layer's
logical native bytes were 0.25, 1 and 4 MiB. Zero-native pairs expose noise;
negative individual deltas are retained. The intervals include dispatch/queue
work and are not pure kernel execution or whole-model answer latency. No archive
search was performed inside this microbenchmark.

A separate full-budget check in the pinned serving environment (its different
Torch/Triton versions) passed at 4,096 text and 2,048 native positions, with
8 MiB logical native bytes per layer and a median paired GPU increment of
182.3 microseconds across 30 pairs. Its intervals must not be pooled with the
research-environment matrix. Both environments retain exact version labels.

## Decisions on reuse, compression and writes

Retain the existing exact per-record reuse path. This cycle exercised working-set
churn; library regressions cover revision invalidation, publication retention,
namespace separation, LRU pressure and positional integrity. Existing reuse
validation remains the evidence for broader workloads. No cross-model reuse is
claimed: model-specific derived states must retain their encoder binding.

Do not introduce another lossy codec in this cycle. The measured failures are
missing records, while oracle-selected exact native states already answer all
fixture questions. A compact semantic block has not demonstrated a quality or
cost advantage over the current bounded exact working set.

Do not add a native mutation channel. Query-address vectors have demonstrated
neither validated factual proposals nor an advantage over the authority's existing
textual proposal workflow. The proposal's write-path prerequisite is unmet. This
is a negative gate decision, not an unfinished automatic implementation step.

## Validation and reproducibility

- 55 Rust library tests passed with the checkpoint tokenizer enabled; the serving
  binary built successfully. New regressions cover failed-call budget accounting,
  record overflow before encoding, and withdrawal on a skipped retrieval step.
- 22 offline auditor/router tests passed. Historical 42-request audit still
  retains 42 external passing scores and 360 unchanged-bank events.
- 35 serving admission/cache/state/telemetry/control tests passed using the current
  Rust policy library and the pinned serving environment, including enabled
  telemetry with failed plans/uploads. Initial attempts with old/ABI-mismatched
  native libraries failed; those were environment mismatches, not passing checks.
- The pinned serving GPU numerical test passed all 18 ragged/window/soft-cap
  geometries (three requests per case), alongside the new 12-cell cost benchmark.
- Python compilation and `git diff --check` passed.

The exact executed runtime sources, test output, original campaign traces,
predeclared protocols, external scores, feature exports and kernel samples are in
[evidence/20261003](evidence/20261003/). The trained router weights are excluded.
All 18 checkpoint files were SHA-256 verified against their download metadata;
all belong to immutable revision `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`.
Evaluated runtime binary SHA-256:
`84eb2a9198a1d3e745723b0811e450b22a638466c31b670fe4272357dfbdcb03`.

The experiments used isolated sources, a loopback-only child server and public
invented records. The runner stops only its own process group. No live service,
production publication, authority store, signing material or checkpoint weights
were changed or committed. The registered repository-memory service was unavailable;
its investigate and hybrid requests failed, so direct repository inspection was used.

The broader proposal's production promotion and large-archive semantic claims
remain unproven. They are not relabelled complete by these engineering results.

## Completion study: real reader and governed candidate expansion

The previous first-cycle closure left candidate integration, larger real archives,
robustness and serving validation unfinished. These are now evaluated rather than
being inferred from the Python fixture or the attention microbenchmark.

The trusted publisher can explicitly publish bounded bundles of exact canonical
references and cues. Signed compilation verifies every target against approved
records. Released-row compilation verifies targets belong to the released rows or
approved public base. No private aliases or graph edges are automatically used.
The current read-only adapter sends an opt-in publication-bound address envelope;
the owner selects complete bundles, and the reader resolves current canonical
records before delivery. Existing preparation reads use the same published routes.
An index lookup examines matched partitions only, not the full routing catalog.

Routing rejects representation/binding errors, ambiguous cues and record overflow;
overflow delivers no partial bundle. Unknown cues use one existing local fallback.
Partition hints narrow matched routes and do not grant access. Route metadata must
be explicitly republished after changes. Source expiry is checked per selected
record and cannot poison the unrelated route index. Existing generation checks,
independent remote authorization, position/device limits and cache bindings remain
in force. The learned prototype remains separate and rejected by its earlier gate.

### Actual archive growth

These are physically published Go-reader archives, not Python dictionaries. Each
query selects one partition and two canonical records. Each warm cell has 1,000
host-wall samples, including canonical source resolution and response creation.
The archive-size cases retain six route partitions; the final case independently
increases the routing catalog. Timings are descriptive, not randomized speedup
comparisons or a universal semantic-search result.

| Published records | Route partitions | Open archive | First route call | Warm median | Warm p95 |
|---:|---:|---:|---:|---:|---:|
| 1,006 | 6 | 40 ms | 145 µs | 26.7 µs | 62.6 µs |
| 10,006 | 6 | 385 ms | 86 µs | 26.4 µs | 31.7 µs |
| 100,006 | 6 | 3.83 s | 121 µs | 24.2 µs | 27.3 µs |
| 1,000,006 | 6 | 48.44 s | 328 µs | 25.7 µs | 38.2 µs |
| 100,006 | 100,006 | 4.31 s | 391.8 ms | 29.9 µs | 68.0 µs |

Warm indexed addressing barely changed with this archive growth. Startup, index
construction, publisher compilation and uncovered-query fallback have different
scaling. This is exact cue/partition addressing, not constant-time semantic search,
and it does not establish ten-million-record or arbitrary-query performance.

### Full-model routing and consumption

The frozen 27B INT8 runtime used the actual Go published reader at 100,006 records.
The experiment retained the original ten tasks and added six paraphrase/alias tasks,
at zero and sixteen preceding conversation turns, under all three schedules.
Protocols declared complete record selection and exact-answer scoring before runs.
The empty remote fallback fixture contains no records or task answers; it is not a
production authorization claim. All 96 scored requests completed.

| Schedule | Correct answers | Correct required-record selection | Source calls |
|---|---:|---:|---:|
| Every step | 25/32 | 32/32 | 171 |
| Preload only | 25/32 | 32/32 | 32 |
| Bounded refresh | 25/32 | 32/32 | 87 |

Every original question passed in every condition and conversation length:
**60/60**, including all **18 multi-hop cases**. The earlier 60-request synthetic
reader campaign had failed every multi-hop case. This is improved evidence of
complete discovery; different readers/archives prevent a matched latency claim.

The six additional questions yielded **15/36** correct answers despite complete
selection. Three short-context paraphrases returned two wrong answers; alias
questions returned five wrong answers across the two conversation lengths in
each schedule. Wrong answers remain failures. The broad exact-answer gate fails;
selecting the right records does not guarantee native composition or alias use.
All schedules produced identical scored outcomes. Preload-only avoided 81.3% of
source calls and bounded refresh avoided 49.1%, relative to every-step. Memory text
added **zero** conversation prompt tokens. Peak active records were two, peak
native positions 33 and peak logical K/V bytes 2,162,688.

The prior learned-router, compression and proposed-write decisions remain negative.
This completion study adds no trained router, lossy codec or memory mutation path.
Owner-approved bundles and address envelopes are available as explicit experimental
interfaces; the failed broad quality gate prevents making them a general production
quality claim or silently changing legacy defaults.

### Current serving runtime: another family and two weight profiles

The current Python plugin source and current Rust portable library were launched
in isolated processes on the pinned serving distribution. The existing explicitly
synthetic three-record banks were consumed by a 12B model from another family,
under BF16 and Q8 weight profiles. Each profile ran 72 matched native/text requests
at zero, sixteen and forty-eight preceding conversation turns: **144/144 correct**,
including **72/72 native requests**. This reuses previously prepared states; it does
not test fresh authorization, preparation or the new cue router for that family.
It therefore cannot repair or supersede the failed 27B alias/paraphrase gate.

Both tensor-parallel workers exposed enabled `native-host-stages-v1` telemetry.
Each profile recorded two bank activations and 144 activation/cache measurements
per worker. Frontend telemetry was enabled; selection-RPC timing remained absent
because this fixture uses a static catalog. No absent stage is inferred as zero,
and nested host counters are not added together or interpreted as GPU time.
Exact answers and current-package operation survive this weight-profile change;
this is limited engineering coverage, not universal address stability or accuracy.

### Completion decisions and retained evidence

- Retain measured scheduling controls, explicit candidate/active-bank bounds,
  stage telemetry and revision-bound exact reuse.
- Keep owner-approved candidate bundles and the publication-bound envelope opt-in.
  Original multi-hop discovery now passes; broader exact-answer quality does not.
- Do not promote the learned router, add a lossy representation, or implement a
  native mutation path on the evidence collected.
- Leave legacy defaults and live deployments unchanged. No unrelated services
  were stopped, and no authoritative or private memory was altered.

The implementation and the proposed evaluation programme are complete with these
positive and negative decisions. Failed research gates remain failures; completion
is not a claim that open-domain native memory or every experimental feature is
production-ready.

Completion evidence is in [`evidence/20261003-completion/`](evidence/20261003-completion/).
It includes all 96 hashed model traces, both serving profiles and worker metrics,
physically verified archive counts/data/index hashes, publication manifests,
executed source inputs/snapshots, failed startup attempts, and validation outputs.
No model weights, learned fitted weights, prepared tensor banks or signing keys
are included. Original first-cycle evidence and hashes remain unchanged.

## Complete hybrid prefix follow-up

The implementation now treats native memory as a complete frozen-model prefix.
The tested model has 16 full-attention layers and 48 linear-attention layers;
K/V-only memory discarded the latter layers' convolution and recurrent states.
The new opt-in profile retains both, seeds private request-local state and replays
observed conversation tokens when an authorized bank changes. A deterministic
hybrid-model regression matches contiguous memory-plus-conversation encoding
through prefill and decode; omitting recurrence deliberately fails that control.

Complete preparation stores lossless, checksummed sidecars and separate model/
profile identities. FP32 recurrent state is preserved. Strict serving rejects
missing, corrupt, incompatible or over-budget state without encoding. Reusable
state cannot be changed by in-place decoding. Publication checks remain active
when retrieval is skipped and before/after replay. No trained adapter, new policy
engine, lossy state, learned-router promotion or native write path is introduced.

The profile was frozen as `complete-hybrid-content-v1` after development diagnosis.
Attention-only joint-content, keyed, JSON and chat-framed variants did not close
the development gap. Complete plain content passed 16/16 development questions;
complete chat and keyed-chat passed 15/16 and 13/16 respectively. These are
diagnosis results, not independent held-out promotion evidence.

The first fresh implicit-alias holdout remains a **failed gate: 135/144 answers**,
with 144/144 canonical selections. All nine failures concern the same outpost
alias across three schedules and three conversation lengths. Its routing cues
contained the alias but its canonical facts did not assert that identity. Cues
authorize candidate selection; they do not establish semantic truth.

A separate fixture freezes new names and codes and adds explicitly approved
canonical identity facts. Its source contains 100,009 physically verified records,
including nine relevant records and six owner-approved routes. The initial
implicit fixture contains 100,006 records. This evaluates explicit semantic
grounding, not a repair or relabeling of the failed implicit-alias holdout.

The complete profile is implemented in the Rust research integration. Historical
serving-plugin tests for another family exercise attention-only banks and do not
certify this complete hybrid profile. Production deployment and open-domain
accuracy are outside this completed implementation/evaluation scope.

### Final full-model gates

| Complete profile | Exact answers | Required canonical selection | Prior turns |
|---|---:|---:|---|
| Development, online | 96/96 | 96/96 | 0, 16 |
| Explicit-identity holdout, online | 144/144 | 144/144 | 0, 16, 48 |
| Development, strict prepared | 96/96 | 96/96 | 0, 16 |
| Explicit-identity holdout, strict prepared | 144/144 | 144/144 | 0, 16, 48 |

All three schedules pass in every row: **480/480** total. The independent auditor
verifies the complete Cartesian task matrix, unique samples, every trace hash,
answers against frozen expected values, canonical identities, matching online/
prepared answers, and the identical executed binary digest across all four cells.
Every request adds zero memory text tokens to the conversation. All 240 prepared
requests perform zero memory encoding passes. Six distinct canonical bundles
were prepared for each fixture; offline encoding is a separate measured stage.

Preload-only makes exactly one source read per request. In each 240-request
online/prepared half, every-step makes 465 reads, preload-only 80 and bounded
refresh 235: reductions of 82.8% and 49.5% respectively, with identical answers.
The bounded per-request source limit remains eight. These stable-bank campaigns
perform no bank-change replays; changing-bank correctness has deterministic
model regression coverage, not a new full-checkpoint changing-bank quality claim.

Peak active state is three canonical records, 44 attention positions, 2,883,584
logical attention bytes and **154,927,104 immutable convolution/recurrent bytes**
(147.75 MiB), below the 256 MiB recurrent cap. Private request copies, staging,
conversation caches, model weights and allocator overhead are additional. Each
six-bundle preparation writes twelve base/positioned entries and duplicates the
recurrent payload: 1,859,125,248 bytes (about 1.73 GiB) per fixture. This is
lossless reuse with a substantial storage cost, not compression or free memory.

HTTP medians are descriptive, approximately 2.6–2.8 seconds, with fixed run order
and startup excluded. No matched speedup, archive-independent semantic search,
GPU-memory-residency or universal model accuracy claim follows.

Validation passes 60 Rust tests and 24 offline Python tests. The earlier Go race
suite and 35 serving admission/cache/control tests remain retained. New evidence
is in [`evidence/20261003-hybrid-state/`](evidence/20261003-hybrid-state/), with
executed sources, binary identities, public fixture inventories, raw successful
and failed model traces, preparation metadata and payload checksum reports.
Prepared tensors, checkpoint weights and private signing material are excluded.

### Retained implicit-alias limitation and final decision

A subsequent text-memory control on the initial implicit fixture passes **16/16**,
including the native-failing alias. It uses the same reader-selected canonical
source facts at zero prior turns and preload selection, but places them in the
system-message memory block. This is a diagnostic representation comparison,
not a matched 144-request text matrix or latency experiment. It shows that missing
explicit identity facts alone do not explain the native failure: implicit alias
inference remains weaker for this native prefix in the tested case. No additional
training, inferred authoritative facts or silent text fallback masks that result.

The scoped implementation and evaluation are complete. Retain the bounded
working set, authority-bound address contract, stage telemetry, scheduling controls,
exact derived-state reuse and complete hybrid prefix profile. The latter is an
explicit research opt-in with demonstrated architectural correctness and passing
explicitly grounded gates, not a general-quality default promotion. Keep the
implicit-alias quality gate failed, the learned router unpromoted, and lossy/write
paths declined. All experimental processes owned by this study have exited;
production deployments and unrelated workloads were not changed.


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
