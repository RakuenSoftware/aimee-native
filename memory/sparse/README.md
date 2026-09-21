# Local sparse memory images (experimental v1)

This implements the first storage/reader slice of the
[layered local-memory design](../../docs/proposals/pending/aimee-local-sparse-memory.md).
Both source paths work:

```text
published general -> KB enrichment -> server-local enrichment
published general -----------------> server-local enrichment
```

Each layer owns a namespace. Record bodies are immutable content-addressed disk
objects; manifests, record offsets, lexical postings, scope/validity fields,
redirects, and edge references are indexed in RAM. Reads fetch only selected
record bodies using file offsets. There is no database or network dependency in
the reader and no GPU dependency in this package.

## Recipient publication and local reads

Authorization belongs to Aimee before data is delivered. `compile-authorized`
creates a fresh recipient-only directory, excluding unapproved objects and
source metadata/history. Its current format includes compiled routing metadata
but does not distribute the signed grant. The trusted publisher retains that
decision and is responsible for replacing or withdrawing delivered snapshots.

Read the resulting directory with `serve-published --root /recipient/image`.
Send `{"op":"pin"}` at the beginning of a request, then `recall` messages with
`query`, `limit`, and the configured retrieval `authority`. Pin returns `view`
and a `publication` identifier; hits carry canonical `memory_ref` fields.
No local credentials, permission checks, or network calls are needed. Image
integrity, record temporal validity, and compiled retrieval semantics still apply.

A request pins its generation. A fresh pin observes the publisher's new active
directory or fails if withdrawn. Immediate withdrawal requires the publisher to
quiesce active consumers and remove obsolete files. Local checks cannot conceal
or retract bytes already delivered. The historical grant-bound `serve` command
remains for compatibility and privileged fallback proxy checks.

The publisher can manage the recipient directory with `install-published --root
COMPILED --output-root RECIPIENT [--reader-gid GID] [--expected OLD_VIEW]`,
`withdraw-published --root RECIPIENT --expected VIEW`, and `prune-published --root
RECIPIENT [--expected VIEW]`. Installation copies reachable snapshot objects,
validates them, atomically switches the current generation, and removes obsolete
snapshot directories. `serve-published --root RECIPIENT` understands this layout.
A pin/open lock prevents races with cleanup; ordinary reads use already-open
files. The publisher, not the model, must own the delivery directory.

Build the executable from the `aimee-qwen` repository root:

```sh
go build -o /tmp/aimee-memory-image ./cmd/aimee-memory-image
go test -race ./memory/sparse ./cmd/aimee-memory-image
```

## Building a layer

The `build` command accepts a source-owned change set. Example general input:

```json
{
  "namespace": "general-example",
  "kind": "general",
  "generation": 1,
  "source": "synthetic-example",
  "coverage": ["memory_records"],
  "records": [{
    "namespace": "general-example",
    "id": "1",
    "revision": "v1",
    "scope": {"type": "global", "value": "_global"},
    "key": "fixture material",
    "content": "The material for fixture-alpha is basalt.",
    "kind": "fact",
    "tier": "L3",
    "confidence": 1,
    "lifecycle": "active"
  }]
}
```

```sh
/tmp/aimee-memory-image build --root /path/to/image --input general.json
```

The command returns a manifest digest. A KB input has `kind: kb`, its own
namespace, and `upstream` equal to the general digest. A server input has
`kind: server`, its own namespace, and `upstream` equal to either the general
or KB digest. General records must be global. KB records may be global,
workspace, or project scoped. Server records use `user:_user` for that instance.
Private records cannot be built into a general or KB layer.

IDs are namespaced; equal numeric IDs in three layers stay distinct. Aliases
index the same record. An authoritative deduplication redirect uses
`redirect: {namespace, id, revision}`. Redirects must resolve, must not cycle,
and must pass scope/validity at every hop. An edge is
`{relation, target: {namespace, id, revision}}`; `View.Neighbors` reads these
links with the same eligibility checks. No new semantic deduplication policy is
implemented here. Arbitrary source metadata round-trips in `metadata`.

## Publishing and distributing

```sh
/tmp/aimee-memory-image publish --root /path/to/image --view MANIFEST_DIGEST
/tmp/aimee-memory-image export --root /path/to/image > image.tar
/tmp/aimee-memory-image import --root /path/to/other-image --input image.tar
```

Export follows only the selected manifest's lineage, not unrelated objects in
the same directory. Import verifies content hashes and lineage and returns a
digest; it **does not publish**. Publish after import using the returned digest.
For an existing `CURRENT`, publication requires `--expected OLD_DIGEST`.
Readers already using the old view continue to use it. Failed or competing
publication cannot silently replace `CURRENT`.

These are local artifact commands, not automatic HTTP distribution or daemon
synchronization. Obtain artifacts through an authenticated source: content
hashes detect corruption, not publisher identity. Directory/files use private
creation modes; source scope grants remain required when reading.

## Updates

A delta carries `previous: OLD_LOCAL_DIGEST`, a greater `generation`, and the
exact chosen `upstream` digest. `records` contains changed/new records only;
`delete` contains exact owned `{namespace,id,revision}` references. Reusing a
revision for different bytes is rejected. Applying new general or KB knowledge
requires building a new downstream view with that explicit upstream digest.
Existing local rows persist through the `previous` chain.

Cross-layer corrections are explicit Aimee decisions:

