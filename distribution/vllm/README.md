# Private, fork-free vLLM integration

The current release uses [three thin model plugins on one shared runtime](MODEL_PLUGINS.md).
Each plugin owns its dedicated Rust adapter; enrollment, selection, preparation,
admission, scheduling and framework integration are shared.


Install the corresponding [model-specific candidate](MODEL_PLUGINS.md).
Each package connects a supported vLLM installation to Aimee without a runtime
container or a fork. [The earlier shared-wheel instructions](STANDALONE.md)
describe historical releases. The manual configuration below is for development.

This package registers an external attention backend and a configured worker
subclass using vLLM's existing extension interfaces. It does not patch, fork,
replace installed source files, or monkey-patch vLLM. The published 0.2.1 wheel
and staged 0.2.2 candidate target the
vLLM 0.30.x plugin interface. Upstream interfaces are version-sensitive. GPU
operations compile through the installed CUDA/HIP runtime; see the
[portable validation record](../../docs/validation/portable-plugin-20260930.md)
for execution coverage, compilation checks and current release limits.

The serving process uses Rust store admission and activation, a small ABI bridge
to the installed public PyTorch API, and a runtime-compiled GPU attention implementation.
Encoding remains in the private preparation system.
Prepared native banks are separate from text KV cache allocation and prompt
positions. The worker pins a specific publication for each request, including
preemption/resumption, and the metadata builder uses the actual reordered batch.
TP ranks consume their own head shards. No memory text is added to prompts.

## Run in the private validation environment

Build `sh distribution/release/build-portable-client.sh`, then install this package
in the supported vLLM environment. Run:

```
aimee-vllm --config /absolute/path/config.json
```

Configuration (paths must refer to admitted, publisher-owned artifacts):

