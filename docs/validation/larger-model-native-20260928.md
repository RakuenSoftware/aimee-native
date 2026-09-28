# Larger-model native validation — 2026-09-28

Neither larger model is release-ready. Gemma 26B Q8 now passes baseline 4/4
and the first native comparison 5/5 after selecting the supported Triton GGUF
matrix backend. Qwen's initial native result was 3/5; a separate negative-position comparison
now passes 5/5, matching text memory. The 12B evidence remains
separate and unchanged.

## Signed delivery and regression follow-up

The first larger signed installation failed during Gemma's GGUF download.
The release server recorded 10,692,279,989 bytes sent out of 29,135,275,488;
the launcher reported only a response-body error. No active release was
committed, and the coordinator restored the original canary account binding.
The transport cause is not established. The next launcher includes the artifact,
received byte count, and underlying read error in this failure diagnostic.
An interrupted-stream test verifies that the existing active release and its
files survive; all 18 unit tests and the signed lifecycle fixture pass.

The `signed-lifecycle-r3` retry uses a new evidence directory and fresh client
roots. The failed `signed-lifecycle-r2` record is retained. Both candidate
sequences remain lab-only; the production release channel is unchanged.
The unused 12B resident compiler was paused to free approximately 49 GB of RAM
during larger-model work. Its documented restoration command is
`systemctl start aimee-native-compiler.service`; larger compilers are separate.

Six selected source-backed coding cases have passed a tokenizer-only preflight
for both larger models. The complete issues and complete accepted-source memories
fit the 4,096-token configuration with 1,536 output tokens and a 280-token reserve.
The largest matched text prompt is 1,406 tokens on Gemma and 1,213 on Qwen;
the largest prepared memory is 432 and 386 tokens respectively. No facts or
initial issues were shortened to pass this check. These are selected prior
success/regression cases, not held-out sampling or new coding outcomes.

Only `preflight-r3.json` is valid preflight evidence. The first attempt incorrectly
counted a tokenizer return object's fields rather than its tokens. The second
stopped on a check that did not account for chat-template whitespace trimming.
Both attempts are preserved. The corrected check renders the complete prompt,
verifies the complete issue is present, and explicitly tokenizes the rendered
string. The runner now uses the actual configured context budget; nine protocol
tests pass, including preserving the initial issue during history trimming.
[Preflight, runner tests, and failed installation evidence](artifacts/larger-release-followup-20260928/).

Stopping the idle 12B compiler exposed a deployment lifecycle defect: both
larger services had placed their sockets inside the 12B service's systemd-owned
runtime directory. Its cleanup unlinked those sockets while their processes
remained alive. The first coding-memory preparation therefore failed before
encoding any procedure. Each larger service now owns a distinct runtime
directory, and its worker configuration references that private socket. Both
services restarted successfully while the 12B service remained stopped; the
new preparation run is producing complete-token-count-checked memories.
The original failure and before/after unit configurations are
[preserved](artifacts/larger-compiler-socket-fix-20260928/).

The [frozen coding protocol](../protocols/larger-source-regression-20260928.md)
plans 24 attempts per larger model: six selected cases with fresh no-memory
and matched-text controls, then two native reuses of the accepted procedure.
The host coordinator waits for the signed lifecycle and complete preparation
before starting Gemma and then Qwen on the paired GPUs. Queueing is not a pass;
no new coding outcomes are claimed here.

Independent token-level audits now pass all six procedures for each model: every
stored native-record token ID equals a fresh tokenizer encoding of the complete
frozen source procedure, not just the same token count. The audit checks the
source, request and index hashes as well. This verifies preparation fidelity;
it does not establish task success or GPU consumption. The first audit invocation
stopped during import because a lab coordinator named `queue.py` shadowed the
Python standard library. That file was renamed, the audit rerun with Python's
safe-path option, and the original setup failure retained.
[Token audit evidence](artifacts/larger-token-audit-20260928/).

Gemma's full signed installation subsequently completed in `signed-lifecycle-r3`.
The first startup probe failed because the test's copied enrollment configuration
pointed at a memory directory the fixture had not created; ordinary `connect`
creates it. The fixture now creates that private directory and resumes the
already verified sequence-one installation without downloading the weights again.
The next cold-client probe (`r4`) exposed a second lab-build omission: its HTTPS
release CA was configured, but the embedded OCI registry trust variable was not.
The checked-in build recipe now sets both `AIMEE_LAB_CA_FILE` and
`AIMEE_RELEASE_CA_PEM`; all 18 unit tests and the lifecycle fixture pass.
The `r5` runtime has successfully pulled the exact image with TLS verification
enabled. Installed GPU answers and the complete lifecycle remain pending.
[Completed preparation, signed installation, setup failures and corrected build](artifacts/larger-installed-followup-20260928/).

