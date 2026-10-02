# Authorized empty-memory selections — 30 September 2026

Plugin **0.2.1** fixes the live no-match limitation discovered in
[the expanded RTX 5080 checks](cuda-5080-expanded-20260930.md). An ordinary
request can proceed without native memory when Aimee explicitly authorizes an
empty selection. A transport error, failed authorization or incomplete contextual
read cannot authorize that behavior.

## Change

The private preparer now recognizes an empty **authoritative restricted read**,
revalidates it and its publication view, and returns `outcome: "no_memory"`
without invoking the encoder. A local cache miss alone is insufficient. The
hosted Go service rechecks identity, policy scope and selection before returning
an empty response; no artifact download lease is issued.

The Rust client validates the response schema, model, recipient and view. The
broker forwards a null selection only over its private socket. For an active
server, resident banks can remain cached, but none is selected for this request.
On cold or paused startup, it clears old catalogue entries, activates the empty
catalogue and rechecks current authority after activation. Errors still fail
closed.

The vLLM middleware removes any caller-supplied publication and replaces the
caller-supplied catalogue digest with the current trusted digest. It serializes
that corrected body even when no bank is selected. The worker therefore pins the
request without native memory; an earlier request's bank is not a default.

No GPU kernel, native tensor library, model weight, vLLM fork or sibling Aimee
repository change is required. The native library hash is unchanged from 0.2.0:
`a14ad42649729a927e74aa03c60d116919b7a3705c89e36c1172bb88b2e91ce8`.
Both the hosted preparation/publication service and client must support the new
response. Existing nonempty publication delivery remains compatible.

## Checks

- Rust launcher library: 19 tests passed, including typed empty-response identity
  validation and rejection of mixed payloads or error objects.
- Hosted Go native-publication package: all tests passed, including empty-result
  revalidation, withdrawal, policy-scope changes, implicit emptiness and malformed
  mixed outcomes.
- Admission middleware: 9 tests passed, including removal of an untrusted bank,
  no reservation for empty requests, stale-selection rejection and failure
  remaining HTTP 503. The empty request is also validated against vLLM's actual
  `ChatCompletionRequest` schema.
- Live authenticated API: authorized empty query **200**; invalid token **401**;
  unapproved model **403**.
- Complete wheel packaging and RECORD audit passed.

## Corrections made during validation

The initial wheel serialized the internal null selection into `vllm_xargs`.
vLLM's typed API rejects null extra-argument values with HTTP 400. The corrected
middleware removes the publication field entirely, preserving the trusted digest.
The regression test now includes the real vLLM request schema. The failed run is
retained separately and is not counted as successful validation.

Deployment also required staging binaries on their destination filesystem before
atomic replacement; a rename from `/tmp` crossed filesystems. The service was
restored with the updated binaries and its temporary diagnostic configuration
removed. The first Python module build used the container's Python 3.13 without
build dependencies; the final wheel was built in an isolated CPython 3.12 build
environment matching the serving runtime. These setup failures are retained.

## Installed-wheel RTX 5080 result

The final **0.2.1** wheel passed through the live authenticated Aimee service,
using Gemma4 12B Q8_0 on stock vLLM 0.30.0 and the same RTX 5080 environment as
the preceding campaign:

| Check | Result |
|---|---:|
| First request after startup: authorized empty selection | 1/1 correct |
| Native three-fact recall | 24/24 correct |
| Interleaved arithmetic with authorized empty selection | 24/24 correct |
| Native recall after automatic interrupted-stream recovery | 1/1 correct |

All empty requests deliberately supplied an untrusted publication name and stale
catalogue digest. They still generated the correct arithmetic answer, proving
the forwarded request was sanitized rather than rejected or bound to that bank.
The first empty request also exercised activation from initially paused admission.
Recovery through model-process replacement and the final answer took **54.124
seconds**. These are 50 scored reliability answers, not 50 distinct knowledge
examples. This run validates the changed path on Gemma4 12B/RTX 5080; it does not
claim a fresh 0.2.1 GPU run on every previously tested model and device.

The corrected hosted service remains active. The 5080 reservation was released;
no GPU compute processes remained. The tested wheel and manifest were published
to the existing private origin with TLS download and pinned Ed25519 signature
verification. Version 0.2.0 and its evidence remain intact.

Wheel SHA-256:
`b3dc503d0bbec6f0f303fb7a2829ac1773d8b5bd0783041929d707351660bc2f`.

[Private 0.2.1 manifest](https://192.168.0.126:8445/plugins/portable/0.2.1/manifest.json).
[Raw results, failed attempt, checksums and deployment evidence](artifacts/no-memory-20260930/).
