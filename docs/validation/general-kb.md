# Local general reference KB: initial full-model experiment

Date: 2026-09-20. These measurements preceded the local authorization correction;
see [published local reads](published-local.md) for the current implementation.
Raw evidence remains unchanged in [the artifact directory](artifacts/general-kb-2026-09-20/).

## What was built

A deterministic public corpus contains 13,261 knowledge objects: 6,323 IANA named
services, 6,366 NASA exoplanet profiles, 355 NIST CODATA constants, and 217 World
Bank economies. See [source provenance and import rules](../../knowledge/general-v1/README.md).
The 19,000,048-byte canonical JSON includes semantic fields and provenance.
Factual bodies tokenize to **871,544 Qwen tokens**, versus the tested checkpoint's
262,144-token context. This is a technical/scientific reference corpus, not a
general encyclopedia. There are no benchmark query/answer contracts in the image.

The image and reader live on `.253` in RAM/SSD. General facts never enter or come
from the Aimee server DB. The disposable Aimee instance holds the two approved
synthetic personal memories used for mixed questions and an excluded canary.
The initial combined image was 15,529,234 bytes including the now-unnecessary
local grant copy. The current publication format is smaller.

Canonical objects stay model-independent. Selected record text is separately
encoded by frozen Qwen into native attention K/V. No memory text enters the main
generation prompt. This is the existing proven connection, not learned vectors
or adapter training. The model is the same 27B research checkpoint and dual
7900 XTX runtime as the preceding experiment; config reports `qwen3_5_text`.

## Measurements

34 fixed questions: 12 ports, 8 recent exoplanet periods, 4 capitals, 4 constants,
3 public two-record compositions, 2 public-plus-personal compositions, 1 unknown.
Greedy decoding, 48-token limit, same prompts and frozen Rust model throughout.

| Arm | Correct |
|---|---:|
| No memory | 8/34 with equivalent capital spelling accepted; raw scorer 7/34 |
| Oracle compact text | 34/34 |
| Initial native local KB + personal fallback | 31/34 |
| Native after exact-identifier addressing fix | 32/34 |

The no-memory answer `Tórshavn` is correct for the source spelling `Torshavn`.
The derived summary records that correction; raw results are untouched.

The addressing fix preserves internal identifier punctuation and chooses the
longest exact key. Previously `pxc-spvr-ft` also activated `pxc-spvr`, causing two
port errors. The corrected reader resolves **13,261/13,261** canonical entries.
It supports question phrasing around the exact named key, not arbitrary semantic
aliases or Aimee's complete graph reasoning. Ambiguity and over-budget requests
fall back instead of arbitrarily selecting a result.

The fixed native run got all 12 ports, all 8 recent planets, all 4 capitals, all
3 public compositions and the unknown case right. It missed the exponent in one
physical constant and omitted the drink in one mixed question. Both personal
records were present before decoding; that omission is not a missing retrieval.
The other mixed question correctly answered `3584;oolong;Lima`.

Audit of all 68 native runs established identical prompt token IDs to the
no-memory control, zero main-prompt memory tokens, exact canonical content and
revision for every public fact, and no excluded personal ID. Public records came
only from local reads. The 34 native prompts totaled 2,153 tokens versus 4,260
for the selected-text control. The full 871,544-token KB was never serialized
into a prompt; the text control contains only oracle-selected relevant facts.

## Remaining issues and limits

Attention-derived requests still use Aimee fallback. In the fixed run, seven
public-only questions received authorized but irrelevant personal records from
that fallback. There were 228 empty and 60 nonempty fallback events. This is a
relevance issue in the current combined path; no causal claim is made that it
explains either generation error. It also means this full-model test is not an
offline or zero-RPC decode benchmark.

Native median end-to-end time was 6.329859 seconds, versus 3.261073 seconds for
compact text and 1.031400 seconds with no memory. Outputs have different lengths;
these are observed totals, not an isolated reader speed comparison. The original
local protocol median was 40.976336 ms on `.253`, dominated by repeated grant
verification. That misplaced boundary is corrected in the next report.

Publisher mutation checks passed on the full corpus: updated value, retired
entry unavailable, old guarded reader rejection, and grant revocation. The
synthetic mutation did not change the public corpus. The later user-approved
design supersedes local grant revocation with publisher-controlled delivery,
replacement and withdrawal. Those historical checks remain recorded as history.

Four corpus tests, 26 gateway test executions and Go sparse/CLI race tests passed.
These runs demonstrate local knowledge consumption beyond whole-corpus context
capacity. They do not establish long-horizon retention, semantic retrieval parity,
production permission issuance, or a speed advantage over remote Aimee.
