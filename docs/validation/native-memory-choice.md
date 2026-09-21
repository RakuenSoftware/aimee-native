# Multiple-choice native composition probe — 2026-09-20

Historical learned-adapter experiment, not the current untrained Qwen ↔ Aimee
adapter. Both projections were supplied here; the later one-record retrieval
restriction does not explain this experiment. See the
[established POC baseline](qwen-aimee-poc-baseline.md) for current conclusions.

This experiment uses the user's exact probe with unchanged existing Aimee
drink/city projections, the original frozen model and native adapter, and
the same greedy decoding settings. A no-memory arm measures option priors.

**Result: the expected independent-axis pattern was not observed.** The
no-memory arm answered `B`; native arms emitted fact strings instead of option
letters. Their first-token label probabilities also failed the proposed axis
checks. This supplies no affirmative evidence of composition and does not
isolate a composition-specific failure from native prompt/response behavior.

```text
Which pair is correct?
A. oolong; Lima
B. oolong; Oslo
C. coffee; Lima
D. coffee; Oslo
Answer only A, B, C, or D.
```

The original system instruction and chat template remain unchanged. Each arm
starts a fresh sequence with identical prompt tokens:

| Arm | Native IDs | Intended signal |
|---|---|---|
| None | — | Measure preference without native memory |
| Drink only | 5 | A+B preferred over C+D |
| City only | 6 | A+C preferred over B+D |
| Both | 5, 6 | A preferred over B, C, D |

No authoritative memory text is injected. Unlike the prior recall probes,
the candidate answer values are present in the multiple-choice text. The
no-memory comparison therefore matters; this probe is not an independent
demonstration of recalling answer strings absent from context.

## Measurements

Raw logits are captured at the first generated-token position. The tokenizer
must encode each of A/B/C/D as a distinct single token. The harness saves:

- Full first-token logit vectors and the four label logits.
- Full-vocabulary probabilities for the labels and their total probability.
- Probabilities conditional on choosing one of A/B/C/D.
- Drink-axis probability P(A)+P(B), city-axis probability P(A)+P(C), and their
  log odds, with log-odds shifts relative to no memory.
- A's logit margins over B/C/D and the unrestricted greedy answer.

Conditional probabilities do not by themselves establish instruction following:
the total probability assigned to the labels and the actual answer are reported
alongside them. This is one fixed option order, not a broad accuracy estimate.

## Execution

The probability calculations passed an analytic fixture checking full versus
conditional probability, both axes, and log odds. The experiment completed
on `.253` with process exit status 0:

- Service: `aimee-native-choice-001.service`.
- Immutable source: `/opt/aimee-native-p0-training/aimee-choice-001-source/`.
- Results: `/opt/aimee-native-p0-training/aimee-choice-001/`.
- Log: `/opt/aimee-native-p0-training/aimee-choice-001.log`.

Before running, Aimee IDs 5 and 6 were reread and verified unchanged. The
harness checks original-selector execution, identical prompt tokens, and
exact before/after equality of the values and adapter parameters. There are
no parameter updates, projection alterations, forced labels, or sampling.

## Observed outputs and logits

All four prompts contained the same 80 tokens. The labels were verified as
single tokens: A=32, B=33, C=34, D=35. Native selector calls occurred in all
three native arms and not in the no-memory arm. Parameter and vector equality
checks passed. All generations terminated normally.

Raw first-token logits:

| Bank | A | B | C | D | Greedy answer |
|---|---:|---:|---:|---:|---|
| None | 20.50000 | 21.25000 | 20.62500 | 20.50000 | B |
| Drink only | 6.75000 | 4.53125 | 9.75000 | 6.40625 | oolong |
| City only | 8.18750 | 8.75000 | 8.00000 | 8.37500 | Lima |
| Both | 7.21875 | 5.81250 | 10.43750 | 7.12500 | oolong |

Probabilities **conditional on A/B/C/D**, in percent:

