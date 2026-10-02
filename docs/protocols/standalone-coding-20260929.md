# Installed plugin: full coding tasks

Frozen before inspecting this campaign's outcomes. This follows the three-model
standalone plugin smoke checks and tests a larger workload on the released
0.1.1 consumer, using Gemma4 26B A4B Q8 on two RX 7900 XTXs.

## Question and scope

Can the installed wheel execute complete repository repair workflows with native
procedural memory, while retaining control successes and using the same source
information as a text-memory comparator?

Use six previously selected public SWE-bench issues: Flask 4169, pytest 5808,
Astropy 7336, SymPy 20590, Matplotlib 25340, and Requests 2193. These are selected
regression/transfer cases with prior results, not a newly sampled benchmark.
Each memory is a complete previously accepted source procedure. The native bank
contains 94–432 memory tokens per task; all indexed token counts and prepared
artifact hashes must match the frozen preparation inventory before execution.
One complete procedural record applies to each task. This is not a multi-record
composition experiment or a corpus selection stress test.

The wheel comes from the signed private release, SHA-256
`935ad0fd307883bba31338686cc57df63e5f2f4afacff34a8b2c9fcd80cf85b3`.
Install it in an unmodified supported vLLM environment. The disposable upstream
container is test isolation only. No private serving image, source checkout,
patched vLLM, or alternative native library supplies the consumer.

The coding comparison fixes publication selection explicitly using the existing
research fixture catalog. It tests the installed consumer and task quality;
it does **not** repeat the separately completed live Aimee authorization,
connection, or retrieval evaluation. Keeping this boundary explicit also makes
it possible to give the control zero memory and the text arm exactly the same
source information as native consumption.

## Four conditions, 24 fresh attempts

- Control: no memory publication and no added memory text.
- Text: complete procedure appended to the common system message.
- Native: complete prepared procedure selected by publication, no memory text.
- Native repeat: the same native memory with a fresh clean checkout.

Rotate the first three conditions across tasks, then execute the native repeat.
The repeat tests reproducibility; it neither updates memory nor represents an
additional learning round. Temperature is zero and the seed is fixed. Inference
batching and GPU arithmetic can still introduce run-to-run differences.

Every attempt starts at the dataset base commit in an isolated repository
container. Agent-visible input excludes reference patches, test patches, and
private grading definitions. Grading runs separately using the official harness.
Retain each generated patch, trajectory, grading result, and failed attempt.
An infrastructure error stops further scheduling and is not scored as a model
failure. Already running attempts finish and remain recorded.

Budgets are identical across conditions: 8,192 context tokens, 1,536 output tokens
per response, at most 60 agent steps and a 900-second agent wall-time budget,
concurrency two. The existing harness checks that time budget between calls;
an in-flight model/tool call can finish after the deadline. It is not a hard
cancellation at 900 seconds. This clarifies the unchanged runner behavior; no
budgets or scheduling conditions were changed after observing outcomes.
The runner reserves 280 tokens and caps input history at 6,376 tokens. Complete
initial issues remain in history; older interaction pairs are removed as needed.
Grading gets 300 seconds, except the previously established Requests requirement
of 3,600 seconds. Grading time is distinct from agent time.

These are larger budgets than the earlier 4,096-token/40-step/600-second
comparison. Compare conditions *within this campaign*; do not attribute changes
from that earlier campaign solely to wheel packaging.

## Reporting

Report per-task official outcomes, paired gains/regressions against control,
native-repeat consistency, and infrastructure errors. Record each model call's
prompt/output tokens, elapsed seconds, finish reason, publication identity, and
prompt/response hashes. Aggregate tokens and time separately from task success;
different agent trajectories need different numbers of calls, so campaign token
totals are not a matched-prompt prefill benchmark. Record prompt context savings
without pretending native tensors occupy no GPU memory or attention work.

Operators: `distribution/tests/standalone_coding_host.py` on the designated host,
and `distribution/tests/standalone_coding_campaign.py` in the existing isolated
SWE evaluator. The runner source and input hashes are bound in the campaign
manifest. No model weights or credentials belong in the evidence archive.
