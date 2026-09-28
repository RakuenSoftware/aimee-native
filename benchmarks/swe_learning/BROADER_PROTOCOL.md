# Additional source-backed task replication, 28 September

This separate follow-up expands the repaired evaluation from 16 to 48 distinct
SWE-bench tasks. It does not replace or pool away the primary study's three
native rounds, its failures, or its declared prior calibration experience.

Select the first 32 tasks from the original frozen 150-task order whose identities
are absent from the primary 16-task list. Selection does not use outcomes. The
manifest records previous exposure in the broken run: 16 of these 32 tasks were
previously attempted. No memories from those attempts or from calibration are
supplied. This is not a held-out generalization claim.

Each task has two conditions: a fresh no-memory control, then a fresh native
attempt consuming experience automatically captured from that control. Both use
600 seconds, 40 calls, 512 output tokens, the same bounded-history policy, and
the official grader with a 900-second allowance. Preparation and grading remain
outside the model's attempt budget. Capture preserves complete source-backed
procedures and exact replay; unsuccessful controls provide observed failure
information, not model-generated summaries. No reference solution or hidden
test content is supplied to the agent or memory.

Four independent task pipelines share the existing server. A pipeline awaiting
CPU grading does not impose a barrier on unrelated pipelines. Each native
attempt's publication remains retained until that attempt returns; publication
updates are serialized so concurrent tasks cannot evict each other's required
records. A four-way overlap test checks this retention property and tolerates
unrelated result files being mid-write. This concurrency differs from the
primary study's two-agent setting, so report results separately.

The controller waits for all primary results to be scored before starting.
Images are fetched in advance under a host thin-pool reserve check; the controller
cannot bypass that check with its own on-demand pulls. Missing/ungraded results,
preparation rejection or image failure remain infrastructure failures and cannot
be converted to task failures or passing release evidence. The release queue
requires all 64 follow-up results as well as the primary 64 before certification.

Report paired gains and losses, passing-control retention, model calls, and
actual task outcomes. One further attempt is not a three-round retention test;
a gain here does not alone separate memory's causal effect from another attempt.
The primary multi-round study and matched diagnostics provide distinct evidence.