| Bank | A | B | C | D | Drink axis A+B | City axis A+C |
|---|---:|---:|---:|---:|---:|---:|
| None | 19.05 | 40.32 | 21.58 | 19.05 | 59.37 | 40.63 |
| Drink only | 4.57 | 0.50 | 91.70 | 3.24 | 5.06 | 96.27 |
| City only | 20.88 | 36.64 | 17.31 | 25.18 | 57.51 | 38.18 |
| Both | 3.68 | 0.90 | 92.06 | 3.35 | 4.59 | 95.74 |

Total full-vocabulary probability assigned to A/B/C/D:

| Bank | Total label probability, percent |
|---|---:|
| None | 95.78396% |
| Drink only | 0.00024634% |
| City only | 0.00000286% |
| Both | 0.00170197% |

The drink projection did not resolve the drink axis in the requested direction;
its conditional distribution instead favored C, which says `coffee; Lima`.
The city projection did not increase the city axis relative to the no-memory
control (38.18% versus 40.63%). The combined bank resembled drink-only in both
its emitted fact and its conditional choice distribution, rather than pushing
A above the alternatives.

The conditional city-axis preference under drink-only is therefore not evidence
that city knowledge was recovered: it occurs without the city projection, while
almost all output probability lies outside the option labels. The singleton
axis checks have not established that this checkpoint can use either projection
to answer the probe as intended. The observations remain compatible with a
native prompt/response generalization problem and do not establish the cause.
No prompt tuning, retraining, or further experiments followed this run.

## Prompt and training audit

A subsequent read-only audit checked the actual captured prompt and the
immutable training source/fixtures. The chat serialization includes the system
message, exact user question, and assistant generation prefix with the empty
thinking block produced by `enable_thinking=False`. The choice logits are read
at the first generated-token position. There is no observed missing user turn
or misplaced answer boundary; the no-memory arm also follows the letter format.

However, the probe is not matched to the adapter's training task. The saved
fixture has 210 examples: 200 single-memory examples and 10 two-memory examples.
There are no A/B/C/D answer targets and no `unknown` answer targets. The training
code supervises the answer tokens plus an end token, with prompt tokens masked
out of the loss. The drink singleton targets are `oolong`; the city singleton
targets are `Lima`. Those queries identify their respective synthetic entities;
the multiple-choice probe does not name either entity. The drink value also
appears in one trained composition (`violet; oolong`), while this city value
appears only in its two singleton examples. The drink/city pair is not a trained
composition example.

The retained system message requests the value or values and says to return
`unknown` when unknown; it was not tailored to the new letter-only task. This
is a possible instruction ambiguity, not a demonstrated serialization defect.

Consequently this experiment also tests new response-format and task
generalization. The observations are consistent with a learned tendency to
emit the fact directly and stop, but that mechanism has not been causally
established. The test does not establish that the bank cannot hold both
memories, or that the frozen model cannot compose them through a suitable
native interface. Prompt correctness at the token boundary does not establish
that this is a clean composition-only probe.

## Saved evidence

- [Summary, probabilities and baseline-relative log odds](../../benchmarks/native_memory/results/2026-09-20/aimee-choice-001/summary.json).
- [Protocol and label token IDs](../../benchmarks/native_memory/results/2026-09-20/aimee-choice-001/protocol.json).
- [No-memory output](../../benchmarks/native_memory/results/2026-09-20/aimee-choice-001/none.json).
- [Drink-only output](../../benchmarks/native_memory/results/2026-09-20/aimee-choice-001/drink_only.json).
- [City-only output](../../benchmarks/native_memory/results/2026-09-20/aimee-choice-001/city_only.json).
- [Both-memory output](../../benchmarks/native_memory/results/2026-09-20/aimee-choice-001/both.json).
- [Checkpoint and source provenance](../../benchmarks/native_memory/results/2026-09-20/aimee-choice-001/provenance.json).

Each arm's full first-token logit vector is saved as
`<arm>-first-token-logits.pt` in the same evidence directory, alongside the
original log and source hashes.
