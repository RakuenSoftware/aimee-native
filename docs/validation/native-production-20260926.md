# Native distribution integration and certification, 2026-09-26

This follow-up implements the missing Aimee ingress bridge and tests the compiled
client beyond the earlier six-answer installation smoke check. Production
acceptance is not declared complete: the bridge is pushed but has not been
installed on the live Aimee frontend, and the non-lab release is not signed.

## Authenticated ingress

Aimee branch `feature/native-delivery-bridge`, commit
`ea17b8a5d`, adds a Linux Unix-socket bridge after the existing bearer,
certificate-grant and capability checks. Four endpoint patterns require
`CAP_MEMORY_READ`. The bridge forwards only the server-attested principal;
caller-supplied identity headers and credentials are not forwarded. It accepts
only the configured service UID, a private Unix socket, bounded requests and
bounded streamed responses. Native responses retain the frontend access log and
request ID, including the actual backend status. It explicitly closes the frontend connection after
a transfer, including partial transfers. No encoder is added to Aimee.

The new `cmd/aimee-native-delivery` in this repository owns the private listener.
It checks the peer's kernel credentials before reading the forwarded principal.
An operator-owned registry binds that principal to an existing recipient release
policy and preparation profile. Every request validates the current release via
Aimee's execution-policy implementation. Current recipient, model, template and
release identity are included in lease scope; preparation and final approval
also recheck selected records. Search permission alone is not an export grant.

The registry does not create grants or replace membership/revocation policy.
Deployment must connect the same current release used by the authoritative
publisher. See [the deployment contract](../../distribution/service/DEPLOYMENT.md).
The core frontend currently runs as UID 1000 in its container; the private
service's UID and socket ownership must match, including namespace translation.

Validation so far:

- Full Aimee server build on current `testing`, using GNU17 and the provisioned
  PostgreSQL development toolchain.
- API conformance: 379 documented endpoints routed; no undocumented routes.
- Route ordering, CLI route consistency and dispatch capability checks passed.
- Go package tests and native-publication race tests passed.
- Actual C bridge → Go Unix service tests passed for a current binding, immediate
  withdrawal/restoration, unknown/empty identity, malformed routes and insecure
  socket permissions. A separate 1 MiB segmented transfer preserved every byte
  and the backend HTTP 206 status through the actual C bridge. These use explicit
  temporary grants, not a live account.

The branch was pushed. GitHub's connector returned HTTP 403, “Resource not
accessible by integration,” when asked to create its draft PR. Git push worked.
No production deployment is inferred from that push.

## Resource telemetry

The private control socket now exposes `metrics`. Every configured worker must
respond; a missing rank is a failed measurement. Measurements include native
payload residency, mapped payload RSS, process RSS/high-water, Torch allocated
and reserved bytes/peaks, and driver free/total bytes. This is an explicit
control-plane operation, outside attention and ordinary request admission.

Torch allocation totals include model weights, model KV cache, native banks,
pointer tables and tracked temporaries. Driver use also includes allocations
outside Torch and other processes on that device. Per-worker RSS cannot simply
be summed as unique system RAM; the certification probe additionally records
cgroup current/peak/limit and device-use samples. Filesystem page cache is not
silently equated with mapped payload RSS.

## A streaming failure found and corrected

The r11 candidate passed all 72 BF16 matched matrix answers and 128 concurrent
pressure requests. The first streaming answer completed, but the next request
returned 503. A client closing after the engine's `[DONE]` frame could arrive
before ASGI's final empty body. Admission incorrectly treated that successful
completion as an unacknowledged GPU cancellation and poisoned the instance.

The new bounded SSE tracker requires a terminal finish reason for every requested
choice and the engine's exact `[DONE]` frame. Model text inside JSON cannot imitate
that acknowledgment. Partial streams, malformed/error frames and incomplete
multi-choice responses still retain reservations and require recovery. It does
not infer GPU cancellation acknowledgment from a client disconnect alone.

