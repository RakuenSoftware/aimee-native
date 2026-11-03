# Aimee release and protocol compatibility

The current application target is [Aimee v1.0.2](https://github.com/RakuenSoftware/aimee/releases/tag/v1.0.2),
commit `204d4e55828993a7683cb2610fb4165e44cabb9f`, checked as the latest
published application release on 2026-11-03. The machine-readable target is
[dependencies/aimee-release.json](../dependencies/aimee-release.json).
Application, plugin, vLLM, Torch and model-checkpoint versions are independent.
[The .252 validation report](validation/aimee-v1.0.2-20261103.md) records 27
passing real-application checks, all five installed bindings and CPU coverage.
[The .253 RTX 5080 follow-up](validation/aimee-5080-20261103.md) records actual
CUDA execution for the rebuilt artifacts and their precise validation scope.

## Enrolled model runtime

The standard Aimee thin client enrolls once. `connect-aimee` reads its existing
profile, validates credential ownership/modes, establishes mTLS and checks
`POST /v1/native/primitive`. The plugin stores the profile path, not a copied
bearer or signing key. The same profile is reopened for subsequent reads.
An endpoint or enrolled identity change requires reconnecting/restarting the
serving instance. Token refresh within the same valid identity is read again.

A request is a JSON object:

```json
{"task_hint":"the current user question","limit_tokens":1024,"store":"user"}
```

The client requires a nonblank query of at most 16,384 bytes and a token budget
between 64 and 8,192. Normal managed selection currently requests 1,024 tokens.
The versioned response consumed by Rust is:

```json
{
  "schema": 1,
  "records": [{
    "id": 7,
    "content": "An approved synthetic fact.",
    "version": {
      "schema_version": 1,
      "owner_id": "00000000-0000-0000-0000-000000000001",
      "record_id": "7",
      "record_revision": "3"
    }
  }]
}
```

IDs and revisions come from Aimee. Records must be unique by owner/record ID,
source versions must match their record, and the bank contains at most 32 records.
The client bounds the complete response at 1 MiB. Empty selection is valid and
preserves ordinary text-only model behavior. A malformed response, denied request
or unavailable source cannot authorize a stale bank. HTTP redirects are refused.
HTTPS and the enrolled client identity are required. A pinned server certificate
is consumed with the existing thin-client pin semantics.

The Rust broker checks source authority again before warm reuse, after cold
preparation and after activation. Changed source is prepared through the resident
model while admission is withdrawn. A model host can inspect already delivered
data; revocation does not retract it. Shared organization memory needs a separate
core authorization/selection contract and is not enabled by changing `store`.

Aimee 0.4.6 lacks the required endpoint. The 1.0.x application includes it;
this audit targets the exact v1.0.2 image, rather than assuming that a moving
`testing` branch or a newer development build has the same contract.

## Legacy Go research dependency

The Go raw-row exporter, restricted module-bus ingress and sparse authorization
fixtures depend on the historical core revision in
[aimee-source.json](../dependencies/aimee-source.json). Aimee v1.0.2 has retired
`modules/memory/readcontract`, `ExportMemoryRows`, `ExportMemoryRowsSelected`
and the earlier restricted-search API. These tools cannot be rebuilt against
that modern source merely by changing a version number. They are not the enrolled
plugin's server interface and must not be deployed as a v1.0.2 policy bridge.

`go.mod` therefore resolves the research dependency from an isolated ignored
extraction prepared by `scripts/prepare-research-dependency.py`. This consumes
core source as a dependency without copying its maintained implementation into
this repository. The sibling checkout is never switched or rewritten. The
historical dependency archive predates additional APIs and is insufficient.
Do not use a broad database export, a fabricated restriction receipt or fixture
approval as a substitute for v1.0.2's authenticated source release.

See [development](development.md) for reproduction and
[usage](usage.md) for current installation.
