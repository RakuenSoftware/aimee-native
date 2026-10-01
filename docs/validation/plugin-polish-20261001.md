# vLLM plugin feature validation — 1 October 2026

This is a source and candidate-wheel validation record. The published signed
0.2.1 wheel is unchanged. The correct Proxmox GPU host is `192.168.1.253`;
an earlier attempt used `192.168.0.253` in the same `/23` subnet.

## Changes

The 0.2.2 candidate adds a trusted prefix-cache salt over recipient, full
catalogue digest and selected publication; a caller cannot choose this salt.
It permits optional asynchronous scheduling after recording a GPU completion
event for native attention, and optional model compilation with `NONE` or
`PIECEWISE` graph mode. Full native-attention graph capture is still rejected.
The V2 runner resolves request identities from the stable request-state slots
carried in attention metadata during forward, without patching vLLM. These
features default off and are enabled explicitly in serving configuration.

## Installed-wheel results

The test environment used unmodified vLLM 0.30.0, Gemma 4 12B GGUF Q8_0, one
RTX 5080, the installed 0.2.2 candidate and an authenticated live Aimee
service. The test asked for three facts supplied by the native publication and
interleaved arithmetic questions authorized with empty native memory.

| Configuration | Native correct | Empty correct | Observation |
| --- | ---: | ---: | --- |
| Baseline, eager | 2/2 | 3/3 | Installed-wheel control |
| Prefix cache | 8/8 | 9/9 | Correctness; logged hit rate remained 0% on these short prompts |
| Async scheduling | 8/8 | 9/9 | GPU completion ordering exercised |
| Compilation, graph `NONE` | 2/2 | 3/3 | vLLM compiled model segments |
| Compilation, graph `PIECEWISE` | 2/2 | 3/3 | vLLM logged actual graph capture |
| Prefix + async + piecewise, V1 | 8/8 | 8/8 | Four simultaneous clients, no admission retries |
| V2, eager | 2/2 | 3/3 | vLLM logged `Using V2 Model Runner` |
| Prefix + async + piecewise, V2 | 8/8 | 8/8 | Four simultaneous clients, no admission retries; vLLM logged V2 and actual piecewise capture |

In the V2 combined run, median full-response time was approximately 2.88 s
for native answers and 0.44 s for empty controls. These are end-to-end
generation times for different answers, not a native-vs-empty latency effect.
Neither prefix-cache acceleration nor an option-level throughput gain is
established by this matrix. The V1 combined run had approximately 3.09 s and
0.52 s medians respectively; the paired runs are too small and not controlled
enough for a speedup claim.

A separate V2 repeated-prompt probe sent a 139-token native question four
times and a 141-token empty question twice. All six answers were correct and
vLLM logged a 61.1% prefix-cache hit rate. The API did not return a per-request
cached-token count, so that aggregate log establishes reuse but not a measured
per-request token saving or speedup. The probe did not use identical text under
two different banks; live cross-revision isolation remains to be tested.

A separate V1 lifecycle run kept a native stream open for 129 events, waited
for that stream before a catalogue refresh, then confirmed another native
answer. Withdrawal was followed by an authorized empty response. That run
did **not** install a changed catalogue revision, so a live revision-isolation
claim still needs a replacement test. Local tests cover changed cache namespace
and pin retention after a replacement.

An initial combined V2 run stopped at HTTP 503 before scoring because the
selection broker timed out connecting to Aimee through the test relay. The
broker recorded `Connect: operation timed out`; an immediate retry passed all
16 requests. Similar transient service-selection failures occurred in earlier
individual-option probes. They are availability observations, not incorrect
native answers, and should be investigated before release.

The two RX 7900 XTX devices are occupied by an existing continual-routing
experiment in CT101. The AMD Gemma 12B/26B and Qwen 27B installed-wheel
matrix is still pending; that experiment must finish before claiming it.

## Candidate and remaining gates

The candidate wheel is built with CPython 3.12 and a Rust launcher linked
against Ubuntu 22.04's glibc 2.35. The first candidate launcher was linked
against glibc 2.39 and could not start in the AMD Ubuntu 22.04 container; it
was rebuilt. The native library is unchanged from the validated 0.2.1 build.
The wheel's packaging and RECORD audit passes. Test output and server logs
remain on the GPU host under
`/var/lib/aimee-large-release-validation/plugin-polish-20261001/`;
credentials and model files are not copied into this repository.

The final cleaned candidate has SHA-256
`b6f852d28a85be972eed8f6a04d77f0b1528b9f9245b0784438d0aaeefceda9b`.
Its RTX 5080 V2 eager probe passed two native answers, empty controls and a
forced restart; the post-restart native answer was correct. Eleven focused
CLI, cache-identity, request-identity and GPU-ownership tests pass in the
Python 3.12 test environment.

The final cleaned wheel also passed the V2 combined matrix with four clients:
8/8 native and 8/8 empty answers, zero admission retries, and vLLM-confirmed
piecewise graph capture. Median full-response times were approximately 3.03 s
and 0.46 s respectively in that run.

Before publication, run the Gemma 12B/26B and Qwen 27B matrix on the two RX
7900 XTXs. Exercise an actual changed publication while old requests are active
and verify that the trusted salt isolates revisions. Record
startup/JIT time, throughput, first-token time and GPU memory for paired
option-level comparisons. Do not claim these optimizations improve speed until
those comparisons are measured.
