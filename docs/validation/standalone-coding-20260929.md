# Installed plugin: full repository repair workflows

The released 0.1.1 wheel completed the primary six-task comparison on Gemma4
26B A4B Q8: **native memory resolved 4/6 issues, text memory 3/6, and no memory
2/6**. Native memory added Flask and pytest successes while retaining both
control successes. **The native repeat resolved 5/6**, retaining all four
initial successes and additionally resolving Requests. All 24 attempts completed
with zero recorded infrastructure errors across 167 model calls.

This is a larger workload than the preceding connection and canary checks:
agents inspect repositories, execute commands, edit source, and produce patches
for separate official SWE-bench grading. These are six selected, previously
studied regression/transfer cases, not a random or unseen SWE-bench sample.
The repeat uses unchanged memory and tests consistency, not further learning.

## Outcomes

| Issue | No memory | Text memory | Native memory | Native repeat |
|---|---|---|---|---|
| Flask 4169 | Unresolved | Unresolved | Resolved | Resolved |
| pytest 5808 | Unresolved | Resolved | Resolved | Resolved |
| Astropy 7336 | Resolved | Resolved | Resolved | Resolved |
| SymPy 20590 | Resolved | Resolved | Resolved | Resolved |
| Matplotlib 25340 | Unresolved | Unresolved | Unresolved | Unresolved |
| Requests 2193 | Unresolved | Unresolved | Unresolved | Resolved |
| Total | **2/6** | **3/6** | **4/6** | **5/6** |

The primary matched comparison has two gains, zero regressions, and two retained
control successes. A successful patch must pass the official issue-resolution
criteria; a nonempty patch alone is not a success. Empty predictions are counted
as unresolved but distinguished from patches that fail grading in the archive.
The repeat's additional success reflects run-to-run variation with unchanged
memory, not a learned improvement between these two attempts. We report both
native runs rather than selecting the better one as the primary result.

| Native success | Issue tests changed from failing to passing | Existing tests retained passing |
|---|---:|---:|
| Flask 4169 | 1 | 24 |
| pytest 5808 | 1 | 6 |
| Astropy 7336 | 1 | 339 |
| SymPy 20590 | 1 | 21 |

Both native runs passed these checks for all four issues: four issue-specific
tests and 390 preservation checks per run. These checks do not turn six issues
into hundreds of independent task samples. The successful patches change
production source (`cli.py`, `pastebin.py`, `decorators.py`, and
`_print_helpers.py`), not the grading tests.
The Requests repeat additionally passed eight issue-specific tests and 125
preservation checks with a patch to `requests/adapters.py`.

## What was tested

We installed `aimee_vllm-0.1.1-1-cp312-cp312-linux_x86_64.whl` from the controlled
release into an unmodified supported vLLM environment. The wheel SHA-256 is
`935ad0fd307883bba31338686cc57df63e5f2f4afacff34a8b2c9fcd80cf85b3`.
The disposable upstream container provided laboratory isolation; it is not a
distributed Aimee runtime. The consumer library and kernel assets came from the
installed wheel, without a private source checkout or vLLM fork.

The run used both RX 7900 XTXs, tensor parallelism two, and vLLM
`0.30.0+rocm723`. Each fresh attempt started from the issue's base commit.
Budgets were 8,192 context tokens, 1,536 output tokens per response, 60 steps,
and 900 seconds of agent time, with at most two concurrent attempts. The
existing runner checks time between calls: an in-flight call can finish after
900 seconds. Patches present at that point are still graded. Grading time is
separate, with the previously established longer allowance for Requests.

The first three conditions rotate across tasks; a fresh native repeat follows.
All conditions receive the same issue; memory conditions use the same frozen
source procedure. Text memory appends the
complete procedure to the system message; native memory supplies the complete
prepared record without its text in the prompt. Indexed token counts and
prepared artifact hashes were checked before execution. The records span
94–432 native memory tokens, with one complete procedure per issue.

Publication selection is fixed explicitly through the research fixture catalog.
This isolates consumer task quality and lets text and native receive the same
source information. It does not retest live Aimee retrieval or authorization;
those remain the separately reported [standalone connection checks](standalone-plugin-20260929.md).
It also does not test multi-record composition or corpus selection pressure.
Reference patches and private grader definitions were excluded from agent input.

