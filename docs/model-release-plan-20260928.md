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
