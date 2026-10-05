# Dedicated model plugins and quantized native serving

Date: 4 October 2026. Host: `192.168.1.253`; GPU: NVIDIA RTX 5080,
16 GiB, compute capability 12.0. This report extends the completed
[BF16 repair](native-memory-completion-20261004.md) and
[INT8 research retest](native-memory-int8-20261004.md). Those historical bytes
and failed observations remain unchanged.

## Release boundary

The candidate release contains three separately installable packages, version
0.3.0 build 1, for Linux x86-64 / CPython 3.12:

| Model | Package | Dedicated Rust source |
|---|---|---|
| Gemma4 12B | `aimee-gemma4-12b` | `src/model_adapters/gemma4_12b.rs` |
| Gemma4 26B A4B | `aimee-gemma4-26b` | `src/model_adapters/gemma4_26b.rs` |
| Qwen 3.8 27B | `aimee-qwen3-8-27b` | `src/model_adapters/qwen3_8_27b.rs` |

Each release library exports one model adapter. Selecting multiple release
features fails compilation. Each wheel has its own module namespace, console
command and vLLM entry point; co-installation does not overwrite another plugin.
The installed-plugin probe admits the three matching configurations and rejects
all six cross-model combinations. The development source can exercise all three
entry points but is not the shipped plugin. The old shared-plugin build commands
and generic Python model compilers are retired from this release path.

Rust owns each model's accepted architecture, layer/memory geometry and live
position mapping. Admission binds the exact checkpoint and arithmetic identity
at the frontend and worker. Gemma checkpoint/profile comparisons, publication
serialization and checksums execute in Rust. Qwen's adapter additionally owns recurrent layout,
initialization/reinitialization policy and private-slot validation. Common byte
I/O, transport and ABI allocation are infrastructure. Model-specific decisions
are not selected from a generic model implementation.

Python remains the vLLM registration/lifecycle bridge and observes runtime tensors.
Tensor copies use Torch; GPU attention uses the pinned runtime/Triton interfaces.
Cython compiles the bridge for packaging; it does not make that code Rust. The
release inventory retains this distinction. Gemma memory is observed from the
stock quantized model at ordinary positions `0..M-1`; its adapter starts the live
conversation at `M`. No negative positions, reflected rotary caches or changes to
installed Gemma/vLLM source are part of the release. Legacy negative-position
Gemma publications require re-encoding.

## Executed checks

The current Rust/ABI suite passes **32 tests** in the pinned private build
snapshot with `--no-default-features --features vllm-portable`. The serving bridge suite passes
**79 tests without skips**, including actual ABI publication readback, rejected
model/precision bindings, private recurrent seeding and CUDA attention comparisons
against dense reference results. The offline audit/regression suite passes
**43 tests** (`python3 -m unittest discover -s benchmarks/native_addressing
-p 'test_*.py'`). These are separate from full-model execution results.

| Installed plugin / checkpoint | Recall matrix | Scope |
|---|---:|---|
| Gemma4 12B Q4_K_M | 36/36 | Six frozen direct/paraphrase questions, native and matched text, 0/16/48 prior turns |
| Gemma4 26B A4B Q3_K_M | 36/36 | Same attention-family matrix, dedicated 26B plugin |
| Qwen 3.8 27B dynamic-activation FP8 | 324/324 | 48 original tasks plus six held-out phrasings, native/text × 0/16/48 turns |

The Qwen operational suite also passes unauthorized access (401), altered system
context (400), withdrawal (503), rejected BF16-as-FP8 refresh (503), exact
catalogue recovery and the native 7391 canary. Its two forced 40-token
continuations exercise mechanical preemption: one actual preemption and 144
layer-seed events were observed. They are not scored QA.

Independent auditors reconstruct source/request bindings, coverage and exact
scores. The instruction profile, canonical source facts and selections remain
frozen. The six Qwen held-out phrasings include descriptive-noun changes and an
unknown entity; source facts were not supplemented with answer aliases. These
finite public-fixture results certify the executed profiles, not arbitrary
models, quantizations or organization-private authorization.

