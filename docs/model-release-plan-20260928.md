# Required model releases — 2026-09-28

Release scope now includes Gemma4 12B (current validation candidate), Gemma4
26B, and Qwen3.8 27B. Complete the current regression investigation first;
then build and validate each larger model as a separate deliverable. Keep
private implementation in aimee-qwen and retain the fork-free vLLM approach.

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

Current status: Gemma4 12B candidate runtime checks passed, full-task regression
validation pending, normal signed lifecycle pending. Gemma4 26B and Qwen3.8
27B artifact discovery, builds and validation are not yet complete.


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
