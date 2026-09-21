# Aimee local sparse memory

State: agreed persistent local knowledgebase with Aimee fallback, 2026-09-20.
The existing implementation is an earlier, partial storage/reader slice.
The complete design is not yet implemented. See the
[implementation and validation report](../../validation/aimee-local-sparse-memory.md)
and [usage/coverage](../../../../aimee/server-go/modules/memory/sparse/README.md).
Starting point: [native-memory POC and corrected baseline](../../validation/qwen-aimee-poc-baseline.md).

Validation correction: the lexical prototype is not quality-equivalent to Aimee.
Its lookup and answer timings must not be used to justify the architecture.
Expanded graph storage may use more RAM/disk; preservation of Aimee retrieval,
contraction, contradictions, evidence, and mutation semantics is the gate.

## Agreed responsibility boundary

The core is a persistent, continuously updated knowledgebase. Published general
knowledge is present before the first request; optional KB enrichment and
server-local knowledge remain part of the distribution design. A cache of
previous requests or native payloads is an optimization around this core.

Aimee owns all learning, knowledge creation, semantic deduplication/contraction,
contradiction handling, overrides, rewrites, and policy decisions. The local
knowledgebase stores and applies Aimee's published results. It performs lookup
and checks the supplied scope, validity, revision, and coverage conditions; it
does not learn, resolve uncertain knowledge independently, or become a second
Aimee implementation. The model adapter translates requests and transports
model-consumable states. No adapter training or local knowledgebase learning.

Both prompt preload and model-native requests try local lookup first. A clear,
valid result can be consumed locally. Missing, ambiguous, stale, or unsupported
results go to Aimee. A lexical match alone is not a completeness or eligibility
certificate. The precise local-result contract and fallback conditions must be
specified and validated against Aimee rather than learned by the adapter.

Aimee may answer the current request and publish an update that improves future
local requests. A response is not automatically permission to persist or reuse
it outside its authorized context. Updates and invalidations also arrive
proactively: an obsolete result can appear clear and never generate a miss.

```text
Prompt preload / native model request
                  |
          local knowledgebase
           /               \
 clear, valid result    missing / unclear / stale / unsupported
          |                         |
 native model delivery       Aimee retrieval and governance
                                    |                 |
                           immediate delivery   authorized local update
```

Full offline reproduction of every Aimee decision is not a prerequisite.
Preserve Aimee behavior across the combined local-plus-fallback system. Aimee
calls are an intended part of the architecture; measure their frequency and
cost rather than treating every call as failure. Extra RAM/disk for expanded
knowledge and indexes is acceptable.

## Read-only model boundary

The model cannot change the persistent knowledgebase. Native requests, prompt
preload, and adapter responses are read-only operations. Neither the model nor
its adapter may create, edit, delete, merge, promote, re-scope, or invalidate
knowledge, or publish a generation. Model output and tool arguments do not
confer update authority.

Aimee evaluates proposed changes using its existing learning and governance
machinery. Only a separate Aimee-controlled publisher/updater can apply approved
knowledge, index, eligibility, and native-payload changes. A model may provide
observations or proposals through Aimee's existing intake, but those are inputs
for evaluation, never direct writes to the local store.

Enforce this as a capability boundary, not a prompt instruction:

- The model-facing API exposes reads only, including local lookup and Aimee
  recall. It exposes no publication or mutation operation.
- The reader/adapter has no authoritative store-write credentials or image
  publication authority. Authoritative image objects and manifests are mounted
  or opened read-only under a distinct reader identity.
- The Aimee-controlled updater has separate write authority and verifies the
  authorized source and generation before publication. Claimed approval in
  model text or retrieved content is not authorization.
- Runtime cache bookkeeping is separate from knowledge publication. It may
  retain validated read results or deterministic encodings within their reuse
  conditions; it cannot turn generated content into authoritative knowledge.

A fallback read may cause Aimee to evaluate and subsequently publish an update,
but the model request itself cannot select or approve that mutation. Test
rejection of model-originated writes, forged update claims, and attempts to
bypass Aimee evaluation, as well as successful authorized publication. The
current prototype's same-user file permissions do not yet establish this
separation; it is a required implementation milestone.

## Intended result

Provide the model with sparse, fast, local access to Aimee knowledge while
preserving Aimee's memory capabilities. "Sparse" means each request reads a
small relevant subset; it does not mean discarding the rest of the knowledgebase
or reducing Aimee's semantics to exact n-gram matches. SSD holds persistent
state; system RAM holds indexes and cached pages. Do not require a persistent
VRAM memory bank.

