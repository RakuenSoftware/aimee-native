# General KB plus Aimee memory — initial implementation

Date: 2026-09-20. The Rust adapter now consumes canonical, namespace-qualified
knowledge objects from a combined authorized image and from Aimee fallback.
The native Qwen interface and zero-training constraint remain unchanged.

## What changed

The [starter general corpus](../../knowledge/general-v0/README.md) contains 25
public unit/prefix facts with structured semantics, source provenance and
content revisions. Its offline Go entrypoint invokes the existing Aimee image
compiler; it is not a new image implementation or an authorization issuer.

Aimee core now resolves authorized fact responses to canonical
`{namespace, id, revision}` references. Both local read contracts and remote
responses pass this gate. Rust uses namespace + ID for bank membership and the
full references in encoding-cache keys. Therefore `general/5` cannot overwrite
`server/5`. A new revision replaces the same canonical object. Identical text
in different objects is not semantically deduplicated by the adapter; Aimee owns
that decision. Legacy responses that cannot identify one unambiguous authorized
object are rejected rather than guessed.

The Rust gateway also provides a read-only `/resolve` operation, bound to the
same grant, for canonical identity resolution if the local reader transport has
failed. This verifies the supplied response against the authorized image; it
cannot create records, publish an image, or widen authorization. Explicit local
rejection remains terminal, including during resolution.

## Serving composition

```text
general source → optional KB additions → server memories/resolutions
                                         ↓
                              Aimee-authorized snapshot
                                         ↓
                     published local reads / Aimee fallback
                                         ↓
                           canonical object references
                                         ↓
                        Rust → frozen Qwen native K/V
```

There is one model-visible logical image. The adapter does not fan out to three
independent stores or decide which source wins. Aimee applies explicit scoped
suppression, redirect/deduplication and lifecycle decisions before export.
Unknown, complex, stale or unsupported reads retain the existing fallback;
lexical similarity alone is not permission to answer from a local record.

Production authorization and rich episode/evidence release codecs remain
unfinished. This work does not claim full offline Aimee replication, automatic
model generation switching, a broad general corpus, or production sync. A
changed signed grant still requires a freshly authorized image/client session;
it cannot silently replace a running request's authorization.

## Reproduction

```sh
go -C ../aimee/server-go build -o "$PWD/.local/bin/aimee-memory-image" ./cmd/aimee-memory-image
go build -o .local/bin/aimee-issue-fixture ./benchmarks/local_memory
go build -o .local/bin/aimee-kb-seed ./cmd/aimee-kb-seed
go test -v ./cmd/aimee-kb-seed
go -C ../aimee/server-go test -race ./modules/memory/sparse ./cmd/aimee-memory-image
cargo test --locked --no-default-features
cargo build --locked --no-default-features
RUST_QWEN="$PWD/target/debug/aimee-qwen" \
 AIMEE_IMAGE_READER="$PWD/.local/bin/aimee-memory-image" \
 AIMEE_FIXTURE_ISSUER="$PWD/.local/bin/aimee-issue-fixture" \
 PYTHONPATH=integrations/qwen_aimee python3 -m unittest -v test_authorized_gateway
```

The live research scripts use existing approved synthetic Aimee rows and fresh
fixture grants on `.253`. They are not production issuance or corpus-import
commands. Their signing keys/source store are inaccessible to the model.

## Verified storage, identity and enforcement checks

- Six Rust unit checks pass, including same numeric ID across namespaces,
  replacement by revision, preserving distinct same-text objects, and rejection
  of unqualified native facts.
- The real Go image reader and Rust gateway/client pass the six existing
  authorization scenarios plus four native-identity scenarios (16 executions
  because the fixture subclass reruns the six inherited cases). Native checks
  cover local/remote identity parity, forged reference rejection, revocation,
  and guarded fallback after terminating the local reader process.
- The starter build is deterministic. Its control-plane objects occupy 26,734
  bytes. Private-scope rows and missing provenance are rejected by the seed path.
- Both direct and optional-KB paths compile authorized layered snapshots. The
  optional-KB case actually includes an approved project record, while another
  project's canary and withheld local bytes are absent from the delivered image.
- Aimee suppression of a base fact invalidates the old export approval and read
  contract. A fresh narrowed approval compiles successfully. This tests applying
  an explicit Aimee decision, not learning contradictions locally.
