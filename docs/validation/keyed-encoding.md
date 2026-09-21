# Keyed native encoding investigation

Date: 2026-09-20. This extends the [larger-KB follow-up](kb-scale-followup.md).
The base model stays frozen and the adapter stays read-only and untrained.
Experimental controls do not place factual memory into the main prompt. Explicit text-control arms are
reported separately.

## Question and controls

Adding a canonical key to the separate memory encoding makes two planet answers
regress to `unknown`, while fixing one omitted-drink answer. Every question has
the correct canonical facts admitted. The key is ordinary input to the frozen
memory encoder, not merely a transport address. It changes content positions and
the encoded K/V states.

The diagnostic run keeps the question, system prompt, greedy decoding and
current Aimee publication fixed. It disables decode recall and encoding reuse.
Actual prefill recall still goes through the Rust adapter and restricted Aimee
connection; no fixture-supplied facts enter the serving request. Each result
records ordered bank identities so selection/order differences can be identified
rather than blamed on consumption.

Formats:

- `content`: existing authoritative-memory heading and factual bodies.
- `keyed`: the same heading with `canonical key: body` per object.
- `keyed-neutral`: keyed tokenization with only key token slots replaced by
  single whitespace tokens. Token count and every non-key token slot are fixed.
- `keyed-suffix`: factual body followed by its key in brackets.
- `json`: the existing JSON key/content representation.

A separate positional experiment translates rotary key coordinates, leaving
memory values, source facts and token IDs unchanged. Zero shift is an exact
no-op. A `before_prompt` variant places the bank at `[-M,-1]` relative to a main
prompt beginning at zero; other runs use fixed shifts. Nonzero rotation involves
BF16 rounding. A small float32 unit test checks rotary translation equivalence
and preservation of non-rotary dimensions. This began as a diagnostic; the
user-requested correction below adopts the disjoint convention after controlled
validation.

Measurements include per-step next-token log probabilities and last-query
attention distributions at each full-attention layer. These use the same BF16
matmul/float softmax as generation. Attention mass is descriptive, not proof of
causal attribution. Causal interpretations require the controlled interventions.

Research controls require the server's explicit `--enable-memory-diagnostics`.
The initial diagnostic build preserved the original defaults. The subsequent
fix changes the positional default, as described below. No domain-specific logic
or training is introduced into the adapter.

## Original token geometry

| Question | Main prompt tokens | Content bank | Keyed bank | Value position, content → keyed |
|---|---:|---:|---:|---|
| TOI-2267 d period | 66 | 116 | 126 | 65–77 → 75–87 |
| TOI-799 b period | 65 | 114 | 123 | 62–74 → 71–83 |
| u-dbap + drink + city | 89 | 69 | 108 | oolong 66–67 → 105–106 |
| xic + drink + city | 88 | 60 | 98 | oolong 57–58 → 95–96 |

Positions above are zero-based memory-token slots. Initially both the main prompt
and the independent memory encoder start at rotary position zero. The private
keys are opaque research identifiers such as `research.native-bank.20260920.d1`;
they do not spell out “preferred drink.” This makes semantic disambiguation by
the key's wording an unproven explanation for the improvement.


## Controlled results

All 52 native diagnostic runs received identical prompt token IDs and identical
**ordered canonical memory references** within each question. This checks the
actual admitted bank, not just the retrieved candidate list. Decode recall and
encoding reuse were disabled in this stage. Prefill recall remained enabled.

| Native encoding / addressing | TOI-2267 d | TOI-799 b | u-dbap + drink + city | xic + drink + city |
|---|---|---|---|---|
| Content, original positions | correct | correct | correct | `6115;unknown;Lima` |
| Keyed, original positions | `unknown` | `unknown` | correct | correct |
| Neutral key slots, original positions | correct | correct | correct | correct |
| Key suffix, original positions | correct | correct | correct | correct |
| JSON, original positions | `unknown` | `unknown` | correct | correct |
| Content, memory before prompt | correct | correct | correct | correct |
| Keyed, memory before prompt | correct | correct | correct | correct |

The eight text controls returned all expected factual values. The archived strict
scorer marks two as failures because `3584; oolong; Lima` has spaces around its
separators. The analysis adds a separate `value_match` field; it does not rewrite
those raw results. These controls establish that both serializations can express
the facts clearly to ordinary text consumption. They are not a context-efficiency
comparison and deliberately include memory text in the control prompt.