Engram is an inspiration, not a selected architecture or required format.
Neither Qwen's PLE layout nor the POC's K/V representation is the final design
by default. The layout below is a candidate serving organization; choose its
indexes and native payload codec by measured recall, locality, update behavior,
and end-to-end consumption cost. Keep knowledge identity, lookup, storage, and
model delivery separable so those choices can change independently.

```text
Published general knowledgebase
    |                         |
    v                         | direct path when no KB is configured
optional aimee-kb             |
    | adds KB-specific        |
    | knowledge and updates   |
    v                         v
              aimee-server
                  | adds local memories and adjustments
                  | applies Aimee deduplication and governance
                  v
        combined local serving graph
           NVMe + RAM indexes/cache
                  v
        local reader -> model adapter -> native consumption
```

Both prompt-based preload and Qwen native requests reach this same local reader.
Locally answerable requests do not require a synchronous upstream call. Other
requests use the configured Aimee authority; that authority may itself be local
or remote. Synchronization also runs independently of request misses. If Aimee
is unavailable, retain only behavior permitted by the synchronized knowledge's
validity contract and surface unresolved requests rather than inventing answers.

## Source ownership: publication, optional KB enrichment, local server

The general knowledgebase is a published artifact, separate from any particular
`aimee-kb` deployment. An `aimee-kb` consumes it, incorporates its own specific
knowledge and corrections, and exposes an enriched distribution to connected
servers. `aimee-server` consumes either that KB-enriched distribution or the
published general knowledgebase directly, then adds its own local memories and
adjustments. The model reads the resulting combined local graph.

| Layer | Responsibility | Consumed by |
| --- | --- | --- |
| Published general base | Broad reusable knowledge and versioned general releases | `aimee-kb`, or `aimee-server` directly |
| Optional KB enrichment | KB-specific knowledge, relationships, additions, corrections, deduplication, and governance | Connected `aimee-server` instances |
| Server-local enrichment | Local/user memories, preferences, configurations, relationships, and adjustments under existing Aimee scope and mutation semantics | The model's local reader |

The KB is an optional enrichment stage, not the origin of all general knowledge
and not a prerequisite for local native memory. Both supported paths are first
class:

```text
published general -> aimee-kb enrichment -> aimee-server enrichment -> model
published general ---------------------> aimee-server enrichment -> model
```

A temporary loss of KB connectivity does not by itself mean switching to a
bare general image and discarding previously synchronized KB knowledge. The
server can continue from its last locally available, authorized generation
subject to the applicable validity and scope rules. Attaching or detaching a
KB is an explicit source/view transition; preserve server-local memories and
reconcile their dependencies during that transition.

## One local graph, layered physical storage

Keep the general base, KB changes, and server-local changes separately
identifiable. Physical overlays and shared pages avoid copying the entire
general graph for every KB and user. The reader exposes one logical graph;
the model and its adapter do not implement three separate memory systems.

All layers use compatible logical record/index/payload contracts and the same
RAM/NVMe storage policy. General pages can be shared; KB and user pages, as well
as cached request results, remain within their authorized scopes. Producing
the published general corpus and its serving image is a separate deliverable.
The working personal-memory POC does not already supply that image or a
compatible Qwen PLE table.

The local reader returns a bounded working set from any applicable layer. A
hardware question might combine general device specifications, KB-specific
project requirements, and the user's local workstation configuration. Preserve
each record's source namespace and evidence through native delivery. No
additional model adapter is needed for each knowledge origin.

Use namespaced identities such as `(knowledge_base_id, record_id, revision)`.
Numeric ID equality across layers is not deduplication. Aliases point to their
canonical records; cross-layer edges can reference stable upstream entities
without copying their whole subgraphs. Record the referenced revisions where
correctness depends on them. An upstream change invalidates affected dependent
artifacts, not every artifact at every downstream installation.

A valid more-specific fact may qualify an applicable general default. There is
no unconditional "last layer wins" rule for factual contradictions. Aimee's
existing scope, provenance, temporal, and contradiction semantics govern local
adjustments. This policy belongs to Aimee, not the model adapter. A local change
does not silently publish private knowledge into a KB or the general release.

## Update lineage across the three stages

Each stage owns its changes and publishes a versioned manifest identifying its
exact upstream dependency:

```text
general release G
    -> optional KB view K, based on G
        -> server view S, based on K (or directly on G)
```

