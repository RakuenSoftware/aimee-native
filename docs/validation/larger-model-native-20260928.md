# Larger-model native validation — 2026-09-28

Neither larger model is release-ready. Gemma 26B Q8 now passes baseline 4/4
and the first native comparison 5/5 after selecting the supported Triton GGUF
matrix backend. Qwen's initial native result was 3/5; a separate negative-position comparison
now passes 5/5, matching text memory. The 12B evidence remains
separate and unchanged.

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

Repair Gemma Q8 baseline behavior and Qwen native quality before expanding the
model-specific comparison, procedural learning, retained-success/regression,
revision/authorization, concurrency/stream/recovery, and latency checks. Then
validate the compiled client artifacts and signed install/update/rollback flow
independently for each larger model. Existing 12B passes cannot fill those gates.
