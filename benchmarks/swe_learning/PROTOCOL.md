# Repeated SWE-bench native-memory learning, 26 September 2026

User authorization: subset study using the two 7900 XTXs, at least ten hours
available; 30 cases rejected as too small. Freeze 150 tasks drawn from all 12
repositories in SWE-bench Full (2,294 cases), using the deterministic selection
in select.py. Publish task IDs and content hash before inference. No outcome or
patch-size filtering. This is a stratified engineering subset, not the full score.

One no-memory control plus five learning attempts per task: 900 target attempts.
Learning attempt 1 starts empty. Attempts 2–5 consume the task's cumulative
experience from the preceding learning attempt as native attention memory.
Control experience is never imported. Every attempt starts a fresh task container
at base_commit. Fixed Gemma Q8 checkpoint, 8,192 context positions, temperature 0,
seed 20260926, 40 steps, 240-second agent wall budget, 512 tokens per response,
four concurrent agents. Whole earliest action/observation pairs may be removed to
fit the fixed context budget, identically in every condition; the initial issue
is retained. This is a custom text-action model wrapper around mini-swe-agent
2.4.6, graded with the official SWE-bench 4.1.0 harness, not a leaderboard run.

Process groups of four tasks through every arm before advancing. This bounds
container/image disk use. Within a group each arm completes before the next;
there is no cross-task transfer in this first study. Five learning rounds are
five attempts total, with four opportunities to reuse experience. Every learning
attempt additionally produces a retained experience record, including round 5.

Only public issue text, the learner's own command observations and patch, and the
overall grader resolved boolean enter experience. Gold patches, hidden test code,
hidden test identifiers and per-test hidden output are withheld from the learner.
They remain in the isolated grader. The same model synthesizes a <=320-token
cumulative lesson, retaining earlier useful steps and distinguishing failed
outcomes. The existing private CPU compiler prepares all selected lesson content;
receivers load the result through the exact compiled release's native path.
No learned memory text is appended to task conversations. The encoding pass is
separate, recorded and excluded from serving latency claims.

Archive predictions, trajectories, selected publication identities, experience
text/hash/lineage, grader reports, per-call token counts and worker native metrics.
Empty predictions count as task failures. Infrastructure failures are separately
reported, never silently relabeled as model failures or successes. Resume only
from a completed per-attempt result. Do not shrink denominators or drop failing
cases. Preserve regressions as well as gains, and report paired results on the
same tasks completed across rounds with the total scheduled denominator visible.

This tests repeated-task improvement from retained experience and binary feedback.
It does not establish unseen-task generalization, cross-model transfer, trained
weight changes or changes in the model's underlying reasoning ability. Scores may
plateau or regress; running a learning loop does not guarantee improved results.

Execution: CT113 isolates public task containers and official grading. CT101
serves the real model on both 7900 XTXs, with a restricted SSH compiler/control
bridge and loopback-forwarded inference. Existing Aimee account credentials and
production memory are not mounted in task containers. Experiments, preparation
and all new code belong to aimee-qwen, not Aimee core.

The 8,192-token engine uses the release-5 base image with an explicitly archived
extended binary kernel bank. Both head geometries passed dense-reference checks
at 32 and 8,000 text positions on both GPUs. The signed customer release remains
the separately certified 2,048-token profile. Initial unsupported-profile and
preflight infrastructure failures remain recorded and are not scored tasks.

Image setup correction before scored continuation: some official images include
a setup commit. The runner explicitly resets tracked files to dataset base_commit
and verifies HEAD, while preserving installed environment/build files. The first
checkout failure and incomplete concurrent attempts were archived as infrastructure
preflight evidence after draining GPU requests; no learned records existed yet.

Images already present are reused and their immutable image IDs are recorded in
each result. Missing images are fetched four at a time before a task group starts,
outside the per-attempt budget. Official harness documentation:
https://www.swebench.com/SWE-bench/guides/evaluation/ and
https://mini-swe-agent.com/latest/reference/run/swebench/.

## 27 September repair boundary

The original campaign stopped after 180 records; see
`docs/validation/swe-diagnosis-20260927.md`. Do not resume into its result tree.
The 150-task selection remains unchanged. A separate eight-task calibration uses
the first eight frozen tasks, 600 seconds, 40 steps, one control and three learning
passes. It uses local-window-corrected attention, FP32 private preparation with a
new encoding identity, and corrected format-recovery history. It is exploratory
repair/budget validation, not a completed demonstration of learning or a new
independent effect estimate. The larger campaign is held until this gate is read.
