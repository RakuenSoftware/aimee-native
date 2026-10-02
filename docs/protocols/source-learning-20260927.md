# Source-backed overnight learning campaign

The goal is to restore useful task capability, not merely native record delivery.
This campaign uses sixteen frozen SWE tasks, two concurrent attempts, and four
arms per task: no-memory control followed by three native-memory learning rounds.
Each attempt has the same 40-step, 600-second, 512-output-token, 8192-context budget.
There are 64 scheduled attempts. Task selection interleaves the eight previously
calibrated tasks with the first eight other tasks in the original frozen order;
selection does not filter on outcomes. This is repeated-task experience reuse,
not held-out-task generalization or underlying weight learning.

Generated summaries are disabled throughout acquisition. Successful experiences
retain the complete agent-produced patch, trajectory hash, exact task/base scope,
and an executable procedure. A procedure is accepted only after independent
replay on a clean checkout reproduces the exact patch that passed the official
overall evaluation. Candidate commands come from actually executed, zero-exit
commands in the trajectory, never assistant claims. A complete quoted patch
application is the fallback when individual commands cannot reproduce a
multi-step edit. Replay is confined to a network-isolated benchmark container.
No hidden grader tests or reference patch enter this path.

The two historical calibration learn-1 successes, where present in the selected
set, are automatically acquired with this same replay check. They are prior
experience, not newly learned successes in this run. New control and native
outcomes then feed the same capture logic. Failed outcomes cannot replace an
accepted success. Failed attempts contribute exact observed tool failures,
explicitly labeled as unsuccessful, rather than model-generated explanations.
Every complete source observation remains archived, including those not selected
for the bounded failure-memory record.

Preparation publishes each complete selected experience. Oversize records fail
explicitly instead of being silently shortened. The consumer receives no memory
text in the prompt and no pre-applied patch. It must choose, execute and validate
its own actions, then submit a patch to the official grader. Changing the memory
representation does not change the editing tools or increase inference budgets.

Primary outcomes are task success, paired gains and paired regressions against
control, and retention across rounds. Infrastructure errors remain separate.
Exact per-attempt timings, output limits, source hashes and publications are
retained. No result from the superseded summary-based experiments is rewritten.
The queued process waits for the frozen-lesson diagnostic to finish before
changing the shared publication catalog.

This implements the research acquisition loop in aimee-qwen. Official benchmark
outcome is its acceptance signal; it does not substitute for a production
validator or authoritative Aimee authorization policy. Production release
readiness additionally requires exact-package certification and lifecycle checks.
