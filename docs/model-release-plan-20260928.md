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