Four parser tests cover every split position in a terminal sequence, multi-choice
completion, model-text imitation, error/partial frames and parser limits. The
real Rust admission test additionally confirms that completion followed by a
client disconnect releases capacity, while a genuine interrupted stream stays
pinned. All seven admission tests pass. The compiled r15 wheel includes this fix.

The failed r11 run is retained as failure evidence; it is not relabeled as a
successful end-to-end certification. The replacement r12 image passed **592/592 answers**. After the dependency
remediation below, r13 independently repeated **592/592 answers**: 240 each on BF16 and Q8
(72 matched matrix answers, 128 concurrent pressure answers, 40 streaming answers
per profile), plus 112 matched Q8 answers with all 32 records active together.
Every single-, two- and three-fact wide-set query used the complete 32-record bank.
The bank identity contains all 32 canonical references and its payload hash is
recorded. This reconsumption test does not claim a new authorization or preparation
measurement. These remain synthetic engineering workloads, not population-level
knowledge accuracy.

The current r13 image configuration ID is
`87d4ee28688c4862d2fe0bb8980fd4375d91950155c6699736c47a2bb93fc8d6`.
The earlier r12 image was
`5243ee266c208bc11d8c5a23f3d9ead6edf6c15834ae32b70252946ed873fe3a`;
its reports are retained separately. The figures below describe r13.
It is not substituted for a registry manifest digest or a signed release ID.

| Profile | Matrix | Concurrent pressure | Streaming | 32-record bank |
|---|---:|---:|---:|---:|
| Gemma BF16 | 72/72 | 128/128 | 40/40 | — |
| Gemma Q8 | 72/72 | 128/128 | 40/40 | 112/112 |

Pressure produced 130 retryable 429 responses on BF16 and 141 on Q8, with every
request eventually answering correctly. Native payload residency peaked at
9,551,872 bytes per rank under a 10 MiB budget, with eviction/reload exercised.
Overall cgroup RAM peaked at 28,347,445,248 bytes for BF16 and 27,520,335,872 for
Q8, both below the enforced 48 GiB limit. Peak Torch reservation was approximately
16.65 GiB per rank, while end-of-run driver usage was approximately 17.5 GiB.
Those totals include much more than native-bank payload.

Streaming comparisons generated the same 14 completion tokens in every case.
Native prompts used 36 versus 89 tokens without preceding dialogue, and 948
versus 1,001 after 48 dialogue pairs: a persistent 53-token difference. The wide
bank saved **586 prompt tokens per answer**, using 30/36/42 native tokens versus
616/622/628 with the same 32 records as text.

| Profile | Prior dialogue pairs | Native median TTFT | Text median TTFT |
|---|---:|---:|---:|
| BF16 | 0 | 54.4 ms | 59.4 ms |
| BF16 | 48 | 425.6 ms | 423.7 ms |
| Q8 | 0 | 62.2 ms | 83.5 ms |
| Q8 | 48 | 626.4 ms | 626.3 ms |

Each timing cell contains ten observations. Full values, nearest-rank p95 and
completion/token counts are retained in `summary-r13.json`. TTFT includes HTTP,
scheduling, model prefill and activation when needed. It is not isolated memory
application, controlled cold-SSD latency, a production SLA or proof of a universal
speedup. The long-dialogue rows are effectively tied at this sample size.

## Isolated activation and attention dispatch

The shipped compiled consumer was also measured outside model generation on
rank 0 of a two-rank profile. This is the actual `PreparedStore.activate` path,
not a replacement implementation. Initial admission (including integrity checks)
is reported separately. No hash, file-open or verification was added to attention.

The three-record file occupies 18,239,700 bytes and materializes 9,551,872 GPU
bytes on this rank. The 32-record file occupies 201,627,944 bytes and materializes
105,611,264 GPU bytes. These are the current prepared artifacts, not claims about
an arbitrary text-to-memory compression ratio.