```json
{"suppressions":[{
  "target":{"namespace":"general-example","id":"1","revision":"v1"},
  "reason":"authoritative local resolution reference",
  "scope":{"type":"user","value":"_user"}
}]}
```

The same target/scope with `release: true` withdraws that layer's suppression.
A private suppression does not hide the base fact from an ungranted reader.
An upstream revision change invalidates an unreconciled pinned suppression.
No automatic last-layer-wins or inferred contradiction resolution is performed.

Tombstones prevent visibility in new views. Immutable old versions remain on
disk and remain readable by already-pinned readers. Physical erasure, garbage
collection, compaction, and active-model-state revocation are not implemented.

## Local reads and native integration

```sh
/tmp/aimee-memory-image query --root /path/to/image \
  --scopes user:_user,project:my-project --query 'fixture-alpha' --limit 4
/tmp/aimee-memory-image verify --root /path/to/image
/tmp/aimee-memory-image serve --root /path/to/image --scopes user:_user
```

`serve` is a persistent local JSON-lines process, not an HTTP service. Send
`{"op":"pin"}` once at each model request boundary, then
`{"op":"search","query":"fixture-alpha","limit":4}`. Publication never
changes that request's pinned view. `--view DIGEST` fixes a reader to a particular
view instead of following `CURRENT` at pin boundaries. Scope grants are fixed
at process startup; individual search requests cannot widen them.

[Qwen integration code, configuration, and validation](../../../../../aimee-qwen/README.md)
are maintained in the separate `aimee-qwen` repository.

## Authoritative memory-row export

`export-postgres` is a read-only, repeatable-read snapshot of the appropriate
memory table. It reuses the memory module's placement/scope normalization.
Supply the connection string privately in `AIMEE_IMAGE_DATABASE_URL`, then:

```sh
/tmp/aimee-memory-image export-postgres --placement server \
  --namespace my-server > local-records.json
/tmp/aimee-memory-image export-postgres --placement kb \
  --scope-type project --scope-value my-project --namespace my-kb > kb-records.json
```

Output contains `records`, `coverage`, and `not_exported`. Put the records and
coverage into the source change set with its chosen generation and upstream.
The original row JSON is retained as metadata and hashed as its revision.
The exporter does not mutate Aimee, publish artifacts, or start a sync daemon.

## Current coverage and limits

- The Go writer/reader supports layered records, aliases, explicit redirects,
  versioned edges, lifecycle, suppression, temporal intervals, and exact scope
  grants. Source metadata is preserved without pretending to execute unknown
  policy fields.
- The PostgreSQL exporter covers memory rows only. Full entity/episode/vector
  export, policy dependency compilation, and comprehensive Aimee retrieval
  parity remain to be implemented. General-corpus production is also separate.
- Query discovery is explicitly `lexical-v1`, with frequency-weighted lexical
  matches and confidence as a tie-breaker. It is **not** the existing full hybrid
  retrieval stack. There is no ANN, query encoder, or automatic graph expansion.
  Candidate overflow fails visibly rather than silently cutting off records.
- Payloads stay on disk, but indexes and metadata fit in RAM. Build/export input
  is currently materialized in memory; million/billion-record streaming builds
  and segmented indexes are not claimed. Delta ancestry is bounded at 4096.
- Warm sparse-lookup benchmarks measure only the reader. They do not establish
  cold-NVMe or end-to-end native-model latency.

## Published read decisions

An optional manifest `read_contracts` section preserves exact Aimee search
responses with query, limit, authority, exact scope grants, expiry, and source
ID/revision dependencies. `recall` returns a response only for a matching,
unexpired contract whose source records remain eligible. It does no lexical
approximation. Other requests must reach Aimee through the local-first client.
Only the tip manifest's contracts apply: every publication withdraws prior
contracts unless explicitly republished, including when new knowledge changes
which answer should win without modifying an old source record.

Source content must match the response. Evidence fields are preserved in the
raw response; opaque metadata preservation is not implementation of Aimee's
policy engine. Research publishers currently set bounded expiry themselves;
authority-issued freshness and mutation invalidation are not yet wired. Readers
pin a generation per request. Protect the image and CURRENT with OS permissions;
the reader protocol exposes no publication operation.

## Authorization-specific snapshots

`CompileAuthorized` consumes a signed Aimee approval: subject, policy epoch,
expiry, source view, exact approved record revisions/content hashes, and optional
read-decision digests. It writes only a fresh directory and physically excludes
all unapproved objects, history, metadata, aliases and edges. Scope labels alone
never authorize export. The canonical objects remain in Aimee.

`CheckAuthorization` checks physical data, indexes and manifests, not merely the
visible records. Unknown manifest data, unindexed bytes, extra index terms,
unreachable object files, wrong subjects, expired/revoked grants and altered
content are rejected. The verification key and expected subject/epoch must come
from trusted configuration, not from the downloaded image or model.

CLI `compile-authorized --root SOURCE --output-root NEW_DIRECTORY` requires
`--authorization`, `--authority-key` (hex Ed25519 public key), `--subject` and
`--policy-epoch`. Normal `serve` and `export` require the same authorization.
Raw `import`, `export` and `export-postgres` require `--internal-backup` and must
stay in the control plane. `serve --unsafe-research` remains solely for explicit
synthetic low-level tests; the Qwen server does not expose that bypass.

The research fixture issuer under benchmarks is not a production policy engine.
Do not install its private key or signing tool in the model environment. Aimee's
real authorization service must issue grants before organization use.
