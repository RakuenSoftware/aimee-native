# Native addressing baseline audit

This offline tool joins existing native traces with explicit experiment conditions
and externally scored outcomes. It requires only the Python standard library.
It does not launch inference or modify memory, selection, scheduling or source traces.

```sh
python3 benchmarks/native_addressing/audit.py /private/experiment/manifest.json \
  --output /private/experiment/new-audit.json
python3 -m unittest discover -s benchmarks/native_addressing -v
```

The output must be new. Files created by the tool use mode 0600. Reports exclude
queries, answers and source memory content; task labels and condition labels are
still caller-supplied, so store reports according to the experiment's data policy.

## Manifest

```json
{
  "schema": "native-addressing-v1",
  "samples": [{
    "task_id": "composition-001",
    "replicate": 0,
    "trace": "traces/request-001.json",
    "correct": true,
    "selection_correct": true,
    "condition": {
      "model": "checkpoint-and-runtime-revision",
      "selector": "attention-spans",
      "schedule": "decode",
      "archive_records": 249105,
      "context_tokens": 64,
      "position_budget": 2048,
      "cache_state": "warm-record-cache",
      "encoding_granularity": "record"
    }
  }]
}
```

Trace paths are relative to the manifest directory, or absolute. All eight condition
fields are required; numeric dimensions are nonnegative integers. Include checkpoint,
quantization and runtime revision in `model`; keep positional/layer/router variants
distinct in `selector`. `context_tokens` describes the declared task input context,
not the final generated conversation length. Task/condition/replicate must be unique.

`correct` and `selection_correct` are independently supplied boolean scores or null.
Selection scoring must use external expected canonical identities/revisions and an
explicit criterion (for example, all necessary records discovered before answering).
Correct selection with a wrong answer identifies a consumption **or execution**
failure; the auditor cannot identify its exact cause. Runtime failures take precedence.
An unscored request stays unscored. Failed traces cannot be labelled correct.

## Trace compatibility and coverage

The tool reads the existing request `elapsed_ms`, `native_reads`,
`memory_encoding_passes`, `native_ready_ns`, `native_bank_application_cpu_ns` and
`recall_events` fields. Recall events expose `source_selection_ns`,
`encoding_elapsed_ms`, `recall_elapsed_ns`, `memory_encoding_tokens` and `status` where available.
Nanosecond fields convert to milliseconds. Encoding timing includes cache and
assembly bookkeeping; it is not isolated neural encoder time.
Tokenization/serialization before the encoding/cache timer is outside that substage;
the new complete recall timer includes it.
The existing source-selection timer can also include response validation and merge
bookkeeping; it is not an isolated database-query timer.

The instrumented research runtime supplies `native_addressing_ns` and a
`native_memory_metrics` object on both successful and failed requests. Addressing
is wall time including bank preparation, scoring, host readback and lexical
translation, excluding the subsequent source recall. No new GPU synchronization
is added. It is not isolated GPU kernel time and overlaps bank-application timing.
Attempts include empty addresses and failed translations.

The versioned metrics object carries current and peak active positions, records
and logical encoded K/V bytes across native layers, plus addressing attempt/failure
counts. These peaks observe post-recall working sets and survive cleanup on failure.
Logical bytes exclude cache-owned banks, prepared/device copies, staging, allocator
overhead and the ordinary conversation cache. They are not physical GPU residency.
Record mode sums all record/layer K/V tensors; bank mode sums all bank layers.
The auditor validates the schema, measurement scopes and peak/current consistency.

`native_activation_ns` and `native_attention_gpu_ns` remain future per-request
producer contracts and are unknown when absent. Separate GPU consumption
measurements and serving-plugin host aggregates are now available (below); the
auditor never invents those missing per-request measurements from aggregate data.

An event stage gets a request total only if **every** recall event supplies it.
The report includes observed/total event counts. An unchanged bank in old evidence
may lack an encoding measurement; that is missing coverage, not proof of zero work.
New unchanged-bank events measure equality/cache bookkeeping. Empty or rejected
source reads explicitly record zero encoding with `encoding_outcome=not_started`.
Later admission/encoding failures retain a failed recall event with total duration;
unavailable substage costs remain absent. Prepared loading has its own existing
timers and is not relabelled neural encoding. No events
means no stage measurement. Success and failed-request distributions are separate.
Nearest-rank p95 includes its sample count and is not a production tail guarantee.

