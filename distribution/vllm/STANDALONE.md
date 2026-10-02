# Standalone Aimee vLLM plugin

Enroll the standard Aimee thin client using the invitation issued in Aimee's
Settings → Clients and the existing `aimee remote set URL INVITATION` command.
The thin client pins TLS and enrolls its certificate. Then run
`aimee-native connect-aimee` to use that enrolled identity for native memory.
`connect-aimee` is not in the staged 0.2.2 wheel. The self-hosted release under
development obtains a versioned memory primitive from the latest Aimee server;
the inference host prepares model-specific memory locally. See
[the public-install gate](../../docs/validation/public-native-aimee-enrollment-20261002.md)
before describing the staged preview as a general public release.

Install the compiled wheel into your existing supported vLLM environment. The
planned self-hosted wheel contains the plugin, Rust memory consumer and
connection client, portable GPU operations and a compiled local encoder. It
does not contain vLLM, PyTorch, an operating system, model weights or a
container runtime. Aimee supplies authorized source records through the
enrolled thin client; model-specific preparation happens beside vLLM.

Version 0.2.1 includes the authorized empty-selection correction. Its portable
GPU path, unchanged from 0.2.0, removes the `gfx1100` binary-kernel requirement and the exact
ROCm/PyTorch/Triton build locks. The plugin uses the installed PyTorch runtime
for allocations/transfers and Triton to compile its attention and lossless
transport operations for the active **CUDA or HIP** GPU. Users do not compile
Rust/C++ or install another GPU toolkit. Initial GPU compilation is cached by
Triton; it is distinct from warmed request execution.

The current wheel targets **Linux x86-64 / Python 3.12 / glibc 2.34+** and the **vLLM 0.30.x
plugin interface**. The installed runtime must support the GPU and BF16. There
is no GPU-model allowlist. Compiling for a target is not equivalent to executing
on it: see the [portable validation record](../../docs/validation/portable-plugin-20260930.md)
for actual hardware coverage and remaining limits. The same published wheel has
now passed physical checks on the RX 7900 XTXs and an
[RTX 5080](../../docs/validation/cuda-5080-20260930.md).

In the fresh CUDA pip environment, upstream FlashInfer sampling required an
`nvcc` setup. The 5080 check used `VLLM_USE_FLASHINFER_SAMPLER=0` to select
vLLM's PyTorch sampler. This is an upstream runtime setting; existing environments
with a working sampler do not need to change it.

```sh
python -m pip install ./aimee_vllm-0.2.1-1-cp312-cp312-linux_x86_64.whl
# The scoped token is read from stdin, never from a command-line argument.
aimee-native connect https://your-aimee-endpoint
aimee-native serve --config ./aimee.json
```

Those commands document the controlled 0.2.1 preview. For the pending
self-hosted 0.2.3 wheel, enroll the standard Aimee thin client first, then use
`aimee-native connect-aimee` followed by `aimee-native serve --config
./aimee.json`. The plugin reuses the enrolled certificate, TLS pin and token;
no separate plugin enrollment or server-side model installation is required.

For a GGUF model, install the wheel with its `gguf` extra:

```sh
python -m pip install './aimee_vllm-0.2.1-1-cp312-cp312-linux_x86_64.whl[gguf]'
```

The extra supplies upstream's existing Triton GGUF loader implementation,
without its optional hardware-specific binary. All retained upstream code is
unchanged. Aimee uses its loader interfaces, not its patching entry point.
The dependency URL and hash are pinned, and the default matrix backend is
Triton on both CUDA and HIP. No per-GPU dependency selection is necessary.
The configuration references your local model files:

```json
{
  "model": "/models/my-model",
  "serve": {"tensor_parallel_size": 2, "port": 8080}
}
```

The model directory includes the matching `config.json`, tokenizer and
safetensors for initial local memory preparation. For GGUF serving, add
`gguf_weights` with the absolute weight-file path; the local safetensors are
still required by the current encoder. GGUF-only local preparation remains
unvalidated.
`gguf_matrix_backend` defaults to `triton`. Other serving
limits remain the existing plugin's supported settings. The Rust client
obtains fresh authorization, initializes local memory, and supervises the
selection broker and vLLM process. Serving binds loopback. No model container
is started by this command.

## Why a native-memory attention kernel remains

The plugin already uses vLLM for model execution, ordinary attention when no
native bank is selected, and text K/V cache updates. The supported Triton
attention interface takes one paged K/V cache. Aimee's selected native banks
are separate allocations; they do not occupy text positions or prompt tokens.
The native attention operation combines those banks and the text cache in one
normalized attention computation. vLLM's FlashAttention cascade helper is not
a drop-in replacement: its implementation rejects sliding windows, which the
Gemma profile uses. Packing memory into the text cache or running independent
softmaxes without their normalization state would change the tested behavior.

