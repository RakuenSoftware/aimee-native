# Native distribution production follow-up — 2026-09-25

All changes in this follow-up are in `aimee-qwen`. Aimee's storage,
authorization and scoped-export contracts remain dependencies. The runtime is
unmodified vLLM; no fork, source patch or monkey-patching was introduced.

## Evidence boundary

This is substantial production engineering progress, **not a customer-ready
release**. We have exercised signed distribution on a clean Debian 13 container,
real Gemma GPU inference and the actual scoped publication reader/compiler.
The memory records and signing/authorization identities are explicitly synthetic
lab fixtures. No live customer Aimee account has been authenticated by these tests.
The clean client's memory was installed by the test harness, not downloaded by
`connect`. Account authentication, hosted recipient-bound native delivery and
complex-read fallback remain implementation/deployment work.

Artifacts are in [vllm-production-20260925](artifacts/vllm-production-20260925/).
Failures are retained alongside corrected attempts.

## Automatic selection and actual preparation

The private selection service uses `serve-published` to pin, recall and approve
records. An exact ordered `(namespace, id, revision)` list plus authorization view
must match a prepared bank. Every record must be present; a bank containing one
record cannot satisfy a three-record selection. A caller's publication ID cannot
override automatic selection. Cache hits are reapproved. Missing prepared sets
can invoke the private compiler and coordinated catalog activation; unresolved or
complex source reads currently reject instead of silently using incomplete memory.
The service drops its reader process after protocol timeout/failure to prevent
an old response being consumed as a later request's approval.

The real-reader test exposed a bug in the earlier protocol fixture: local recall
results had been passed to the remote-receipt approval operation. The reader now
has a separate `resolve_local_response` operation. It checks canonical content,
record reference and hash against the current authorized view. Remote results
still require their remote receipt. Tests reject changed content and missing
local hashes, and confirm local receipts cannot satisfy the remote boundary.

`automatic-selection-r1.json` records alpha and beta answers, each containing all
three expected facts, a forged-publication override check, HTTP 503 after source
withdrawal, and successful restoration. Each native prompt contained 38 tokens.
This uses the real Go reader and compiled GPU consumer with synthetic scope.

`real-reader-preparation-r2.json` runs the actual CPU Gemma compiler through Rust
`native-prepare`, not a copying stub. It encoded all three approved records, then
reused the prepared result. One first preparation took 39.7 seconds including
process/model setup; one approved reuse took about 6 ms. These are control-plane
observations, not hot-path or performance-distribution claims. Attempt 1 failed
because the test pointed at a consumer-only library without publisher exports;
attempt 2 used the private publisher library. No publisher was added to the client.

The worker now owns its small Python/Rust publisher bridge inside
`distribution/service`, removing the research-checkout dependency. A further
actual preparation (`real-reader-preparation-r3.json`) passed first preparation
and approved reuse; `publisher-parity.json` checks identical encoded payload
bytes against the previously tested wrapper.

## Combined publication feed and GPU lifecycle

`feed-gpu-r1.json` connects the actual Go `PublicationStreamHandler`, the actual
publication follower/delivery store, scoped reader, Rust preparer, CPU encoder,
automatic selector and BF16 GPU server. The source uses a same-UID authenticated
Unix socket and synthetic grants, rather than a mocked JSON event producer.

The initially prepared alpha working set returned all three facts. Selecting the
unprepared beta set invoked the real compiler, activated the complete three-record
bank and answered correctly; a subsequent beta query reused it. The first beta
HTTP response took 23.2 seconds including preparation, versus 1.18 seconds for
reuse including answer generation. Those single observations are lifecycle
evidence, not application-latency estimates. All prompts contained 34 tokens.
Both catalog bindings contained three canonical source records.

Denying the source produced HTTP 503; restoring authority resumed correct alpha
answers. Terminating the publisher also produced HTTP 503. This tests the combined
stream and GPU path, but not remote customer authentication, HTTPS native-artifact
transfer, every expiry/revision race, or broad workload reliability.

## Demand-loaded catalog residency

With `disk_backed: true`, Rust verifies the immutable payload once at admission
using a 256 KiB scratch buffer and retains a read-only mapping/open descriptor.
It does not allocate a complete catalog of payloads. Selected pages are faulted
on demand for GPU activation; mapped pages are released after synchronous copies.
Verification and file opening remain outside attention.

