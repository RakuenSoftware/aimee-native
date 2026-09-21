# Aimee-authoritative native memory POC — 2026-09-20

**Demonstrated on one actual Aimee memory using an existing, content-matched
latent projection.** All six question forms succeeded without memory text in
the native prompt. One controlled success was the requested feasibility criterion.

The question was: can a Qwen latent-memory mechanism consume a memory whose
authoritative source is Aimee, with no representation of that memory in the
model's textual context? Accuracy parity, speed, routing, archive scale and
production architecture were explicitly excluded from this acceptance test.

## Source and observed result

The registered Aimee CLI stored and read back synthetic research memory `4`:

> The beacon color of unit-81b1315e68 is teal.

The actual [Aimee read-back](../../benchmarks/native_memory/results/2026-09-20/aimee-source-cached-poc/get.json)
reports store `user`, scope `user/_user`, tier `L3`, kind `fact`, and key
`research.native-poc.20260920.cached-beacon`. Only this synthetic record was
used; no private memory was accessed. A second Aimee read after evaluation
confirmed the authoritative content was unchanged.

The runtime verified that Aimee's content exactly matched an existing learned
projection, bound the derived artifact to Aimee ID `4` and the content/model
hashes, saved and reloaded it, then supplied it to Qwen's native memory layer.
No parameters were trained in this direct source-consumption test. The
pretrained base and memory interface remained frozen.

| Mode | Correct answer `teal` |
|---|---:|
| Native, Aimee-selected matching projection | **6/6** |
| Text control | 6/6 |
| No memory | 0/6 |
| Native disabled | 0/6 |
| Empty native bank | 0/6 |
| Wrong latent value, same Aimee ID | 0/6 |

The no-memory, disabled and empty conditions answered `unknown`. Native
prompts were token-for-token identical to no-memory prompts and added zero
memory tokens. They contained only the ordinary system instruction and question:
no fact, answer, memory ID token or hidden memory prefix. Each generation used
a fresh context; the text-control context was not reused.

The [summary](../../benchmarks/native_memory/results/2026-09-20/aimee-source-cached-poc/summary.json)
records six paired native successes and all invariant checks passing. Exact
[native prompts](../../benchmarks/native_memory/results/2026-09-20/aimee-source-cached-poc/native-prompts.json),
[per-arm outputs](../../benchmarks/native_memory/results/2026-09-20/aimee-source-cached-poc/evaluation.jsonl),
source/projection provenance and the small latent artifact are retained beside it.

This demonstrates the Aimee-source-to-latent-consumption path using a cached
projection. It does not establish a general compiler for arbitrary new facts.

## Separate writer attempt

Before isolating source consumption, a separate test stored Aimee memory `3`:
`The beacon color of unit-e470f703d0 is ultraviolet.` That answer was absent
from the trained memory table. Optimizing only one external vector for 240
steps, while freezing both model and interface, scored 0/6 versus text's 6/6.
The [writer result](../../benchmarks/native_memory/results/2026-09-20/aimee-source-poc/summary.json)
is preserved. This bounded writer failure is separate from the demonstrated
ability to consume an existing projection selected from authoritative Aimee
content; it has not been hidden or counted as success.

## Reproduction and test criterion

`run_aimee_source.py --compiler cached` implements the successful test. It reads
unmodified `aimee --json memory get` output, refuses a cached projection whose
content differs, and generates six query forms under six controls. The optional
`--compiler optimize` performs the separate value-writing experiment.

The test records feasibility when at least one native answer matches Aimee
while paired no-memory and wrong-value conditions do not, with prompt equality
and disabled/empty parity intact. There is no percentage-accuracy or speed gate.
The end-to-end tiny-Qwen smoke passed before the real-model run; the actual
27B cached run then completed with process exit status zero.

Remote completed artifacts:

- Successful run: `/opt/aimee-native-p0-training/aimee-source-002/`.
- Immutable source: `/opt/aimee-native-p0-training/aimee-source-002-source/`.
- Service: `aimee-native-source-002.service` (completed).
- Separate writer attempt: `/opt/aimee-native-p0-training/aimee-source-001/`.

The previous oracle study's completed BF16 (85.5%) and FP32 (70%) results remain
intact. Its third learning-rate trial was stopped at 708 steps after the user
narrowed scope; that partial trial is not an accuracy result.