Reusing upstream kernels further remains a valid implementation option, but
requires evidence that positional visibility, normalization, request isolation,
and performance remain correct. It does not require a vLLM fork. The required
operations compile automatically through the installed Triton runtime.

## Platform and feature limits

Portability follows the installed runtime's GPU support; it does not make a
CPU-only runtime, Metal, or an unsupported GPU into a supported execution target.
Prepared memory must match the model configuration. This implementation uses
BF16 causal decoder attention; ALiBi, attention sinks, cascade attention,
quantized K/V cache and multimodal prefix ranges are not currently supported.
The signed 0.2.1 launcher disables graph capture, prefix caching and
asynchronous scheduling. These are separate from GPU portability.

The staged 0.2.2 candidate adds opt-in work on those limits:
`serve.enable_prefix_caching`, `serve.async_scheduling`,
`serve.enable_model_compilation`, `serve.enable_piecewise_graphs`, and
`serve.v2_model_runner`.
They are **not in the published 0.2.1 wheel**. The exact 0.2.2 wheel has passed
the [installed-wheel release-candidate checks](../../docs/validation/plugin-polish-20261001.md)
for these options. Prefix caching uses a server-generated
identity tied to the recipient, catalogue revision and selected publication;
the caller's `cache_salt` is replaced. Asynchronous scheduling waits for the
previous GPU forward before releasing native pointers. Piecewise graph mode
captures compiled model segments while native attention remains outside the
graph; full graph capture remains unsupported. The candidate's paired
installed-wheel GPU comparison is recorded in that validation report;
publication remains a separate step.
The V2 runner candidate uses the stable request-state slots in vLLM's
attention metadata to associate requests with native banks during forward.
In vLLM 0.30, the hybrid model state does not supply those slots for live
attention requests. The 0.2.2 candidate therefore rejects V2 for hybrid
models with an explicit configuration error; use `serve.v2_model_runner: false`
for Qwen3.8 27B. Native memory remains available through the V1 runner.
Live publication replacement pauses new admission until active requests drain.
The broker obtains fresh approval after the drain and verifies that the
authorized publication is unchanged; a long stream can therefore delay the
first answer under a new revision.
The [0.2.2 candidate validation](../../docs/validation/plugin-polish-20261001.md)
records the installed-wheel AMD model matrix, candidate integrity checks, and
the separate option, live-revision, and CUDA gates.

The private memory encoder, publication service, and Rust storage implementation
are not distributed as source. The generic attention and bit-unpacking operations
are supplied as runtime-compilation inputs; this deliberately replaces the
architecture-specific binary bank. No vLLM fork is required.

## Controlled download

The published controlled preview is version 0.2.1. Version 0.2.2 is signed and
staged but is not yet available from the download origin. The 0.2.1 portable
GPU execution coverage is recorded in the
[0.2.0 validation report](../../docs/validation/portable-plugin-20260930.md),
and its changed empty-selection path in the [0.2.1 validation report](../../docs/validation/authorized-empty-20260930.md).
On the private origin, use the provisioned release CA with pip's `--cert` option.
The earlier 0.1.1 architecture-specific package remains an immutable prior release.

Once the signed 0.2.2 stage is published to the controlled origin, install its
wheel in the same supported vLLM environment:

```sh
python -m pip install ./aimee_vllm-0.2.2-1-cp312-cp312-linux_x86_64.whl
```

Use the existing `aimee-native connect` and `aimee-native serve` commands above.
For the tested Qwen3.8 27B hybrid profile, set
`"v2_model_runner": false` inside `serve` in the JSON configuration. The 0.2.2
[release review](../../docs/validation/plugin-0.2.2-release-review-20261001.md)
sets out the tested models, GPUs, and runner boundaries.
For the planned public GitHub asset, build tag `2` changes only the optional
GGUF dependency URL and wheel `RECORD`; the compiled runtime is byte-identical
to this controlled candidate. Its separate
[public release preparation](../../docs/validation/public-plugin-release-readiness-20261001.md)
records the asset hash and direct installed-wheel CUDA check.

### 0.2.1 empty-selection correction

Version 0.2.1 supports an explicit, freshly authorized “no relevant memory”
response from the hosted service. Such a request runs with no native bank,
including when earlier requests used resident memory. It still rejects failed
or unavailable authorization. **Upgrade the Aimee hosted service and plugin
together** before serving empty selections. An older hosted service does not
authorize them. No new GPU kernels, model weights or runtime fork are required.

The signed [0.2.1 manifest](https://192.168.0.126:8445/plugins/portable/0.2.1/manifest.json)
identifies the current private wheel. Its SHA-256 is
`b3dc503d0bbec6f0f303fb7a2829ac1773d8b5bd0783041929d707351660bc2f`.
