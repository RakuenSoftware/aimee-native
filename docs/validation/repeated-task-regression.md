# Repeated-task regression analysis, 2026-09-23

User requested stopping if Gemma attempt 3 finished below attempt 2.
Attempt 3 completed at 134/480, versus 154/480 in attempt 2 and 134/480
in attempt 1. The retry service was stopped during attempt 4 procedure learning;
its partial files remain on the lab host and are not scored as a completed run.
Attempts 4–5 and Qwen retries are paused pending analysis.

## Exact source of the decline

Workflow Cedar020 has the frozen expected rule 5x+15. Model-generated rules:

- Attempt 1: multiply by 5, add 5; 0/20 correct.
- Attempt 2: multiply by 5, add 15; 20/20 correct.
- Attempt 3: multiply by 5, add 10; 0/20 correct.

Between attempts 2 and 3 there are zero newly correct cases and 20 newly
incorrect cases. Every other task retains its correctness status. The attempt-3
learning prompt supplied the correct preceding rule and twenty successful
outcomes, and explicitly instructed retaining successful rules. The model
nevertheless emitted an incorrect replacement. The fixture published it without
checking that it preserved demonstrated behavior. This is a directly observed
procedure-revision regression, not evidence of memory losing the previous fact.
Other unsuccessful rules also changed but produced no additional correct cases.

## Interpretation and next controlled experiment

The initial gain is real but concentrated in one of 24 workflows: its twenty
inputs are correlated evidence, not twenty independent discoveries. All seven
originally correct procedures remained unchanged; the newly corrected eighth
procedure was subsequently lost. Native consumption cannot ensure that the
content supplied by a learner is correct.

The experimental retry publisher lacks a behavioral acceptance gate. A proposed
follow-up should preserve the last validated procedure, check replacement
candidates against the three original training examples (not evaluation gold),
and promote only candidates meeting a predeclared criterion. Rejected candidates
and reasons should remain in memory. Compare that arm with the recorded
unconditional-replacement arm; do not revise these historical outcomes. No
follow-up is started by this analysis. No inference is made about the production
harness having the same deficiency.

Raw responses and fixture specification are preserved in
`artifacts/task-repeat-regression-2026-09-23/observations.tar.gz` with a SHA-256
manifest. Independent result verification reported no trace/scoring violations.
The pipeline verifier's `regressed` field compares native against disabled within
a round; cross-round regression above was computed by matching task IDs.
