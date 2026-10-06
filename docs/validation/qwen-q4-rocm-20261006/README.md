# Qwen Q4 text-only loader fix — 2026-10-06

Qwen 3.8 27B Q4_K_M passed all seven short native-memory smoke checks on one
7900 XTX with zero CPU weight offload. Cold and warm requests returned the
random value stored through the enrolled Aimee client. The inference prompt
did not contain the value. Warm recall reused the bank, and unauthenticated
inference was denied before source selection.

The original failure used a text-only NAS GGUF with a multimodal configuration.
The upstream adapter also assigned the multimodal architecture to explicit
`qwen3_5_text` configurations. Shared runtime 0.3.3 build 5 preserves the
upstream tensor/layout mapping but selects `Qwen3_5ForCausalLM` for explicit
text-only configurations. Vision weights or a vision configuration in that
path are rejected; multimodal configuration handling remains separate.

The first build-5 run loaded the model and captured its native state, but its
128 MiB device budget could not admit the 154,927,104-byte recurrent state.
It returned HTTP 429. The successful rerun used a 256 MiB native-memory budget.
The rejection is preserved in [undersized-budget.json](undersized-budget.json).

The model loaded using 17.77 GiB of GPU memory. The successful smoke used the
existing .254 `storage/models` Q4_K_M GGUF, SHA-256
`31629f53165ab6a7dad8c9847dcfd1fdf55829dac1e6e748f4a68581b0033d34`.
No model was downloaded or copied to CT storage. Logs, native banks, runtime
caches and the fresh Aimee source data remained on .254. The successful rerun
reused the first run's Triton kernel cache. Test records were deleted and the
owned model/source/bridge services were stopped afterward.

The tested runtime wheel is
`aimee_native_runtime-0.3.3-5-cp312-cp312-linux_x86_64.whl`, SHA-256
`a6ddd22b908b8195e51e7a65953fd66f8987c9eb7944ed67bc5f6fcb14ed4511`.
Build 5 replaces only build 4's compiled GGUF loader, plus wheel metadata and
RECORD. All five model adapter wheels retain their executable bytes.
The candidate wheel audit passed for all five adapters, and the compiled
capture, precision, CLI, GGUF-loader and state regression suite passed 26 tests.

This fixes the Qwen failure in the [earlier NAS smoke](../nas-supported-model-smoke-20261006/README.md).
The four Gemma models passed that run on build 4. They were not rerun on build 5;
the new loader branch applies only to explicit text-only Qwen configurations.
This short smoke does not establish broader lifecycle or performance readiness,
signing, manifest publication or published-release installation.

Transformers still emits a tokenizer regex warning for this local metadata;
the tested tokenizer bytes are unchanged and both recall checks passed. vLLM
uses its Triton GDN decode path because the optional fused decode operation is
not built. These diagnostics are retained in the NAS logs, rather than treated
as warning-free qualification.

- [Results and artifact identity](results.json)
- [Exact tested serving configuration](serving.json)
- [Text-only model configuration](model-config.json)
- [Compiled regression output](compiled-regressions.txt)
- [Build-4 payload provenance](../../../distribution/release/candidates/model-plugins-0.3.3-20261006/q4-runtime-build4.json)
- [Build-5 payload provenance](../../../distribution/release/candidates/model-plugins-0.3.3-20261006/q4-runtime-build5.json)

The serving configuration records this fixture's local paths. Supply matching
local tokenizer metadata alongside `model-config.json`, use your checkpoint's
verified SHA-256 and connect through your enrolled Aimee profile. The fixture
used the NAS tokenizer SHA-256
`0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3`.
Authority credentials and serving API keys are not included.
