# Fork-free vLLM packaging and serving validation — 2026-09-25

Private implementation evidence, not a production release announcement. All
records in the serving probes are synthetic. No Qwen run was performed.

## Demonstrated

- Unmodified vLLM 0.30.0, commit
  `ced6857afa0ea7b2e3f0846a62e1394e90f15607`, on two RX 7900 XTXs.
- External attention backend, worker subclass and ASGI middleware; no fork,
  engine source edits or runtime monkey-patching.
- Client modules compiled as CPython extensions. Client wheel contains no private
  Python implementations, encoding procedure or Triton kernel source. Native
  attention uses packaged HIP binaries and metadata; preparation stays private.
- Clean official ROCm container passes recall, isolation, three-record composition
  and live publication replacement. Base image is pinned to
  `docker.io/vllm/vllm-openai-rocm@sha256:2e7da1ad1c66836802072588adea75f9f4991da5f9545b4318e91d422c22ce6a`.
- Gemma Q8_0 GGUF: 12,863,382,944 bytes, 677 tensors, 329 quantized tensors.
  Native recall, both three-record composition cases and live replacement pass.
  Prompt count remains 26 in the direct recall conditions. Original BF16-prepared
  memory banks were reused; this is a compatibility smoke test, not a general
  quantization-accuracy benchmark.
- GGUF loading uses unmodified `vllm-gguf-plugin` 0.0.5, upstream commit
  `e2b8ad532b8b5ea175100202c30430c1d2b5e6a8`, through public vLLM registries.
  Its default entrypoint (which patches engine configuration) is never invoked.
  The test asserts the relevant EngineArgs methods retain identity. HF model
  configuration/tokenizer sidecars are still required; arbitrary GGUFs and other
  inference engines are not certified by this result.
- Rust admission reservations account for shared active native banks and reject
  excess demand before generation. GPU eviction remains Rust-owned.
- HTTP control drains requests and activates only after every worker confirms
  the same catalog digest. Replacement succeeds; withdrawal returns HTTP 503.
  A failed/mixed refresh keeps admission closed.
- Private preparation resolves **every** selected record/revision and rechecks
  approval after compilation and on cache hits. The protocol fixture verifies
  three-record delivery, cache reuse, denied reuse and revocation during compile.
  This fixture uses a stub compiler and is not live Aimee authorization evidence.

## Concurrent memory pressure

512 logical requests, eight clients, alternating two publications, each holding
three facts. Per-GPU native budget is 9,551,872 bytes: only one publication fits.
All 512 answers contain the correct code, project and drink. Runtime is
182.946 seconds; median end-to-end logical request latency, **including retries**,
is 2,156.484 ms. These repeated fixtures test operational isolation and pressure,
not 512 independent knowledge questions or representative throughput.

The initial client generated 18,244 HTTP 429 responses with aggressive fixed
polling. No logical request exhausted its retry budget. Subsequent code adds
`Retry-After: 1` and bounded exponential backoff. Preserve the first run as measured;
do not silently substitute the improved retry policy into its protocol.

## Preliminary paired HTTP probe

Same three records, supplied either natively or as system-message text. Five
alternating measured trials per condition after shape warmup, deterministic
sampling, TP2, eager execution, prefix caching disabled, context limit 2,048.
Each condition answered the code correctly in all five trials.

| Prior conversation turns | Native median ms | Text median ms | Native input tokens | Text input tokens |
|---:|---:|---:|---:|---:|
| 0 | 253.366 | 296.585 | 26 | 79 |
| 16 | 339.861 | 394.588 | 330 | 383 |
| 48 | 618.042 | 707.773 | 938 | 991 |

53 input/context tokens are avoided on each request. This is a small synthetic
probe, with concurrent host image-building activity: it is not an isolated
performance certification, production economics estimate, or microsecond
application measurement. End-to-end latency includes generation and HTTP.

## Lifecycle and distribution

The private supervisor follows the existing Aimee publication feed, starts
serving with admission paused, prepares approved records and coordinates catalog
activation. Feed failure stops its owned server. Poisoned admission triggers a
bounded full-session restart; fresh publication approval is required again.
Protocol/unit tests cover these boundaries. Recovery still needs GPU cancellation
and real authenticated-feed fault injection before external preview.

The signed Rust launcher now accepts a signed, digest-pinned OCI descriptor
(`runtime/image.json`) and invokes Podman without mounting account credentials.
The compiled package and GPU image have been tested separately. A fully signed
clean-machine installation, hosted artifact delivery, update and rollback against
that deployment have **not** passed yet. Release gates remain closed.

## Remaining release gates

- Deployment hostname, authenticated Aimee publication/preparation service,
  remote prepared-artifact delivery and automatic trusted selection per request.
- Release registry/origin and signing authority, model/license redistribution
  checks, signed clean-machine install/upgrade/rollback.
- Broader quantization parity; isolated cold/warm latency, TTFT/decode and sustained
  workloads; total GPU allocator accounting, not only bank payloads.
- Real feed expiry/revocation/disconnect and GPU cancellation/restart tests.
- Host residency is currently catalog-wide RAM admission. Demand-loaded disk
  working sets are not implemented by this serving change.
- Current certified binary geometry is Gemma TP2 on gfx1100, context 2,048 and
  batch-token limit 256. Other model/device profiles need their own binary banks.

The first container build exhausted VFS storage through duplicated layers;
overlay storage resolved it. A directory device mount failed; explicit render
nodes resolved it. The first host unit-test invocation lacked its MPI library
path; the corrected invocation passed. Retain these logs with the successful
runs. Container execution itself does not require that host-library workaround.

The first quantized **HTTP CLI** run also failed: `--model-weights` is not exposed
by upstream's CLI although its Python API accepts `model_weights`. The registered
loader now receives `gguf_weights` through `--model-loader-extra-config` and uses
an instance-local model-config copy. No upstream method replacement was used to
resolve this. Preserve the failed run separately from the subsequent HTTP test.

## Final compiled GGUF HTTP container

The corrected CLI and compiled client (wheel build r8) passed **128/128** further
three-record requests through the ordinary HTTP endpoint, eight concurrent clients,
again with only one bank fitting per GPU. All logical requests completed;
238 overload responses were retried using Retry-After/backoff. Runtime was
57.100 seconds and median latency including retries was 2,461.857 ms. This is
another repeated serving-isolation probe, not an independent knowledge benchmark
or a matched BF16/Q8 speed comparison. The client/backoff protocols differ from
the 512-request run, so their rejection counts are not a controlled comparison.

Final private local image configuration ID:
`55021b9128cd400557a0baa13896b083f8017bbbb3232aef59d4af32b217684d`.
This is not a published registry manifest digest. Build-context, wheel and image
identities plus raw results are under `artifacts/vllm-release-20260925/`; earlier
r4 artifacts are retained separately from final r5 artifacts.
