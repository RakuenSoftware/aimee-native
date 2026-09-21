# Authorization changes in the local/Aimee memory path

Date: 2026-09-20. This follows the
[authorized-image experiment](aimee-authorized-memory.md).

The prototype now treats an explicit denial as terminal for the current memory
request. Previously `LocalFirstClient` caught every local `AimeeError` and tried
the remote authority. Because a complete authorization rejection subclasses that
error, a local revocation could fall through to a gateway still holding the old
grant. The reverse direction also needed protection: after a remote denial,
subsequent local hits must not revive the same request.

## Change and observed behavior

- Local pin/read rejection propagates without remote fallback.
- Remote HTTP 400/401/403 and changed identity are typed request rejections.
- A rejection clears local readiness and the request's authorization latch.
- Ordinary local transport failure can still use the authorized remote gateway.
- Complete denials leave reader framing intact. A new, properly authorized
  request can continue after a query-specific rejection.

No model training, memory selection, learned policy, or neural interface changed.

## Transition tests

The six new integration tests run real compiled Go image readers and the Python
Unix gateway in separate processes. The upstream is an explicitly synthetic HTTP
protocol fixture. It allows deterministic grant replacement during an upstream
read; this is not a live Aimee membership or policy evaluation.

| Test | Result |
|---|---|
| Local grant revoked; remote still has old valid grant | Denied; zero upstream reads |
| Local grant narrowed; old image/session still present | Denied; zero upstream reads |
| Local grant replaced by expired grant | Denied; zero upstream reads |
| Remote grant revoked, then caller tries an old local hit | Both reads denied; zero upstream reads |
| Grant revoked while upstream read is in progress | Returning payload denied; next request blocked before upstream |
| Upstream mixes permitted and unauthorized facts | Whole response denied without either fact; next valid read succeeds |

All six passed. Four additional binding/fallback unit tests passed, including
both pin-time and recall-time denial and transport-failure cases. Temporarily
removing the local-denial handling in an isolated in-memory test copy caused all
three local revocation/expiry/narrowing tests to fail with **no rejection raised**.
This establishes that those tests detect the previous fall-through behavior.

The full Python suite on `.253` passed **42 tests in 0.952 seconds** using the
installed research PyTorch/Transformers environment and real tiny-Qwen forward
passes for the neural regression tests. This is test-run duration, not serving
latency. Raw final output is archived with this report. Go sparse-image and CLI tests
passed with the race detector. No new full-27B accuracy or throughput claim is
made by these authorization tests.

Tests generate signing keys only inside temporary fixture directories, remove
those directories, and terminate their reader/gateway processes. No production
memory, permissions, memberships, or database state was changed. Research source
copies remain under `/opt/aimee-qwen-adapter/auth-transition-tests-20260920`.

## Real authorization integration finding

Tracing current source revealed a missing policy dependency, not a callable
production issuer that can simply be connected:

1. `src/kb/kb_identity_resolve.c` resolves service/caller team intersection.
   `src/kb/http/kb_tls_serve.c` authenticates the service and caller and opens a
   tenant scope for content reads. This is existing KB ingress authority.
2. `server-go/modules/memory/scope.go` normalizes storage placement and scope.
   It does not authenticate a model or decide which organization objects it
   may export. `ExportSparseRecords` is a control-plane snapshot; its misleading
   “authorized source scope” comment has been corrected.
3. `src/server/server_state.c`'s memory search is appliance-local. Successful
   access through a broad appliance connection does not establish a different
   model's right to receive every returned object.
4. `server-go/modules/execution-policy/execution_policy.go` implements tool
   policy. The canonical content decision described in the pending
   [content-visibility proposal](../../../aimee/docs/proposals/pending/per-user-content-scope-visibility.md)
   is not implemented there. That proposal explicitly assigns canonical
   content-visibility policy to Go `execution-policy` and says memory still
   needs to consume it.

Therefore production grant issuance remains unfinished. The correct connection
is an authenticated, exact-resource release decision from Aimee's policy owner,
followed by compilation of only the approved fields and records. An adapter must
not infer that release from an arbitrary principal string, a scope label,
successful broad search, or possession of the experimental signing key. No
parallel membership engine or automatic broad grant was added.

## Limits and next work

These changes ensure an **observed denial cannot be bypassed** within the current
request. They do not propagate remote revocation instantaneously to every local
reader: before a denial is observed, an independently valid local grant may still
serve within its lease. Model request admission checks the gateway; local reads
check the trusted local grant file. Production needs Aimee-issued expiry and
invalidation, coordinated publication, and session/cache retirement. Already
emitted information cannot be retracted.

The conservative fallback still releases only facts explicitly approved in the
bound image. It cannot yet return a newly authorized object absent from that
grant, or a rich evidence/episode/graph response. Removing that limitation needs
fresh Aimee-authorized response releases and corresponding codecs, not weaker
gateway checks. This remains necessary for the intended local-KB plus complex
Aimee fallback architecture.

## Reproduction

Build the image reader and **research-only** fixture issuer from the
`aimee-qwen` repository root (the image reader remains owned by `../aimee`):

```sh
go -C ../aimee/server-go build -o /tmp/aimee-memory-image-denial ./cmd/aimee-memory-image
go build -o /tmp/aimee-issue-fixture-denial ./benchmarks/local_memory
go -C ../aimee/server-go test -race ./modules/memory/sparse ./cmd/aimee-memory-image
```

From `integrations/qwen_aimee`, the transition tests do not require model weights:

```sh
AIMEE_IMAGE_READER=/tmp/aimee-memory-image-denial \
AIMEE_FIXTURE_ISSUER=/tmp/aimee-issue-fixture-denial \
python3 -m unittest -v test_authorized_gateway test_local_first.AuthorizationBindingTests
```

The full `unittest discover -v` suite additionally requires PyTorch/Transformers.
[Archived evidence](artifacts/aimee-authorization-transitions-2026-09-20/).