For historical traces, recorded encoding-position peaks remain partial observations.
The report labels their coverage separately from the new post-recall working-set
peaks. Missing position telemetry stays unknown. Timings can nest or overlap: do
not add them or subtract them from request
time to infer attention cost. CPU application timings are not GPU consumption cost.
`bank_unchanged` counts potential scheduling opportunities; skipping those calls can
change future generated states and requires a new full-model evaluation.

The report hashes the exact manifest and source trace bytes, keeps conditions
separate, and identifies repeated tasks. It does not establish causal speedups,
retrieval scaling or quality from unmatched archives or self-scored runtime events.

See the [programme proposal](../../docs/proposals/pending/native-memory-addressing-and-working-set.md).

## Research controls and evaluation tools

See [results and gate decisions](RESULTS.md) for the completed first cycle.

Server options (research runtime; defaults preserve existing cadence):

```sh
# No attention-driven recall; latest-message preload still uses the memory owner.
... serve --native-schedule preload-only
# Periodic addressing; source-call budget includes preload and failed recalls.
... serve --native-schedule bounded-refresh --native-refresh-interval 4 \
  --native-max-reads 8 --max-active-records 6 --max-memory-tokens 2048
```

`decode_recall=false` may reduce work further; a request cannot increase server
limits. A bounded refresh requires a finite call limit. Budget exhaustion skips
further scheduled reads and records exhausted steps; an explicit extra recall
fails visibly. The generation check is independent of the schedule. The active
record limit checks the merged, canonical set before encoding. No fact eviction
or record truncation is introduced. Native position and cache/device-byte budgets
remain separate. `source_reads` means recall attempts, excluding publication,
retention and generation-check protocol calls.

Versioned traces include the schedule and source-read/skip/exhaustion counters.
The auditor validates finite read budgets and keeps absent legacy counters unknown.
With existing diagnostic enablement and a bounded `memory_diagnostics` request,
`routing_trace` exports query-state features. These diagnostics require protected
trace storage and introduce host readback; they are excluded from timed tasks.

`router.py` fits a development-only partition centroid model and evaluates a
family-disjoint holdout. Contracts bind checkpoint/representation/layer/pooling/
position/width. Results contain candidate partitions, not records or eligibility.
Current-view partitions must come from the trusted host. A mismatch or uncertainty
requires the memory owner to decide bounded fallback. A candidate hint can still
be confidently wrong; no fallback reliability is assumed. Fitted weights remain
research artifacts outside the production adapter.

```sh
python3 benchmarks/native_addressing/router.py /private/features.json \
  --budget 1 --output /private/new-routing-report.json \
  --router-output /private/new-research-router.json
# Requires Torch/Triton and this repository's serving package, plus a real GPU.
PYTHONPATH=distribution/vllm python3 benchmarks/native_addressing/attention_cost.py \
  --output /private/new-attention-cost.json
```

`campaign.py` creates a new, exclusive public synthetic experiment directory,
launches its own research server for paired schedules, scores exact answers and
expected record discovery independently, and separately collects address features.
`oracle_campaign.py` tests oracle-selected native banks against native-disabled
controls. `fixture_reader.py` is exclusively a synthetic read fixture; it must
never serve real memory or stand in for an authorization implementation.
`analyze_campaign.py` applies the predeclared primary routing and scheduling gates.

```sh
python3 benchmarks/native_addressing/campaign.py --binary /research/aimee-qwen \
  --model /research/checkpoint --placement /research/placement.json \
  --output /private/new-campaign
python3 benchmarks/native_addressing/analyze_campaign.py /private/new-campaign \
  --output /private/new-campaign/new-decision.json
```

Production serving configuration accepts `native_stage_telemetry: true` (boolean,
default false). Existing publisher-only `metrics` returns frontend selection-RPC
counters and per-worker activation/cache counters, separated by success/failure.
These are bounded process-lifetime count/total/max host-wall aggregates, not
per-request percentiles or completed GPU kernel times. RPC validation/admission,
preparation on the selection service, and nested activation costs must not be
summed or inferred from these aggregates. Missing stages remain unmeasured.

## Owner-approved candidate bundles

The published-reader protocol now accepts `native_recall` with an `address`:

