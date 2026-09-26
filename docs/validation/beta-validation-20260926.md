# Beta load, connected Aimee checks and remaining gates

The exact release-5 runtime passed 2,048/2,048 concurrent pressure answers with
eight clients. The 10-MiB per-rank native budget fits only one of two complete
three-record banks. Both ranks completed 144 uploads and 143 evictions through
the concurrency stage; resident payload stayed at 9,191,424 bytes and recorded
peak payload was 9,551,872 bytes. No selected record was dropped.

There were 2,534 HTTP 429 retry events. Every logical request eventually passed,
but this is consequential backpressure, not a zero-error first-attempt result.
Latency including retries was median 1.346 s, p95 5.038 s, p99 7.364 s. These
figures describe deliberate memory pressure, not idle response latency or an SLA.

The cgroup peaked at 27,923,517,440 bytes against its 51,539,607,552-byte limit.
Current cgroup use fell from 18.65 GB after model load to 16.88 GB after streaming.
Worker RSS also fell; native mapped-payload RSS was zero after transfer. This
run shows no retained growth in these observations, not an indefinite soak or a
proof against every leak. The same run also passed its 72-answer matched matrix
and 40 streaming answers.

The normal installed signed client on CT110 then completed 64/64 answers against
the real enrolled Aimee account's approved canaries, including its automatic
selection/delivery path. Median whole-response latency was 1.738 s, p95 4.354 s,
p99 7.614 s. It supplied no caller-selected publication IDs. This is the current
live path, not a fresh source-update benchmark. The earlier live source-revision,
authorization, disconnection and process-recovery evidence remains applicable to
the unchanged authority/compiler services and is retained in native-live-release-
20260926.md; this new run does not re-label those observations as new measurements.

[Original evidence](artifacts/beta-validation-20260926/) includes per-request retry
counts, full measurements, cgroup/device samples, live answers and hashes.
[Beta instructions](../../distribution/beta/README.md) document the exact profile,
installation/update/rollback workflow and measured limits. Public distribution
source/notice fulfillment remains an explicit gate in REDISTRIBUTION.md. No
public-release clearance or external publication is asserted.

A separate 8,192-token SWE learning configuration initially failed because the
release's compiled kernel bank only covered 2,048-token block-table geometry.
The runtime correctly rejected the unsupported profile. Extended compiled kernels
are being validated against dense references on both GPUs before scoring any
learning attempts; this does not change the signed release profile.

The extended profile passed eight binary-kernel/dense-reference comparisons across
both GPUs at 32/8,000 text positions plus native memory. The real-model preflight
then preserved an in-flight old answer (38491), returned the replacement (77283)
after refresh, rejected requests after withdrawal, rejected stale-generation
refresh, and restored the replacement after valid refresh. It ended with zero
native resident payload on both ranks. These are synthetic local publication
controls, separate from the real Aimee account run. The official SWE grader also
passed a trusted reference-patch calibration, excluded from model scores.
