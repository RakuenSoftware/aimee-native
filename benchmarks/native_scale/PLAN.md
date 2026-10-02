# Native memory: personal assertions and public knowledge

Frozen before the large inference run on 2026-09-22; seed 20260922.

## Units and conditions

1,250 distinct source facts, one single-record question per fact. There are 625
synthetic personal assertions and 625 sampled public facts: 250 IANA services,
250 GeoNames places (125 population and 125 timezone questions), 100 NASA orbital
periods, and 25 World Bank capitals. Both Gemma 4 12B and Qwen3.8-27B answer each
question with memory disabled and enabled. Target: 5,000 generated answers,
2,500 per model. Paired conditions are not independent facts.

The personal fixture covers 125 fictional projects with five preferences each.
Each assertion has the explicit form `My ATTRIBUTE for project NAME is VALUE.`
Aimee's actual ExtractPatterns code extracts the value. GateCheck records its
ontology verdict; novel relations are explicitly accepted for this synthetic
research release. NewPostgresDataStore.Put writes the asserted preference to an
isolated PostgreSQL database. ExportSparseRecords exports source-owned records
and row-hash revisions using a read-only repeatable-read transaction. The driver
renders each extracted assertion as `The user's ATTRIBUTE is VALUE.`

This is explicit-assertion learning through production Aimee components in an
isolated integration driver. It is not an autonomous dialogue extraction test,
a production HTTP deployment, or an experiment in learning trained weights.
Publication uses signed research fixture grants. Personal queries have exact
publisher-approved read contracts; general queries use the existing exact-key
reference reader. The campaign evaluates native consumption of selected facts,
not unrestricted semantic retrieval. All 249,105 public KB records are present
alongside the 625 authorized personal records.

## Controls and scoring

No facts enter the actual conversation prompt. Weights stay frozen, each request
has a fresh conversation cache, and encodings are recomputed for native requests.
Within each model, paired requests use identical conversation token IDs. Qwen
uses the memory-use system instruction from its earlier archived experiments;
Gemma uses its previously tested user-only conversation. The two models therefore
are not a controlled speed or model-ranking comparison.

Expected facts are fixed before inference. Text scoring strips surrounding
whitespace and a terminal period and compares case-insensitively. Numerical
scoring parses the entire response as Decimal and accepts relative error <=1e-5.
No substring/answer extraction or response-dependent aliases are accepted.
Both conditions are scored against the fact; `unknown` is separately recorded.
Public facts may already be known to the checkpoint. Report baseline, native,
recovered answers and regressions separately for personal and general knowledge.
Report exceptions and incomplete requests; never count transport checks as model
answers. Record native-read counts, selected revisions and zero prompt additions.

No composition questions. No model training or optimizer. No changes to source
facts or question wording based on large-run answers. Raw outputs are append-only.

## Reproduction

The dedicated lab uses CT101 and both 7900 XTX GPUs. Source dependency:
Aimee ad3585ac5381e3f0569dd8661b41fbe82cd6501d. Checkpoint revisions are pinned in
`../gemma_native/PLAN.md` and the existing Qwen provenance. Prepare isolated
PostgreSQL database `aimee_scale_20260922`, owned by the root research publisher;
model worker runs under `memory-model` and cannot read private signing material.

```
go build -o .local/bin/scale-ingest ./benchmarks/native_scale/ingest
python benchmarks/native_scale/prepare.py FRESH_SOURCE_ROOT
python benchmarks/native_scale/gemma.py SOURCE_ROOT FRESH_GEMMA_ROOT
python benchmarks/native_scale/qwen.py SOURCE_ROOT FRESH_QWEN_ROOT
```

Run models sequentially. Preserve source/case plans, ingestion rows, exported
synthetic records, logs and traces. Exclude `private/` and compiled `image/` from
repository evidence bundles. Record exact executed script hashes separately.

## Predeclared correction follow-up

After both models complete the 5,000 requests, seed 20260923 selects 125 personal
facts. Each value advances to the next entry in its original five-value list;
all values change and all questions remain unchanged. The same Aimee extractor,
PostgreSQL upsert and exporter process the explicit new assertions. A new
publication retains the full general base and all 625 personal records. Both
models then answer the 125 questions with memory disabled and enabled: 500
additional requests. These are corrections to previously tested facts, not 125
additional independent facts. Models are reloaded between campaigns, so this
follow-up measures retained corrections across model processes, not same-worker
update latency. `revise.py SOURCE_ROOT FRESH_CORRECTION_ROOT` prepares it.

Before the correction follow-up starts, an additional tensor-level check was
specified: a persistent Gemma worker reads all 125 old values, remains loaded
while Aimee ingests and publishes the corrections, then reads all 125 new values.
The worker records SHA-256, shape, dtype and byte count of the actual external
key/value tensors for every memory layer before request cleanup. Its parameter
version counters remain checked on every request. The immutable revised image
is then also installed into the already-loaded worker's published-image root,
using the previous generation as the expected predecessor. These are 250 extra
native answers (125 paired old/new), separate from the 500 paired disabled/native
correction requests. Total planned large-campaign model answers: 5,750.
The 125 facts and their new values remain those fixed by seed 20260923. This
adds evidence instrumentation; it does not tune queries or answers.