The [frozen protocol](../protocols/standalone-coding-20260929.md) specifies these
conditions and the distinction from earlier, smaller-budget experiments.
Do not attribute differences from those earlier experiments solely to packaging.

## Prompt context, tokens, and time

Native and control first-turn prompt token counts match on every task. Native
memory therefore adds no prompt text tokens in this comparison. The native
tensors still occupy memory and participate in attention; absence of prompt
tokens does not mean zero computational cost.

| Issue | Control / native initial prompt | Text initial prompt | Prompt tokens avoided |
|---|---:|---:|---:|
| Flask 4169 | 458 | 547 | 89 |
| pytest 5808 | 478 | 567 | 89 |
| Astropy 7336 | 627 | 741 | 114 |
| SymPy 20590 | 356 | 492 | 136 |
| Matplotlib 25340 | 980 | 1,407 | 427 |
| Requests 2193 | 221 | 606 | 385 |
| Total | 3,120 | 4,360 | 1,240 |

That is **28.4% fewer first-turn prompt tokens** than the text condition across
these six inputs, with the same source procedures available through native
memory. It excludes output tokens and later conversation turns.

First-turn context savings and whole-task token consumption answer different
questions. Once agents take different actions, they generate different command
outputs and need different numbers of calls. For example, pytest native passed
but used more total tokens and agent time than pytest text. This campaign is
not evidence that native memory is uniformly faster or cheaper per task.

| Condition (six attempts each) | Model calls | Prompt tokens, all calls | Output tokens | Summed agent seconds |
|---|---:|---:|---:|---:|
| No memory | 51 | 143,689 | 10,945 | 5,197 |
| Text memory | 40 | 87,031 | 9,724 | 3,825 |
| Native memory | 38 | 67,918 | 8,152 | 3,758 |
| Native repeat | 38 | 69,506 | 8,392 | 3,432 |

These totals describe the observed workflows, including unresolved attempts.
Summed agent seconds are not campaign wall time because attempts overlap.
They are rounded to whole seconds rather than implying subsecond timing
precision for this workload.

Recorded agent time includes generation, tool execution, compilation effects,
and shared GPU scheduling. It is not an isolated native-memory activation
latency measurement. The unchanged between-call deadline explains attempts
whose elapsed time exceeds 900 seconds.

## Failure observations and operational corrections

Matplotlib remained unresolved in all four conditions. The initial native
attempt made ten calls, without an output-token-limit hit or command-format
correction, and kept inspecting widget code without producing a patch before
the deadline. The initial Requests native attempt made seven calls, hit the
output limit once, received three command-format corrections, and produced no
patch. These traces identify unfinished agent workflows; they do not establish
that memory could never help these issues, or isolate the cause of each failure.

Requests text did produce a patch, but introduced an `IndentationError` in
`requests/adapters.py`; package installation and test collection failed. The
official report consequently marks its expected tests unsuccessful. Those are
not 133 independently executed assertion failures, and the error is in the
agent's patch rather than a serving failure.

Flask native and its repeat, Astropy control, and Requests native repeat reached
the time budget with correct patches already on disk. They passed official grading and remain
successes. Conversely, pytest control submitted an empty patch. Reporting only
the runner's exit label would misrepresent both kinds of outcome.

One setup problem occurred before any task attempt: host-created output files
were not writable by the mapped container user. Correcting the shared directory
ownership allowed server startup. The original executed coordinator and the
explicit correction are retained. No model, memory, input, or budget changed
in response to task outcomes, and no product-code repair was needed during
this campaign.

## Evidence

The [evidence directory](artifacts/standalone-coding-20260929/) retains the frozen
manifest, installed environment, trajectories, generated patches, official
grading reports, raw logs, and checksums. The campaign archive excludes model
weights, credentials, and the private grader-only input file. The halfway
checkpoint remains separately preserved rather than overwritten.
All evidence checksums and trajectory hashes passed, and regenerating the
summary from the archived files reproduced the committed summary exactly.
The disposable serving container was stopped and removed after completion;
the normal native compiler service remained active.