```json
{"op":"native_recall","query":"Which access code is downstream of Neris?","limit":6,"authority":"public-research","address":{"schema":1,"view":"<pinned immutable view>","representation":"text-query-v1","step":0,"partitions":[]}}
```

Supported representations are `text-query-v1` and `attention-token-spans-v1`.
These are lexical addresses, not hidden-state embeddings. `limit` bounds the
complete candidate/record set (1–32); `partitions` supplies at most 32 optional
hints. Hints narrow cue matches and confer no eligibility. Wrong publication or
invalid representation is terminal. A cue miss performs one legacy local fallback;
remote fallback retains its independent authority boundary. Initializing routing
indexes and fallback search can scale with the archive.

The trusted publisher supplies `CandidateRoute` entries with an authority,
partition, explicit cues and exact canonical references. Use signed authorization
metadata or `Store.CompileReleasedRoutes` after the existing authoritative release
decision. Raw aliases, graph edges and metadata are never automatically admitted.
Routes are tip-publication data and must be explicitly republished after updates.
Ambiguous cues, unavailable revisions and complete-bundle overflow return no partial
payload. Canonical source records are resolved at read time with temporal checks.

The research adapter enables the envelope with `--native-candidate-routing`.
Existing preparation reads also use bundles when explicitly published. Legacy
images have no route metadata and preserve their previous retrieval path. The
learned prototype remains offline and is not enabled by this flag.

```sh
go build -o /private/published-fixture benchmarks/native_addressing/published_fixture.go
/private/published-fixture --root /private/new-archive --distractors 1000000
# Also vary the size of the cue catalog, independently of returned record count.
/private/published-fixture --root /private/new-catalog --distractors 100000 --route-distractors
python3 benchmarks/native_addressing/published_campaign.py \
  --binary /research/aimee-qwen --model /research/checkpoint \
  --placement /research/placement.json --reader /research/aimee-memory-image \
  --archive /private/new-archive/published --output /private/new-model-campaign
```

`serving_probe.py` tests the current serving package and a library built with
`--no-default-features --features vllm-portable`, using explicitly synthetic,
previously prepared banks. It tests BF16/Q8 weights, conversation growth, text
controls and actual per-worker telemetry. Its scope excludes fresh authorization
and encoding; it does not select bundles or certify learned routing.

## Complete hybrid native prefix

For a hybrid model, attention K/V alone does not represent the entire memory
prefix. The frozen encoder must also retain convolution and FP32 recurrent
states. `serve --enable-hybrid-native` selects the complete profile by default;
legacy serving remains attention-only unless this explicit host setting is used.
The profile requires a joint bank before the conversation, with no diagnostic
position shift or compact attention-only snapshot. Independently encoded records
cannot be composed by summing their recurrent states.

`--max-recurrent-mib` defaults to 256 and bounds immutable recurrent/conv state
before encoding or prepared loading. Attention positions and active canonical
records have their existing separate bounds. Request-local copies keep decode
updates from changing reusable prefixes. Changing the selected bank triggers a
replay of observed conversation tokens against the new complete prefix; replay
performs no extra source reads and checks the publication before and after.
Replay count and wall time are reported separately from routing and encoding.

`prepare-memory --enable-hybrid-native` publishes lossless recurrent sidecars
alongside attention entries. Complete-profile keys and model identities are
separate from attention-only artifacts. Each sidecar records exact layer shapes,
dtypes, byte extents and a SHA-256 checksum. Serving misses fail without encoding;
corruption, incomplete state, placement mismatch and over-budget state fail
closed. Recurrent load wall time includes checksum validation and transfer and
is reported separately from attention payload read time. Memory text contributes
zero conversation prompt tokens, while native prefix state and preparation still
have real resource costs.

The reproducible suite is `hybrid_validation.py`. `hybrid_holdout.json` retains the initial implicit-alias holdout.
`hybrid_grounded_holdout.json` freezes new facts with explicit canonical alias
identities before evaluation. Routing cues alone never establish factual identity. It exercises the actual published
reader under three schedules, online and strict prepared serving, and up to 48
prior conversation turns. GPU capacity waits never stop another workload.

Long remote model runs should use an isolated transient test service with stdout
and stderr retained in the experiment directory. Attached-shell interruptions
are startup/runtime failures, never missing samples counted as successes. Reuse
of an already completed development matrix verifies its exact binary digest and
keeps the original traces; it does not rerun or relabel held-out outcomes.


