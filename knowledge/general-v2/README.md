# General reference KB v2

This extends the pinned [v1 corpus](../general-v1/README.md) with real populated
place records from [GeoNames](https://www.geonames.org/). The city extract is
licensed under CC BY 4.0; attribution: GeoNames. Source format and limitations:
[official dump documentation](https://download.geonames.org/export/dump/readme.txt).
The snapshot URL, timestamp and SHA-256 are pinned in `sources/manifest.json`.

Records preserve names, identifiers, coordinates, population, time zone,
administrative codes, source modification dates and provenance. Values are
reported as GeoNames assertions, not independently certified current facts.
Alternate names are retained in canonical source metadata for subsequent
publisher cue compilation; they are not automatically exported to the model.

The initial size experiment uses the existing exact-key reader unchanged.
Canonical place keys contain a stable GeoNames identifier to distinguish namesakes.
Exact-address accuracy therefore measures address isolation and scaling, not
semantic entity disambiguation. Unchanged v1 queries are tested with the added
objects as distractors. Alias/ordinary-language routing is evaluated separately.

`python3 knowledge/general-v2/build.py` verifies pinned source hashes and builds
`records.json`. The pinned source ZIP and a deterministic `records.json.gz` are included in this
repository. The expanded JSON remains a local artifact. `archive.json` records
the compressed and expanded hashes; expanding the archive restores the exact
249,105-record corpus used in the experiments.

```sh
gzip -dc knowledge/general-v2/records.json.gz > knowledge/general-v2/records.json
```
Neither building the corpus nor possessing public data grants access to any
private Aimee records. Recipient images are compiled upstream before delivery.

## Approved alternate cues

`cues.py` produces explicit cue-to-canonical-reference mappings from these public
source names. They must be included in the publisher's approved release, not
read indiscriminately from metadata in the model runtime. Canonical source names (including ASCII names) reserve their normalized
addresses across the release. Alternate names supply fallback addresses only.
This prevents an alternate name of one place from hiding another place whose
canonical name matches the query. Multiple canonical owners, and shared aliases
without a canonical owner, remain ambiguous and defer to Aimee.

This is an explicit public-reference publication policy, not general semantic
disambiguation: historical-name questions still need Aimee. Source aliases and
provenance remain unchanged in canonical knowledge objects. The compiler emits
only approved routing bindings; the adapter contains no place-name logic.

```sh
python3 knowledge/general-v2/cues.py --records knowledge/general-v2/records.json \
  --authority YOUR_READ_AUTHORITY --output /publisher/public-cues.json
```

The original compiler generated 821,128 cues. The canonical-name precedence
correction generates 800,470 cues without changing any of the 249,105 objects.
See [the correction and measurements](../../docs/validation/canonical-cues.md). Do not apply this public-only compiler
to private Aimee aliases without Aimee's field-level release decision.

`normalize_quantities.py` is a separate rendering experiment for finite NIST
quantities. It uses exact decimal arithmetic, preserves original source values
in semantic metadata and produces changed records with new revisions. It does
not edit the pinned v1/v2 inputs, round through floating point, or train anything.
Approximations with ellipses and textual uncertainties are preserved as supplied.