```json
{
  "model": "/models/certified-model",
  "library": "/opt/aimee/libaimee_native.so",
  "catalog": "/var/lib/aimee/catalog.json",
  "recipient": "approved-recipient",
  "host_memory_budget": 1073741824,
  "device_memory_budget": 268435456,
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

## Original development validation and feature limits

Gemma4 12B with BF16 native memory and certified Q8 GGUF weights, two
RX7900XTXs, tensor parallel size2, V1 runner, eager execution,
chunked text prefill and decode. Native attention supports ragged requests, GQA,
local text windows and logit softcaps. Native memory visibility matches the
existing independent negative-position encoder. Other model/position profiles
require certification; a generic kernel is not a universal empirical result.

Graph capture, prefix caching, asynchronous/speculative scheduling, pipeline
parallelism, multimodal prefix attention, quantized KV and sink attention are
rejected. The pinned loader supports the certified Q8 GGUF artifact. This does
not establish compatibility with arbitrary GGUF files or runtime versions.

With `disk_backed: true`, startup verifies and admits immutable banks, prepares
rank layouts and optionally authors lossless transport extents. Rust bounds the
native memory reservation per rank (`device_memory_budget`, default 256 MiB),
evicts idle banks and protects active request pins. The reservation covers dense
banks and encoded staging where used, but excludes model/text KV, pointer tables,
host staging and allocator-reserved memory. Leave device headroom. Ingress
admission rejects incompatible concurrent working sets before generation. Failed
activation poisons the worker cache rather than serving incomplete state.

The historical container preview included hosted preparation, authorized delivery,
signed installation, compiled client code and a pinned runtime image. The
standalone release packages the compiled client components as a wheel; that
image is build/test infrastructure, not a required client artifact. The source plugin
and kernel remain private development artifacts. Public redistribution and broader
hardware/model certification remain separate gates. See the release evidence in
`docs/validation/`; isolated activation, preparation and end-to-end serving are
different measurements. The old llama.cpp patch is abandoned, not a dependency.


### Native activation boundary

The current bridge requires a `vllm-runtime` consumer build against the pinned
runtime's `LIBTORCH` and `PYTHON_INCLUDE`. This enables only the ATen/CPython ABI
shim; it does not enable the Rust `torch` feature, private model implementation
or publisher. Rust owns allocation, I/O, transfer completion and tensor geometry.
The Python bridge receives a dictionary of already-created tensors and retains
their framework ownership. There is no Python allocation/transfer/view fallback.

Build the small lossless decoder with `distribution/release/build-vllm-codec.sh`
inside the pinned ROCm image (`AIMEE_GPU_ARCH=gfx1100` for the certified XTXs).
Pass its `AIMEE_CODEC_OBJECT` and that image's `HIP_LIB_DIR` to the client build.
This reuses the installed ATen/HIP runtime; it does not implement a tensor engine.
An admission-time lossless transport copy occupies extents in one owned file.
Its index remains in RAM, and its descriptor remains open while any extent is
live. Activation reads the extent into pinned storage and decodes on the GPU.
`lossless_transport: false` selects raw transport. Insufficient GPU staging budget,
poor compression or unavailable optional arena storage also use raw transport.
Rust accounts for dense residency and temporary staging separately. Completed
uploads release the staging charge. If staging cannot fit, the worker uploads the
same bank through raw transport, preserving active pins and complete tensor bytes.
Frontend admission reserves dense bytes; the worker enforces each upload's peak.

Compressed reads use the retained descriptor and four existing Rust I/O workers.
Completed chunks are submitted on the caller's ATen stream while other chunks
are read. `pipeline_transport: false` keeps parallel reads but waits for all reads
before upload, for diagnostics or workloads where overlap is unfavorable.
Read failures drain the I/O workers and synchronize already-submitted GPU work
before buffers are released. No model encoding or integrity work enters activation.

See [the runtime ownership report](../../docs/validation/native-runtime-ownership-20260926.md)
for profiling boundaries and exactness/ownership checks.

See [streaming and transient-residency measurements](../../docs/validation/native-streaming-20260926.md)
for the latest implementation and the still-unmet cold microsecond target.


## Complete hybrid native prefix

The opt-in `enable_hybrid_native: true` profile retains attention keys/values,
convolution history and FP32 recurrent state. The worker initializes the real
request's private GDN cache slots, shifts conversation positions by the native
prefix length before RoPE, and reseeds on zero-token recomputation after
preemption. Later chunks and decode retain their evolving request state. Plain
requests in the same batch keep their ordinary positions and initialization.
The immutable prepared tensors remain reusable across requests.

This profile requires matching BF16 weights or serialized dynamic-activation FP8
weights with prefixes captured from the same serving engine, an immutable
`model_revision`, eager synchronous V1 execution and FP32 Mamba state caches.
The catalogue's `hybrid_state` is the SHA-256 of `hybrid.json`; that manifest binds
the attention index, recurrent payload, checkpoint revision, configuration,
tokenizer, encoder precision and positional profile. A same-architecture revision
or tokenizer change requires new preparation. Runtime identity checks trust the
configured revision pin; operators must ensure the installed weights correspond
to it. FP8 identity additionally binds vLLM, Torch, Triton, device capability,
attention/convolution/recurrent dtypes and the checkpoint's weight provenance
manifest. Static-activation and block-quantized FP8 prefixes are rejected.
Serving performs no memory encoding.

`system-message` preparation binds the closed instruction prefix to a system
context digest. Admission requires matching instructions and removes that one
system message once a nonempty native bank is selected. A miss keeps the ordinary
system message. `content` preparation leaves conversation instructions in place.
Prepared state from one framing or context cannot be reused for another.

On devices requiring model offload, `serve.cpu_offload_gb` is the stock weight
budget. `serve.cpu_offload_pinned_memory: false` selects pageable transfers and
disables UVA; complete-hybrid offload defaults to matrix projection weights,
keeping small convolution/gating tensors resident. This trades speed for bounded
host/device loading. `serve.cpu_offload_disable_uva: true` also permits pinned
copy transfers without UVA reads; pinning and UVA are independent controls.
The native host reservation includes recurrent payloads and
rank plans even with disk-backed attention. The native device budget covers
attention plus immutable recurrent seeds; private conversation caches and model
weights require additional headroom. Validation processes should have explicit
host-memory limits.

Complete preparation deduplicates identical immutable recurrent payloads by their
SHA-256 name. Offline export hardlinks them on the same filesystem; publication
across filesystems copies them without changing their content identity. This
reduces stored bytes, not the private per-request recurrent-state requirement.

Use `benchmarks/native_addressing/collect_native_prepare_requests.py` for exact
published-reader selections, `export_hybrid.py` for offline catalogue artifacts,
`checkpoint_storage_validation.py` for payload verification,
`hybrid_serving_validation.py` for the frozen BF16 serving matrix and live control
checks, and `audit_hybrid_serving.py` to independently audit its coverage/scores.
The separate [INT8 research retest](../../docs/validation/native-memory-int8-20261004.md)
passes its matching consumption contract; historical failures remain recorded.
That runtime does not establish INT8 kernel support in vLLM on Blackwell.

For same-engine FP8 preparation and isolated deployment, see the
[deployment instructions](deployment/README.md). The offline capture worker
cannot be enabled through the HTTP launcher. Process-lifetime host-stage counters
remain cumulative across catalogue refreshes.

Hybrid hooks install even with an initially empty publication catalogue, so a later
validated refresh can activate the first banks. Convolution seed and private-cache
dtypes must match exactly; mismatches reject before cache writes. See the
[full-checkpoint validation report](../../docs/validation/native-memory-completion-20261004.md)
for the RTX 5080 quality matrix, actual preemption/reseeding and publication gates.
