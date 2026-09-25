# Private preparation service boundary

Do not put this service in the client package. Its implementation and deployment
specification belong in aimee-qwen. Consume Aimee's authoritative scoped exports;
do not clone membership, governance, selection or authorization policy.

The existing publisher-controlled sparse-image lifecycle supplies installation,
replacement and withdrawal semantics (see `docs/validation/local-delivery.md`).
The native preparation worker must bind each output to that authorized view,
recipient and exact source revisions. `src/preparation_cache.rs` supplies a
private cache primitive for compiler callbacks. It is not an authorization API
and is not yet wired into a hosted production worker.

Before accepting public client requests, integrate the actual authenticated
publication feed. Client-supplied IDs/tenant names are not release authority.
Preparation failures leave the previously published revision active. Withdrawals
must prevent new pins; already-delivered data cannot be erased from a malicious
host. Artifact expiry and connection-loss behavior must follow Aimee policy,
not a locally invented grant.

The deployment host, authenticated feed contract and release origin remain
unconfigured. No credentials, signing keys or test-issued grants may substitute
for those inputs. The research `/aimee/prepare` endpoint is not a production API.

Keep service-only logs/symbols and operational diagnostics off the client.
Model-specific preparation can involve model execution on the service. The
completed benchmark's exact RAM snapshots are not evidence that a compact
arbitrary memory representation can always be reconstructed without that work.
