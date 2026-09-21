# Native memory probe matched to trained answer format — 2026-09-20

This experiment tests the existing Aimee drink/city projections using trained
direct-answer questions and a trained composition format. No multiple-choice
labels or missing-value conventions are introduced. The purpose is to establish
single-fact behavior in a shared bank before interpreting a composition result.

**Result: both singleton checks passed, but the city question failed when the
drink memory was added.** The prompt and expected one-value response were
unchanged. This establishes a shared-bank single-fact failure for this pair;
composition is not isolated. The text-composition control passed.

## Fixed protocol

The singleton prompts are exact training examples:

> What is the preferred drink of unit-b03646cbf4?

> What is the home city of unit-121330aded?

The joint prompt uses the composition format present in training, with this
new pair of memories:

> Give the preferred drink of unit-b03646cbf4, then the home city of
> unit-121330aded. Separate with a semicolon.

The original system message and chat template are unchanged. All seven arms
are fixed before loading the model, without adaptation to observed outputs:

| Arm | Question | Memory representation | Expected |
|---|---|---|---|
| Drink singleton | Drink | Native drink only | oolong |
| City singleton | City | Native city only | Lima |
| Drink shared | Drink | Native drink + city | oolong |
| City shared | City | Native drink + city | Lima |
| Composition none | Joint | No memory | Control; score against oolong; Lima |
| Composition text | Joint | Both authoritative Aimee texts | oolong; Lima |
| Composition native | Joint | Native drink + city | oolong; Lima |

Single and shared-bank versions of each question have identical prompt tokens.
Native and no-memory joint prompts also match exactly. Only the labeled text
control receives authoritative text. Each generation starts a fresh sequence.

For composition to be isolated, both native singleton checks, both shared-bank
single-fact checks, and the text-composition control must pass. If a singleton
question fails with a shared bank, the issue already occurs before composition.
The no-memory control qualifies attribution if the native joint answer succeeds.

## Execution and controls

Aimee IDs 5 and 6 were reread and matched to their unchanged source content and
scope. The original checkpoint, latent values, frozen model, adapter, learned
attention, injection point, and greedy decoding settings are unchanged.
The harness records per-step attention using a read-only hook on the existing
query projection, and verifies exact parameter/value equality before and after.
No writer operation or training is performed.

The experiment completed on `.253` with process exit status 0:

- Service: `aimee-native-matched-probe-001.service`.
- Immutable source: `/opt/aimee-native-p0-training/aimee-matched-probe-001-source/`.
- Results: `/opt/aimee-native-p0-training/aimee-matched-probe-001/`.
- Log: `/opt/aimee-native-p0-training/aimee-matched-probe-001.log`.

Local evidence directory:
`benchmarks/native_memory/results/2026-09-20/aimee-matched-probe-001/`.

The exact singleton queries were seen during training; success on them is a
prerequisite check, not evidence of query generalization. The joint format was
seen during training, but this particular pair was not. This remains a bounded
experiment on two memories, without scale or speed claims.

## Results

| Question | Bank/control | Expected | Actual | Result |
|---|---|---|---|---|
| Drink | Native drink only | oolong | oolong | Pass |
| City | Native city only | Lima | Lima | Pass |
| Drink | Native drink + city | oolong | oolong | Pass |
| City | Native drink + city | Lima | oolong | Fail |
| Joint | No memory | oolong; Lima | unknown | Negative control |
| Joint | Authoritative text | oolong; Lima | oolong;Lima | Pass |
| Joint | Native drink + city | oolong; Lima | oolong | Recorded; composition not isolated |

All generations terminated normally. Each singleton/shared pair had identical
prompt token IDs; native/no-memory joint prompts also matched. Native arms
contained no answer values or memory text. The text control added 41 tokens.
All parameter, vector and native-path checks passed; zero training steps.

The decisive comparison is the city question: adding only the drink projection
changed `Lima` to `oolong`, without changing the question, response format,
projection contents, or decoding settings. This is a native working-set
selection/interference failure under the familiar single-answer task. It does
not depend on multiple-choice formatting or an `unknown` convention.

At the final prefill position, the shared bank assigned effectively all attention
to drink under both questions. City attention was approximately 4.25e-18 for the
drink question and 3.31e-18 for the city question. It was approximately 5.45e-18
under the joint question. These traces show the selector strongly favoring the
drink row despite the city request; they do not alone establish why that happened.

The earlier teal/distractor matrix established success for its particular target,
not general discrimination among arbitrary memories. This counterexample narrows
that interpretation. The existing ability to consume each Aimee-backed projection
individually remains reproduced. No conclusions about the general feasibility
of latent composition or Aimee's upstream retrieval follow from this failure.

No prompt changes, model changes, or further experiments followed these results.

## Adapter and training interpretation

The text control appends the complete authoritative sentences, including entity,
property, and value, to the user message. The native hook receives no bank in
that arm and returns the hidden state unchanged. Qwen therefore uses its
existing text-processing machinery to resolve and combine explicit facts.

The native arm supplies two learned vectors to a single adapter after block 1.
The adapter computes one query, softmax weights over projected keys, and one
weighted value sum per token, followed by its output projection and scalar gate.
Memory IDs are bank metadata, not an additional entity/property input to this
neural selector. The latent values were learned through answer-token loss;
explicit entity/property binding is not guaranteed by the interface.

A concrete training limitation is visible in the saved oracle setup. Of 210
training examples, 200 present exactly one memory and only 10 present two.
With a one-entry bank, softmax is identically `[1]`: changing query/key scores
cannot change the selected value. Consequently those examples provide no
answer-loss gradient to teach query/key discrimination through the attention
weights (optimizer weight decay/momentum can still change those parameters).
The two-entry examples supply selection learning only within their limited
pairs, with no irrelevant distractors. The city projection appears only in
singleton training examples; this drink/city competition was never trained.

This makes the current adapter and its selection-training coverage concrete
suspects. It explains why singleton recall does not establish multi-memory
selection ability. It does not prove the root cause is solely training, nor
that a single-layer adapter is inherently incapable. The observed failure is
in this implementation's use of a multi-memory bank, not evidence against the
general native-memory design or Aimee's retrieval machinery.

## Saved evidence

- [Summary and prerequisite adjudication](../../benchmarks/native_memory/results/2026-09-20/aimee-matched-probe-001/summary.json).
- [Fixed protocol and training examples](../../benchmarks/native_memory/results/2026-09-20/aimee-matched-probe-001/protocol.json).
- [City alone](../../benchmarks/native_memory/results/2026-09-20/aimee-matched-probe-001/city_single.json).
- [City with drink present](../../benchmarks/native_memory/results/2026-09-20/aimee-matched-probe-001/city_shared.json).
- [Drink with city present](../../benchmarks/native_memory/results/2026-09-20/aimee-matched-probe-001/drink_shared.json).
- [Text composition control](../../benchmarks/native_memory/results/2026-09-20/aimee-matched-probe-001/composition_text.json).
- [Native joint output](../../benchmarks/native_memory/results/2026-09-20/aimee-matched-probe-001/composition_native.json).
- [Checkpoint and source provenance](../../benchmarks/native_memory/results/2026-09-20/aimee-matched-probe-001/provenance.json).
