# Native personal/general knowledge: 5,750 completed requests

2026-09-22. Protocol and drivers: [native_scale](../../benchmarks/native_scale/PLAN.md).
Raw evidence: [native-scale-2026-09-22](artifacts/native-scale-2026-09-22/).

## Main paired evaluation: 5,000 requests

1,250 distinct facts, one question each, memory disabled/enabled on both models.
The publication contains all 249,105 pinned public records plus 625 synthetic
personal assertions processed by real Aimee extraction, PostgreSQL storage and
canonical export. Personal access uses approved exact-query read contracts;
public access uses the existing reference-key reader. This measures native
consumption of selected records, not unrestricted retrieval or freeform dialogue
extraction. The source database and all assertions are isolated research data.

| Model | Source | Disabled correct | Native correct | Recovered | Regressed |
| --- | --- | ---: | ---: | ---: | ---: |
| Gemma 4 | Personal | 0/625 | 625/625 | 625 | 0 |
| Gemma 4 | General | 126/625 | 625/625 | 499 | 0 |
| Qwen 3.8 | Personal | 0/625 | 615/625 | 615 | 0 |
| Qwen 3.8 | General | 32/625 | 625/625 | 593 | 0 |

Every native request selected the expected revision. All paired prompts matched;
no memory text entered the conversation. Gemma cache and frozen-parameter checks
passed. Qwen ran its inference-only Rust/INT8 runtime. Its ten native misses were
preferred-drink abstentions (nine oolong, one jasmine) with correct memory selected.
Neither main run had runtime exceptions. Both consumed the same publication;
Qwen's before/after file hashes match Gemma's saved CURRENT digest.

## Live tensor update: 250 requests

125 old values and 125 corrected values were all answered correctly by one
persistent Gemma worker. Aimee stored explicit changed assertions and published
new source revisions without changing canonical identities. Across 48 layers
per fact, all 6,000 external key tensors and all 6,000 external value tensors
changed byte hashes. Every parameter-version check stayed unchanged, all weights
were frozen, and every ordinary conversation-cache check passed. SHA-256 was
computed on actual tensor bytes before request cleanup, not encoder token IDs.

This full-snapshot follow-up prepared its revised publication in 101.3985s and
installed it into the loaded worker's publication root in 28.4922s. The latter
reused 267,390,752 bytes and copied 494,295 bytes. These batch timings differ from
the earlier optimized incremental publisher's seconds-scale measurements.

## Corrected knowledge across fresh model processes: 500 requests

Both models returned unknown for all 125 disabled controls. Gemma returned
125/125 revised native values; Qwen returned 123/125 and abstained twice. Neither
repeated an old value. Qwen answered both versions correctly for 122 facts;
one earlier abstention became correct. Every expected revised record was selected,
prompts were unchanged, identities persisted and revisions changed. Both models
consumed the same revised publication. Its files stayed unchanged during Qwen.

## Evidence handling and reproduction

Main outcomes: [native-scale-main.json](native-scale-main.json).
Corrections: [native-scale-corrections.json](native-scale-corrections.json).
Actual tensor audit: [native-scale-tensors.json](native-scale-tensors.json).

```
python3 benchmarks/native_scale/verify.py docs/validation/artifacts/native-scale-2026-09-22
python3 benchmarks/native_scale/verify.py docs/validation/artifacts/native-scale-2026-09-22 --corrections
python3 benchmarks/native_scale/verify_tensors.py docs/validation/artifacts/native-scale-2026-09-22/native-scale-corrections-r2
```

The manifest hashes all archived files. Private signing material, database
credentials, compiled images and model weights are excluded. Checkpoint hashes
and model configurations are pinned in the earlier Gemma/Qwen provenance;
new provenance captures executable/script hashes. The initial campaign code is
commit `1d81845`; correction/tensor protocol is `6dae4d9`, followed by the recorded
expected-generation fix. The collector's `campaign_source_commit` field names
the initial base; its individual file hashes distinguish later protocol code.

The first source preparation incorrectly proposed a general-reference lookup
policy for personal records; compilation rejected it before inference. The
corrected setup uses explicit personal read contracts. No fact or question was
changed in response to model answers.

The first correction attempt performed source upserts but omitted the expected
source-generation digest when publishing. The guard rejected it. Its 125 old-value
reads are preserved as an incomplete attempt, outside the 5,750 completed-protocol
requests. A recorded restoration returned the synthetic source assertions to their
old values before the successful rerun. The revised values, questions and scoring
were unchanged. All raw artifacts are append-only.
