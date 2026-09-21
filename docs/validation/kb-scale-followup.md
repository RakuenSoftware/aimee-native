# Larger local KB and follow-up validation

Date: 2026-09-20. Work follows the [published local delivery](local-delivery.md)
implementation. Qwen integration, corpus, drivers and evidence stay in this
repository; generic publication/retrieval code stays in Aimee.

## Corpus growth and retrieval

The corpus grew from 13,261 to **249,105** canonical public objects. The original
four registries are unchanged. The addition is 235,844 populated-place records
from the pinned [GeoNames cities500 export](https://download.geonames.org/export/dump/readme.txt),
attributed under CC BY 4.0. Canonical JSON occupies 318,559,559 bytes; factual
bodies alone occupy 54,535,429 bytes. No synthetic padding or query-answer read
contracts were added. Source manifests, hashes and rebuilding instructions are
in [general-v2](../../knowledge/general-v2/README.md).

The same release Rust adapter and Go reader ran on `.253` as the unprivileged
model account, with no available fallback gateway. The 100K and 249K corpora
retain every original record. Each size tested every record's canonical identity
and exact content, the original 34 query result sets, 100 two-record queries and
100 missing records. These measure named-address retrieval, not Qwen accuracy
or unrestricted semantic retrieval.

| Objects | Same 256 queries median | Mixed 512 queries median | Reader startup | Compiled image bytes | Go reader RSS |
|---:|---:|---:|---:|---:|---:|
| 13,261 | 0.054161 ms | 0.053873 ms | 0.682851 s | 12,734,494 | 88,504 KiB |
| 100,000 | 0.057226 ms | 0.058578 ms | 3.263585 s | 104,962,072 | 678,996 KiB |
| 249,105 | 0.057277 ms | 0.067510 ms | 8.453328 s | 267,391,338 | 1,798,644 KiB |

All exhaustive lookups passed: **13,261/13,261; 100,000/100,000;
249,105/249,105**. Every query-set, composition and miss check passed at all
three sizes. The largest image's source build took 18.925016 s and authorized
compile took 21.298187 s. RSS above is the Go reader only; Rust/libtorch process
RSS was respectively 660,248, 717,148 and 814,952 KiB. These are warm serial
lookup timings on a shared research host, not controlled production speedups or
comparisons against equivalent remote Aimee retrieval.

[Raw size results](artifacts/kb-scale-2026-09-20/summary.json).

## Publisher and download lifecycle

Aimee's image CLI now has `sync-published`, which consumes independently issued,
revision-bound approval and reconciles an authoritative source into managed local
delivery. It supports one-shot operation and periodic `--watch`. Changed source
without matching approval, missing/rejected/expired approval, and failed source
validation withdraw the delivered generation. Compilation is staged privately;
source and approval are checked again before installation. The model receives no
grant or signing key. An unchanged generation recovers abandoned staging files.

The generic `PublicationHandler` requires Aimee's authenticated API to resolve
the request to its approved, immutable recipient snapshot. It never accepts a
caller-provided source directory or scope. `fetch-published` uses HTTPS, the
existing Aimee client certificate and bearer credential, conditional downloads,
private staging, checksum validation and atomic installation. Redirects are not
followed. Denial, withdrawal, failed/truncated/oversized transfers withdraw the
old delivery rather than retaining potentially unauthorized bytes.

**Integration boundary still outstanding:** the current Aimee authenticated
search surface does not issue the signed per-recipient publication decisions
consumed by this publisher. The handler and client are implemented and tested;
mounting that handler in the production authenticated API and connecting its
resolver to the real release-policy issuer is not established by these tests.
Research corpus releases still explicitly use the fixture issuer. Existing
search permission is not silently promoted to permission to persist a whole
organization's knowledge. No production organization store was exported.

Publisher withdrawal is observed by new requests. Already-open sequence banks,
outputs and cached conversation text are not secure-erased; immediate revocation
requires quiescing active consumers. Periodic synchronization adds its configured
poll interval to detection time. An offline/stopped publisher cannot retract
bytes it previously delivered. The current implementation copies complete
snapshots, not incremental network deltas.

## Broader local coverage

Signed, explicit `ReferenceCue` mappings now bind approved cues to approved
canonical references. Source metadata, aliases, graph edges and provenance are
still not blindly copied into recipient images. Cues for unapproved records are
rejected before publication. Multiple records sharing a cue cause abstention;
Aimee remains responsible for resolving ambiguity.

The public-data compiler emitted **821,128 cues** from published names and typed
registry keys. These produce 683,779 unique addresses and 42,729 ambiguous
addresses. The expanded compiled image occupies 419,211,104 bytes. First full
reconcile/compile/install took 80.433062 s. With the actual Rust/local reader:

- 2,048/2,048 sampled unique alternate-name lookups returned the intended object.
- 256/256 sampled ambiguous names abstained (and attempted the absent fallback).
- Successful warm lookup median: 0.113353 ms; p95: 0.240263 ms.
- Reader startup with cues: 18.954158 s.

These are deterministic alias lookups, not a replacement for Aimee's semantic
retrieval. The complete cue map is larger than the canonical-key-only image and
makes index startup more expensive.

## Fallback relevance correction

A concrete source of seven earlier irrelevant personal-memory matches was
PostgreSQL's default compound-word parser. It indexes fragments of identifiers
such as `unit-121330aded`; queries containing measurement “units” therefore
matched those personal entities. Subsequent attention requests could then
reinforce the unrelated memory already admitted.

Aimee's restricted retrieval now preserves compound identifiers as whole lexemes
while retaining English stemming for ordinary words, positions for ranking,
OR matching of native attention keyword clusters, and authorization/scope/
lifecycle filtering before the limit. This is Aimee retrieval behavior; there
are no city/drink/domain rules in the adapter. Disposable PostgreSQL tests cover
exact identifiers, entity-fragment misses, ordinary-word matches, two-record
composition, scope/temporal gates, restricted top-one selection and operator-like
input. All passed against the actual PostgreSQL backend.

## Sustained publication tests

The initial unbounded 16-reader stress test exposed writer starvation in the
shared publication lock: the first replacement could wait indefinitely while
new reader opens continued arriving. It was interrupted and the evidence is
recorded here rather than counted as a passing test.

A short exclusive entry lock now prevents new shared opens from bypassing a
waiting publisher. It is held only while acquiring the publication lock, not
through ordinary pinned lookups. After the fix, a Go race-enabled run completed
50 replacements, 5 withdrawals/reinstalls, 50 restart recoveries and 6,125 reads
from 16 concurrent readers in 4.36 s, with zero read failures. A subsequent full
transport run observed 5,923 reads with zero failures. Read counts vary with
scheduling. Restart recovery includes simulated abandoned staging; it is not a
power-loss or filesystem durability certification.

HTTPS transport tests cover recipient denial before conditional responses,
replacement, withdrawal, raw-source rejection, partial transfers, redirects,
oversized transfers and service failure. Existing real Rust/Go local-delivery
integration tests also pass. No model trains or writes knowledge in these tests.

## Native-consumption investigation

The runtime exposes `memory_encoding` (`content`, `keyed`, `json`) for controlled
experiments on the **separate frozen memory encoder**. The default remains the
previous content form. Keys and content are transported without domain-specific
rewriting. The main generation prompt contains no injected memory. This is
separate tokenization/encoding into native attention K/V, not a claim that memory
is never tokenized anywhere. No adapter or model parameters are trained.

Full model results and bounded conversation/concurrency results follow below.

The second relevance change requires two shared lexemes for a noisy multi-term
cluster unless it contains an exact compound address. Precise single-term
queries remain supported. This removes the separate “city” overlap problem
without adapter domain rules. It is a conservative rule for the restricted
lexical fallback, not a claim to duplicate Aimee's full semantic ranking. Real
PostgreSQL tests cover the precision/recall boundaries explicitly.

The original expanded-image run completed 32/34, with exactly the old failures.
Keyed and JSON native encoding each recovered the personal-1 answer; neither
recovered the exponent. Disabling decode recall recovered neither. A separate
compiler ablation rendered finite NIST quantities using `Decimal` into exact
plain decimal notation. It updated 289 public records, with source values and
provenance preserved in metadata and fresh revisions. The original corpus files
and previous results remain unchanged. This is public KB rendering, not a
per-question rule in the adapter.

The update used the real publisher against the still-running Qwen process.
Recompile/replacement took 95.245312 s and copied 419,212,064 bytes; this is a
full-snapshot cost despite only 289 changed records. The next native request
returned `0.00152103220230` for the previously failing quantity and the next
mixed query returned `6115;oolong;Lima`. The first request included opening the
new image and took 30.410763 s; it is not a steady-state generation measurement.

The initial numeric-update driver incorrectly expected a JSON response from the
successful `publish` command, which is silent. It stopped after advancing the
private source, before changing the delivered image. The driver was corrected
to recognize the already-published immutable source and resumed. This was a
driver failure, not a model or publication failure.

## Completed model results and limits

The full keyed-format run scored **32/34** on the original questions and
**10/12** on new GeoNames population questions. Keyed encoding recovered the
original exponent/drink failures after numeric rendering, but regressed
`planet-3` and `planet-6` to `unknown` despite the correct records being present.
The content format recovered both planets in immediate follow-up; JSON also
failed them. Therefore the default remains content; keyed encoding is an
experimental option, not a generally better adapter. The separate
[keyed-encoding investigation](keyed-encoding.md) examines this tradeoff.

The two GeoNames abstentions were `Nuevo US` and `Lanne FR`. Their supplied names
are ambiguous across the approved cue map, so no record was admitted. These
are routing/disambiguation cases, distinct from the two native planet failures.
The raw population score remains 10/12; it is not relabeled as 12/12.

After both restricted-retrieval corrections, **zero public-only questions**
in the 46-query run admitted private facts, versus seven in the earlier baseline
and four after only the compound-identifier correction. The two intended
personal-memory composition questions still admitted the authorized personal
records. This is fixture-specific evidence, not broad retrieval-quality parity.

Four requests with 32 prior marker exchanges and two with 96 prior marker
exchanges passed. Those histories contain no target factual answers. Four and
16 simultaneous HTTP requests also all passed (4/4 and 16/16). GPU work remains
serialized: the 16-request group's median response time was 36.572203 s. This
measures correct queueing and isolation, not parallel decode throughput.

All native runs contain zero memory tokens in the main generation prompt.
The new public objects, personal records and canonical revisions are visible in
the recorded native traces. No adapter or base-model training occurred.
Raw results and summaries are in
[follow-up artifacts](artifacts/kb-followup-2026-09-20/).

## Subsequent native positioning correction

The [controlled keyed-encoding investigation](keyed-encoding.md) identified an
adapter positioning bug behind the two keyed planet failures and the content
drink omission. Memory and conversation K/V had overlapping rotary coordinates.
The corrected adapter places memory before the conversation; the report retains
the original failures and records paired tests, exact probabilities and regression
coverage. This is an adapter fix, not an Aimee retrieval or source-data change.
