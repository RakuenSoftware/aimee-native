# Supported-model NAS smoke — 2026-10-06

Four Gemma models passed. Qwen failed before inference. This run does not qualify
the full release.

| Model | Existing NAS GGUF | Cold/warm native recall | Result |
| --- | --- | --- | --- |
| Gemma 4 E2B | UD-Q4_K_XL | Both passed | Passed |
| Gemma 4 E4B | UD-Q4_K_XL | Both passed | Passed |
| Gemma 4 12B | UD-Q4_K_XL | Both passed | Passed |
| Gemma 4 26B | Q3_K_M | Both passed | Passed with compiler diagnostics |
| Qwen 3.8 27B | Q4_K_M | Not reached | Startup failed |

Each model ran sequentially on one 7900 XTX with zero CPU weight offload, using
existing GGUFs from .254 `storage/models`, mounted read-only through .253.
These runs did not download or copy model weights onto the CT. Logs, runtime
caches, native banks and the fresh Aimee source data were backed by .254 storage.

The four passing runs also denied unauthenticated inference, left the source
unselected after that denied request, and reused the native bank for warm recall.
The recall answer was a random value stored through the enrolled Aimee client;
the inference prompt did not contain that value. Test records were deleted after
each run.

Qwen's loader required a vision projector for its configured multimodal
architecture. The NAS Q4 GGUF is text-only. Startup ended with
`Could not find mm_proj`; no Qwen inference succeeded.

26B loaded in 152 seconds using 12.78 GiB of GPU memory. Its Q3/Q5 expert kernels
emitted Triton matrix-instruction compilation errors during initialization.
Startup continued and both actual recall requests passed. The compiler
diagnostics remain unresolved; this result does not establish warning-free
startup or performance readiness.

These tests used installed model adapters 0.3.3 and shared runtime 0.3.3 build 4.
Build 4 differs from the original runtime wheel committed to PR #5. These
results therefore do not qualify that original runtime artifact or the
unfinished text-only Qwen loader change. No new runtime artifact is promoted by
this evidence update.

See [results.json](results.json) for the checks, exact GGUF paths and failure.
Full operational logs remain on .254 under
`storage/proxmoxbackup/aimee-experiments/release-smoke-20261006`.
