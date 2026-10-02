# General knowledge and learned task transfer

Protocol fixed 2026-09-22 before new inference. Existing checkpoints and runtime
settings remain unchanged. Each request starts a fresh conversation cache.

## General knowledge

10,000 distinct records from the existing 249,105-record general-v2 corpus:
3,000 IANA TCP ports, 4,000 GeoNames places (2,000 population / 2,000 timezone),
2,850 NASA orbital periods, 150 World Bank capitals. Seed 2026092201; exclude
all 625 general facts tested in the previous study. This is a stratified sample,
not a population-weighted estimate of general intelligence. The full existing
KB is published, not just the sampled facts. Both Gemma and Qwen answer each
question disabled and native: 40,000 generated responses. Same original wording
and scoring rules, same per-model system prompts. Report baseline, native,
recovered, regressed, abstentions and errors by domain. Verify prompt identity,
zero added memory prompt tokens and selected source revisions. Preserve raw
answers and failures. No test-data adjustments after seeing answers.

## Learned task improvement

Measure transfer of a learned procedure to unseen inputs, rather than repeat
an answer previously stored. Synthetic private workflows use hidden affine
integer transformations, with separate training examples and held-out inputs.
The model receives execution feedback on training examples and produces its own
procedure. Store that procedure through Aimee's actual extraction, PostgreSQL
store, canonical export and native publication. Score new input/output tasks
with the procedure absent and natively available. Never store held-out answers
in memory. Freeze specific environments, splits, prompts, scores and controls
before task inference. Keep training and evaluation denominators separate.

Task outcomes will establish only the tested procedural-transfer scope, not
weight learning or unrestricted autonomous improvement. Failed learned rules
and failure to apply a correct rule are both retained and reported.

### Frozen task instantiation

Seed 2026092202 selects 24 distinct affine rules `a*x+b`, with `a` in 2..9 and
`b` in 1..19. Names Cedar000..Cedar023 conceal each rule. For each workflow the
learner receives executor-labeled examples at inputs 1, 4 and 9, and generates
one single-sentence reusable instruction under 100 characters (the source extractor has a 128-character value limit). This is supervised rule induction from feedback;
it does not claim an autonomous exploration loop. Twenty held-out inputs per
workflow are sampled without replacement from 20..119, with exact integer
answers fixed before inference. Both models independently induce their own
24 rules. Store every generated rule without semantic repair, even if wrong;
whitespace flattening for the assertion extractor is logged. Each model reads
its own learned publication in a fresh process for 480 disabled/native pairs.
Total: 1,920 held-out task responses plus 48 separate rule-induction responses.
The general-study Decimal scorer uses relative tolerance 1e-5. Task execution
uses exact numeric equality to the expected integer, with no tolerance. Training answers
are free-form instructions: ignore the reused runner's literal-match `correct`
field for training, and evaluate transfer only on held-out executions.

The authorized publisher selects the learned procedure by workflow identity
through existing exact read contracts. It never calculates or stores task
outputs. Each procedure is a single memory record shared across that workflow's
20 held-out inputs. The task and training split is synthetic and restricted to
affine workflows; it supports procedural learning and transfer, not a claim of
universal task improvement.
