# Native composition with singleton prerequisites — 2026-09-20

Historical learned-adapter experiment, not the current untrained Qwen ↔ Aimee
adapter. Do not carry its outcome forward as a limitation of the current native
path. See the [established POC baseline](qwen-aimee-poc-baseline.md).

This replaces the invalid equal-mixing experiment with the user's three-run
protocol. Existing drink and city projections pass through the unchanged
native interface; no manual mixing, scaling, normalization, parameter updates,
or writer operation is applied.

**Result: both singleton prerequisites failed. Composition was not adjudicated.**
The observed issue is prompt/latent generalization: each singleton supplied its
known value but did not follow the requested two-field response with `unknown`.

## Fixed protocol

The user prompt is identical in all three runs:

> Return exactly: <drink>; <city>. Use unknown for any value you do not know.

The original system instruction and chat template are unchanged:

> Answer using the available memory. Return only the requested value or values.
> If unknown, return unknown.

| Native bank | Expected |
|---|---|
| Aimee 5: drink projection only | oolong; unknown |
| Aimee 6: city projection only | unknown; Lima |
| Both untouched projections | oolong; Lima |

Both single-memory arms must pass under this same prompt before the combined
arm can establish composition success or failure. If either fails, the result
is classified as a prompt/latent generalization issue and composition is not
adjudicated. All three runs are executed and retained regardless.

Scoring requires normal termination and the two expected semicolon-separated
values in order, allowing case and surrounding whitespace differences. Exact
string matches and raw outputs are also reported.

## Controls

The model, saved adapter, latent values, injection point, original learned
attention, and greedy decoding settings are unchanged. Each arm starts a new
generation with no previous sequence state. The ordinary adapter still does
its learned aggregation; the experiment does not replace or override it.

The harness verifies equal prompt token IDs, zero memory text, use of the
original selector, and exact before/after equality of both value vectors and
all adapter parameters. Aimee IDs 5 and 6 were reread and their contents, scopes,
and stores checked against the earlier source capture. The frozen model and
checkpoint are loaded through the original implementation and hash checks.

## Execution

The experiment completed on `.253` with process exit status 0:

- Service: `aimee-native-composition-001.service`.
- Immutable source: `/opt/aimee-native-p0-training/aimee-composition-001-source/`.
- Results: `/opt/aimee-native-p0-training/aimee-composition-001/`.
- Log: `/opt/aimee-native-p0-training/aimee-composition-001.log`.

Local evidence directory:
`benchmarks/native_memory/results/2026-09-20/aimee-composition-001/`.

## Results

| Bank | Expected | Actual | Prerequisite/result |
|---|---|---|---|
| Drink only | oolong; unknown | oolong | Singleton prerequisite failed |
| City only | unknown; Lima | Lima | Singleton prerequisite failed |
| Both | oolong; Lima | oolong | Recorded; not adjudicated as composition |

All outputs ended normally. All three runs used identical 56-token prompts
and zero memory tokens. The original learned selector executed three times
in each generation. Both source vectors and all adapter parameters compared
exactly equal before and after. No training or inference-path override occurred.

The known values remained accessible individually, but their behavior under
the requested response format and missing-value instruction was not established.
The combined-bank output therefore provides no valid composition verdict.
No further prompt changes or experiments were performed in this run.

Saved evidence:

- [Summary and adjudication](../../benchmarks/native_memory/results/2026-09-20/aimee-composition-001/summary.json).
- [Drink-only prompt and output](../../benchmarks/native_memory/results/2026-09-20/aimee-composition-001/drink_only.json).
- [City-only prompt and output](../../benchmarks/native_memory/results/2026-09-20/aimee-composition-001/city_only.json).
- [Both-memory prompt and output](../../benchmarks/native_memory/results/2026-09-20/aimee-composition-001/both.json).
- [Checkpoint and source provenance](../../benchmarks/native_memory/results/2026-09-20/aimee-composition-001/provenance.json).

No latency, scale, writer-generalization, or broad accuracy claims are part
of this experiment.
