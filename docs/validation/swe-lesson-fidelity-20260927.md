# SWE lesson fidelity investigation

## Observed regression

The first fifteen completed matched attempts resolve 5/5 without memory, 0/5
with the frozen successful lesson as text, and 0/5 with the same lesson as native
memory. There are no infrastructure failures. The original eighteen-attempt
comparison is continuing unchanged. These are fixed-seed repeats of one
previously inspected task, not fifteen independent tasks.

The [initial audit](artifacts/swe-lesson-fidelity-20260927/initial-audit.json)
records the exact snapshot, per-attempt diagnostic counts and CPU-only replays.
Raw trajectories remain in `/opt/swe-native/matched-flask-20260927` on CT113.

## First divergence and independently reproduced failures

The successful calibration trajectory used an edit anchored immediately before
`self.name = name`. Its exact command, replayed in a fresh isolated benchmark
container at the same dataset base, passes all 59 existing Flask blueprint tests.
The resulting diff matches the source successful patch. This replay uses only
the agent's own command and existing tests, not the hidden reference patch.

The derived lesson contains the correct validation code, but omits the command
that actually succeeded. It instead tells the next agent to insert a check
"immediately after the dot character check." That is semantically reasonable,
but is not an executable record of the successful procedure. Its claim about
partial initialization is explanatory model-generated prose, not something the
original test established.

In the first text attempt, `cat` returns only the first 5,000 characters through
the observation template, without a truncation marker. The constructor is not
visible in that excerpt. The agent proceeds without a targeted constructor read.
Its first executed source edit inserts a four-space `if not name` immediately
after the existing eight-space `if "." in name`, splitting the existing block.
Independent replay produces an `IndentationError` on import.

In the first native attempt, the agent does read the relevant constructor. Its
first edit nevertheless inserts a four-space check at line 201, outside the
method. Independent replay produces `NameError: name 'name' is not defined`
while defining the class. Thus invisible source alone cannot explain both arms.

Both conditions then attempt repairs with fragile nested shell/Python quoting.
The maximum number of identical executed commands is 13 in the text trajectories
and 15 in the native trajectories. Errors are visible in the observations; the
agent does not reliably change its action in response. These are repeated validly
formatted but failing commands, not the earlier kernel-induced `thought` loop.

The control is itself brittle: it makes malformed edits and receives four format
corrections, with four output-limit terminations, before recovering in twenty
calls. Text attempts have two truncations and three format corrections; native
attempts have eight or nine truncations and nine or ten format corrections.
The fixed 512-token output limit, repeated-error handling, silent observation
truncation and bounded-history trimming are additional candidates, not proven
sole causes. Increasing a budget by itself would not fix a repeated bad command.

## Relation to earlier successful experiments

The earlier procedural-learning pipeline used retained, validated procedures and
explicit prediction-versus-observation feedback. Its consumer was a Transformers
BF16 eager-attention worker answering individual procedural questions. The SWE
consumer is a Q8 vLLM service operating a multi-turn shell-editing loop. Both the
runtime and downstream task changed; this is not a controlled reproduction of
the earlier result. Earlier evidence is not invalidated, but cannot certify this
new integration or multi-turn execution behavior.

The SWE learner currently publishes a generated prose summary after receiving
the task outcome. It does not validate that the summary reproduces the successful
behavior, and does not deterministically preserve the exact working action.
The matched study deliberately froze that summary, so its failures are not due
to later rounds overwriting it. The architectural lesson is to distinguish a
successful experience from an unvalidated description of that experience.
Whether preserving the exact action restores performance remains to be tested.

## Predeclared diagnostic follow-up

The driver `benchmarks/swe_learning/diagnostics/lesson_fidelity.py` is deployed
at `/opt/swe-native/lesson-fidelity-20260927`. It waits for the matched comparison
to complete before preparing or using the shared engine. It does not mutate the
matched run or its publication during that run.

Eight attempts, serial, at the same seed, model, 600-second/40-step budgets,
512 output tokens and unchanged editing tools:

1. No-memory control.
2. Original summary plus the exact successful command, text.
3. Exact successful command with provenance, native.
4. Concise behavioral invariant, text.
5. Original summary plus the exact successful command, native.
6. Exact successful command with provenance, text.
7. Concise behavioral invariant, native.
8. No-memory control.

The successful command is extracted from the original agent trajectory, not
written from a hidden solution. All memory variants are frozen before the
queue starts. Their hashes and source hashes are persisted. No lessons change
between trials, and no variant is dropped based on its outcome. Publications
retain every complete selected record. Each attempt gets a fresh checkout and
the official grader. This is an exploratory one-trial-per-cell diagnosis, not
an effect-size estimate or a new claim of general learning success.

If preserving the action helps, validate source-backed experience retention on
additional tasks before promoting it. If both delivery modes still fail, isolate
tool execution and recovery at captured histories before changing memory content
again. A native-only residual regression requires a separate runtime probe;
text failures do not exonerate native integration.

No production learning policy or customer runtime is changed by this diagnostic.
