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

The completed AMD matrix below is for the preceding wheel
`eb911584b455b042b3baee0c681e708f2dfda8bf59d4583814b2d2707a52615c`.
The only change in the current wheel is the Rust selection broker's lease
renewal after a publication refresh; its inference modules and native library
are byte-identical. An exact-wheel repeat is queued after the live revision
check. The AMD matrix uses two RX 7900 XTX cards, unmodified vLLM
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

The Qwen native and empty matrix medians were 31.74 s and 3.52 s; the Gemma
12B medians were 13.45 s and 1.69 s; the Gemma 26B medians were 12.66 s
and 2.14 s. These arms
generate different answers and are not a native-versus-text latency
comparison. The model's first startup included a long compile and JIT warmup;
the report below records startup separately from warm-request measurements.

The RTX 5080 remains occupied by a separate workload. A smoke run of the
current exact candidate is queued for when it becomes available. Earlier candidates
passed installed-wheel Gemma V2 tests on that GPU, but those runs do not
substitute for an exact-candidate result.

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

The paired option test below also used the preceding wheel. The current wheel
has the same inference code and will be measured again. It used Gemma 4 12B
on AMD. Each condition started a fresh
installed-wheel server, warmed one native and one empty request, then
alternated six of each. All 72 scored answers were correct. Every condition
generated 186 completion tokens across its 12 measured, sequential requests.
The table separates startup from request time; VRAM is the sampled peak across
both cards, not an allocation trace.

| Configuration | Startup s | Native TTFT ms | Native full s | Empty TTFT ms | Empty full s | Requests/s | Peak VRAM MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Eager V1 | 140 | 867 | 9.49 | 783 | 1.42 | 0.183 | 41,567 |
| Prefix V1 | 75 | 523 | 9.15 | 453 | 1.09 | 0.196 | 41,566 |
| Async V1 | 74 | 981 | 9.61 | 980 | 1.61 | 0.176 | 41,566 |
| Piecewise V1 | 185 | 907 | 9.89 | 1,223 | 2.02 | 0.147 | 41,416 |
| Eager V2 | 84 | 860 | 9.43 | 803 | 1.44 | 0.183 | 41,674 |
| Prefix + async + piecewise V2 | 197 | 630 | 9.08 | 633 | 1.26 | 0.188 | 41,037 |

TTFT and full response are medians. Requests/s is 12 divided by the measured
sequential interval; it is not a concurrent throughput benchmark. The prefix
condition showed a lower median TTFT than eager V1 and vLLM's aggregate
prefix-cache hit log reached 78.6%. The combined V2 log also reached 78.6%.
The other optional modes establish correctness here but no speedup. Fresh
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
not publish it.