- Aimee sparse-image and CLI tests pass with the race detector, including new
  canonical-reference collision and ambiguous-response cases.

## First live run and retained failure

All 25 source queries resolved through the signed local image and Rust client.
A direct mixed read returned both `aimee-general-v0/5` and
`aimee-published/5`, demonstrating that the same bare ID is preserved separately.
However, the first single-entity native-composition question was rejected during
its subsequent model-attention read. The upstream returned IDs `[5, 7]`; only
5 was in the model's grant. The gateway rejected the whole response before any
record-7 content entered model state. Existing private-memory composition still
returned `oolong;Lima`.

This is a remaining limitation of the broad upstream connection and conservative
research egress guard, not evidence of native composition success or failure.
Production needs Aimee retrieval bound to the caller's actual authorization;
export filtering alone does not make broad remote search authorization-aware.
The implementation does not silently drop unauthorized rows, convert denials
into misses, or expand the model's grant. A failed request now writes a protected
trace of its request and previously authorized events; rejected upstream payloads
are not recorded there.

The follow-up question names both already-approved private entities, while the
approved corpus is unchanged. Its local contract supplies the general canary
and one private memory; subsequent Aimee reads can supply the second private
memory. This explicitly tests cross-source three-value composition. The canary
exists only in the research general layer and is **absent** from the real starter
corpus. Do not mistake the resulting fixture routing for general semantic recall.

## Live outcome: functional read path, combined generation not cleared

The second broad-upstream run also rejected mixed composition. Naming both
approved private entities did not remove the out-of-grant retrieval result.
The [initial results](artifacts/layered-kb-2026-09-20/initial-live-results.json),
[three-field results](artifacts/layered-kb-2026-09-20/broad-upstream-three-field-results.json),
and [upstream diagnosis](artifacts/layered-kb-2026-09-20/upstream-diagnostic.json)
are retained as failures, not rewritten as successes.

A disposable Aimee instance was then created in its own Compose project inside
CT 103 with copies of only the two approved synthetic personal records. Its
schema and migration ledger came from the previous disposable scale-test DB;
no production tables, permissions or memories were mutated. The deployed memory
module's binary hash matched the primary instance. The general KB and canary
remained in the separate signed serving image. The same Rust gateway used the
isolated authority's Unix API; no Python process served memory or the model.

That instance returned no facts for the attention-generated multiword query,
although an exact single-entity lookup returned its record. The conservative
egress guard rejects empty/non-releasable results identically, so mixed and
personal-attention generation were blocked. The replica therefore did **not**
establish equivalent Aimee retrieval behavior. Copying two canonical rows and a
schema is insufficient evidence that a full Aimee knowledge environment has
been reproduced; the cause of that retrieval difference remains unestablished.
[Isolated outcomes](artifacts/layered-kb-2026-09-20/isolated/results.json) remain
failed checks. They are not evidence of a neural composition limitation.

Across those runs, all **25/25 starter queries** resolved correctly through the
actual Rust client and signed reader. The combined authorized image contained
25 real general records, one separately labeled synthetic general canary, and
two approved personal records. Its physical size was **46,541 bytes**, including
27 exact read contracts and authorization data; one withheld personal canary
was absent. The standalone real general source was **26,734 bytes**. These are
small functional fixtures, not scale or performance evidence.

The public/private identity collision is verified at the source-to-Rust boundary
and in bank-merge tests. **Full-Qwen combined-answer acceptance is still open.**
The next integration dependency is authorization-bound Aimee retrieval (plus
explicit authorized abstention semantics), without inventing selection or
permission policy in the adapter. Current exact published reads remain useful;
unknown general queries are not promoted to local answers by lexical guessing.

Temporary Qwen/gateway services and the disposable Aimee containers are stopped
after validation. Research grants are revoked. The final binary remains at
`.local/bin/aimee-qwen` locally and `/opt/aimee-qwen-rust/target/release/aimee-qwen`
on `.253`; it must be used with the updated Aimee image reader. No production
service was switched to this build.

## Follow-up

The [restricted upstream implementation and full-Qwen run](restricted-kb.md)
now clear the combined-answer check, including an excluded distractor and grant
revocation. The failures above remain historical evidence.
