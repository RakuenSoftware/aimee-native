# Standalone Aimee vLLM plugin

Install the compiled wheel into your existing supported vLLM environment. The
wheel contains the plugin, Rust memory consumer and connection client, and
portable native-memory GPU operations. It does not contain vLLM, PyTorch,
an operating system, model weights, a container runtime, or the private encoder.
Aimee supplies authorized model-specific native memory through the connection.

Version 0.2.0 removes the `gfx1100` binary-kernel requirement and the exact
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
python -m pip install ./aimee_vllm-0.2.0-1-cp312-cp312-linux_x86_64.whl
# The scoped token is read from stdin, never from a command-line argument.
aimee-native connect https://your-aimee-endpoint
aimee-native serve --config ./aimee.json
```

For a GGUF model, install the wheel with its `gguf` extra:

```sh
python -m pip install './aimee_vllm-0.2.0-1-cp312-cp312-linux_x86_64.whl[gguf]'
```

The extra supplies upstream's existing Triton GGUF loader implementation,
without its optional hardware-specific binary. All retained upstream code is
unchanged. Aimee uses its loader interfaces, not its patching entry point.
The dependency URL and hash are pinned, and the default matrix backend is
Triton on both CUDA and HIP. No per-GPU dependency selection is necessary.
The configuration references your model files and the native model identity
authorized by Aimee:

```json
{
  "model": "/models/my-model",
  "native_model": "<Aimee native model identity>",
  "serve": {"tensor_parallel_size": 2, "port": 8080}
}
```

The model directory includes the matching `config.json` and tokenizer. For
GGUF, add `gguf_weights` with the absolute weight-file path.
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
The launcher continues to disable graph capture, prefix caching and asynchronous
scheduling to preserve request ownership. These are separate from GPU portability.

The private memory encoder, publication service, and Rust storage implementation
are not distributed as source. The generic attention and bit-unpacking operations
are supplied as runtime-compilation inputs; this deliberately replaces the
architecture-specific binary bank. No vLLM fork is required.

## Controlled download

The portable candidate is version 0.2.0. Its signed download and execution
coverage are recorded in the [validation report](../../docs/validation/portable-plugin-20260930.md).
On the private origin, use the provisioned release CA with pip's `--cert` option.
The earlier 0.1.1 architecture-specific package remains an immutable prior release.

### 0.2.1 empty-selection correction

Version 0.2.1 supports an explicit, freshly authorized “no relevant memory”
response from the hosted service. Such a request runs with no native bank,
including when earlier requests used resident memory. It still rejects failed
or unavailable authorization. Hosted service and plugin must both support this
response; no new GPU kernels, model weights or runtime fork are required.
