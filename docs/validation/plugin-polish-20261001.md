# vLLM plugin 0.2.2 release-candidate validation — 1 October 2026

The signed 0.2.1 preview remains the published version. The current audited
0.2.2 candidate wheel has SHA-256
`ff069f26ff20316e91576e3f901275b41e74599b5c2b73b5f307eb297fa9d46e`.
It is an installed-wheel validation against a live, authenticated Aimee canary,
not a claim that all vLLM versions, models, GPUs or workloads are certified.
The wheel contains no model weights, runtime image, private encoder source or
credentials. The correct Proxmox GPU host is `192.168.1.253`.

## What changed

The candidate adds a server-controlled prefix-cache identity derived from the
recipient, full catalogue digest and selected publication. Callers cannot
choose that identity. Optional asynchronous scheduling waits for GPU completion
before releasing a native bank. Optional model compilation supports `NONE` and
`PIECEWISE` graph modes; full native-attention graph capture remains unsupported.
The V2 runner uses request-state slots from vLLM attention metadata to associate
native banks with requests, without patching vLLM.

vLLM 0.30's hybrid V2 model state does not expose those slots during live
attention. The plugin rejects that unsafe combination with a configuration
error. Qwen3.8 27B therefore uses the V1 runner; Gemma 4 12B and 26B use V2.
Native memory remains available with Qwen's V1 runner. This is a runner limit,
not a model-family or GPU limitation.

## Correctness matrix

The completed matrix uses the current audited wheel on two RX 7900 XTX cards,
unmodified vLLM
`0.30.0+rocm723`, installed 0.2.2 wheel, authenticated live Aimee and a canary
publication. Each probe starts with an authorized empty-memory arithmetic
request, asks for three values carried by native memory four times, and
interleaves empty-memory controls. Each matrix sends eight native and eight
empty requests through four simultaneous clients. The scorer checks answer
content and admission retries, not only HTTP status.

| Model | Runner | Probe | Four-client native | Four-client empty | Retries |
| --- | --- | ---: | ---: | ---: | ---: |
| Qwen3.8 27B | V1 | 4/4 | 8/8 | 8/8 | 0 |
| Gemma 4 12B | V2 | 4/4 | 8/8 | 8/8 | 0 |
| Gemma 4 26B | V2 | 4/4 | 8/8 | 8/8 | 0 |

The native and empty response medians respectively were 31.67 s and 3.33 s
for Qwen, 12.99 s and 1.61 s for Gemma 12B, and 12.98 s and 2.11 s for
Gemma 26B. These arms generate different answers and are not a
native-versus-text latency comparison. Startup, compile and JIT costs are
measured separately below.

The first exact-wheel Gemma 26B startup stopped before serving a request when
the host logged an RX 7900 XTX SDMA timeout and GPU reset. A small PyTorch
allocation and sum then passed on both GPUs. The separate Gemma 26B retry
passed the probe and matrix above. The failed startup is retained as
infrastructure evidence and is not counted as an answer result.

The preceding wheel
`eb911584b455b042b3baee0c681e708f2dfda8bf59d4583814b2d2707a52615c`
also passed the three-model matrix, but its broker exposed the expired-lease
failure described below. The current wheel differs only in the Rust launcher
and wheel RECORD; the inference modules and native library are byte-identical.

The exact candidate also passed the RTX 5080 CUDA smoke with unmodified vLLM
`0.30.0`: Gemma 4 12B on V2 answered all four native-memory questions and
all five empty-memory controls correctly. The four native requests took
2.78–3.26 s end to end in this sequential canary run. This is an additional
backend check, not a CUDA performance distribution or a four-client CUDA
matrix.

## Availability, revision isolation and option performance

The earlier HTTP 503 selection failures came from a lab relay still targeting
the old authority address `192.168.0.45`. CT100 is currently at
`192.168.0.228`; the corrected relay and all three AMD clients passed
authenticated connection checks. The corrected Qwen probe and matrix had no
selection failure. This is a test-environment correction, not a product fix.

The first live-revision test on the preceding wheel held a native stream open
while a second question selected a different signed canary publication. The
catalogue digest changed, the old stream stayed correct, and 30/30 follow-up
requests were correct. The first replacement request nevertheless returned 503
after approximately 63 seconds, then a retry passed. The broker had obtained a
lease before waiting for the old stream to drain and tried to approve it after
expiration. The current wheel obtains fresh authority after the drain and
checks that the publication, authorized view, records, artifacts and local
prepared path are unchanged. Release staging requires a single successful
replacement attempt. In the fresh-client
repeat on the current wheel, the request began while the old stream was active,
the catalogue digest changed, and the replacement returned 200 on its first
attempt. The old stream and all 30 follow-up answers were correct. The
replacement took 65.95 seconds because activation still drains the old stream;
the test demonstrates safe ordered revision change, not simultaneous old- and
new-revision execution. It does not mutate authority records.