The fixed-shift sweep is also informative: keyed banks shifted by -16 or +4
passed all four questions, while -8 and -4 still failed both planets; +8 and +16
still failed TOI-2267 d. Thus a hand-picked constant offset would overfit these
probes. Placing the entire bank before the conversation supplies a coherent
positional contract instead.

### Actual answer probabilities

These are full-vocabulary next-token probabilities, not probabilities normalized
across a hand-picked answer set. Planet rows measure the first digit of the
answer at step zero. Drink rows measure the first `oolong` token (`ool`) at step
five, after the **same** generated prefix `6115;` in every listed run. They are
not probabilities of the complete multi-token answer.

| Question / encoding | Original correct-token probability | Before-prompt correct-token probability | Original `unknown` | Before-prompt `unknown` |
|---|---:|---:|---:|---:|
| TOI-2267 d, keyed (`2`) | 34.27% | 99.07% | 56.50% | 0.86% |
| TOI-799 b, keyed (`5`) | 45.65% | 98.96% | 51.73% | 0.97% |
| xic drink, content (`ool`) | 1.48% | 84.79% | 91.68% | 0.00182% |
| xic drink, keyed (`ool`) | 88.56% | 83.13% | 0.133% | 0.0124% |

The keyed drink case already worked. The fix makes the content case work too;
it need not increase every already-correct token's probability.

Attention traces show that the old failed drink run **did attend to the drink
record**. Mean record attention across heads and full-attention layers at the
drink decision was 16.57%, versus 20.31% after the content positioning fix. This
is descriptive only: record attention is not proof of correct interpretation.
The controlled positional intervention, not the attention aggregate, supports
the diagnosis.

## Adapter bug and correction

The separate memory encoder assigned its M keys positions `0..M-1`. The main
conversation independently started at position zero. Concatenating their K/V
banks in attention did **not** relocate their rotary coordinates. Consequently,
some visible memory states had the same positional coordinates as conversation
states, and a sufficiently long bank put later memory states ahead of the query's
position despite exposing the entire bank as prior memory.

The adapter now translates the rotary portion of each memory key by `-M` at
read time. Memory occupies `[-M,-1]`; conversation positions remain unchanged.
The same preparation function is used for native attention addressing and for
consumption, including after recall replaces the bank. Non-rotary dimensions,
memory values, encoding tokens, Aimee references and main conversation cache are
unchanged. Cached banks retain their original encoding coordinates, preventing
cumulative rotation on repeated reads. A replacement bank uses its own length.
There is no training, prompt injection, re-encoding for the shift, or replay of
the conversation cache.

For rotary matrix R, the new memory/query score is based on
`R(t)q · R(j-M)k`. It equals the relative-position score of a disjoint virtual
prefix, `R(t+M)q · R(j)k`. Our unit regression checks the actual attention output
against that reference with causal masks, grouped heads, multiple memory sizes,
prefill and decode queries. This is an attention-position equivalence, **not** a
claim that separately encoded K/V equals a joint text-prefill forward pass.

The normal adapter and HTTP request defaults now use this correction. The old
overlapping convention remains available only as an explicitly enabled research
control (`--enable-memory-diagnostics` plus `memory_before_prompt:false`).
Normal serving rejects those diagnostic request fields. Encoding remains
`content` by default; no keyed-format workaround is required.

### Regression coverage

The full release build passed 12 Rust tests (9 library, 3 executable), including:

- A rotation-equivalence test and preservation of non-rotary dimensions.
- Attention equivalence to a disjoint virtual prefix with causal masking and
  grouped heads across bank lengths 1, 5 and 17, prefill/decode positions
  0, 3, 31 and 128, and query lengths 1 and 4.
- Adapter default placement, bank replacement/growth/shrinkage, repeated reads,
  cached-key immutability, unchanged values, empty bank and mismatched lengths.
- The HTTP request default, preventing it from silently reverting the adapter's
  corrected positioning.
- Actual-checkpoint tokenization checks for unchanged original serialization and
  preservation of non-key token IDs/slots in the neutral-key control.

The no-libtorch local suite also passes; the actual-tokenizer test is only fully
exercised by the remote release suite with `AIMEE_TEST_TOKENIZER` set.

### Limits of the conclusion