The `r5` initial installed Gemma probe has now passed: both ordinary client
requests correctly recalled all three live canary facts. Each used 27 prompt
tokens and generated 40 tokens. The first took 90.9 seconds, including cold
Triton compilation; the repeat took 7.70 seconds. These are complete request
durations, not native-memory application latency. The tested container was
unprivileged with a 36 GiB memory limit and the exact signed image digest.
[Installed answers and complete startup log](artifacts/larger-first-installed-20260928/signed-lifecycle-r5/gemma26/).

Before any coding outcomes, the queue was rescheduled to start each model's
coding comparison after its initial installed probe, rather than waiting for
both full signed lifecycles. The host and CT110 verified exclusive ownership of
the same GPU-lock file: a competing nonblocking acquisition failed while held
and succeeded after release. All subsequent lifecycle probes and coding runs
share that lock. Gemma's coding server is starting while its sequence-two
package downloads. Remaining update/rollback/restore gates still apply.
[Scheduling and lock evidence](artifacts/larger-first-installed-20260928/assembly/).

All four lab-only signed packages are now built: sequences one and two for
Gemma and Qwen, with their runtime descriptors and model-specific tokenizer
sidecars. Qwen's first CPU-only installation has been started early into the
same dedicated client root, while Gemma owns the GPUs. The installer update
lock serializes any later overlapping invocation; its lifecycle coordinator
will still perform the required installed-answer, update and rollback probes.
[Immutable manifests and runtime descriptors](artifacts/larger-signed-packages-20260928/).

## Gemma 26B quantized backend repair and native comparison

Paired full-checkpoint activation traces agreed closely through layer 25
(cosine similarity 0.9994). The original Q8 runtime first produced NaNs at
layer 26 on both GPU workers; the original FP32 reference stayed finite.
Stored layer-26 quantization scales and nonquantized tensors were finite.
This localizes the failure but does not establish its internal arithmetic cause.
[Derived trace statistics](artifacts/gemma26-layer-trace-20260928/comparison.json).

Keeping the image and Q8 weights unchanged, selecting the installed plugin's
supported Triton matrix backend (`VLLM_GGUF_USE_CUDA=0`) repaired baseline
inference: **4/4**, versus the original Q8 backend's **0/4**. This setting selects
GGUF matrix/MoE kernels, independently of the attention backend. No upstream
fork or runtime monkeypatch was introduced. First-request compilation took
about 86 seconds; subsequent baseline requests took about 0.9–1.0 seconds.
[Baseline responses](artifacts/gemma26-baseline-20260928-triton-r1/responses.json).

The subsequent three-record comparison used the complete same memory and
five questions as the initial Qwen comparison below:

| Question | Control | Native | Text |
|---|---|---|---|
| Synthetic vault code | Miss | Pass | Pass |
| Project name | Miss | Pass | Pass |
| Drink | Miss | Pass | Pass |
| All three facts together | Miss | Pass | Pass |
| Unrelated arithmetic | Pass | Pass | Pass |
| Total | 1/5 | 5/5 | 5/5 |

Native prompt-token counts matched control for every question. Text added
40 prompt tokens per question; native consumed 41 separately prepared memory
positions. Those positions still require attention computation and storage.
The run includes first-use compilation and different output lengths, so its
end-to-end timings are not a controlled latency comparison. This is a small
synthetic smoke test, not authorization, learning or release certification.
[All responses, counts and cache statistics](artifacts/gemma26-native-smoke-20260928/result.json).

The signed runtime descriptor now supports the validated matrix backend and
an optional signed GGUF projector artifact. The launcher resolves these into
serving configuration, and the CLI forwards them through existing plugin
options. Existing descriptors retain their default backend. This configuration
is release-owned; users need not tune it. Launcher tests pass (16 unit tests
and one signed lifecycle integration test); two CLI tests pass. The lifecycle
fixture verifies backend/projector propagation and cleanup on rollback. These
are configuration tests, not a larger-model signed GPU lifecycle pass.