A KB incorporates a general update, reconciles it with its own changes, and
publishes a new consistent view. A connected server then incorporates that
view and reconciles its local changes. A standalone server follows general
releases directly. Do not independently advance the general layer underneath
a KB view that was compiled against a different general release.

At each stage, preserve local additions and use Aimee's existing contradiction
and supersession rules for overlaps. Do not overwrite local records, resurrect
locally retired facts, or resolve contradictions by import order. Retain the
upstream revision against which each adjustment was made.

Each request pins the published server-view manifest and its complete source
lineage. Cache keys include source namespaces and revisions, authorization
scope, and model/codec identity; combined query-result caches also identify the
composed view. Publish a replacement view atomically after its dependencies and
local changes are consistent. Unaffected payloads remain reusable.

For example, a general release supplies device entities; a KB adds its project's
hardware requirements; the server records the user's actual workstation and
local exceptions. A new general or KB release updates inherited knowledge
without erasing the user's configuration. Any upstream promotion of local
learning is a separate governed operation.

Validate both deployment paths, combined consumption across all present layers,
user/KB isolation, independent updates, attachment/detachment, cross-layer
dependencies, and deletions. Required records must actually reach the model
before judging a joint answer's composition behavior.

## Knowledge and deduplication

Export authoritative identities and versions, canonical content, entity and
relationship links, aliases, provenance references, scope, temporal validity,
lifecycle, supersession, and dependency information. Preserve the results of
Aimee's existing deduplication and contradiction handling. A model codec may
initially support only some record types; report coverage and unsupported types
rather than silently presenting a partial export as the whole knowledgebase.

Multiple cues and aliases point to one canonical record. They do not duplicate
its native payload. Preserve deduplication redirects and lineage where Aimee
supplies them; do not infer new semantic equivalences in the exporter or adapter.
Physical payload sharing does not merge authoritative identities or scopes.

Aimee remains responsible for learning and semantic deduplication. Local updates
apply Aimee's resulting record changes and redirects. Any future local authoring
must use Aimee's mutation semantics, not create a second writer in the adapter.

## Logical image layout

| Structure | Contents | Main residence |
| --- | --- | --- |
| Manifest | Knowledge-base identity and kind, generation, format, source identity, scope, compiler and codec identities | SSD and RAM |
| Retrieval indexes | Aimee lexical/cue postings, aliases, and applicable semantic and graph indexes | RAM; larger portions may be paged |
| Record directory | Canonical IDs, revisions, payload references, redirects, eligibility metadata | RAM or paged SSD |
| Relationship/dependency tables | Aimee graph links and reverse dependencies for invalidation | SSD with RAM cache |
| Canonical knowledge store | Portable source representation and evidence references | SSD |
| Native payload store | Model-specific compiled values, page directory, checksums | SSD with RAM cache |
| Delta journal and tombstones | New versions, retirements, merges, deletions, published generation | SSD and RAM overlay |

These are logical sections, not a decision to create seven new services or
databases. Start with one local reader and one image format. Reuse Aimee's
retrieval and governance definitions instead of reproducing them in the adapter.

Routing and payloads remain independent:

```text
many cues -> canonical record ID + revision -> one compiled payload
```

A cue hash match identifies candidates, not truth. Resolve hash collisions
against the stored cue identity. Apply existing Aimee scope and validity rules
before returning any payload. Expiry still needs a local time check; an active
bit exported yesterday cannot alone establish validity today.

Cheap cues are one local access path. Missing semantic or relationship coverage
must be visible and cause Aimee fallback when required by the request. Local
indexes can expand incrementally without duplicating every Aimee retrieval
lane. If a semantic lane is implemented locally, identify its compatible query
encoder as well as its document vectors; it must not learn independently.
Expensive discovery belongs at prefill or a working-set miss where practical.
The adapter must not implement a replacement ranker or deduplication policy.

## RAM/SSD serving and speed

The corpus and persistent caches live outside VRAM. Use RAM-resident indexes,
bounded candidate sets, contiguous value pages, and a bounded RAM page cache.
Group related records for prefetch where Aimee's entity structure supports it.
Demand paging handles cold SSD data; asynchronous prefetch prepares likely
records during prompt processing. Do not scan the full knowledgebase or repeat
remote retrieval on every generated token.

Prompt preload prepares a request's host-memory working set. Native requests can
read that set, fetch additional local pages, or fall back to Aimee. Cache recall
results only within Aimee's authorized reuse conditions. Cache model-consumable
payloads separately: a result may require revalidation while unchanged payloads
remain reusable. New knowledge or conflicts can invalidate a result even if
none of its previously returned records changed; source/scope generations may
provide conservative invalidation initially. The compiler performs expensive
model encoding ahead of serving where practical, without introducing local or
adapter learning.