Gemma 12B's Q4 checkpoint was produced from its original BF16 weights through a
streamed F16 GGUF intermediate. The final file is 7,024.34 MiB (mixed Q4_K_M,
4.95 bits/weight). Matching stock Q4 engine capture observes all 48 layers and
46 memory tokens; published K/V occupy 15,826,944 bytes. Load takes 96.900 seconds;
actual encoding plus publication takes 1.430 seconds. The passing r6 consumer's
host cgroup peaks at **10.851 GiB**, under its 12 GiB cap. Its post-matrix worker snapshot records **1.966 GiB RSS**, a **9.658 GiB RSS
high-water mark** and **8.974 GiB GPU driver usage**. Cgroup memory includes
file cache and staging; it is distinct from the worker RSS measurements.

Gemma 26B's original BF16 files are checked against local cached download metadata.
Its independently derived Q3_K_M file is 13,286,734,912 bytes (12,656.13 MiB,
4.21 bits/weight); standard quantizer fallback affects 60 of 658 tensors. This
is a mixed Q3_K_M profile. Its capture/consumer runs under a 16 GiB host cgroup,
whose peak reaches the cap, with no CPU matrix offload. The post-matrix worker
snapshot records 2.182 GiB RSS, a 14.881 GiB RSS high-water mark and 14.054 GiB
GPU driver usage. Quantization uses an 8 GiB
CPU cgroup and a 1,024 MiB quantizer buffer. Neither Gemma checkpoint was
requantized from Q8. Tool, original-source and derived-weight hashes are retained.

## Qwen operations and deployment

The installed-plugin deployment controller passes all six gates: initial native
canary/refresh, full 324-case quality, independent audit, operational controls,
real rollback and final restoration. Rollback starts the immutable previous
`fp8-20261004-r5` release and verifies its native answer; restoration starts
`model-plugins-20261004-r1` and verifies readiness plus two native canaries.
Populated process-lifetime host counters survive publication refresh unchanged.

The final service is **active, enabled and configured with `Restart=on-failure`**;
the JIT mount is enabled. The temporary validation restart override is removed.
An independent request from the development machine returns HTTP 200 and the
native answer `7391`; unauthenticated model listing returns 401. The control socket
and credential file both have mode 0600. Only the final engine remains on the
5080; temporary model validation services are inactive.

The owned environment is `/opt/aimee-native-serving`; the authenticated private
endpoint is `192.168.1.253:18950`. The publisher control socket is
`/run/aimee-native-serving/control.sock`, mode 0600. Credentials remain solely in
a mode-0600 host file. Public canary publications do not grant access to private
organization memory: recipient/resource/revision/expiry/withdrawal policy remains
required through Aimee's authoritative publication path.

The deployment has immutable releases, its own Python virtual environment and
NAS-backed weights/prefixes. It depends on the existing pinned CUDA package
installation and Python base through read-only paths. Runtime versions are
vLLM 0.30.0, Torch 2.13.0+cu130 and Triton 3.7.1. Gemma uses the pinned upstream
GGUF loader 0.0.5+triton, included alongside the candidates and selected by the
`gguf` installation extra; this is not another Aimee adapter.

The Qwen FP8 profile uses 18 GiB matrix CPU offload with pinned copies and UVA
disabled, a 56 GiB host cap and no swap. Attention/convolution state is BF16;
recurrent state is FP32. Native host/device budgets are 8 GiB / 512 MiB.
Eager synchronous V1 execution, text-only inputs, no prefix caching and an
11-block KV override bound the tests; this is a two-request operational service,
not a throughput claim. Memory state is prepared offline from the exact consumer
checkpoint/arithmetic. Serving consumes already prepared state. Recurrent seeds
initialize private slots on prefill and zero-token recomputation; ordinary decode
avoids re-copying those GPU slots.

The final dedicated Qwen plugin's 48 frozen-task medians are 7.027 / 7.086 /
10.147 seconds for native calls at 0/16/48 prior turns, versus 6.927 / 7.008 /
9.949 for matched text. The six held-out native medians are 7.065 / 7.089 /
10.334 seconds. These describe this bounded offloaded serving configuration.

## Performance and retained failures