## Qwen 27B position-policy comparison

The independent follow-up changed only preparation's memory-position policy
from nonnegative positions to negative positions. Model weights, all three
source records, questions, scoring and runtime remained unchanged. The private
compiler exposes an explicit policy; the previous default remains unchanged
until the release profile is bound to its tested policy. Publication identity
includes the policy so incompatible prepared artifacts are not reused.

The follow-up passed **5/5 native, 5/5 text, 1/5 control**, resolving both the
standalone project-name miss and combined-answer miss. Native prompt counts
again match control; text adds 43 tokens for each question. Reduced real-model
architecture tests also check both Qwen position policies against independently
evaluated reference caches. This result identifies a working preparation policy
for the synthetic fixture; it does not establish broader accuracy or learning.
The initial 3/5 result below remains part of the record.
[Follow-up responses and device statistics](artifacts/qwen27-position-ablation-20260928/qwen27-result.json).

A compiled client wheel and combined private GPU binary bank are assembled in
image `56e44a78b4ddbb228d5728311a709ee8118acc51f685b9f0e428a809b5ad2935`
(seven kernel profiles). The 64-request Gemma packaged HTTP validation passed. That next check uses the actual serving CLI,
conversation growth, longer prompts, streaming and concurrent requests, with no
private Python or kernel source mounted into serving.
The initial image build failed on this Podman version's `--pull never` argument
syntax; `--pull=never` fixed the invocation. That failed build and the corrected
build are preserved separately. No model or memory result was changed.
[Completed image build](artifacts/larger-binary-client-20260928-r2/build.json).
The installed client package contains compiled modules and no private Python,
encoder or kernel source; the native bank contains metadata and GPU binaries.
This audit covers that package and bank, not whole-image confidentiality.
[Installed-package audit](artifacts/larger-binary-client-20260928-r2/source-audit.json).

## Gemma 26B packaged HTTP validation

The compiled image completed all 64 requests: **46/46 native**, **14/14 matched
text**, and **0/4 no-memory controls** recovered all three synthetic facts.
There were no private-source mounts or runtime modifications. This validates
the actual CLI configuration path and compiled attention dispatch on both XTXs.

Coverage included zero, four, 16 and 48 prior conversation turns; two longer
prompt sizes; eight streamed native and eight streamed text responses; and
32 native requests submitted with four concurrent client workers. Every
memory-backed answer contained all three values. Native and text prompts use
the same query/background, with records added only to the text condition.
These are repeated operational checks of one synthetic working set, not 60
independent knowledge tasks or a population accuracy estimate. This run does
not test live authority, record changes, cache eviction or learned task gains.

Qwen 27B also completed the matching packaged check: **46/46 native**,
**14/14 text**, and **0/4 no-memory controls** recovered all three facts.
The same limits apply: these are operational checks of a fixed synthetic working
set, not independent knowledge or learning tasks.
[Qwen packaged results](artifacts/qwen27-binary-validation-20260928/report.json).
[Gemma responses, token counts and timings](artifacts/gemma26-binary-validation-20260928-r2/report.json).

## Resident-service integration

The resident compiler now forwards the operator's `position_policy` to the
bounded backend. If configured, position and encoding revisions must match
request identity before model evaluation. This closes a gap where the standalone
Qwen experiment could choose the successful policy but service construction
would silently retain the backend default. The 12B construction path is unchanged.
Four resident transport/configuration tests and five remote transport tests pass.

A separate full-checkpoint service test sends a deliberately mismatched policy,
then all three valid source records through the resident Unix socket, Rust
publisher and bounded artifact transport. Gemma 26B passed: mismatch rejected,
valid preparation completed, 41 positions evaluated and a 9,240,740-byte payload
returned. Qwen 27B also passed, returning a 2,494,616-byte payload after rejecting
the mismatched policy. Both daemons logged the negative-position policy.
[Full-checkpoint service results](artifacts/larger-resident-validation-20260928-r2/results.json).
This does not exercise live Aimee
authorization. Preparation overlapped GPU startup work and is not an isolated
latency benchmark. The first operator attempt used an incorrect fixture-directory
name and failed before preparation; the corrected run has a separate evidence root.

## Live canary preparation and reuse

