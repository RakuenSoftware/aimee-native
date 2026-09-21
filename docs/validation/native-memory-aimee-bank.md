# Tiny Aimee native-memory bank — 2026-09-20

Question: can Qwen consume the right Aimee memory when multiple individually
proven latent memories are present? The writer is excluded. This experiment
uses the unchanged BF16 oracle interface and existing latent values.

**Result: A–F all passed. The subsequent two-memory prompt produced one value.**
All five projections revalidated independently. The run completed successfully
with zero training steps and zero memory tokens in the native prompts.

**Composition interpretation superseded:** the original composition output
did not establish a composition failure because the singleton prerequisites
under that prompt were not satisfied. The user's
[controlled replacement test](native-memory-composition.md) explicitly checks
those prerequisites and classifies their failure as a prompt/latent
generalization issue. Raw observations below remain preserved.

## Fixed inputs

All five projections had previously answered their own held-out question
correctly in the completed oracle study. They are stored/read through the
registered Aimee CLI and matched exactly to the learned projection content:

| Role | Aimee ID | Learned row | Fact value |
|---|---:|---:|---|
| Target | 4 | 100006 | teal beacon, unit-81b1315e68 |
| Distractor 1 | 5 | 100001 | oolong preference, another entity |
| Distractor 2 | 6 | 100002 | Lima home city, another entity |
| Distractor 3 | 7 | 100003 | Kestrel release codename, another entity |
| Wrong-value control | 8 | 100012 | silver beacon, another entity |

The new run revalidates every projection alone on its own question before
executing the matrix. Failure at that stage stops the experiment as an invalid
precondition rather than being counted as multi-memory interference.

## Exact matrix

Every condition uses the identical question and prompt tokens:

> For unit-81b1315e68, which value is recorded under beacon color?

| Test | Native bank, in order | Expected | Actual | Result |
|---|---|---|---|---|
| A | teal | teal | teal | Pass |
| B | teal, oolong | teal | teal | Pass |
| C | teal, oolong, Lima, Kestrel | teal | teal | Pass |
| D | Kestrel, Lima, oolong, teal | teal | teal | Pass |
| E | oolong, Lima, Kestrel | not teal | oolong | Pass |
| F | silver under Aimee ID 4, oolong, Lima, Kestrel | not teal | oolong | Pass |

Answers must terminate and be nonempty. A–D require exact case/whitespace-
normalized `teal`; E–F must not mention `teal` anywhere. E/F passing demonstrates
only target exclusion, not general abstention quality. There is no memory text
in any prompt, no training, no writer, and no latency acceptance criterion.

The experiment also records singleton controls, a no-memory control, exact
generated tokens, C/D first-token score differences, and per-step attention
weights by Aimee ID. Reversing C into D changes no value, identity or query.

Only if all six conditions pass and C/D output order invariance holds does the
runner test two-memory composition: oolong preference plus Lima home city,
with each-memory-removed controls. Otherwise composition is deferred.

## Interpretation and composition

This establishes that the existing interface can consume the target Aimee
projection in a four-memory bank without losing the target answer. Reversing
that bank preserved every generated token. Removing or replacing the target
value removed `teal` from the answer, even when its Aimee ID remained present.
The no-memory control answered `unknown`.

The negative controls answered an unrelated fact, `oolong`; they did not abstain.
These results therefore establish the requested target-exclusion behavior, not
reliable rejection of irrelevant memories. One target question also cannot
establish general query-dependent discrimination across the bank.

C/D had identical generated tokens but not identical first-token scores:
maximum absolute score difference was 0.29296875. Thus ordering did not change
the answer in this test; numerical order invariance is not established.

The composition query was:

> Give the preferred drink of unit-b03646cbf4, then the home city of
> unit-121330aded. Separate the two values with a semicolon.

| Bank | Answer |
|---|---|
| Both memories | oolong |
| Drink only | oolong |
| City only | Lima |

The expected combined answer was `oolong; Lima`. Both constituent projections
work individually, but the combined bank did not produce both facts.

At the last prefill position, C/D assigned approximately 93.25% attention to
teal and 6.75% to oolong. The composition bank assigned effectively all attention
to oolong and approximately 7e-18 to Lima. This is consistent with selection
dominating composition in this instance; it does not by itself identify the
cause. The injected residual norm was approximately 21 times the incoming
hidden-state norm at that position, another measured diagnostic rather than
an independently established cause.

No writer changes are justified by this test. The immediate unresolved behavior
is combining existing values through the native interface. A useful next
experiment would hold the same bank fixed and ask for each constituent
individually, then together, to separate query-sensitive selection from
composition. That experiment has not been run here.

## Execution and evidence

The [fixed plan](../../benchmarks/native_memory/aimee_bank_plan.json) and
[source captures](../../benchmarks/native_memory/results/2026-09-20/aimee-bank-001/sources.json)
are saved. Structural tests verify the exact bank interventions and negative
control scoring; both tests passed. The experiment completed on `.253` with
process exit status 0:

- Service: `aimee-native-bank-001.service`.
- Immutable source: `/opt/aimee-native-p0-training/aimee-bank-001-source/`.
- Results: `/opt/aimee-native-p0-training/aimee-bank-001/`.
- Log: `/opt/aimee-native-p0-training/aimee-bank-001.log`.

Saved local evidence:

- [Summary](../../benchmarks/native_memory/results/2026-09-20/aimee-bank-001/summary.json).
- [Prompts, generations and attention traces](../../benchmarks/native_memory/results/2026-09-20/aimee-bank-001/generations.jsonl).
- [Checkpoint and source provenance](../../benchmarks/native_memory/results/2026-09-20/aimee-bank-001/provenance.json).
- [Post-run Aimee verification](../../benchmarks/native_memory/results/2026-09-20/aimee-bank-001/source-verification-after.json): all five source contents, scopes and stores unchanged.

All A–F prompts matched the no-memory prompt exactly (59 tokens each), including
their token-ID hashes. The composition prompts contained 77 tokens and no
memory values. The native interface and value table remained frozen throughout.

This is one target query and one fixed distractor set. It measures the requested
smallest progression, not broad accuracy across arbitrary memory banks.