This diagnoses a concrete native-interface bug and fixes these controlled
failures. It does not establish that all future encoding, routing, composition,
long-context or native-consumption failures have the same cause. Key text also
changes the encoder's content states; the neutral-slot result shows that useful
key semantics were not required for these four questions, not that labels never
matter. No selection policy, authorization rule or source memory was changed.

## Wider paired regression

A further 138 native generations ran 46 questions under three conditions:
original content positioning, corrected content positioning and corrected keyed
positioning. All 46 comparisons have identical main prompt IDs and identical
ordered admitted banks. No memory text was supplied in the request. These runs
turned detailed diagnostics off; prefill recall stayed enabled, decode recall
and encoding reuse stayed disabled to isolate consumption.

| Condition | Original 34 questions | Added 12 place questions | All 46 |
|---|---:|---:|---:|
| Original content positions | 33/34 | 10/12 | 43/46 |
| Corrected content positions | **34/34** | 10/12 | **44/46** |
| Corrected keyed positions | **34/34** | 10/12 | **44/46** |

The two remaining factual misses, `new-place-2` (Nuevo US) and `new-place-4`
(Lanne FR), have ambiguous compiled cues and empty native banks in all three
conditions. They remain `unknown`. They are retained in the raw 44/46 score;
changing positional handling cannot supply a fact that was not admitted.
The separate unknown-memory test also continues to abstain correctly. No
previously correct answer regressed in this paired set.

The fixed executable is then checked separately with **ordinary serving
requests**, diagnostics disabled, and the normal preload/decode-recall/cache
settings. This verifies the actual defaults rather than relying solely on the
explicit experimental positioning flag. See the archived `fixed/results.jsonl`
for those subsequent runs.

## Reproduction and evidence

Scripts are in `benchmarks/encoding_diagnostics/`:

- `probe.py`: the 20 format, 32 position and 8 explicit text-control runs.
- `analyze.py`: prompt/bank identity, answer-step logits and attention summaries;
  preserves strict scorer outputs and adds whitespace-insensitive value matching.
- `regression.py`: the 138 paired native generations.
- `summarize_regression.py`: requires all 138 records and verifies identical
  prompts and admitted banks for all 46 questions.
- `verify_fixed.py`: normal-server answer, cached-reuse, history, memory-disabled
  and diagnostic-rejection regressions; asserts native answer correctness.

They use the existing approved synthetic Aimee setup and the actual frozen Qwen
runtime on `.253`; they are not a substitute retrieval implementation. Python
orchestrates HTTP tests only. Serving, attention and the adapter are Rust.

Artifacts are under `artifacts/keyed-encoding-2026-09-20/`, including original
JSONL responses, full traces, derived analysis, paired regression summary,
configuration/tokenizer/binary hashes, the diagnostic source snapshot and the
fixed release test log. Source snapshots contain no model weights or authority
credentials. Facts are public reference data and synthetic private test facts.

### Fixed normal-server results

The rebuilt release ran with **diagnostics disabled** and no positioning fields
in requests. All **18/18 native answers passed**:

| Normal serving check | Result |
|---|---|
| Four target questions × content/keyed | 8/8 correct |
| Repeat those requests using cached banks | 8/8 correct; **zero encoding passes** |
| xic/drink/city after 32 prior exchanges, content/keyed | 2/2 correct; 1,230 prompt tokens each |
| Memory disabled, same four questions | Both planets `unknown`; both triplets `unknown;unknown;unknown`; zero native reads/encodes |
| Attempt to request old overlapping positions | HTTP 400; diagnostic override rejected |

Native bank references match the diagnostic baselines. All target answer strings
are absent from the main prompts, including the longer-history runs. Decode-time
recall was enabled. The two cold personal requests per format initially encode a
public fact and subsequently expand the native bank with the two authorized
Aimee facts; repetitions reuse those encodings. No main conversation cache is
rebuilt. This is a 1,230-token history regression, not a claim of validation at the
model's maximum context length.

The fixed binary SHA-256 is
`6e150e6d2671d113dd95452e890b32028b226cc682742ccc40af77fd4af68b38`.
The `.253` research service is running this binary with diagnostics off.
Production Aimee services were not changed by this investigation.

## Subsequent cue-compiler correction

The remaining Nuevo/Lanne routing misses are investigated separately in
[canonical cue precedence](canonical-cues.md). That change belongs to the public
KB publisher and preserves this report's archived results and positional fix.