Both larger profiles now complete preparation from the existing live Aimee
canary through the scoped gateway, pinned SSH transport, private resident
compiler and Rust publisher. Each selected all three approved records and
reused the same key and ordered record references on a subsequent request.
Gemma's first preparation took about 47 seconds and reuse about 43 ms; Qwen's
first preparation took about 65 seconds and reuse about 51 ms. These are
end-to-end authorization/preparation operations, not native attention application
or isolated latency measurements.
[Live preparation report](artifacts/larger-live-preparation-20260928/report.json).

The root-owned private worker now supports explicit model-to-profile routes,
while preserving the existing 12B default. Requests name an enrolled identity;
they cannot supply configuration paths, sockets or commands. Seven transport
tests and four resident tests pass, including full subprocess artifact transport
through a selected profile. The two larger resident services are staged
separately; account bootstrap remains on its existing model until enrollment
and signed runtime validation are complete. Both profiles passed canary expiry, withdrawal, disconnection and recovery:
cached preparations were denied while authority was unavailable and reused
after restoration. These exercise preparation authorization, not the
client-to-GPU route. The first lifecycle operator script failed to parse before
changing policy; the corrected operator and both logs are retained.
[Lifecycle outcomes](artifacts/larger-live-preparation-20260928/lifecycle-status.json).

## Release assembly follow-through

The Python release assembler now accepts the same optional matrix-backend and
projector fields as the Rust launcher. Previously it rejected the larger-model
descriptor before packaging. Tests sign and verify the resulting artifact set,
check projector inclusion, and reject absent projectors, invalid backends,
escaping paths and unknown fields. Existing exact-artifact gate binding remains
unchanged; these tests do not authorize a production release.

Remaining model-specific work includes completing the packaged GPU runs,
live-authority selection and revision/withdrawal checks, procedural reuse and
retained-success checks, dependency/model notice assembly, and signed
installation/update/rollback/restore. The existing live account binding selects
one preparation profile. Installing another model must not silently reuse its
12B preparation binding; the tested larger profile must be explicitly enrolled
and matched at bootstrap. The normal published channel remains unchanged.

## Signed larger-model candidates (in progress)

The validated compiled image is now present in the private registry at digest
`sha256:b71da5a610b2871b2bb96ed05cf4d9de71036a78baa4d349aa9d87e1f23f5a9d`.
A lab-edition installer was built from the larger-model launcher source, with
17 unit tests and the signed lifecycle fixture passing. Its first build omitted
the required lab CA input; the corrected builds and failure log are retained.
[Build provenance](artifacts/larger-candidate-assembly-20260928/launcher-build.json).

Qwen's `models/merges.txt` tokenizer sidecar is now explicitly admitted by both
the package assembler and launcher. Arbitrary model-directory text files remain
outside the artifact allowlist. The two package tests pass, including signed
artifact and descriptor checks.

Each model is being assembled as two signed **lab-only** packages, differing
in the supported serving concurrency setting. The queued test covers fresh
installation, update, explicit rollback and restoration, with two ordinary
Aimee-backed queries at each step. It temporarily selects the larger profile
for the dedicated canary account and restores the original binding on exit.
No production gate report or ordinary release-channel promotion is implied.

The existing thin pool was 92.29% full. Dedicated staging/client directories
were therefore mounted into CT101 and CT110 from the host's separate root
storage pool, without restarting either container or moving model/memory test
data. Only verified immutable weight copies within the staged test packages
are deduplicated; original checkpoint files are not linked or modified.
[Storage scope](artifacts/larger-candidate-assembly-20260928/storage.json).

## Full-checkpoint preparation

The corrected private FP32 preparation path loads learned persistent buffers
as well as parameters. It uses the existing model implementation and supported
Accelerate hooks, with no upstream model changes. Qwen retains the previous
independent raw-memory-text framing; Gemma retains its system framing and
negative memory positions. All three selected synthetic source records are
encoded together, with no record filtering or truncation.

| Checkpoint | Selected records | Memory positions | Exported attention layers | FP32 forward | Export |
|---|---:|---:|---:|---:|---:|
| Gemma 26B | 3 | 41 | 30 | 46.2 s | 248 ms |
| Qwen 27B | 3 | 38 | 16 | 66.0 s | 4 ms |

Every exported layer contains all positions; banks are finite. Qwen's 48
recurrent layers are not represented as attention banks. All model parameters
were released by the offload hooks after each pass. These are offline,
first-attempt preparation timings, not memory-application or serving latency.
[Preparation evidence](artifacts/bounded-buffer-fix-20260928/).