## Matching BF16 complete-hybrid serving gate

`native_context_suite.json` supplies 48 frozen tasks: original questions, the
retained implicit-alias holdout and a fresh implicit-alias set. The serving gate
uses their task facts/expected identities, with its own declared matrix: native
at 0/16/48 prior turns, paired text controls at zero turns, mixed request ownership,
eight native/text development probes of previously observed long-context failures,
forced native preemption, instruction mismatch, withdrawal, checkpoint-revision
mismatch, empty publication and republishing. This is distinct from the older
INT8 research suite's three-schedule online/prepared matrix.

The collector calls the real published reader before preparation. Each task must
select exactly its frozen canonical identities; an empty selection has no bank.
Preparation and export are offline. The serving gate requires a finite cgroup
host-memory limit and checks the longest input before checkpoint loading.
Its pressure configuration uses the stock `num_gpu_blocks_override` option;
require an observed preemption counter and extra recurrent initialization events.

After the run, independently audit immutable reports:

```sh
python3 benchmarks/native_addressing/audit_hybrid_serving.py \
  --report /private/retained-quality/report.json \
  --integration-report /private/current-live/report.json \
  --suite benchmarks/native_addressing/native_context_suite.json \
  --selection /private/full-native-selections.json \
  --output /private/new-serving-audit.json
python3 benchmarks/native_addressing/checkpoint_storage_validation.py \
  --root /private/prepared-bf16 --output /private/new-storage-audit.json
```

The audit recomputes exact answers against frozen tasks, rejects missing or
repeated matrix rows, checks canonical selections and publication mapping, and
requires the live control and actual recomputation probes. With `--integration-report`,
it retains the quality producer's failed preemption-coverage status and checks a
separate current integration gate. Forty-token pressure continuations are unscored
mechanical tests; the frozen matrix and live QA observations remain distinct. It does not certify
production authorization, arbitrary aliases or the separate INT8 precision profile.

The serving-only consumption instructions are frozen separately in
`hybrid_serving_profile.py`. They explicitly permit resolving named entities
across different descriptive nouns while prohibiting invented identities or
connections. Preparation keys and admission bind the complete instruction hash.
The original generic-instruction BF16 run remains a failed diagnostic; changing
instructions creates a separately evaluated profile, without changing source
facts, questions, answers or historical research prompts.

The completed RTX 5080 run and its exact configuration are documented in the
[final validation report](../../docs/validation/native-memory-completion-20261004.md).


## Matching-contract INT8 research gate

`int8_consumption_validation.py` runs 48 frozen tasks at 0/16/48 prior turns
through online native, paired text and strict-prepared native conditions. Incorrect
answers remain scored failures while the remaining matrix continues. Run on an
idle RTX 5080 under a transient service with finite `MemoryMax` and no swap;
all matrices, source identities and request traces are retained. Offline preparation
requires room for eighteen complete recurrent payloads.

```sh
python3 benchmarks/native_addressing/int8_consumption_validation.py \
  --output /private/new-int8-run --binary /private/aimee-qwen \
  --model /private/checkpoint --placement /private/cuda-placement.json \
  --reader /private/published-reader --archive /private/published \
  --tasks benchmarks/native_addressing/native_context_suite.json
python3 benchmarks/native_addressing/audit_int8_consumption.py \
  --root /private/completed-int8-run \
  --suite benchmarks/native_addressing/native_context_suite.json \
  --output /private/new-int8-audit.json
```

`--resume /private/incomplete-int8-run` requires matching binary, reader, model,
questions and instruction identities. It preserves every retained trace and checks
four replay observations before continuing under a new matrix-storage placement.
Both replay tasks must already be present in the retained run at those lengths
for the four-check audited resume contract. Both placement identities are reported.
The audit verifies coverage, trace hashes,
actual native facts, text-control prompts, paired answers and strict zero encoding.
See the [completed INT8 report](../../docs/validation/native-memory-int8-20261004.md)
for the capacity failure and the 432/432 matching-contract result.

## Dedicated model-plugin release

The [dedicated model-plugin validation](../../docs/validation/native-memory-serving-and-model-plugins-20261004.md) records three isolated Rust-adapter plugins, actual quantized
Gemma 12B/26B execution and complete-prefix Qwen FP8 serving. It preserves
the earlier INT8, BF16 and failed-attempt evidence as separate profiles.
