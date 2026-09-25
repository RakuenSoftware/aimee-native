# Private, fork-free vLLM integration

This package registers an external attention backend and a configured worker
subclass using vLLM's existing extension interfaces. It does not patch, fork,
replace installed source files, or monkey-patch vLLM. Pin vLLM 0.30.0; the tested
ROCm wheel is 0.30.0+rocm723. Upstream interfaces are version-sensitive.

The serving process contains a Torch-free Rust store reader and an external GPU
attention implementation. Encoding remains in the private preparation system.
Prepared native banks are separate from text KV cache allocation and prompt
positions. The worker pins a specific publication for each request, including
preemption/resumption, and the metadata builder uses the actual reordered batch.
TP ranks consume their own head shards. No memory text is added to prompts.

## Run in the private validation environment

Build `sh distribution/release/build-vllm-client.sh`, then install this package
in the pinned vLLM environment. Run:

```
aimee-vllm --config /absolute/path/config.json
```

Configuration (paths must refer to admitted, publisher-owned artifacts):

```json
{
  "model": "/models/certified-model",
  "library": "/opt/aimee/libaimee_qwen.so",
  "catalog": "/var/lib/aimee/catalog.json",
  "recipient": "approved-recipient",
  "host_memory_budget": 1073741824,
  "serve": {"tensor_parallel_size": 2, "host": "127.0.0.1", "port": 8000}
}
```

The private catalog binds the model configuration digest and recipient to named
publications, each with its Rust store root, model identity, and immutable key.
It is installed by trusted publication machinery, never supplied by a request.
A request supplies `aimee_publication` in vLLM `SamplingParams.extra_args` (the
OpenAI-compatible API uses `vllm_xargs`). Unknown names fail closed. One instance
is one recipient boundary; a trusted Aimee gateway must perform authorization
and selection before forwarding requests. A catalog is not an authorization
service. Do not directly expose this prototype to untrusted tenants.

Replacing the catalog is a control-plane operation. Atomically publish the new
catalog then use `LLM.collective_rpc('aimee_refresh_catalog')` at a quiescent
boundary. Admission checks occur there, not in attention. Existing request pins
retain old revisions; new requests see replacements. Withdrawn aliases reject
new requests. This is graceful withdrawal, not immediate cancellation/revocation
of an in-flight request. Multiworker refresh has no distributed commit protocol;
if any rank rejects admission, stop admission and restart the serving instance
with a consistent catalog before resuming traffic. No public refresh HTTP route
is provided.

## Validated scope and remaining gates

BF16 Gemma4 12B, two RX7900XTXs, tensor parallel size2, V1 runner, eager execution,
chunked text prefill and decode. Native attention supports ragged requests, GQA,
local text windows and logit softcaps. Native memory visibility matches the
existing independent negative-position encoder. Other model/position profiles
require certification; a generic kernel is not a universal empirical result.

Graph capture, prefix caching, asynchronous/speculative scheduling, pipeline
parallelism, multimodal prefix attention, quantized KV and sink attention are
rejected. GGUF loading/quantization has not been validated by this integration.
Test weights are Hugging Face safetensors, not a GGUF release.

Startup admits catalog banks into host memory; first use uploads each selected
bank to its GPU rank, later use reuses it. This implementation is not yet a
bounded device cache or on-demand SSD streaming service. Catalog sizing must
leave GPU headroom. CPU/DMA, attention, compilation warmup and end-to-end latency
must be measured separately; this validation establishes correctness, not a
microsecond performance result.

Hosted preparation/authorized publication feed, bounded GPU eviction, production
API gateway, clean-machine driver image, latency certification, and signed
installer integration remain release gates. The source plugin and Triton kernel
are private development artifacts: do not ship this source wheel as the promised
closed-source product. A protected binary distribution and disclosure audit are
still required. The old llama.cpp patch is abandoned, not a dependency.