The paired option test below used the current wheel and Gemma 4 12B on AMD.
Each condition started a fresh
installed-wheel server, warmed one native and one empty request, then
alternated six of each. All 72 scored answers were correct. Every condition
generated 186 completion tokens across its 12 measured, sequential requests.
The table separates startup from request time; VRAM is the sampled peak across
both cards, not an allocation trace.

| Configuration | Startup s | Native TTFT ms | Native full s | Empty TTFT ms | Empty full s | Requests/s | Peak VRAM MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Eager V1 | 102 | 868 | 9.51 | 780 | 1.42 | 0.183 | 41,566 |
| Prefix V1 | 94 | 547 | 9.22 | 453 | 1.10 | 0.194 | 41,566 |
| Async V1 | 88 | 981 | 9.64 | 979 | 1.61 | 0.178 | 41,565 |
| Piecewise V1 | 98 | 875 | 9.59 | 789 | 1.43 | 0.176 | 41,932 |
| Eager V2 | 80 | 889 | 9.42 | 789 | 1.42 | 0.185 | 41,674 |
| Prefix + async + piecewise V2 | 80 | 632 | 9.06 | 635 | 1.26 | 0.194 | 41,560 |

TTFT and full response are medians. Requests/s is 12 divided by the measured
sequential interval; it is not a concurrent throughput benchmark. The prefix
condition showed a lower median TTFT than eager V1 and vLLM's aggregate
prefix-cache hit log reached 78.6%. The combined V2 log also reached 78.6%.
The other optional modes establish correctness here but no clear speedup. Fresh
processes still reuse warmed disk and compilation caches, so startup differences
cannot be attributed to a setting. These small canary runs do not establish a
production latency distribution or general throughput improvement.

## Candidate integrity and history

The current wheel is 4,814,570 bytes and passed wheel-member and RECORD
audit. It targets CPython 3.12, vLLM `>=0.30.0,<0.31`, and CUDA/HIP backends
supported by the installed runtime. The Rust launcher was rebuilt under
Ubuntu 22.04 and requires glibc 2.34 at most. An earlier host build required
glibc 2.39 and could not start in the AMD container. The native library is
unchanged from the validated 0.2.1 build. Twenty-two Rust launcher tests and
seven focused request-state and hybrid-runner tests pass in the installed
environment. Failed interim candidates remain in the host evidence directory:
the first hybrid V2 attempt lacked live request slots, and the next V1 guard
looked up V2-only state during startup. Those failures led to the explicit
hybrid V2 rejection and corrected V1 short circuit in this candidate.

The GPU-host record is under
`/var/lib/aimee-large-release-validation/plugin-polish-20261001/`.
Credentials, model files and private memory are not copied into this repository.
The release staging script signs a tested candidate into a non-web directory
only after all matrix, CUDA, option and live-revision gates pass; staging does
not publish it. All those gates passed for the exact wheel. The wheel and
manifest were staged and their Ed25519 signatures verified, including a
separate verification after staging. The staged wheel SHA-256 is
`ff069f26ff20316e91576e3f901275b41e74599b5c2b73b5f307eb297fa9d46e`;
the staged manifest SHA-256 is
`0fcab09a03a536b896b3176a532911b2c486de370c793629de70bc218703909d`.
The stage is still private and unpublished.

## Reproducible evidence

The [wheel audit](artifacts/plugin-polish-20261001/wheel-audit-lease-r1-ubuntu.json)
identifies the exact tested artifact. Installed-wheel [Qwen probe](artifacts/plugin-polish-20261001/qwen27-amd-probe-r9.json)
and [matrix](artifacts/plugin-polish-20261001/qwen27-amd-matrix-r9.json),
[Gemma 12B probe](artifacts/plugin-polish-20261001/gemma12-amd-probe-r9.json)
and [matrix](artifacts/plugin-polish-20261001/gemma12-amd-matrix-r9.json),
and [Gemma 26B retry probe](artifacts/plugin-polish-20261001/gemma26-amd-probe-r9b.json)
and [matrix](artifacts/plugin-polish-20261001/gemma26-amd-matrix-r9b.json)
contain the scored answers. The [initial 26B startup failure](artifacts/plugin-polish-20261001/gemma26-amd-probe-r9.json)
and [GPU reset log excerpt](artifacts/plugin-polish-20261001/gemma26-r9-gpu-reset.txt)
are retained alongside the successful retry. The [live revision run](artifacts/plugin-polish-20261001/live-revision-amd-lease-r1.json)
records the single successful replacement attempt. The
[option measurements](artifacts/plugin-polish-20261001/perf-amd-lease-r1-r2/)
include per-request JSONL, condition summaries and prefix-cache log excerpts.
The [RTX 5080 probe](artifacts/plugin-polish-20261001/gemma12-5080-lease-r1-probe.json)
contains its scored answers. The [staging record](artifacts/plugin-polish-20261001/release-stage-lease-r1-staging.json)
and [manifest](artifacts/plugin-polish-20261001/release-stage-lease-r1-manifest.json)
identify the signed, unpublished release candidate.
