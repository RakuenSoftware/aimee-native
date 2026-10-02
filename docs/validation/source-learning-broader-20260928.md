# Completed 32-task source-learning follow-up

The frozen follow-up completed 64 officially scored attempts: one control and
one native-memory attempt per task. Control passed **5/32 (15.6%)**; native
passed **4/32 (12.5%)**. Four tasks passed in both conditions, twenty-seven
failed in both, and Requests-2193 passed only in control. No task passed only
with native memory. These results do not establish a broader task-success gain.

All four retained successes reproduced the control's patch and used fewer
model calls. The agent-duration reductions are useful procedure-reuse evidence,
but exclude acquisition/preparation and do not isolate memory from a second
attempt. No fresh second no-memory attempt was run in this study. The earlier
16-task campaign's one retained gain remains a separate result, not a reason
to omit this regression.

## Protocol and evidence

The 32 tasks were fixed before this follow-up, excluding the primary sixteen.
Sixteen had earlier broken-run exposure, documented in the protocol; no prior
memory was supplied to this follow-up. Each task used a clean base checkout,
40-call/600-second agent budgets, 1,536 output tokens, and the same 8,192-token
runtime context. Four pipelines ran concurrently. Wall limits are checked
between steps; an in-flight final request can overrun the nominal time budget.
Success memory used only the agent's own patch, own observations, an overall
grader outcome, and independent clean-base patch replay. No generated summary
or hidden reference patch was provided as memory.

Two infrastructure interventions are retained: the generation deadline was
raised after an interrupted request, and Requests-2193 grading used 3,600 seconds
after the original 900-second control grade timed out. The unchanged control
patch passed that extended grade. Interrupted attempts and original reports
remain in the linked recovery evidence; they were not scored as model failures.

- Final report: [64-attempt outcomes](artifacts/broader-source-learning-20260928/scored-checkpoint-1790575273.json).
- Complete snapshot: [253-file archive, including checksum manifest](artifacts/broader-source-learning-20260928/scored-checkpoint-1790575273.tar.gz), SHA-256 `cb1899815821906554f94dcea501aa19dc0f0d39a1418ce335b45e7068cf96f0`.
- Final delivery audit: [1,233 calls, 64 trajectories, 31 publications](artifacts/broader-source-learning-20260928/delivery-audit-final-1790575308.json).
- Successful-pair costs: [scope-corrected measurements](artifacts/broader-source-learning-20260928/four-successful-pairs-v2.json).

All 252 embedded file checksums were independently verified after download.
The delivery audit verifies complete source records, identities, and request
routing, not an independent proof of tensor semantics.

## Requests-2193 regression

The control's passing patch was replayed successfully before its complete
procedure was encoded. During native generation the model reproduced a
malformed diff: a four-command response was first rejected, then `git apply`
reported a corrupt patch. Subsequent malformed multiline `sed` commands
corrupted the checkout. The agent submitted after 11 calls and 309.5 seconds;
the official grade completed and failed. This is a generation/use failure,
not evidence that the original stored patch was wrong or silently truncated.
The preserved final patch makes the failed edits inspectable.

A separate corrective candidate mechanically converts ordinary text patches
to shorter exact line-edit procedures. For this patch it reduces the command
from 2,079 to 960 characters. It preserves all edits, including duplicated
lines; it is not a generated summary or a hand-written solution. On a fresh
Requests benchmark checkout, the generated procedure reproduced the same
passing patch byte for byte. The [CPU replay evidence](artifacts/source-procedure-representation-20260928/requests-compact-replay.json)
is a representation check, **not** proof of improved model recall or a new
successful task attempt. GPU validation remains required. The completed
32-task study and its source representation are unchanged.

## Residual repetition diagnostic

A post-hoc replay of one preserved Pytest prompt ran twice per condition in
reversed order at temperature zero, retaining the original seed and budget.
Both no-memory responses repeated `thought` until the 512-token limit. Both
native-memory responses repeated a command until that same limit. The same
record supplied as text produced one fenced command and stopped normally in
both trials. There was no task grading in this diagnostic.

The [six raw responses](artifacts/broader-source-learning-20260928/pytest-repetition-replay-result.json)
and [fixed input fixture](artifacts/broader-source-learning-20260928/pytest-repetition-replay.json)
are preserved. This is evidence of a remaining native-versus-text behavioral
difference on a known problematic prompt. It does not establish its cause,
its frequency across tasks, or a model-wide defect. Summaries alone cannot
explain this residual case: the source record was an observed failure notice,
not a model-generated summary.

## Release implication

Source capture and routing now preserve verified procedures, and simple
native recall is separately undergoing exact-image certification. Automatic
learning reliability is not release-cleared by those checks. The Requests
regression and native/text repetition difference require corrective validation;
they must remain visible in any release recommendation.

## Subsequent repair and present scope

The chronological pending statements above describe the original follow-up.
A later literal-source Requests comparison completed: native and matched text
both passed official grading; the fresh no-memory control failed. Five selected
previously successful tasks then passed both native attempts (10/10). These
results are recorded in the [release work record](release-readiness-20260928.md)
and its linked immutable evidence. They support the targeted source-use repair
and retention; they do not replace this study's 5/32 versus 4/32 outcome or
resolve the separate native/text repetition diagnostic.
