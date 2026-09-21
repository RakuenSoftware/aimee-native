# Canonical-name cue precedence

Date: 2026-09-21. Follow-up to the [native positioning fix](keyed-encoding.md).

The two remaining place questions did not reach Qwen's native bank because the
public cue compiler treated canonical and alternate names equally:

| Query | Intended canonical record | Competing alternate-name record |
|---|---|---|
| Nuevo US | Nuevo, GeoNames 5378087, population 6447 | Ramona, 5385793, also lists Nuevo |
| Lanne FR | Lanne, GeoNames 3007631, population 572 | Port-de-Lanne, 2986018, also lists Lanne |

The reader was correctly reporting multiple bindings for each cue. This was not
a hash collision or a failure to read admitted native memory. The correction is
an explicit **publisher policy for ordinary public-reference name lookup**:
canonical/ASCII names own their normalized addresses, and alternate names fill
addresses without canonical owners. Multiple canonical owners remain ambiguous.
Shared aliases without a canonical owner remain ambiguous too. No record-order
or population-based tie-break is introduced.

The compiler makes this decision across the entire approved release before
publishing signed cue bindings. Canonical knowledge, provenance, source aliases,
Aimee authorization, the generic reader and the Rust/Qwen adapter are unchanged.
Historical-name or other semantically qualified questions remain Aimee work;
this policy does not turn literal cue matching into general semantic retrieval.

## Scope and tests

The change is in `knowledge/general-v2/cues.py`. `compile_cues` separates canonical
names from alternate candidates and applies precedence after normalization using
the reader's Unicode letter/number and identifier-punctuation rules. The raw
`cues(record)` helper remains available for auditing the original candidates.

Four new tests cover canonical/alias collisions, preserved genuine ambiguity,
input immutability, iteration-order independence, namespace identity, Unicode
normalization, and the actual signed-image → Go reader → Rust local path. The
existing five publication/authorization integration tests also pass: **9/9**.
The test binaries must be built from current source. Initial setup corrected an
empty-output parsing error in the test helper and replaced an outdated local
image-reader binary before the reported passing suite.

The research publication refreshes expired fixture approvals and changes their
cue bindings. A separate source audit verifies that all 249,105 canonical objects,
source view, explicit read contracts and other approval fields stay unchanged.
Fixture approvals remain research-only; this does not complete production
permission issuance.

## Full-index audit and measured lookup

| Measure | Before | After |
|---|---:|---:|
| Cue-to-object bindings | 821,128 | 800,470 |
| Normalized addresses | 726,412 | 726,412 |
| Unique addresses | 683,692 | 690,210 |
| Ambiguous addresses | 42,720 | 36,202 |

All previously unique address-to-object mappings remain unchanged. There are
10,354 changed addresses: 6,518 become unique, and the others retain multiple
canonical owners after alternate-owner bindings are removed. No address is lost.

These counts use the reader-compatible normalization in the new audit. The older
report used Python regex/full-string lowercasing and reported slightly different
Unicode totals; it is preserved, not silently rewritten.

The real Rust/Go local path passed **9,078/9,078** checks:

| Group | Passed | Median lookup | p95 |
|---|---:|---:|---:|
| Every newly resolved address | 6,518/6,518 | 0.059106 ms | 0.091224 ms |
| Sample of unique addresses | 2,048/2,048 | 0.0627545 ms | 0.096265 ms |
| Sample of remaining ambiguities | 512/512 | 0.0284165 ms | 0.0369 ms |

Ambiguity checks deliberately use an absent gateway: local lookup must defer,
and the overall request returns unavailable rather than selecting an arbitrary
record. These are routing checks, not generated-answer accuracy measurements.
Reader startup took 17.531063 seconds; publication took 76.450617 seconds and
copied 415,439,227 bytes. No controlled performance improvement over the old image
is claimed from these timings.

## Reproduction

- `benchmarks/general_kb/test_cues.py`: deterministic compiler and real-reader tests.
- `prepare_cue_fix.py`: a separate research publication with unchanged source data.
- `probe_cue_fix.py`: exhaustive changed-address checks and regression samples.
- `probe_model_cue_fix.py`: unchanged 46-question native regression plus alias-owner,
  true-ambiguity and keyed-encoding controls.

Artifacts are under `artifacts/canonical-cues-2026-09-21/`. Earlier images, questions
and result files remain intact. Serving is still the untrained Rust adapter;
Python runs offline compilation and HTTP test orchestration only.

## Frozen-Qwen results

The unchanged expanded suite now passes **46/46**, versus 44/46 before this cue
correction. Its 46 generation prompts have identical token IDs to the preceding
positional study. Native memory text is still absent from the main prompts.
Both newly admitted records produce their expected source values:

| Case | Before | After content | After keyed |
|---|---|---|---|
| Nuevo US population | unknown | 6447 | 6447 |
| Lanne FR population | unknown | 572 | 572 |

All six additional keyed checks pass: the two place questions, both previously
problematic planets, and both port/drink/city questions. Port-de-Lanne separately
returns its own population, 759. Springfield US has multiple canonical owners,
admits no record, and returns `unknown`.

One extra control initially had an **invalid expected answer**. It asked for
`Ramona US` and expected the California record's 20292, but this release contains
two canonical Ramona US records (4548897 and 5385793). The runtime correctly
admitted neither and answered `unknown`. The original run's raw score is
therefore **54/55**, and is preserved. A supplemental run verifies both:

- The unchanged ambiguous Ramona question still returns `unknown` with no bank.
- `place Ramona US 5385793` admits that specific record and returns **20292**.

The current probe uses the qualified control and a fresh output filename. It
refuses to reuse archived results when a case's question or expected value has
changed. The original probe is archived alongside its results. The 46-question
headline does not include either version of this extra control.

This run uses normal decode-time recall, whereas the preceding 46-question
positional comparison disabled it. All but three final banks are identical:
Nuevo and Lanne now have their intended records, and `constant-2` adds a related
mass record during decode. A paired supplemental test switches only decode recall:
both modes answer **1.29333251**, with one record under prefill-only and two under
decode recall. Thus the broader comparison is not described as an identical-bank
consumption experiment. All **4/4 supplemental controls** pass.

## Research gateway restart correction

Two initial requests returned HTTP 502 before the research gateway was ready:
its prior time-limited unit had left a stale Unix socket, and an immediate retry
preceded the restored gateway's readiness. These were startup failures, not
answered memory questions, and are retained in the server log.

The research launcher now assigns its socket directory to systemd through
`RuntimeDirectory=aimee-rust-native`. The lifecycle test stops and restarts the
managed gateway, verifies that stop removes the socket, and then obtains
`6115;oolong;Lima` through the restored real Aimee connection. The model and
gateway are running on `.253` with the new research publication. Production
Aimee services and permission policy were not changed.
