# Restart from attempt 2: controlled learning improvements

Author authorized 2026-09-23. Preserve the ongoing gated campaign, including
Gemma attempt 5. The new queue waits for that campaign to finish successfully,
then executes all Gemma branches before Qwen branches. Each model/branch starts
independently from its own saved attempt-2 state, then performs attempts 3–5.
The previously measured gated rounds are the reference condition.

Branches: actionable feedback only (32-token learning output); reasoning only
(512-token learning output); combined feedback and reasoning (512 tokens).
Actionable feedback computes the current procedure's predictions against only
the original three training examples. Reasoning prompts request derivation and
checking before an explicit FINAL rule. Raw outputs are retained. Exactly one
FINAL line is required; missing/ambiguous output is rejected by the existing
gate, retaining the prior rule. No evaluation gold is given to either learning
or the acceptance gate. Evaluation decoding and task prompts remain unchanged.

This is an exploratory follow-up after observing the plateau. Larger learning
budgets and prompts are explicit treatment differences, not improvements in the
unchanged original protocol. All 480 tasks recur, so this is repeated-task
learning rather than new held-out generalization. Each candidate must pass the
original examples before publication. Diagnostics distinguish rule correctness
from execution errors. Stop on a round's score declining relative to its predecessor.

New budget: 3 branches × 3 rounds × 2 models × (24 learning + 960 evaluation)
= 17,712 requests. Runs and raw observations use new task-learning-* paths.

## Scope correction

The author cancelled Qwen retries and requested the new changes on Gemma only.
The scheduler now requires the completed Gemma attempt-5 baseline, without
waiting for Qwen. All three Gemma branches restart at attempt 3 from the saved
attempt-2 state. Budget is 8,856 requests. Partial Qwen artifacts are preserved.

## Feedback-only scope

The author cancelled reasoning-only and combined branches. Complete actionable-feedback attempts 3–5 only, then stop. The existing running scheduler is externally stopped after the feedback attempt-5 diagnostics are written; future invocations enumerate only feedback.