The publisher must replace immutable inodes, never rewrite/truncate an admitted
file in place. A Rust test retains old views across replacement, unlink and page
release. This ownership contract is necessary for safe mapped tensor views.

`disk-pressure-r1.json`: catalog payload 35,782,656 bytes; host working-set budget
20 MiB; device bank budget 9,551,872 bytes per rank. Alpha → beta → alpha returned
68731 → 94268 → 68731. Each rank uploaded three times and evicted twice without
exceeding the bank budget. Mapped payload RSS was zero at every post-transfer
checkpoint. OS page cache can still retain data; this is not zero total host RAM
usage, a total-process memory bound, or a measurement of cold SSD latency.

## Signed clean-host distribution

CT110 was created fresh on the authorized .253 lab with Debian 13, 32 GiB RAM,
100 GiB disk and access to the two RX7900XTXs. Only Podman, CA support, curl and
Python were installed as test prerequisites. There was no development repository,
HF environment or compiler on this client. The launcher downloaded signed model
artifacts and pulled a digest-pinned image from an isolated TLS registry.

- Image digest: `sha256:6e8baf0e9a95f6a4b66bbb2923199b47ee94ed3434c5082a272f31fc731c02f0`.
- Actual Gemma Q8_0 GGUF: 12,863,382,944 bytes, with model/tokenizer sidecars.
- Initial signed release: `c42ec33cf47795e7ed5b351f660d35d7c965fd1ec0ca9ab9ed74fe532a47a1c6`.
- Upgrade: `d52dd20aeb7fa3395bfc7f126324afb8d2fc92121b658f6f1a13961d77e36403`.

Installation, upgraded runtime restart and rolled-back runtime restart passed.
Both restarted versions answered all three native facts correctly. Rollback kept
the high-water release sequence at 2. See `installed-lifecycle.json`.
The first HTTPS attempt failed; replacing the inappropriate CA-as-server setup
with a CA-signed server leaf fixed the connection without disabling verification.

Lab launchers are explicitly compiled with `lab-release`, a public lab CA and
lab release verification key. They announce their status and accept only a
`lab-` model identity when a manifest carries `lab_only`. Normal launchers reject
that marker. Lab container settings accommodate nested LXC; these tests do not
certify every customer host/container configuration.

`connect` saved a generated fixture credential but no account service consumed
it. Approved memory/catalog configuration was explicitly installed by the test
harness. Therefore this validates signed install/run/upgrade/rollback, **not** the
complete advertised account-connect → native-delivery workflow.

## Installed Q8 native/text matrix

The paired matrix covers two three-record banks, six question forms (single,
two-record and three-record answers), and 0/16/48 preceding conversation turns.
There are 72 answers: 36 native and 36 text controls. Both arms passed 36/36.
This is an engineering fixture with six underlying facts, not 72 independent
knowledge discoveries or a general model-quality estimate.

| Prior turns | Native correct | Text correct | Native median request | Text median request | Prompt tokens saved per request |
|---:|---:|---:|---:|---:|---:|
| 0 | 12/12 | 12/12 | 994 ms | 1,166 ms | 52 |
| 16 | 12/12 | 12/12 | 825 ms | 1,146 ms | 52 |
| 48 | 12/12 | 12/12 | 1,203 ms | 1,346 ms | 52 |

Completion-token totals matched between arms at each conversation length
(190, 191 and 194). Native avoided the memory text's 52 prompt/context positions
on every request. Native memory still occupies separate tensor/device storage;
zero added prompt tokens is not zero attention work or zero memory cost.
Measurements are sequential full HTTP responses; they include output generation,
startup/cache effects are not controlled as a cold-storage experiment, and these
numbers must not be described as native application latency. Exact answers and
usage are in `q8-matrix-r1.json`.

## Matched BF16 checks

The same 72-answer matrix on BF16 also passed: native 36/36 and text 36/36,
with the same 52 prompt tokens saved per request. Thus the two profiles passed
144/144 answers across both arms on this fixture. This does not certify arbitrary
quantization formats or unrelated model families.

Raw BF16 HTTP timing is retained in `bf16-matrix-r1.json`, but the private CPU
preparation validation ran during the broader test window and the host/container
CPU allocations differ from the clean Q8 client. Do not interpret BF16 versus Q8
timing as a controlled quantization performance effect. At 16 turns the two BF16
arms also generated one different completion token in aggregate. These checks
establish fixture correctness and token accounting, not isolated performance.

## 32-record simultaneously active working set

