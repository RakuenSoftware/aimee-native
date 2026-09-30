# Portable vLLM plugin — 30 September 2026

Version 0.2.0 replaces the preview's hardware-specific binary bank with GPU
operations compiled by the user's installed Triton runtime. The compiled Rust
consumer continues to own memory storage, selection plans, activation and the
Aimee connection. There is no vLLM fork and no replacement GPU driver or runtime
image in the distribution.

The installation path is documented in [Standalone setup](../../distribution/vllm/STANDALONE.md).
This is a Linux x86-64, CPython 3.12 wheel (glibc 2.34+) using the vLLM 0.30.x plugin interface.
The supported execution paths are CUDA and HIP with BF16 support. The user's
vLLM, PyTorch and Triton installation must already support their GPU. Removing
the hardware binding does not establish physical validation on every GPU.

## What changed

- Native attention and lossless transport decoding compile for the active GPU;
  the package no longer contains a `gfx1100` binary bank or HIP-only decoder.
- The tensor bridge calls the installed public PyTorch API for allocation,
  transfers, synchronization and views. It has no ATen, HIP or CUDA shared-library
  dependency. Small compiled framework wrappers remain; Rust still owns the
  memory implementation. This is not an entirely Rust inference engine.
- Runtime checks accept the supported vLLM interface range rather than exact
  vendor build strings for vLLM, PyTorch and Triton.
- The optional GGUF dependency retains 131 upstream code assets byte-for-byte,
  omitting its optional GPU-specific binary. Its existing Triton implementation
  is the default on both backends. No upstream source fork or monkey-patching
  is used.
- The launcher and consumer build on a CPU-only builder with CPython headers,
  Rust and a C++ compiler. End users install the wheel; they do not build these
  components or install an additional GPU toolkit.

The generic attention and bit-unpacking kernels are runtime-compilation inputs
in the wheel. The memory encoder, preparation algorithms and publication service
remain private. Runtime compilation necessarily exposes these small generic GPU
operations; compilation is not a claim of source secrecy or irreversibility.

The private build entry point is
[`build-portable-plugin.py`](../../distribution/release/build-portable-plugin.py).
Build against the deployment libc baseline with CPython 3.12; supply the upstream
GGUF wheel, consumer notices and controlled dependency download base. GPU devices
and toolkit headers are unnecessary on this builder.

## Validation protocol

Tests install the complete wheel in an existing, unmodified vLLM runtime on two
Radeon RX 7900 XTX GPUs. They do not import the consumer from a source checkout.
The runtime versions are vLLM `0.30.0+rocm723`, PyTorch `2.12.0+git6bbd260` and
Triton `3.7.1+gitf0b55c07`. Vendor suffixes describe this test environment, not
mandatory install versions.

The decoder test covers all 65,536 BF16 bit patterns, including escape values,
odd lengths and block boundaries. Attention output is compared against an
independent PyTorch reference across ragged prefill and decode, multiple native
banks, grouped-query attention, sliding windows, soft capping and nontrivial
paged text-cache mappings. Maximum absolute error was `9.54e-7`.

The installed consumer is also compared bit-for-bit with the Rust raw-storage
reference: six complete records, both tensor-parallel ranks, raw and lossless
transport, and three activations per case. Each activation releases its Rust
handle, evicts residency and forces garbage collection before checking every
tensor. Two fresh-process suites passed all 144 activations. This checks both
data correctness and ownership after the activation handle is released.

Offline compilation covers all seven attention specializations from the prior
validated model profiles and both decoder kernels on each of seven targets:
CUDA `sm80`, `sm89`, `sm90`, `sm120`; HIP `gfx942`, `gfx1100`, `gfx1201`.
All 63 compilations passed. These are compiler checks, **not GPU executions**.
The later [RTX 5080 follow-up](cuda-5080-20260930.md) supplies physical NVIDIA
execution evidence for the same wheel. Other AMD and NVIDIA targets retain
compilation-only coverage.

Three live-model checks use the installed `aimee-native connect` and `serve`
commands and an authenticated Aimee service. Each asks twice for three authorized
canary facts absent from the prompt, exercising initial and resident consumption.
This is an integration check, not a new learning benchmark or a replacement for
the earlier coding evaluation. The [24 repository-repair attempts](standalone-coding-20260929.md)
used version 0.1.1; they have not been rerun on this wheel.

## Live results

| Model | Correct requests | Prompt tokens | First response | Second response |
|---|---:|---:|---:|---:|
| Gemma4 26B | 2/2 | 27 | 88.55 s | 7.65 s |
| Gemma4 12B | 2/2 | 27 | 23.11 s | 12.24 s |
| Qwen3.8 27B | 2/2 | 26 | 32.18 s | 30.30 s |

Every response included all three requested native facts. Times cover each
complete HTTP response after the server becomes ready; they exclude model
startup and include inference, plus any request-time JIT/tuning. They are not
memory activation timings or a matched performance comparison with version 0.1.1.
The first request is not a controlled cold-disk experiment.

## Failures found and fixed

The initial package accidentally included a launcher built against a newer host
libc. A clean installation caught the incompatibility before inference. The
launcher now builds alongside the consumer in the deployment-baseline builder.

A subsequent repeated activation test exposed intermittent stale values in the
pipelined lossless path. Raw transport and standalone decoder checks passed.
Completing uploads before handing raw pointers to the external decoder eliminated
the mismatch in the diagnostic; the corrected installed wheel then passed both
full activation suites. Rust now enforces that completion boundary. Chunked reads
and transfers still overlap during loading; resident attention is unchanged.
The superseded candidate and its failure logs remain in the evidence record.

The host thin pool also reached capacity while the container filesystem reported
free space. Podman consequently failed to launch a repeat test. Reclaiming already
unused filesystem blocks recovered 6.6 GiB; no model or user files were deleted.
That failed process launch is separate from numerical test results.

## Remaining limits

This change removes GPU-model coupling. It does not add CPU/Metal inference,
unsupported model attention features, quantized native K/V, or graph-safe memory
lifecycle management. The current launcher uses eager execution, disables prefix
caching and asynchronous scheduling, and requires prepared memory matching the
model identity. ALiBi, attention sinks, cascade attention and multimodal prefix
ranges remain unsupported by this backend.

First-use Triton compilation and GGUF tuning can be substantial and are cached.
Activating nonresident memory still takes milliseconds in these repeated-file
tests; they do not isolate cold physical-disk latency. The microsecond target
remains optimization work rather than a release condition.
End-to-end model response times include inference and must not be presented as
memory activation latency. This work establishes a portable implementation and
its measured execution coverage, not equal performance across all GPUs.

## Delivery and evidence

The signed [0.2.0 wheel](https://192.168.0.126:8445/plugins/portable/0.2.0/aimee_vllm-0.2.0-1-cp312-cp312-linux_x86_64.whl)
and [manifest](https://192.168.0.126:8445/plugins/portable/0.2.0/manifest.json)
are available on the controlled origin. Use the provisioned release CA.
The wheel is 3,081,352 bytes; SHA-256:

```text
511a16373291774b85d427468f484fedc531310465c25ee55d22fa79ec99ce37
```

Full TLS downloads and pinned Ed25519 signature verification passed for the
plugin, dependency and manifest. The GGUF extra resolves against the installed
runtime; pip also downloads its pinned dependency with the expected hash.
The prior 0.1.1 release is unchanged.

[Raw results, logs and checksums](artifacts/portable-plugin-20260930/README.md)
retain both final evidence and superseded failures. No credentials, model weights,
private client state or memory payloads are archived.
