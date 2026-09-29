# Standalone Aimee vLLM plugin

Install the compiled wheel into your existing supported vLLM environment. The
wheel contains the plugin, Rust memory consumer and connection client, and
matched native-memory attention kernels. It does not contain vLLM, PyTorch,
an operating system, model weights, a container runtime, or the private encoder.
Aimee supplies authorized model-specific native memory through the connection.

The first binary profile targets Python 3.12, Linux x86-64, vLLM
`0.30.0+rocm723`, PyTorch `2.12.0+git6bbd260`, Triton `3.7.1+gitf0b55c07`, and
RX 7900 XTX (`gfx1100`). Version checks at startup preserve that ABI boundary;
this wheel is not a claim of CUDA or arbitrary-vLLM-version compatibility.
The same compiled consumer assets passed live Aimee memory queries on
Gemma4 12B, Gemma4 26B and Qwen3.8 27B; interrupted-stream recovery also passed.
See the [standalone validation record](../../docs/validation/standalone-plugin-20260929.md).

```sh
python -m pip install ./aimee_vllm-0.1.1-1-cp312-cp312-linux_x86_64.whl
# The scoped token is read from stdin, never from a command-line argument.
aimee-native connect https://your-aimee-endpoint
aimee-native serve --config ./aimee.json
```

For a GGUF model, install the wheel with its `gguf` extra (or install the
tested ROCm build `vllm-gguf-plugin==0.0.5+rocm723`). Aimee uses its loader interfaces,
not its upstream-patching entry point. The extra pins the ROCm wheel by URL and
SHA-256, so pip cannot substitute the CUDA wheel with the same version. The configuration references your model
files and the native model identity authorized by Aimee:

```json
{
  "model": "/models/my-model",
  "native_model": "<Aimee native model identity>",
  "serve": {"tensor_parallel_size": 2, "port": 8080}
}
```

The model directory includes the matching `config.json` and tokenizer. For
GGUF, add `gguf_weights` with the absolute weight-file path, and the certified
`gguf_matrix_backend` (`triton` for the current Gemma26 profile). Other serving
limits remain the existing plugin's supported settings. The Rust client
obtains fresh authorization, initializes local memory, and supervises the
selection broker and vLLM process. Serving binds loopback. No model container
is started by this command.

## Why a native-memory attention kernel remains

The plugin already uses vLLM for model execution, ordinary attention when no
native bank is selected, and text K/V cache updates. The supported Triton
attention interface takes one paged K/V cache. Aimee's selected native banks
are separate allocations; they do not occupy text positions or prompt tokens.
The current private kernel combines those banks and the text cache in one
normalized attention computation. vLLM's FlashAttention cascade helper is not
a drop-in replacement: its implementation rejects sliding windows, which the
Gemma profile uses. Packing memory into the text cache or running independent
softmaxes without their normalization state would change the tested behavior.

Reusing upstream kernels further remains a valid implementation option, but
requires evidence that positional visibility, normalization, request isolation,
and performance remain correct. It does not require a vLLM fork. The current
kernel binaries are internal wheel assets, not an extra user installation.

## Current controlled download

Version 0.1.1 is [available here](https://192.168.0.126:8445/plugins/rocm723-gfx1100/0.1.1/aimee_vllm-0.1.1-1-cp312-cp312-linux_x86_64.whl).
The adjacent `manifest.json` and detached `.sig` files retain the existing
release signing identity. On this private origin, use the provisioned release CA
with pip's `--cert` option; do not disable TLS verification. The GGUF extra
automatically downloads the matching ROCm loader.
