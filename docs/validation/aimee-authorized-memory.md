# Authorization-specific native memory — 2026-09-20

The compiler, reader, fallback gateway and native-state cache now enforce a
fixed authorization boundary. Tests passed against an actual isolated Aimee
instance and frozen Qwen3.8-27B. **The grants in these experiments are explicit
signed research fixtures. Production Aimee authorization issuance is not yet
connected, and organization-wide deployment is not authorized by these results.**

## User requirements implemented

- Aimee decides the grant. Model text cannot grant access or choose another
  subject, policy revision, scope, source image or authority credentials.
- Compile the KB for that grant before distribution. Do not transfer an entire
  organization image and rely on filtering after it reaches the model/server.
- Different grants have separate images and native-state cache identities.
  The same complete grant can share an image; model-specific states additionally
  require the same model/codec. More models do not imply more access.
- Canonical knowledge stays in Aimee. Model-facing copies and projections are
  derived state; neither the model nor adapter can update authoritative memory.
- Local reuse is limited to explicitly approved read decisions. Other requests
  reach Aimee through the same authorization boundary, with no partial fallback
  response when any returned information is outside that boundary.

## Implementation

`server-go/modules/memory/sparse/authorization.go` implements signed decisions,
fresh-directory compilation, physical payload validation and fallback response
checks. A decision binds subject, policy epoch, expiry, source view, exact
record revisions and serving-content hashes, and optional complete read-decision
digests. Signature verification uses an independently configured Ed25519 public
key. The key and expected subject/epoch must not come from the model or an
untrusted downloaded image.

The compiler copies only approved canonical serving fields. It does not copy
source history, old versions, unrelated objects, opaque metadata, aliases,
redirects or graph edges. These remain in Aimee and need additional authorization
and codec support before release. An approval for a scope is not an approval for
every record in that scope: even a `global` record requires explicit approval.
Compilation rejects existing destination directories to prevent old private
objects from remaining alongside a new CURRENT pointer.

Validation covers complete physical objects. It rejects unindexed data bytes,
extra index terms, unknown manifest data, unrelated object files, altered
records, wrong subjects, invalid signatures, expired/revoked grants, and policy
revision mismatches. Canonical data objects are separate from model-specific
native-state caches.

Raw archive import/export and PostgreSQL export now require explicit
`--internal-backup`; normal native serving/export require a verified grant.
The flag acknowledges an unfiltered control-plane operation; it is not an
access-control mechanism. OS permissions keep that source away from models.
Only explicit low-level synthetic tests may use `serve --unsafe-research`.
The Qwen service exposes no such bypass and accepts no direct Aimee credentials.

The separate read gateway holds the authority connection, verifies the same
grant, and checks every complete fallback response before delivery. Returned
record identity, canonical content and supplied semantic fields must match the
approved objects. Unsupported fields, rich evidence, episode payloads, missing
context, and any unapproved record reject the entire result. It neither silently
filters a mixed result nor learns an authorization decision. Empty results use
the same unavailable response as denied results; this avoids a direct status
oracle, but is not a constant-time or side-channel security guarantee.

Local and fallback authorization identities must match. Mismatch aborts the
session; it does not select the more permissive backend. Cache keys include the
authorization identity, and every use still requires an eligible read. Grants
are rechecked on reads, including requests with an already-pinned image.

## Tests and measured results

### Structural and adversarial tests

Go race tests and targeted vet passed: 23 top-level tests plus their subtests.
The authorization coverage includes:

- 1,000 objects across ten independent grants: 10,000 access decisions,
  comprising 1,000 permitted and 9,000 denied reads; the same grant reproducibly
  creates the same immutable view.
- Project isolation, same-scope withheld objects, explicitly unapproved global
  objects, deleted history, private aliases, private relations and opaque notes.
- Wrong subject/epoch, expiry boundaries, revoked grants, duplicate identities,
  tampered signatures, stale revisions and altered content hashes.
- Retired, pending, suppressed, expired and not-yet-valid source records.
- Hidden physical bytes, injected index terms, unknown manifest fields and
  unreachable foreign objects.
- Mixed permitted/denied fallback results, changed content, foreign scope,
  unsupported metadata, episode payloads, missing context and empty results.
- Unbound native readers and unfiltered transfer commands fail closed.

The Python suite passed 31 tests, including native tensor/logit equivalence,
authorization-specific cache partitioning, revocation with cached states,
mismatched local/fallback identities, and denial before local activation.
These tests use real tiny-model forward passes where applicable; they do not
establish broad pretrained-model knowledge accuracy.

### Actual Aimee, two independent grants

The disposable `aimee-sparse-scale-20260920` instance contains one million
synthetic facts. We read 64 existing facts through its real memory.search API.
Two fixture grants each approve a disjoint set of 32 records; each approves local
reuse for half of its exact queries. All 64 queries are exercised for each grant.
The test does not load an organization-wide image into either model reader.

| Outcome | Requests | Correct outcome | Median read time |
|---|---:|---:|---:|
| Authorized local hit | 32 | 32 | 1.355141 ms |
| Authorized Aimee fallback | 32 | 32 | 87.931267 ms |
| Cross-authorization request | 64 | 64 denied | 87.638085 ms |

