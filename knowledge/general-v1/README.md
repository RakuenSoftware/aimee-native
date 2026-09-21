# General reference KB v1

A model-independent canonical snapshot with **13,261 real knowledge objects**.
This is a useful initial scientific/technical reference corpus, not a broad
encyclopedia or a reproduction of Aimee's entire knowledge graph.

| Primary source | Records | Contents |
|---|---:|---|
| IANA service registry | 6,323 | Named services and registered transport/port pairs |
| NASA Exoplanet Archive | 6,366 | Planet/host identity, discovery and reported physical parameters |
| NIST CODATA 2022 | 355 | Physical constants, units and uncertainties |
| World Bank country API | 217 | Economy identifiers, listed capitals, regions and income groups |

The 19,000,048-byte canonical JSON includes structured semantics and provenance.
The factual bodies alone tokenize to 871,544 tokens with the tested Qwen tokenizer;
its configured context is 262,144. No filler, synthetic facts, personal records
or benchmark query/answer contracts are included. Numeric source values remain
strings where that preserves published precision. Confidence 1 denotes faithful
import of the stated source, not zero scientific uncertainty.

## Source attribution and snapshots

Fetched 2026-09-20. `sources/manifest.json` pins URLs, retrieval times, byte counts
and SHA-256 hashes. Each object repeats its source identity and row locator.

- [IANA Service Name and Transport Protocol Port Number Registry](https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.xhtml).
  Only names, numeric ports and transport protocols enter canonical objects.
  Contacts, assignees and descriptive prose are not imported. Duplicate
  transport/port pairs within one named service are consolidated; distinct
  service identifiers remain distinct. Rows without a supported transport and
  numeric port are excluded. A registration does not establish actual traffic
  behavior or security suitability.
- [NASA Exoplanet Archive composite-parameter table](https://exoplanetarchive.ipac.caltech.edu/docs/pscp_about.html),
  retrieved using its [TAP API](https://exoplanetarchive.ipac.caltech.edu/docs/API_resources.html).
  These are reported composite values, which may combine literature sources or
  contain derived estimates; this snapshot is not a precision astronomy dataset.
  This work uses the NASA Exoplanet Archive operated by Caltech under NASA's
  Exoplanet Exploration Program. See its
  [acknowledgment and citation guidance](https://exoplanetarchive.ipac.caltech.edu/docs/acknowledge.html).
- [NIST CODATA complete ASCII table](https://physics.nist.gov/cuu/Constants/Table/allascii.txt)
  and [2022 adjustment documentation](https://www.nist.gov/pml/fundamental-physical-constants).
  The import keeps the stated standard uncertainty; it does not imply that
  approximate constants are exact. Some exact mathematical expressions are
  printed with ellipses by the source and remain so here.
- [World Bank country API](https://datahelpdesk.worldbank.org/knowledgebase/articles/898590-country-api-queries).
  Aggregate regions are excluded. Economy labels and classifications are the
  World Bank's snapshot, not independently resolved geopolitical assertions.
  Credit: World Bank, adapted factual records, under the applicable
  [World Bank data terms](https://data.worldbank.org/summary-terms-of-use)
  (default CC BY 4.0 unless otherwise indicated).

The `.csv`, `.txt` and country JSON inputs are retained as source snapshots.
The model receives only its authorized serving projection, not those raw files,
source metadata, contact data, publisher keys, or the complete source directory.

## Build and use locally

From the repository root:

```sh
# Network access occurs during controlled source acquisition only.
python3 knowledge/general-v1/fetch.py
python3 knowledge/general-v1/build.py
python3 -m unittest discover -s knowledge/general-v1 -p test_build.py -v
go build -o .local/bin/aimee-kb-seed ./cmd/aimee-kb-seed
.local/bin/aimee-kb-seed --root .local/general-v1-source \
  --input knowledge/general-v1/records.json
```

Re-fetching may change the upstream snapshot; preserve the old source files and
manifest when reproducibility is needed. `build.py` verifies every input hash
and rebuilds deterministically. Neither script grants model access or publishes
an image. Aimee's publisher must explicitly approve records and compile a fresh
audience-specific image. Current experiments use research fixture approvals.

The serving image is stored **on the model host**. Indexes and named-entry
addresses are in RAM; immutable canonical payloads are read locally by offset.
Qwen-native K/V is encoded only for the selected records. No general record is
uploaded into or fetched from `aimee-server` in these tests.

The publisher compiles an `exact-key-v1` reference lookup configuration for this
namespace and the configured read authority. It is routing metadata, not local
permission enforcement. Authorization is decided before the recipient's image
is written; local reads require no grant files or repeated verification.
Examples of entry keys are
`IANA service ssh`, `planet TOI-1422 b`, and `economy Aruba`. Question phrasing
can vary around that key; lookup does not depend on a pre-published question.
Identifier punctuation is significant and the longest exact key wins. Duplicate
keys, insufficient budget and unavailable objects do not produce arbitrary
answers. This initial policy provides named reference lookup, not semantic
paraphrase resolution of arbitrary entity aliases or full graph inference.

Complex or uncovered requests retain Aimee fallback. In the current native
runtime, later attention-derived requests may fall back even after a successful
local preload. General facts still come from the local image; the experiment
traces distinguish local facts from personal-memory fallback responses.

Only the trusted publisher can update canonical objects, suppress/retire them,
issue a new generation and authorize its model-visible contents. The model and
Rust adapter remain read-only and untrained. Synthetic update tests are separate
under `benchmarks/general_kb`; they never rewrite this public canonical corpus.