## Qwen packaged model, private native-backend build

The test uses the same Q8 artifacts that passed four baseline smoke checks,
with the private external attention backend and Rust publication/consumption
path. JIT kernel source was mounted only into the private build container to
produce the larger model's GPU profiles. It is not a binary-only release test.
There are no upstream forks or monkeypatches.

The complete three-record working set is present for every native question.
Control and native receive the same prompt; the text condition receives those
same records as a system message. Each question runs once per condition, in
control/native/text order, with temperature zero. Matching requires all expected
strings in the answer. This small exploratory check does not estimate general
accuracy, learning gains, or latency advantages.

| Question | Control | Native | Text |
|---|---|---|---|
| Synthetic vault code | Miss | Pass | Pass |
| Project name | Miss | Miss | Pass |
| Drink | Miss | Pass | Pass |
| All three facts together | Miss | Miss | Pass |
| Unrelated arithmetic | Pass | Pass | Pass |
| Total | 1/5 | 3/5 | 5/5 |

Native returned the correct code and drink. For the standalone project question,
it returned “Release Verification Project” instead of the stored name. For the
combined question it returned the correct project and drink but refused to give
the synthetic vault code. That refusal remains a failed answer under the frozen
criterion; partial recovery is not counted as a pass. The original results must
not be replaced by later revised prompts or memory protocols.

Native prompt counts exactly match control: 24–27 tokens. Text memory adds
43 prompt tokens to every question. Native has 38 separate prepared positions;
those still incur attention/storage work even though they are not prompt tokens.
End-to-end times include different output lengths and first-use compilation,
so this run does not support a native latency advantage. It does not test live
Aimee authorization, automatic acquisition, signed installation, or task learning.
[All 15 responses and counts](artifacts/larger-native-smoke-20260928/qwen27-result.json).

## Gemma Q8 investigation

The original BF16 checkpoint passes all four baseline questions with CPU weight
offload, while the Q8 package produces padding tokens. The read-only worker
extension confirmed 132 checked scalar/BF16 parameter samples against the source
checkpoint, including all 30 complete learned layer scalars on both workers.
Raw parameter samples stay on the private lab machine; the repository records
comparison outcomes rather than model weights.

An independent CPU check sampled 62 Q8 payload slices across layers 0, 5 and 29,
including both ends of dense projections and experts 0/127. All have relative
L2 error below 0.87% against the original checkpoint. Missing V projections in
full-attention layers are also absent from the source; those layers share K/V
projection weights by architecture. They are not silently dropped artifacts.

A separate real-GPU test compares the packaged expert operator against an
independently dequantized FP32 calculation using actual layer-zero weights and
rank-zero TP=2 geometry. All six BF16/FP16 × 1/7/65-token cases are finite, with
relative L2 errors of approximately 1.05–1.16%. This sampled operation does not
explain the full-model failure or certify all quantized computation. Exact
loaded-byte comparisons also passed for all 38 checked matrices: the complete
embedding shard and six fused/TP-sharded matrices in each of layers 0/5/29 on
both workers. This includes the K/V-shared projection layout. All 72 sampled dense/vocabulary
operation checks also remain finite, with maximum relative L2 error below
0.64% against independently dequantized reference weights (BF16/FP16, 1/27
tokens, two input scales). This narrows the fault further but does not establish
correct full-model execution. The six embedding-lookup cases also remain finite and within 0.16% relative
L2 error. A paired original-FP32 CPU / Q8 GPU first-prefill layer trace is now
running to locate the divergence within the complete model.
[Packed-byte parity](artifacts/gemma26-weight-probe-20260928-r3/packed-parity.json),
[dense/vocabulary numerical evidence](artifacts/gemma26-dense-numerics-20260928/result.json),
[embedding numerical evidence](artifacts/gemma26-embedding-numerics-20260928/result.json).

[Loaded scalar/sample comparison](artifacts/gemma26-weight-probe-20260928-r2/source-comparison.json),
[Q8 payload comparison](artifacts/gemma26-weight-probe-20260928-r2/q8-source-r2.json),
and [expert numerical comparison](artifacts/gemma26-moe-numerics-20260928-r3/result.json).

The archive retains diagnostic setup failures: an inspector initially tried to
read lazy quantization metadata as a materialized tensor; the first publisher
invocation selected the planner library instead of the publisher library; a
host helper named `queue.py` shadowed the standard library in the first isolated
expert container; and a single-device container could not initialize HIP. The
successful numerical run used the same paired device exposure as the model
runs. These failures are not scored as model answers.

