# Aimee-driven incremental local KB updates

Status: initial live-source record stream and selective native cache retention implemented.
See [implementation and measured validation](../../validation/incremental-publication.md).
The broader architecture below remains a design direction, not a claim of full
Aimee policy/graph parity.

Aimee should continuously publish changes to the recipient's local KB. Model
requests should consume that KB; they should not trigger repeated reconstruction
of unchanged knowledge or its model-specific encodings. Aimee remains responsible
for learning, resolution, deduplication, authorization and release decisions.
Neither the adapter nor the local KB makes those decisions.

## Two separate kinds of change

1. **Authoritative knowledge changes.** Aimee sends the admitted upserts,
   removals, redirects, cue/index changes and dependency invalidations. A local
   consumer stages and applies a complete generation atomically.
2. **Working-set changes.** Aimee/local lookup selects a different combination
   of existing records for a model request. This should reuse their existing
   native encodings. It is not a knowledge update.

A streaming transport alone cannot solve repeated native encoding: the current
baseline encodes selected records jointly, so one additional record changes the
encoder context for the bank. Independently reusable record encodings must first
be tested for answer quality and composition. They are derived artifacts, never
the canonical knowledge objects.

## Proposed update contract

Use the existing authenticated Aimee connection. Authorization is resolved before
bytes are released; do not add model-side permission decisions.

Each recipient stream needs an issuer-controlled publication identity, previous
and new generation identifiers, and an atomic transaction boundary. Transactions
carry changed canonical records and explicit removals, plus changed routing data
and invalidated dependencies. Record identity includes namespace, ID and revision.
A revision alone is insufficient for artifact reuse: include payload hash and
model/tokenizer/encoding compatibility. No domain-specific interpretation belongs
in the adapter.

The consumer must reject an unexpected predecessor or incomplete transaction.
Replay of an already committed transaction must not apply twice. Reconnect resumes
from the last durable committed generation; an unavailable history requires a new
authorized snapshot. Initial bootstrap and recovery may use whole snapshots;
ordinary record changes should not require them.

Once a complete transaction is validated, unchanged record artifacts can survive
a generation switch. Changed records lose their old artifacts; removals delete
local record access and cached artifacts; dependent artifacts are invalidated as
specified by Aimee. A missing/expired authorization or withdrawal retains existing
fail-closed behavior. Already emitted model output cannot be retracted. Active
sequences need an explicit generation policy; do not silently mix generations or
claim that clearing an artifact cache removes facts already incorporated into
transformer state.

Encoding may run on demand or in a background compiler using the frozen model.
Publishing canonical KB bytes need not wait for every possible model projection.
Unchanged encodings should survive unrelated updates once the transaction contract
makes that safe. Initial in-process cache work does not yet provide persistence
across runtime restarts or proactive projection compilation in Aimee.

## Current implementation boundary

- `aimee-memory-publish` reads exact released IDs from actual Aimee storage and
  streams changed records/cues/removals; its source reconciliation polls once a
  second. It uses a server-owned recipient/UID/scope/ID release policy.
- `follow-published` stages and verifies deltas, commits atomically, resumes from
  private durable state, and withdraws delivery on connection or policy failure.
- Changed canonical records are transferred incrementally. Large routing manifests
  and lookup indexes still undergo expensive reconstruction/validation.
- Rust's optional record cache retains exact unchanged records across generations;
  changed/removed/unprovable entries are invalidated. Active requests abort on a
  generation change. In-process caches do not survive model restarts.
- Full organization-policy integration, rich episode/graph release codecs, source
  history compaction, and persistent/background native projection compilation
  remain outside this initial slice. Deduplication stays in Aimee.

## Required evidence for incremental publication

Measure a single admitted update against an unchanged large base: changed records,
bytes transferred, records encoded, encoding time and time until the next read sees
the change. Verify that unrelated artifact hashes remain identical. Include adds,
replacement, deletion, supersession, cue changes, Aimee deduplication/redirects,
and authorization narrowing. Test duplicate delivery, reordered/missing batches,
crash before/after commit, reconnect and dependency invalidation. Compare Qwen
answers with the current complete-bank baseline using the same prompts and
selected record identities; do not confuse retrieval differences with encoding
quality.
