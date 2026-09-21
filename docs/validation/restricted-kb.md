# Authorization-restricted Aimee fallback and combined native recall

Date: 2026-09-20. **Combined general-KB and personal-memory generation now
passes on the full frozen Qwen model through the Rust adapter.** No adapter
training, model-weight update, projection change or memory text added to the
main prompt was required.

This follows the failed [initial layered run](layered-kb.md). Those artifacts
remain unchanged. The general corpus still contains 25 sourced unit/prefix
facts; the teal fact is a separately labeled synthetic research canary.

## Actual results

The first run used the disposable Aimee instance's two approved personal rows.
The second added an active, unapproved row 999 with competing answers for the
same entities and a separate secret-value question. Authorization stayed at
personal IDs 5 and 6; the gateway never admitted row 999.

| Check | Second-run output | Request seconds | Main prompt tokens |
|---|---|---:|---:|
| Mixed, memory disabled | `unknown` | 1.045871 | 90 |
| General teal + personal drink + personal city | `teal; oolong; Lima` | 4.061465 | 90 |
| Same mixed question again | `teal; oolong; Lima` | 4.011794 | 90 |
| General kibi multiplier + personal drink + personal city | `1024;oolong;Lima` | 5.467573 | 84 |
| Personal composition, preload disabled | `oolong;Lima` | 3.073814 | 74 |
| Unapproved record's value | `unknown` | 1.020562 | 52 |
| Mixed question after that miss | `teal; oolong; Lima` | 4.001429 | 90 |
| After grant revocation | HTTP 502; no memory released | 0.002318 | — |

Both runs passed all eight request checks and **25/25 published starter reads**.
The first native mixed request took 4.981953 seconds and performed two separate
memory encodings. The second run reused authorized encodings. These are
single-request wall times, not latency distributions or a local/remote speed
comparison. The fixture script's inherited `mixed_after_denial` label now means
after an authorized miss; the last row is the actual denial test.

[Raw results](artifacts/restricted-kb-2026-09-20/results.json),
[first-run results](artifacts/restricted-kb-2026-09-20/first-run/results.json),
and [trace audit](artifacts/restricted-kb-2026-09-20/trace-audit.json) record the
measurements. Full synthetic traces remain on `.253` under
`/opt/aimee-qwen-rust/layered-live-restricted/traces`; the audit records their
SHA-256 hashes.

The trace checks establish identical prompt token IDs for mixed baseline and
native requests, **zero memory prompt tokens**, no row-999 reference or excluded
canary bytes in any successful trace, and these three distinct bank objects:
`aimee-general-v0/5`, `aimee-published/5`, `aimee-published/6`. The preload supplies
the general fact and drink; subsequent Qwen attention requests retrieve the city
from the live Aimee memory module. General and personal ID 5 remain distinct.
Memory text is separately encoded by frozen Qwen into native K/V states; it is
not part of the main generation prompt or its sequential cache positions.

## What changed

Aimee core owns a versioned `search-restricted` operation. The verified image
reader derives a namespace-qualified ID restriction from the signed Aimee
release grant. Rust transports it unchanged. Inside Aimee's PostgreSQL search,
ID restriction, scope and lifecycle checks precede ranking and LIMIT. An empty
ID set means no candidates. Ordinary `search` retains its existing behavior.

The new operation uses English full-text OR matching over noisy keyword clusters
and ranks the admitted candidates. This is an explicit lexical operation, **not
a claim of full hybrid/graph retrieval equivalence**. It has no city/drink/entity
special cases. The restriction is a narrowing filter, not an independent bearer
credential or new permission issuer. Exact response-content and canonical
identity checks remain mandatory after retrieval.

A successful restricted response acknowledges the applied namespace, grant
binding and exact candidate IDs. The gateway rejects a missing/mismatched
acknowledgement, including an older upstream silently ignoring the new field.
An acknowledged empty array is now an authorized no-match result. Legacy empty
responses remain rejected, and authorization failures are never converted to
misses. The image guard checks the namespace on returned facts, so a general
fact with the same numeric ID cannot impersonate a personal one.

The tested upstream is the new owner-only Unix ingress `aimee-memory-read`,
which invokes the **existing live Aimee memory module over its module bus**.
The module accesses PostgreSQL through Aimee's existing store bus. It is not a
Python service, database replica inside the adapter, or fixture-answer server.
This ingress exposes only restricted search and fixes the upstream namespace in
trusted configuration. It is currently server/user-scope only. The underlying
Go search has separate KB-scope tests; this does not establish a KB HTTP deployment.
The legacy C HTTP handler was not changed or deployed for this experiment.

## Why the earlier comparison was misleading

The deployed primary C server used the older fact-retrieval path, while the
working-tree migrated handler uses strict ordered multiword matching. Matching
memory-module executable hashes was insufficient to prove those instances
executed the same search path. Their different outputs therefore did not
isolate a model or native-memory defect. This run explicitly exercises the new
Go operation, removing that ambiguity without claiming retriever parity.

## Checks and reproduction

- Six Rust unit tests; rustfmt and Clippy with warnings denied.
- 26 gateway test executions, including inherited authorization/identity checks
  and four new restricted-upstream cases. This is not 26 independent scenarios.
- Race tests for Aimee memory, sparse images, image CLI and restricted ingress.
- Real PostgreSQL integration: excluded higher-ranked row cannot starve the
  allowed top-one result; singleton/empty restrictions; missing and operator-like
  queries; retired/expired facts; KB scope, activation suppression and future
  validity. Temporary tables and a rollback-only schema are used for this test.
- Five live module probes exercise both approved records, each singleton, an
  empty restriction and an unmatched query through the actual module bus.

Run from `aimee-qwen`:

```sh
go -C ../aimee/server-go test -race ./modules/memory ./modules/memory/sparse ./cmd/aimee-memory-image ./cmd/aimee-memory-read
cargo test --locked --no-default-features
cargo clippy --locked --no-default-features --all-targets -- -D warnings
RUST_QWEN="$PWD/target/debug/aimee-qwen" \
 AIMEE_IMAGE_READER="$PWD/.local/bin/aimee-memory-image" \
 AIMEE_FIXTURE_ISSUER="$PWD/.local/bin/aimee-issue-fixture" \
 PYTHONPATH=integrations/qwen_aimee python3 -m unittest -v test_authorized_gateway
```

The database test additionally needs `AIMEE_TEST_DATABASE_URL` pointed at an
explicitly disposable PostgreSQL instance. The live research drivers are in
`benchmarks/layered_memory/restricted/`. They use fixture signing and a dedicated
Compose project; they are not production installation scripts.

## Remaining boundary

This proves the small, authorization-restricted combined consumption path.
Production grant issuance, membership evaluation, rich evidence/episode release,
automatic invalidation publication, broad general-KB discovery, scale and
retrieval-quality parity remain separate work. The general reads are exact
published contracts. The restricted fallback currently caps grants at 4096
numeric IDs per upstream namespace. It must be redesigned for large grants;
this run provides no evidence about million-object performance.

The image remains 28 approved objects / 27 published read contracts / 46,541
bytes. Model-specific learning and authority decisions remain outside the Rust
adapter. No production Aimee service, memory or permission was modified.

After testing, the fixture grant is revoked and the temporary Rust model,
gateway and disposable Aimee containers are stopped. No production service was
switched. Tested binary hashes are retained with the artifacts. The source also
adds strict rejection of malformed module replies; that final ingress hardening
is covered by unit tests and built separately as
`/opt/aimee-qwen-rust/aimee-memory-read` for the next run.