## Remaining release gates

Gemma's baseline repair and Qwen's position-policy smoke comparison now pass,
as do both packaged conversation/stream/concurrency checks and live preparation
authorization checks described above. Complete signed install/update/rollback
and installed GPU serving independently for each larger model, then execute the
fresh source-backed task comparisons and retained-success/regression checks.
Model-specific latency measurements remain limited to their reported scopes.
Existing 12B passes cannot fill larger-model gates.

## Qwen signed preinstallation and model selection follow-up

The CPU-only Qwen 27B installation completed in the shared validation client
root, with current manifest
`c5180309b74100e2e54d00db47b5a69bc02f7b61ada01c5f59f2016c1ad70e75`
and high-water sequence 1. This is a lab package installation, not a passed
installed-runtime or coding gate. Its terminal installer evidence is preserved
in [larger-qwen-preinstall-20260928](artifacts/larger-qwen-preinstall-20260928/).
The lifecycle coordinator will reuse this installation after the Gemma checks;
GPU work remains serialized by the shared lock.

The account no longer needs to be manually rebound for each installed model in
the new control-plane implementation. Approved per-model routing is implemented
and tested, including real TLS bootstrap and artifact delivery. This change is
staged separately from the pinned running campaigns; deployed switching remains
a release gate. See [model selection validation](model-selection-20260928.md).

## First complete larger-model coding task

Gemma 26B completed `pytest-dev__pytest-5808` in all four frozen conditions:

| Condition | Officially resolved | Agent calls | Agent elapsed seconds |
| --- | --- | ---: | ---: |
| No memory | yes | 7 | 610 |
| Same-record text | yes | 3 | 563 |
| Native reuse 1 | yes | 3 | 221 |
| Native reuse 2 | yes | 3 | 262 |

The control reached its time limit after producing a patch that passed official
validation; it remains a success. Native rounds reused the same complete frozen
accepted procedure, without a new acquisition between rounds. These results
show successful procedure consumption and retention for this selected task, not
a success-rate gain, new reasoning ability, or an isolated latency benchmark.
Shared GPU scheduling, generated output and tool activity affect elapsed times.
The other five tasks and the Qwen coding campaign remain incomplete.

All four trajectories, submitted patches, and official grading records are
preserved in [the completed-task archive](artifacts/larger-gemma26-complete-tasks-20260928/).

## Second complete Gemma task: Flask native-only success

`pallets__flask-4169` is now complete across the four frozen conditions:

| Condition | Officially resolved | Agent calls | Agent elapsed seconds |
| --- | --- | ---: | ---: |
| No memory | no | 10 | 674 |
| Same-record text | no | 7 | 697 |
| Native reuse 1 | no | 7 | 625 |
| Native reuse 2 | yes | 9 | 625 |

All four attempts reached their time limit. The second native attempt produced a
patch that passed official grading and therefore counts as a success, following
the same rule used for the Pytest control. This is a native-only success on one
selected task, with the Pytest control success retained in both native rounds.
Both native attempts consumed the same frozen accepted procedure: no new lesson
was acquired between these two attempts. Do not interpret the change between
rounds as a measured learning effect. The four remaining tasks are incomplete,
and the two completed tasks do not establish a population success rate.

The [completed-task archive](artifacts/larger-gemma26-complete-tasks-20260928/)
now includes both tasks with trajectories, patches and available grading files.

## Third complete Gemma task: Astropy retained in both native rounds

`astropy__astropy-7336` is complete across the frozen conditions:

| Condition | Officially resolved | Agent calls | Agent elapsed seconds |
| --- | --- | ---: | ---: |
| control | no | 7 | 627 |
| text | yes | 4 | 186 |
| native-1 | yes | 4 | 119 |
| native-2 | yes | 4 | 152 |

Both native attempts and text memory pass where control fails. The first three
completed tasks therefore yield control 1/3, text 2/3, native reuse 1 at 2/3, and
native reuse 2 at 3/3, with the control success retained. These are interim
selected-task outcomes; the remaining three tasks and Qwen campaign are still
pending. Each native round reuses its frozen source procedure, with no acquisition
between rounds. Full trajectories and official grades are in the completed-task
archive, preserving the earlier tasks unchanged.