The existing Qwen GPU attention path consumes device tensors. A host-resident
image therefore does **not** by itself mean zero GPU transfer or zero temporary
VRAM use: selected states may need to cross to the accelerator for consumption.
The proposed policy is no persistent GPU corpus or retained GPU memory bank.
Only bounded temporary consumption buffers are allowed, with sizes and lifetime
measured. CPU-side native-memory computation is an alternative to investigate,
not an established fast replacement for the current attention implementation.

Speed must include lookup, RAM/SSD misses, host/device transfer, and actual model
consumption. Report warm and cold latency separately, together with throughput,
RAM use, SSD reads, transient VRAM use, and factual results. A fast index alone
does not establish a fast native-memory system. Do not silently omit required
records to meet a latency target.

## Knowledge objects precede model projections

The canonical knowledge object is authoritative in Aimee; a latent vector never
is. Preserve its semantic representation, provenance, relationships, scope,
validity, and revision independently of retrieval indexes and native payloads.
The local knowledgebase holds published copies and derived serving artifacts.

```text
Knowledge object
  + canonical semantic representation
  + provenance, relationships, scope, lifecycle and validity
  + retrieval/index representations
  + model-native projections
      + Qwen 27B / exact model and codec revision
      + other Qwen / exact model and codec revision
      + GLM / exact model and codec revision
      + other supported models
```

Updating a model or evicting a projection must not lose knowledge. A source
change invalidates affected projections; recompile them from the canonical
objects under Aimee control. Model-native output cannot rewrite the source.
This permits knowledge capacity to grow independently of model parameter
count. It does not imply that parameter count alone determines reasoning
quality, nor that a smaller model can use every external fact equally well.

## Native representation: reference codec, not a commitment

The current working representation is separately encoded frozen-Qwen K/V state.
Use it as a correctness reference when evaluating representations, not as an
assumption that cached K/V will meet the RAM/SSD bandwidth target. No adapter
training is permitted. Store portable
Aimee knowledge separately from target-specific payloads so a codec can later
change without changing memory identity or governance.

An artifact must identify its ordered source IDs/revisions and hashes, exact
model/weight and tokenizer identities, quantization, codec version, layer layout,
position convention, tensor shapes/dtypes, and payload checksum. The current
attention-to-search translator also requires token-slot address metadata. Keep
that metadata outside the main prompt; a tensor blob alone is insufficient to
reproduce the present request path.

Current successes encoded the selected records together. They do not establish
that independently compiled per-record K/V blocks can simply be concatenated
without changing behavior. First preserve exact whole-bank artifacts as a
reference. Then test independently compiled records and small stable bundles
with both required memories actually present. Do not assume the result.

If independent blocks work, they give useful incremental replacement and payload
reuse. If they need a different position/assembly convention, change and validate
the model codec rather than teaching the adapter fact-specific behavior. A
compact vector codec may follow, but is not already proven by the K/V results.
Precompiled K/V also must not be advertised as storage compression: measure
artifact size and bandwidth, including all retained layers.

## Incremental updates

1. Aimee commits an authoritative mutation, including any deduplication,
   supersession, scope, or dependency consequences.
2. The compiler produces changed records, postings, tombstones, and affected
   payloads. A bundle is stale if any required source revision changed.
3. Write and verify an immutable local delta. It names its parent generation.
4. Publish the new manifest atomically only after its referenced data is ready.
5. The reader switches generations and invalidates affected RAM cache entries.
   Compact old deltas into a new base in the background.

Retirement must not wait for a replacement payload to finish compiling: publish
the invalidation first and expose the replacement only when it is ready. A
missing or incompatible artifact is a visible miss, not permission to serve a
stale value. Validate update ordering and reject incomplete or wrong-parent
deltas. New readers must see a consistent generation, never mixed records and
indexes from partially applied updates.

Offline readers know only their synchronized generation. Expose that generation
and sync age; do not promise awareness of unseen upstream deletions. Likewise,
removing a payload cannot erase information already incorporated into a running
model's state. New-request invalidation and revocation of an active request are
distinct contracts; strict revocation may require ending that request. Do not
claim that deleting a disk row makes a model forget retrospectively.

## Next implementation milestone