The earlier serving performance experiment retains four separate 24/24 quality
cohorts. With 22 GiB pageable CPU offload, short native calls take 9.78–9.99 seconds
and long calls 14.13–14.51. At 18 GiB pageable, short calls take 8.26/9.14 seconds
and long calls 12.00/**16.26** seconds, including the regression. Pinned offload
with UVA disabled gives 7.117/7.187 and 10.301/10.320 seconds. Avoiding decode-time
seed copies gives 7.049/6.960 and 10.098/10.050, versus matched text
6.998/6.911 and 9.907/9.924. Each cell has only two warm repetitions after its
first call; cache coldness and pure causal precision effects are not established.

Separate CUDA-event attention measurements use an 82-position native bank:
32 text positions measure 30.256 μs without it and 30.896 μs with it;
1,024 text positions measure 88.736 / 95.632 μs. Each cell has 100 repetitions.
Events include dispatch/queue behavior; these are not end-to-end request times.
Host-stage counters measure process-lifetime wall time and may overlap; they
cannot be summed into isolated GPU execution cost. Refresh preserves them.
A repeated FP8 prefix is bit-identical across the earlier and tuned offload
settings; all 18 durable complete prefixes pass byte/hash integrity checks.

Retained unsuccessful attempts include online FP8 meta-tensor offload, capture
scheduler cleanup, no-exec JIT and read-only usage paths, GGUF derived-frequency
mapping, insufficient KV budget, the removed experimental negative-position
Gemma capture, compiled-CLI `-m` launch, staging-path errors and Gemma 26B Q8 load
OOM. The Q8 loader's CPU offload moved only 0.02 GiB before lazy MoE weight
materialization; the 16 GiB GPU could not load that profile. It is not a scored
answer failure and does not establish Q8 execution coverage. Installed upstream
source and rotary caches were not modified to force it through.

The earlier **432/432 INT8** result remains a rowwise-INT8 research profile with
BF16 CUDA arithmetic, not vLLM W8A8 kernels. The
[vLLM INT8 documentation](https://docs.vllm.ai/en/latest/features/quantization/llm_compressor/int8_w8a8/)
excludes Blackwell from that W8A8 profile. The actual FP8 execution reported here
is a separate quantization experiment. The historical implicit-alias failures,
unpromoted learned router and declined lossy native writes also remain separate.

## Reproducible artifacts

The [candidate directory](../../distribution/release/candidates/model-plugins-20261004/)
contains the three wheels, pinned GGUF dependency, symbol/RECORD audit and a
per-executable-member proof that metadata finalization preserved the tested code.
See [installation](../../distribution/vllm/MODEL_PLUGINS.md) and
[adapter ownership](../proposals/pending/model-dedicated-native-plugins.md).

The [public evidence directory](../../benchmarks/native_addressing/evidence/20261004-model-plugins-and-serving/)
contains `raw.tar.gz`, its archive metadata and the independent recheck. The
archive has **1,876 regular-file members**, including a manifest verifying all
1,875 other member hashes. Its SHA256 is
`a7fa3677b9640992ec2f77e2bc192821ca713adc1d2e0e58ac02f9ba6c7f1868`.
It retains executed source stages, private build inputs, runtime/configuration
metadata, package identity/code proofs, every retained attempt's available logs,
quality inputs/rows, performance cohorts and operational controls. A credential
scan passes; model weights, native tensor payloads and signing material are absent.

Re-running the auditors from archived source against archived inputs reproduces
both old/current Qwen 324/324 results and all four retained attention-family
36/36 runs, including the historical BF16/Q8 negative-position profile as a
separate superseded observation. The recheck verifies the actual preemption and
144 seed events, final canaries, exact configuration hash, active/enabled restart
policy and populated refresh-counter preservation. All 60 prior tracked evidence
files remain unchanged, as do the BF16 completion archive
`c2971757e5aff58eec198d11b0df00e8356a036277fa8d2d2ec80cc89e6b7721`
and INT8 archive
`a0dc29351465319b357f1770adc6d20db7b038dd4aaa1b61fda1aef568598e4e`.

No public package-index publication is recorded by this validation. Checkpoint,
private tensor and credential payloads are excluded from repository evidence.