`wide-native-r3.json` selects and encodes **all 32 canonical records** into one
bank through the actual scoped reader and private CPU compiler. Every native
question consumes that full bank, including the 31 irrelevant records for a
single-record question. The text control receives the same 32 records. Values
are deterministic synthetic five-digit codes; scoring requires exactly the
expected set of codes, rejecting missing, repeated or extraneous values.

Both arms passed **56/56**: 32 single-record, 16 two-record and eight three-record
questions. This adds 112 correct answers to the 144-answer small-bank matrices.
It tests a 32-record active set, not an unbounded corpus or unlimited composition.

| Records requested | Native correct | Text correct | Native prompt tokens | Text prompt tokens | Native median response | Text median response |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 32/32 | 32/32 | 30 | 616 | 258 ms | 639 ms |
| 2 | 16/16 | 16/16 | 36 | 622 | 535 ms | 958 ms |
| 3 | 8/8 | 8/8 | 42 | 628 | 759 ms | 1,274 ms |

Native saved 586 prompt/context positions on every request. Completion-token
totals matched for single- and two-record questions (192 and 208 per arm); the
three-record totals were 152 native versus 154 text. These are sequential full
HTTP response timings, not isolated memory application or cold storage latency.
No private compilation ran during this successful GPU measurement sequence.

The prepared payload file was **201,627,944 bytes**; this is model-specific
prepared storage, not the size of the original 32 text facts. First CPU
preparation took 222 seconds including setup; approved cache reuse took about
12 ms on the retry. Those observations must remain separate from inference
application timings. Prepared representations trade background work/storage
for reuse and avoided text prefill; this test does not establish microsecond
cold loading of a 202 MB artifact.

Attempt 1 failed fixture authorization because the chosen reference cue was a
single lexical token, while the existing cue contract requires two. The fixture
was corrected without changing the selection implementation. Attempt 2 completed
all 32-record preparation but the host test environment lacked the pinned GGUF
plugin already present in the released container. Installing that exact unmodified
dependency let attempt 3 reuse and reapprove the same prepared bank and run the
full matrix. All failed setup logs and the successful raw results are retained.

## Packaging, licenses and release gates

The package includes the Gemma Apache-2.0 license and Q8 conversion notice,
alongside existing vLLM/GGUF dependency notices. Tooling captures installed Python
and OS inventory plus public Rust dependency notices. The inspected image has
274 Python distributions and 591 OS packages. Rust resolution includes 224
packages, including optional/platform-specific packages that may not be linked.
Two `r-efi` versions have no root notice file in the collected source package;
these are recorded, not silently counted as resolved obligations. Several Python
packages rely on OS-owned or otherwise separately installed notices. An inventory
is not a completed vulnerability or redistribution-obligation review.

Production packaging now requires `authenticated_delivery` and
`license_dependency_audit` in addition to the existing gates. Each gate report
must name the SHA-256 of the exact artifact descriptor set (paths, bytes, hashes
and executable flags). Stale evidence for changed files fails before signing.
The release assembler does not manufacture passing production reports for lab
builds. No private signing key, authorization credential, model weight or private
memory is committed to the repository.

## Remaining release work

1. Integrate actual account authentication, hosted native-artifact delivery and
   remote selection/update lifecycle; finish authoritative fallback for complex
   reads. The production hostname/host and publication credentials are pending.
2. Expand revision/expiry/failure coverage for the final remote transport. The
   combined actual local feed/GPU test now passes; it is not remote deployment
   certification.
3. Extend measured resource bounds to total process/page-cache/GPU allocations
   and separately measure preparation, cold storage, transfer and attention.
4. Extend certification beyond the matched small-bank BF16/Q8 and 32-record
   Q8 working-set tests that now pass: more domains, quantization profiles and
   separately controlled latency/resource distributions remain useful.
5. Close dependency/license obligations, provision production signing/registry
   identities, and run the finished connect/delivery workflow on a clean client.

The isolated signed lab release is deliberately not promoted through production
release gates while these items remain.

## Verification summary

The complete Go suite passes, along with 18 client CPU tests (none skipped),
9 private-service tests, release-package tests and launcher lifecycle tests.
Three Rust store tests cover byte-preserving views, immutable mapping lifetime
and rejection of invalid identity/budget/content. The GPU checks above ran on
Gemma only; no new Qwen run was started. Source and binary gate tests are retained
alongside their raw logs. Both lab GPU servers were stopped after their probes.