Define and implement the local-first request contract, Aimee fallback, and
Aimee-issued update/invalidation path around the existing native adapter.
Reuse the current image components where suitable; their lexical coverage is
partial and cannot stand in for complete Aimee behavior.

1. Separate the read-only model/adapter identity from the Aimee-controlled
   updater. Load persistent general knowledge, with optional KB and server-local
   layers.
2. Return explicit local outcomes and the source/validity information supporting
   reuse. Route unclear or unsupported requests to existing Aimee retrieval.
3. Deliver results through the proven native path. Only Aimee-authorized
   publications change persistent local knowledge; ordinary reads do not learn.
4. Apply proactive corrections, contractions, contradiction resolutions,
   supersession, and invalidations without waiting for a request miss.
5. Replay Aimee's authoritative decisions through the combined system and
   verify eligible/excluded records, relationships, evidence, and native answers.

Keep the successful two-fact native-only and hybrid cases as regression
controls. Benchmark the combined system against the same external Aimee
adapter at equivalent quality. Include local hits, cold misses, unclear
results, and mutations; report fallback rate, encoding reuse, and total latency.
Measure correctness during updates as well as stable reads. Neither a partial
local reader alone nor a warm-cache-only workload establishes the advantage.

## Authorization-specific KB creation (2026-09-20 refinement)

Authorization precedes distribution. An organization-wide KB must never be
handed to a user server or model with the expectation that query filtering will
hide its other records. The owning Aimee control plane first evaluates the
requester's authenticated authorization, then compiles only the approved
knowledge into the delivered image. Model text can request access but cannot
issue grants, widen scopes, select another principal, or authorize publication.

One server may host models with different grants. Each serving session binds
to a trusted authorization subject/cohort, policy revision, expiry, and approved
object revisions. Distinct grants get distinct materialized images and native
cache partitions. Identical complete grants can reuse the same image; native
projections additionally require model/codec compatibility. Shared weights,
storage, a server address, or a "global" scope label do not confer knowledge
access. Aimee may explicitly grant an entire knowledgebase when appropriate.

The prototype now verifies signed grants and builds fresh directories containing
only approved canonical serving fields. It drops source ancestry, historical
versions, opaque metadata, aliases and graph edges from this initial release
format. Those omitted fields remain authoritative in Aimee and require explicit
field-level release support before distribution. Read decisions are separately
approved by digest; no unchecked ancestor decisions carry forward. Latent
bundles must eventually carry all source dependencies and must not contain
unauthorized constituent knowledge.

Unfiltered archives and PostgreSQL snapshots are internal control-plane backups,
not model-serving images. Their CLI operations require an explicit internal
backup flag. Normal native serving requires a verified authorized image and a
matching read gateway. Protect the authority's source files, credentials,
signing key and other grants' traces with separate OS identities and directories.
A new narrowed grant uses a fresh directory and session; retaining old objects
beside a new CURRENT pointer is not authorization isolation.

Fallback must preserve the same authorization. The current memory.search API
connection can have broader appliance access than a model's grant. Until Aimee
supplies suitably delegated credentials and response authorization, a separate
control-plane gateway checks the complete response against the fixed grant.
Any unapproved record, changed content, unsupported metadata or episode payload
rejects the entire result. It does not silently return a truncated answer. Empty
and denied responses share an unavailable outcome to avoid an obvious existence
status oracle; timing side channels have not been assessed.

This is enforcement infrastructure, not a new authorization policy engine.
The experiments use explicit signed research grants. Integration with Aimee's
actual authenticated grant issuance, field-level permissions, policy changes,
revocation and scoped richer retrieval remains required before organization
memory is deployed. A signed fixture is not evidence of that integration.

An explicit denial from either the local reader or remote authority terminates
the current memory request. It must not become a cache miss, trigger fallback to
an older grant, or permit a subsequent local hit in that request. An unavailable
local transport may still fall back to the independently authorized gateway.
Permission changes require coordination of trusted grants, image publication,
and session admission; the adapter cannot manufacture this coordination.

Source tracing confirms that `execution-policy` currently implements tool policy,
not the proposed `ContentVisibilityDecision`. Follow the existing
[content-visibility ownership proposal](../../../../aimee/docs/proposals/pending/per-user-content-scope-visibility.md)
for canonical policy ownership. The KB's existing authenticated service/caller
intersection and tenant transaction are useful inputs, but scope normalization
and an appliance-local memory read are not model-specific export permission.
Do not sign a model KB from these alone. See the
[transition test report](../../validation/aimee-authorization-transitions.md).
