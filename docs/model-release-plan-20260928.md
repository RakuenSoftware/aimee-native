# Required model releases — 2026-09-28

Release scope now includes Gemma4 12B (current validation candidate), Gemma4
26B, and Qwen3.8 27B. Complete the current regression investigation first;
then build and validate each larger model as a separate deliverable. Keep
private implementation in aimee-qwen and retain the fork-free vLLM approach.

Source-card check on 2026-09-28: the official
[Gemma 4 26B A4B instruction-tuned card](https://huggingface.co/google/gemma-4-26B-A4B-it)
and [Qwen3.8 27B card](https://huggingface.co/Qwen/Qwen3.8-27B) both identify
Apache-2.0. These match the candidate model notices. Qwen's card also explicitly
describes its Qwen3.5 architectural foundation, consistent with the checkpoint's
`qwen3_5` configuration type. Keep product/checkpoint identity distinct from the
implementation class name; this metadata check is not a runtime validation.

For each larger model:

1. Locate and verify the exact checkpoint, architecture/configuration,
   tokenizer, license and quantization artifacts. Record hashes and actual
   byte sizes; do not infer compatibility or VRAM fit from parameter count.
2. Implement the required private preparation/runtime profile using existing
   vLLM extension interfaces. Bind prepared memory to the exact model and
   encoding revision. Validate on both 7900 XTXs without disrupting an active
   experiment. Measure actual memory requirements and choose a supported
   quantization based on accuracy and capacity evidence.
3. Validate native versus no-memory and matched text memory, complete
   multi-record delivery, procedural reuse, retained successes, regressions,
   conversation/long-context behavior, stream/concurrency/recovery, revisions
   and authorization. Include cold/warm/resident latency and token accounting
   with their distinct scopes. Do not transfer 12B results as model-specific
   pass evidence.
4. Package each model with its verified runtime, small user configuration,
   model-specific prepared-memory support, license files, and signed manifest.
   Test normal installation, update, rollback and restored operation against
   live Aimee. Keep private implementation out of shipped source artifacts.
5. Push model-specific code and evidence; report each release decision and
   any unmet gates independently. All three models must be accounted for
   before declaring the expanded release objective complete.

## Current release status

| Candidate | Signed runtime lifecycle | Coding evidence | Release decision |
|---|---|---|---|
| Gemma4 12B | Fresh, update, rollback and restore passed; 8/8 native canary queries | Original studies and selected source-repair/retention checks complete | Supports the documented scoped private preview; broader learning improvement remains unproven |
| Gemma4 26B | All four phases passed; 8/8 native canary queries; updated model-aware sequence-2 probe also passed 2/2 | All six cases complete: control 2/6, text 4/6, both native reuse rounds 4/6; both control successes retained, Requests lost between native rounds | Not yet ready |
| Qwen3.8 27B | Fresh install, update, rollback and restore passed: 8/8 canary queries; final three phases use model-aware authority | All six cases complete: control 5/6, text 4/6, both native reuse rounds 6/6; all control successes retained | Not yet ready |

Both larger models have separately passed native/text smoke comparisons,
conversation/concurrency checks and the recorded private preparation lifecycle.
Those checks do not substitute for the outstanding coding and signed-client
gates. The larger coding protocol reuses frozen accepted source procedures;
it does not measure newly acquired learning between its two native rounds.

The three-model account binding, query-forwarding frontend and delivery service
are deployed and healthy. The same enrolled account passed 10/10 live bootstrap
authorization checks and 6/6 fresh/repeated artifact fetches across all three
models. Installed GPU consumption through the model-aware launcher passed all eight
larger-model queries. Normal-feature 12B compiler restoration and interrupted-
request recovery remain queued.
No larger candidate has been promoted to the ordinary release channel.

See the [larger-model report](validation/larger-model-native-20260928.md) and
[model-selection deployment record](validation/model-selection-20260928.md) for
exact artifacts and outstanding checks. The chronological sections below
preserve earlier findings and failures.



## Existing checkpoint inventory

A header-only inventory found both larger checkpoints already present in CT101.
The Gemma checkpoint reports `Gemma4ForConditionalGeneration`, 30 layers,
128 experts, and approximately 25.806 billion stored tensor elements. Its two
BF16 shards total 51,612,009,916 bytes. Its local configuration download metadata
records revision `4d7ae4984b7db7de8f8457170b3f1a419ee76d52`.

The Qwen checkpoint reports `Qwen3_5ForConditionalGeneration` (the architecture
identifier recorded in its configuration), 64 layers comprising 48 linear
and 16 full-attention layers, and approximately 27.781 billion stored tensor
elements. Its eighteen BF16 shards total 55,563,006,776 bytes. Configuration
metadata records revision `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`, matching the
previous Qwen experiment's pinned checkpoint. Architecture class identifiers
must not be silently rewritten to match marketing names.

These are stored tensor element counts, not active MoE parameter counts.
Expanding all stored weights to FP32 alone would require approximately 103.2 GB
and 111.1 GB respectively, before working memory. The existing Gemma 12B CPU
preparation process cannot simply load these alongside itself. Establish a
bounded-memory preparation profile after releasing the current compiler.
The 26B checkpoint directory has no local LICENSE file; retrieve and verify
its model terms before packaging. Weight-payload hashes and serving fit remain
unverified. [Inventory evidence](validation/artifacts/larger-model-inventory-20260928/inventory.json).


## Loader dispatch implemented

The private GGUF loader now delegates `gemma4` and `qwen3_5` configurations to
the pinned dependency's existing `Gemma4GGUFAdapter` and `Qwen35GGUFAdapter`.
This preserves upstream MoE tensor transformations and hybrid-attention weight
layouts. Gemma4Unified keeps its existing separate mapping path; unknown
architectures are rejected. No upstream registration hook or source is patched.

A CPU-only probe inside the exact current runtime image passed adapter
availability and dispatch checks for both added profiles. It loaded the new
private loader from a temporary file, without replacing installed package code
or loading model weights. This proves dispatch wiring only. Quantized artifacts,
actual model loads, attention-memory compatibility and release certification
remain pending. The running 12B image was not rebuilt or changed.
[Probe evidence](validation/artifacts/larger-model-inventory-20260928/loader-profile-probe.log).


## Bounded-memory Gemma 26B conversion underway

A new two-pass writer plans tensor metadata from the checkpoint headers, then
writes one encoded tensor at a time using the pinned GGUF quantizer. Quantization
uses small source chunks, so it does not retain a full FP32 model or duplicate
the output in a temporary file. The full checkpoint is retained, including
vision weights; no unmapped tensors are silently omitted.

All 1,013 source tensors map through the installed upstream Gemma adapter,
including 60 stacked expert tensors. Dense/expert chunked Q8 payloads and scalar/
router F32 payloads passed a CPU fixture against the pinned quantizer and an
independent GGUFReader readback. This is format/mechanics evidence, not accuracy.

The planned payload is 29,135,212,856 bytes; the largest encoded tensor is
784,334,848 bytes. The full conversion is running in a separate container with
no GPU devices, two CPUs, and a 6 GiB memory limit. Storage reserve was checked
after trimming freed blocks from the verified client-model deduplication.
Pretrained loading, inference/native-memory correctness, preparation profiling
and release packaging remain outstanding.
[Conversion plan and checks](validation/artifacts/gemma26-conversion-20260928/).


## Completed Gemma 26B conversion

The complete 1,013-tensor checkpoint conversion finished in 223.7 seconds in
the CPU-only, two-core, 6 GiB-limited container. The resulting file is
29,135,275,488 bytes, SHA-256
`2b190fd2cd6d7ee93247159dffbd6bcb28aae97e002b52c9cf502536ac1a1f72`.
GGUF readback checked tensor names and shapes. This completes conversion, not
model-loading or native-memory certification. Both larger releases still need
their own real-model runtime, preparation, quality and signed lifecycle checks.
[Completed conversion report](validation/artifacts/gemma26-conversion-20260928/conversion.json).


## Separate larger-model runtime built

Image `79d7f03eedc74943f2ffd9c1271141086ea0813bcd3f697c718e09501908cf58`
is a private child of the pinned 12B runtime with only the compiled GGUF loader
replaced. It leaves the current 12B runtime and signed candidate unchanged.
The installed binary successfully built a loading plan for all 1,013 tensors
in the real 26B GGUF, using the upstream Gemma adapter. Private source exclusion
passed for the client package. No upstream source or registration was patched.

The first CPU-only probe lacked an explicit CPU platform and stopped during
ROCm initialization before reaching the loader. Its log is preserved. Running
with `VLLM_TARGET_DEVICE=cpu` passed the actual loading-plan check without GPU
access. This does not test expert execution, inference quality or native-memory
consumption. Those remain release gates, along with Qwen artifact preparation.
[Build and probe evidence](validation/artifacts/larger-runtime-20260928/).


## Qwen conversion started

No reusable Qwen GGUF was found at the historical path or in the inspected
model-storage roots. Dry runs using the unmodified converter at revision
`e85e15cf6d810cd1268498c2e5b657bb3ece47bc` passed for both the text backbone
(866 output tensors, approximately 29 GB) and vision projector (334 output
tensors, approximately 1.8 GB). This uses a conversion utility only; serving
remains vLLM without a fork. The separate projector preserves the upstream
loader's expected multimodal layout.

The full CPU-only conversion runs with two CPUs, no network or GPU devices,
and a 20 GiB memory cap. Four byte-identical historical client model copies were
independently hashed and hard-linked, reclaiming approximately 51 GB without
removing release paths or evidence. This is an operator storage action, not
installer behavior. A thin-pool reserve and host-memory check passed before
conversion. Final artifact validation, real inference and native-memory checks
are still pending.
[Conversion plans and storage evidence](validation/artifacts/qwen27-preparation-20260928/).


## Qwen artifacts completed; larger GPU baseline queued

Qwen's text and vision conversions completed. The Q8 backbone is
29,047,084,448 bytes and the F32 vision projector is 1,842,940,064 bytes.
Both output files were fully hashed; identities are in the artifact record.
The first actual Qwen loader-plan check rejected incomplete tensor mapping.
The omitted names are being diagnosed before any Qwen GPU load; conversion
success alone does not close this gate.
[Artifact identities](validation/artifacts/qwen27-preparation-20260928/artifacts.json).

The Gemma 26B real-model baseline is queued behind the signed 12B lifecycle and
CPU conversion. It loads the actual Q8 artifact on both XTXs and runs four
deterministic arithmetic, factual, instruction-following and code-output smoke
checks. This is an initial loading/inference gate, not model accuracy or native
memory certification. Its 36 GiB CPU cap and sequential GPU ownership avoid
colliding with the existing compiler and signed runtime probes.


The Qwen loading-plan discrepancy is resolved: the pinned adapter intentionally
excludes the optional single MTP/speculative draft block from ordinary serving.
All 15 excluded names match that complete block at index 64; all 1,185 main-model
and vision tensors map, with 48 hybrid linear layouts registered. The validation
explicitly requires the 64-layer main configuration and one optional draft layer;
it does not accept arbitrary omissions. All 1,200 tensors remain in the GGUF
files. Speculative draft decoding is not enabled or certified.
[Actual compiled-loader result](validation/artifacts/qwen27-preparation-20260928/loader-plan.json).


## Gemma 26B real-model baseline failed

The quantized 26B model loaded across both XTXs, with the runtime reporting
12.91 GiB of model allocation per worker. All four baseline prompts returned
empty visible answers and exhausted their 128-token budgets (0/4 exact). This
is a real release blocker; successful loading does not establish correct
inference. Raw-token diagnostics are running before any native-memory test.
[Original baseline outcomes](validation/artifacts/gemma26-baseline-20260928/responses.json).

A private preparation-only lazy checkpoint mapping now supports FP32 tensor
expansion through Accelerate's existing offload hooks. It passed exact output
comparison and parameter-release tests, plus reduced real Gemma MoE and Qwen
hybrid architectures at two sequence lengths each. Hidden states and exported
K/V caches exactly matched resident FP32 references using the same BF16
checkpoint values. These are mechanics tests, not full-checkpoint certification;
production compiler integration and actual larger-model preparation remain open.
The serving hot path does not import this mapping.
[Preparation fixture evidence](validation/artifacts/bounded-preparation-20260928/).


## Gemma 26B failure isolation

Raw-token inspection reproduced padding-token loops for the chat prompt and
a repeated ` it` token for plain completion. The empty visible response was
not just a missing final-answer field. The original-checkpoint FP32 CPU probe
completed through supported Transformers/Accelerate hooks and released all
parameters, but its leading logits were saturated at the configured soft cap.
That result does not establish a healthy reference model or isolate conversion
as the cause. The original BF16 checkpoint is now being tested directly in
vLLM, with 8 GiB of CPU offload per worker and no GGUF loader enabled.
Its outcomes remain pending.

[Raw tokens](validation/artifacts/gemma26-baseline-20260928/raw-token-diagnostic.json)
and [original-weight CPU diagnostic](validation/artifacts/bounded-preparation-20260928/gemma26-reference.json).


## Verified provenance and revised BF16 reference budget

The actual configuration, checkpoint index and both complete Gemma weight
shards match independently fetched metadata for Google's pinned revision
`4d7ae4984b7db7de8f8457170b3f1a419ee76d52`. The pinned repository metadata
identifies Apache-2.0 licensing; required distribution notices still need to be
assembled with the larger release.
[Source hash verification](validation/artifacts/gemma26-conversion-20260928/origin-verification.json).

The original BF16 vLLM reference failed while loading: the kernel explicitly
records a worker killed at the diagnostic container's 36 GiB memory limit.
This was a test resource failure, not an inference outcome. A retry with a
64 GiB cap is queued after Qwen's independent Q8 baseline. It temporarily stops
the idle 12B preparation service and restores it afterward, rather than loading
both CPU allocations simultaneously. The first failed attempt is preserved.
[Memory failure evidence](validation/artifacts/gemma26-bf16-reference-20260928/kernel-memory-failure.log).


## Qwen real-model baseline passed; larger preparation integrated

The Qwen 27B Q8 package loaded on both XTXs and answered all four baseline
prompts exactly: Paris, 42, Juniper and 21. These are smoke checks, not a broad
accuracy estimate or native-memory validation.
[Actual GPU responses](validation/artifacts/qwen27-baseline-20260928/responses.json).

The private resident compiler now has an explicit `bounded_text_fp32` backend.
Its default 12B backend remains unchanged. The larger backend uses original
Transformers text models and Accelerate offload hooks, exports every selected
position from each applicable attention layer, and rejects incomplete working
sets, missing positions and nonfinite state. Qwen's recurrent layers are not
misrepresented as K/V attention layers. Every preparation is a full FP32 pass.

Reduced real Gemma MoE and Qwen hybrid export tests passed: three selected
records all reached encoding; every applicable layer's BF16 exported K/V
exactly matched the resident FP32 reference. Existing resident transport tests
also passed after supplying a missing sibling fixture script to the isolated
test directory; the initial fixture failure is preserved. The live 12B service
has not been switched to this backend. A full Qwen checkpoint, three-record
preparation is queued after the Gemma BF16 reference releases resources.
[Export and transport checks](validation/artifacts/bounded-preparation-20260928/).


## Corrected trained-buffer preparation and healthy Gemma BF16 reference

The original Gemma 26B BF16 checkpoint passed all four deterministic baseline
checks under the private image with unchanged upstream vLLM, after increasing
the container host-memory allowance from 36 to 64 GiB and stopping the idle
12B compiler during the run. CPU offload remained 8 GiB per GPU worker. The
compiler was restored afterward. This isolates the unhealthy Q8 package from
a healthy full-checkpoint runtime reference; it does not certify native memory.
[BF16 reference evidence](validation/artifacts/gemma26-bf16-reference-20260928-memory-r2/).

Separately, the new bounded CPU preparation path omitted trained persistent
buffers from Accelerate's weight loading. Gemma stores its learned per-layer
scalar in a buffer; leaving constructor values there corrupts computation.
The preparation path now loads persistent buffers, while the supported hooks
retain generated nonpersistent buffers. Strengthened reduced-model tests use
nondefault learned scalars and match the ordinary FP32 reference exactly. All
four test methods passed, including both architecture families and delivery
of all three selected records to exported attention banks.

The corrected full Gemma checkpoint next-token diagnostic now predicts `4`
for `17 + 25`, with finite nonsaturated logits, instead of the prior saturated
output. This diagnostic checks the first token, not the complete answer. It
read 658 tensors and released all parameters after the pass. Its approximately
62-second CPU duration is offline full-checkpoint preparation/reference work,
not resident memory application latency. Existing 12B production preparation
was not changed. [Fix evidence](validation/artifacts/bounded-buffer-fix-20260928/).

The initial full Qwen preparation also exposed incorrect chat framing: its
template rejects a system-only conversation. The corrected path retains the
existing Qwen independent raw-memory-text protocol. A test now explicitly
rejects any use of its chat template. The failed first full attempt is retained
[here](validation/artifacts/bounded-preparation-20260928/qwen27-full.log).
The corrected full-checkpoint Qwen preparation passed: all three selected
records produced 38 positions in each of its 16 full-attention layers. Banks
were finite and every layer retained all positions. The full FP32 forward
took approximately 66 seconds, with approximately 4 ms for export; these are
offline preparation measurements, not serving latency. All parameters were
released after preparation. The corresponding full Gemma memory preparation also passed: all three
records produced 41 positions across all 30 layers, with finite banks. Its
FP32 forward took approximately 46 seconds and export approximately 248 ms.
All parameters were released afterward. Native answer quality and lifecycle validation remain open.


## First Qwen native comparison and Gemma isolation checks

Both full-checkpoint preparations passed complete three-record export. Qwen's
first private native runtime comparison completed at 3/5 native, 1/5 control
and 5/5 text; two native quality failures remain. Native prompt counts matched
control, while text memory added 43 tokens per question. No binary-only
release, live authority or learning certification is implied.

Gemma's sampled source/loaded BF16 checks, Q8 payload checks and isolated expert
numerics have not explained the failing Q8 model. Exact loaded quantized-byte
comparison passed all 38 checked matrices on both workers. Dense/vocabulary
and embedding numerical samples remain finite and close to their independent
references. Paired full-model CPU/GPU layer traces are running next. The [current validation report](validation/larger-model-native-20260928.md)
records the full scope, failures and remaining release gates.