| Stage, median / p95 | Three records | 32 records |
|---|---:|---:|
| Verified OS-page-cache-cold activation, 20 trials | 26.7 / 27.7 ms | 122.4 / 130.2 ms |
| OS-page-cache-warm activation, 100 trials | 6.35 / 6.60 ms | 31.5 / 33.1 ms |
| Already-device-resident lookup, 100 trials | 0.54 / 0.60 µs | 0.54 / 0.69 µs |

Activation includes host tensor views, page faults where labeled, transfer and
GPU completion. The resident row is only the already-materialized bank lookup;
it does **not** measure a complete memory request, selection, attention or model
answer. Initial admission took 11.8 ms and 151.4 ms in one parent-process sample
respectively; these are not distributions. Preparation/compiler timings remain
in the earlier preparation reports and are excluded here.

The initial repeated-process eviction protocols failed their large-bank cold
precondition: thousands of file pages stayed resident after `DONTNEED`, including
a retry after flushing the file. Their reports are retained as failed measurement
attempts. The final protocol uses a fresh child process for each cold trial,
primes GPU allocation/transfer with unrelated zeros, and requires **zero** resident
file pages immediately before activation. Every warm trial requires all file
pages resident. Setup and conditioning are outside the timer. This establishes
OS-page-cache state, not cold SSD-controller state; these sequential stage
measurements are not a randomized whole-system native/text effect estimate.

Separate dispatch probes use the two shipped HIP kernel geometries with actual
native banks, one decode query position and 32 text positions. Each result is
checked against an independent dense attention reference before timing. Completed
wall-time medians (100 observations per condition) were:

| Head width | No native positions | 53 native positions | 586 native positions |
|---|---:|---:|---:|
| 256 | about 54 µs | 66.8 µs | 148.9 µs |
| 512 | about 54 µs | 70.2 µs | 213.3 µs |

These are one-layer dispatch/completion measurements, not whole-model decode.
Recorded GPU-event intervals can contain dispatch/queue gaps; they are not
represented as pure kernel execution time. Earlier probe labels claiming host
launch exclusion are superseded by that explicit interpretation. Use the final
`stage-timing-r13-r3` reports, retaining r1/r2 only as exploratory evidence.

The cold-activation microsecond target is **not met**. Resident reuse is cheap,
but current materialization and transfer of a new bank remain millisecond
operations. Those costs must stay explicit in release sizing and performance
claims; a sub-microsecond lookup does not make cold activation sub-microsecond.

## Dependency review

The target-specific Cargo graph includes 194 native-runtime dependencies and
150 launcher dependencies, with a notice found for each. The earlier missing
`r-efi` notices were for packages outside the Linux resolution. Notice collection
now follows reachable dependency edges and fails on an incomplete graph.
This is a notice inventory, not a blanket conclusion about all redistribution
obligations.

The candidate upgrades active Python imports to cryptography 50.0.1, PyJWT 2.15.0,
oauthlib 3.3.1, httplib2 0.32.0 and zipp 4.1.0. Public wheel hashes and versions
are locked; container context generation verifies the complete set, and the
image installs without consulting a package index. Superseded distro-package
metadata remains visible in the broad inventory. `active-imports-r11.json`
records which files Python 3.12 actually loads; the old versions must not be
mistaken for the selected runtime imports or silently deleted from the inventory.