**128/128 request outcomes passed.** Permitted responses exactly matched the
complete source Aimee responses. Denied results returned no facts. Twelve
additional checks passed across both grants: physical exclusion, missing-result
handling, forged bindings, scope escalation, write attempts and live revocation.

The two 32-record images compiled in 11.729479 and 15.531836 ms and occupied
44,541 and 44,472 bytes respectively, including signed grant/read metadata.
These tiny compilations are not evidence of production export throughput.

The source API was reached over its Unix socket, excluding network/TLS. Ordinary
PostgreSQL trigram/full-text indexes were installed only in the disposable test
project. Timings cover authorized read handling, not Qwen generation, large
semantic graph queries, cold SSD performance, or concurrent serving. The 1M-row
source size does not imply 1M-object local semantic coverage.

### Full Qwen native path

Frozen Qwen3.8-27B ran under a new unprivileged OS identity with its own
authorization-specific image, cache directory and traces. Two existing research
facts were approved. No memory text was appended to the main prompt and no
adapter training was performed.

| Check | Result | Elapsed |
|---|---|---:|
| Authorized composition, first request | `oolong;Lima` | 10.360972 s |
| Same request, native states reused | `oolong;Lima` | 2.877202 s |
| Request for an unapproved record | Blocked, HTTP 502 | 0.209630 s |
| Authorized request after that denial | `oolong;Lima` | 2.872542 s |
| Model-supplied `scope: all` | Rejected, HTTP 400 | 0.001753 s |
| Trusted grant revoked with cached states present | Blocked, HTTP 502 | 0.003230 s |

**6/6 full-model checks passed.** Each permitted request made seven local reads
and 96 native attention reads, with the same approved IDs 5 and 6. The first
request encoded 40 memory tokens into separate native states; the reused cases
performed zero memory-encoding passes. The first request includes runtime
warmup and must not be used as a steady-state comparison. These are functional
checks, not a new end-to-end performance benchmark.

Seven OS permission checks passed. The model could read its own approved image,
but could not modify it or its grant, read the signing key/Aimee credentials,
read the broader source image, or read the earlier model identity's traces.

## Failures found and fixed

An early fallback denial incorrectly closed the persistent reader. This blocked
later valid requests: an initial live run passed only 96/128 outcomes. Complete
semantic rejections now preserve framing, while transport failures still close
the connection. Final reruns pass 128/128, including permitted requests after
foreign requests. The failed run is retained as evidence.

Review also found that a mismatched local/fallback identity could previously
select fallback rather than abort. The service now binds fallback to its verified
startup image identity, and a mismatch aborts. Request handling cannot continue
after a failed authorization bind. Unit tests cover both conditions.

The initial isolated-source read timed out without the optional indexes; no
failed read was counted as a successful fast result. One native probe also hit
a listener-startup race; readiness now checks the actual listening socket rather
than an old ready log line. Neither failure is used as a timing result.

## Boundaries still requiring work

Follow-up tracing and denial-transition tests are recorded in
[authorization transitions](aimee-authorization-transitions.md). They found and
fixed denial-to-fallback escalation; they also confirmed that the proposed
canonical content-visibility issuer is not yet implemented. The earlier explicit
grant tests must not be read as production authorization-issuance evidence.

1. Connect grant issuance to Aimee's real authenticated principal, organization,
   project, field-level and record-level authorization decisions. The fixture
   issuer is explicitly not a production policy engine and must not be installed
   in the model environment.
2. Propagate Aimee policy/source mutations and revocations to grants and images.
   Tested revocation changed the trusted grant file. It does not prove automated
   production revocation propagation, immediate mid-token erasure, or removal
   of facts already emitted to an authorized recipient.
3. Add authorization-preserving richer retrieval and native response codecs for
   evidence, episodes, temporal reasoning and graph operations. These currently
   fail closed if the simple released-fact format cannot represent them. This
   experiment does not establish full Aimee semantic/governance parity.
4. Prefer authority-issued delegated credentials. The current gateway protects a
   broader appliance read connection with a strict egress check; it is not proof
   that the underlying memory.search endpoint itself is model-scoped.
5. Integrate a production multi-session host. The tested Qwen process has one
   fixed grant. Different grants require separate process/filesystem boundaries
   or equivalent verified isolation. Different sessions must not inherit old
   images, traces, native states or conversation caches. Broad concurrency,
   adversarial executable code, and timing/GPU side channels were not tested.

No production Aimee memory was mutated. Experimental model/gateway services and
the disposable authority containers were stopped after testing. The last test
grants were revoked. Private signing keys and Aimee credentials are excluded
from the repository artifacts.

## Evidence

[Raw API observations, failed and passing runs, native traces, permission checks
and test output](artifacts/aimee-authorized-memory-2026-09-20/).

Drivers: `benchmarks/local_memory/authorized_live.py` and
`benchmarks/local_memory/issue_fixture_grant.go`. The native probe and OS access
probe are retained with the artifacts. See also the
[architecture](../proposals/pending/aimee-local-sparse-memory.md) and
[earlier local-first experiment](aimee-local-first-memory.md).
