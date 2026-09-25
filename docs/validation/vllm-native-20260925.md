# Fork-free native memory on vLLM — 2026-09-25

## Outcome

Aimee native memory runs through unmodified vLLM using an external attention
backend and a configured worker subclass. No vLLM fork, source patch, or runtime
monkey-patch was used. The installed wheel's 3,146 SHA-256-recorded files were
checked: zero modifications. The private plugin owns all integration code.

This is an end-to-end correctness result, not production latency certification
or a completed customer distribution. The compiled Rust client exposes only four
store ABI functions and does not link LibTorch or ship preparation entry points.

## Environment and reproducibility

- CT101 on the authorized .253 host; both RX7900XTX 24GB GPUs; TP2.
- Gemma4 12B BF16 checkpoint, Hugging Face safetensors (22.28GiB checkpoint).
- Official vLLM0.30.0+rocm723 wheel, source revision
  `ced6857afa0ea7b2e3f0846a62e1394e90f15607`; Python3.12.14,
  Torch2.12.0+git6bbd260, Triton3.7.1.
- The wheel needed MPI C++ libraries absent from Debian13's MPI5 package.
  Debian libopenmpi3 4.1.4-3+b1 was extracted into an isolated library directory.
- ROCm shared libraries were resolved from the lab's existing working ROCm7.2
  stack through a separate SONAME symlink directory, excluding Torch/c10/shm/gomp
  libraries. This is not a clean matched ROCm7.2.3 deployment image; clean-machine
  compatibility remains a release gate. No upstream package files were edited.
- V1 runner, eager execution, prefix caching and async scheduling disabled;
  max context2048, batch token budget256, max sequences4, GPU utilization0.75.
  Text-only; multimodal prompt limits0. No Qwen run.

Source tests are in `distribution/vllm/tests`. `prepare_gemma_fixture.py` creates
synthetic publications using the existing private publisher; it is not included
in the client package and does not establish an Aimee authorization service.

## Evidence

Raw logs and JSON: [artifacts](artifacts/vllm-native-20260925/).

| Check | Result |
|---|---|
| GPU kernel against independent dense reference | 12 combinations, 3 differently sized requests each; all pass |
| Head widths / local text windows / softcaps | 64,256,512 / disabled,3 / disabled,2 |
| Maximum absolute BF16 difference | 0.0009765625 |
| Request reorder, retirement, invalid selection, missing mapping | Pass |
| Resumed request after alias replacement/withdrawal | Original revision retained; new withdrawn selection rejected |
| Full-model conflicting memory selection | Alpha68731, beta94268, alpha68731, all correct |
| No-memory control | Does not know the private vault code |
| Prompt token count | 26 in every condition |
| Three-record composition | Both publications return all three correct facts |
| Live catalog alias replacement | Both TP workers refresh; alpha subsequently returns beta's three facts |
| OpenAI-compatible HTTP chat endpoint | Both selected memories correct;26 prompt tokens each |
| Installer tests | 7 passed |
| Packaging/signature tests | 2 passed |
| Rust client export audit | Four allowed exports;681,960 bytes in tested build |

Every publication contains three synthetic records. Preparation encoded all of
these together: alpha53 native positions, beta51, with all48 layer banks. The
composition result is not a one-record retrieval masquerading as a multi-record
test. It establishes integration of a prepared three-record working set; it does
not establish arbitrary combinations of independently encoded banks.

The first full-model request batch took10.86seconds in the expanded run,
including first-use Triton compilation and decoding. This number is not native
application latency. Cold/warm attention and end-to-end performance need separate
measurements before comparisons with the previous optimized runtime.

## Mechanics and limits (private)

Rust admits immutable prepared stores and owns host buffers. Each worker consumes
its TP head shard, uploads on first selection, and caches GPU banks. Native
attention reads these separately from the paged text KV cache. Text prompt tokens,
positions and cache allocation remain unchanged. Metadata follows actual reordered
scheduler request IDs, not assumed input order. Request pins retain the exact
publication through preemption; explicit refresh changes future requests.

The refresh test runs at a quiescent boundary. Distributed atomic refresh and
immediate revocation of active requests are not implemented. Prefix cache,
CUDA/HIP graphs, speculative decoding, pipeline parallelism and multimodal native
attention are not certified; unsupported configurations are rejected.

The current catalog is admitted into RAM and selected banks remain on GPU. A
bounded production device cache and publication feed are still required. This
result does not certify all architectures or GGUF quantizations. It also does
not supersede the paper's larger benchmark sets: it validates the new serving
integration against deliberately discriminating synthetic fixtures.

## Distribution status

The installer now targets vLLM and the private `aimee-vllm --config ...` command
works. The old llama.cpp patch/provider are abandoned. Hosted preparation endpoint
and authoritative publication feed remain unconfigured. The private source
plugin/Triton kernel must not be publicly shipped; compiled/protected packaging,
dependency image, release signing/origin and actual production evidence gates
remain necessary before an external preview.
