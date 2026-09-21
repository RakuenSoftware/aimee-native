# Fixed equal native-memory mixing — 2026-09-20

Question: can the existing drink and city projections produce a composed answer
when competitive attention is replaced by fixed equal weighting?

**Status: INVALID EXPERIMENT — excluded from feasibility conclusions.**
The user identified a fundamental problem with the test on 2026-09-20:
the constituent projections had not first been validated under the exact
composition prompt, and the intervention altered their combination.
The [replacement protocol and results](native-memory-composition.md) test
unchanged singleton and combined banks with an explicit missing-value instruction.
The prior interpretation is withdrawn; raw outputs are retained for the record.

Observed output: `ool` followed by its end token. The learned-attention control
returned `oolong`. These observations are not evidence of composition failure.

This is a single intervention following the
[tiny-bank experiment](native-memory-aimee-bank.md). It uses the same frozen
model, checkpoint, existing values, value/output projections, gate, injection
point after block 1, prompt token IDs, and greedy generation settings. There
is no writer, training, added memory text, or performance gate.

## Intervention

Aimee memory 5 supplies the previously proven `oolong` projection; memory 6
supplies the previously proven `Lima` projection. Both were reread from Aimee
and matched to their saved projection content before this run.

Ordinary injection computes query/key attention over the two projected values.
The intervention replaces those weights with `[0.5, 0.5]` at every prefill and
decode position:

```text
mixed = 0.5 * value(drink) + 0.5 * value(city)
output = hidden + sigmoid(existing_gate(hidden)) * existing_output(mixed)
```

The learned gate still modulates the combined signal exactly as before.
Query/key scoring and softmax are bypassed. This changes neither the latent
values nor any trained parameter. The original learned selector is replayed
first in the same process as a control, then the fixed mixer is evaluated in
a fresh generation with the same bank and prompt.

Prompt, identical to the previous composition test:

> Give the preferred drink of unit-b03646cbf4, then the home city of
> unit-121330aded. Separate the two values with a semicolon.

Expected answer: `oolong; Lima`.

## Validation and evidence

Two structural tests passed on the research runtime: fixed mixing matches
the explicit mean while retaining the gate/output arithmetic and ignoring
unusable keys and a disabled query module; an empty bank is an identity and
unexpected bank sizes are rejected. During full-model inference, hooks reject
any query or normalization call in fixed mode. Prompt token IDs must match
the preceding experiment exactly. Adapter parameters are compared before/after.

## Raw observations (invalid test)

| Mode | Expected by original test | Actual | Matched expected string? |
|---|---|---|---|
| Original learned attention | oolong; Lima | oolong | No |
| Fixed 50/50 weights | oolong; Lima | ool | No |

Both generations terminated normally; `ool` was not a generation-length cutoff.
Both used the identical 77-token prompt from the prior experiment, with zero
added memory tokens. The fixed mode made zero query/normalization calls;
the control made six. Fixed weighting applied throughout prefill and decode.
Adapter parameters compared exactly equal before and after. Training steps
and trainable parameter counts were both zero.

The experiment completed on `.253` with process exit status 0:

- Service: `aimee-native-equal-mix-001.service`.
- Immutable source: `/opt/aimee-native-p0-training/aimee-equal-mix-001-source/`.
- Results: `/opt/aimee-native-p0-training/aimee-equal-mix-001/`.
- Log: `/opt/aimee-native-p0-training/aimee-equal-mix-001.log`.

Saved evidence:

- [Validity assessment](../../benchmarks/native_memory/results/2026-09-20/aimee-equal-mix-001/assessment.json): supersedes the interpretation of raw pass/fail fields below.
- [Summary](../../benchmarks/native_memory/results/2026-09-20/aimee-equal-mix-001/summary.json).
- [Fixed-weight output and trace](../../benchmarks/native_memory/results/2026-09-20/aimee-equal-mix-001/equal.json).
- [Learned-attention control](../../benchmarks/native_memory/results/2026-09-20/aimee-equal-mix-001/learned.json).
- [Checkpoint and source provenance](../../benchmarks/native_memory/results/2026-09-20/aimee-equal-mix-001/provenance.json).
- [Aimee read-back inputs](../../benchmarks/native_memory/results/2026-09-20/aimee-equal-mix-001/sources.json).

No conclusions about selection, averaging, downstream interference, or latent
composition should be drawn from this invalid test. Original machine-generated
outputs and scores are preserved unchanged; their pass/fail fields describe
only the original scoring rule, not an accepted scientific result. The user's
replacement test is recorded separately in the report linked above.