Attempting setuptools 84.0.0 violated the pinned vLLM, Torch and LMCache dependency
ranges, so the candidate retains the supported 79.0.1. Its reported
[Unicode sdist exclusion advisory](https://github.com/pypa/setuptools/security/advisories/GHSA-h35f-9h28-mq5c)
affects source-distribution file selection. This build uses an explicit ASCII
module list, removes private source before wheel assembly and never ships or
publishes an sdist. That is a configuration-specific applicability assessment,
not a statement that the installed setuptools version is patched.

The [TorchScript crash report](https://github.com/pytorch/pytorch/issues/149623)
concerns scripting Python classes. Its minimal class example **still segfaults**
(exit 139) in the pinned candidate when executed in an isolated container; it is
not described as patched. The serving API accepts prompts, not supplied
Python classes; remote model code is disabled and model files are signed.
The installed flash-attention wheel contains neither of the advisory's training
`checkpoint.py`/`eval.py` modules. Its separate `flash_attn/models/llama.py` does
contain a `torch.load` call; that model loader is not the certified vLLM GGUF or
safetensors loader. The inventory and call locations are preserved rather than
claiming all unsafe deserialization has been removed. Neither Torch nor
flash-attention was independently upgraded away from the upstream matched runtime.
The broad scan still reports ten package matches, including superseded metadata,
build-only concerns and an unmaintained Rust build dependency.

Trivy 0.74.0 scanned all 591 Ubuntu packages. The first image produced 5,330
package/advisory entries (not unique vulnerabilities): 4,733 concerned
`linux-libc-dev` kernel headers. These are not a running kernel inside the image;
container host-kernel security is a separate deployment responsibility. The two
non-header high/critical entries were the same OpenSSL advisory against two
installed packages. They were not ignored.

Candidate r13 applies 71 Ubuntu package upgrades, including OpenSSL and glibc,
without changing the vendor GPU stack. Exact versions are recorded in
`distribution/container/os-packages.lock`; the final build recipe excludes
vendor source fragments from these updates. The follow-up scan has **no entries
with an available Ubuntu fix** and **no non-header high/critical entries**.
It still reports 4,072 entries: 3,865 against kernel headers and 207 medium/low
entries against other installed packages. The compressed raw scans and their
uncompressed SHA-256 values are retained. This is remediation evidence, not a
claim of zero vulnerabilities or complete host security.

The source-free context builder now rejects incomplete, extra, altered or
symlinked dependency wheels and malformed OS pins before creating its output.
Four context tests passed. Twenty-five client CPU tests passed with the actual
Rust library enabled, without skips. The known TorchScript crash and unresolved
medium/low findings remain explicit limitations of the upstream runtime; release
review must assess them against the supported text-only, signed-model serving
surface. No production security approval is fabricated.

Raw evidence is under [the artifact directory](artifacts/native-production-20260926/).

## Acceptance boundaries

The implementation commit is `bfa0a79` on `feature/native-distribution`. The
Aimee bridge is `ea17b8a5d` on `feature/native-delivery-bridge`; native preparation,
consumer, synchronization, distribution and test code remain in this repository.
Neither runtime is forked or patched.

| Workstream | Implemented and checked | Remaining release acceptance |
|---|---|---|
| 1. Cache/backpressure | Rust reservations/eviction, coordinated workers, pressure recovery, total process/cgroup/device telemetry | Customer-host sizing remains profile-specific. |
| 2. Authoritative publication | Existing Aimee authentication bridge, kernel-attested service identity, current release/recipient/model binding and denial tests | Install bridge/service against the live enrolled recipient and current publisher policy. |
| 3. Preparation/reuse | Actual private compiler, full selected-record sets, reusable preparation, approval-only and record-only fallback tests | Exercise the deployed authoritative gateway with that live binding. |
| 4. Protected package | Source-free consumer, hosted preparation, target license inventories, locked OS/Python remediation, negative packaging checks | Final redistribution/security review retains known upstream limitations. |
| 5. Certification | Exact-image BF16/Q8, concurrent pressure, streaming, token counts, long dialogue, full working set and resource measurements | Cold-activation microsecond target is not met; bind final acceptance evidence to the registry manifest and supported deployment profile. |
| 6. Signed distribution | Signed lab clean install/run/update/rollback already exercised | Actual release origin/signing authority/catalog and non-lab clean-client lifecycle. |

The deployed Aimee account endpoint still returns 404 for native bootstrap.
Existing lab signing identities and fixture grants are not repurposed as
production authority. The production hostname and account/recipient binding
have been requested; those are deployment inputs, not missing user permission
for the implementation work. No signed non-lab release has been published.
