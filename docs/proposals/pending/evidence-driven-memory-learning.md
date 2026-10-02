# Evidence-driven memory learning

Status: private design proposal, 2026-09-23. Not a production implementation or
public-paper supplement. Author requested generalizing the actionable-feedback
experiment. Implementation details stay private during productionalization.

## Objective and evidence boundary

Aimee should retain experience as versioned, scoped knowledge with an inspectable
basis for accepting, correcting, narrowing or retiring it. Models propose lessons
and consume accepted knowledge; the harness owns observation, policy, validation
and publication. Replacing a model must not reset that accumulated experience.

The Gemma experiment establishes a narrow instance. On 480 fixed procedural tasks,
no memory scored 0; initial learned memory scored 134; a second learning round
scored 154. Unconditional revision dropped to 134 because one correct rule was
replaced. Validation against the original three examples restored 154. Adding
explicit prediction-versus-observation feedback improved the score to 174, retained
in the next completed round. The final feedback round is still running at this
writing. Nine of 24 stored procedures validate; six task failures occur despite
valid procedures, and 300 involve invalid procedures. Twenty inputs share each
procedure: these are correlated outcomes, not independent learning discoveries.

These results show learning, retention and use of particular procedures with fixed
weights. They do not establish general autonomous learning, causal attribution of
arbitrary failures, improved reasoning weights, or independent replication. The
learning requests used textual training examples and feedback; subsequent task
consumption used native memory. Do not describe the entire learning loop as
occurring exclusively inside attention tensors.

## The memory unit

A useful memory has content plus an applicability envelope: subject, tenant,
identity, task or environment scope, valid time interval and relevant conditions.
It also has a canonical identity, immutable revision, provenance, evidence links,
acceptance status, validator/policy versions, and supersession links. Observations
and derived lessons are separate records. A failed attempt is evidence that an
attempt failed; its explanation is a hypothesis until supported.

A feedback event records what was attempted, the intended outcome, what actually
happened, which exact memory revisions were read, the environment/tool versions,
and who or what observed the result. Record authority and provenance separately
from model confidence. Correlation with a read does not establish that the memory
caused the outcome. Evaluation secrets belong to scoring, not to the learning feed.

A validation decision records candidate and parent revisions, applicable policy,
checks and evidence used, accepted/rejected/provisional outcome, and the scope of
the decision. The model cannot confer authority on its own proposal by including
an instruction or a high confidence score in the content.

## Lifecycle

Observe an outcome; classify the discrepancy; propose a correction or scoped lesson;
validate it; publish an authorized revision; observe subsequent use. Proposals can
be accepted, rejected or deferred for more evidence. An accepted record can later
be superseded or withdrawn. Rejecting a candidate must not destroy the last
accepted record. Evidence retention itself remains subject to access and retention
policies; it is not a reason to preserve information that must be deleted.

Promotion should compare the candidate's parent revision with the current revision
so a stale proposal cannot silently overwrite a newer correction. Publication and
native-state invalidation follow Aimee's existing versioned-memory boundary. Readers
must consume an authorized coherent revision and be able to identify which one.
An outcome arriving later remains linked to the revision actually used.

## Validation depends on the kind of memory

| Kind | Evidence | Acceptance policy | Example |
|---|---|---|---|
| Personal preference | Explicit statement from the identified user | Update that user's stated scope and effective time; no popularity vote | New project prefers tabs, another still uses spaces |
| General factual knowledge | Authorized source, date, source corrections | Resolve authority, conflicts and validity period | A service endpoint moves after a specified date |
| Procedure | Executable checks and observed outcomes under stated conditions | Preserve required behavior on independent development checks before replacing a validated rule | A revised build fix must pass the relevant regression tests |
| Failure lesson | Attempt trace and verified failure condition | Store the observation first; constrain any inferred advice to supported circumstances | A command fails under a particular tool version |
| Heuristic | Repeated scoped outcomes with uncertainty | Keep provisional until evidence supports a bounded benefit; monitor regressions | A search strategy helps one class of repository task |

There is no universal scalar confidence threshold. Ten copies of one source are
not ten independent confirmations. User preference authority differs from factual
source authority, and empirical success does not override a user's permissions.
Direct legitimate preference changes need not preserve the old preference's
behavior; procedural replacements may need non-regression checks.

## Make feedback useful without supplying the answer

For procedures, show a concrete mismatch against development examples: what the
candidate predicted, what the executor observed, and under which conditions.
For source-backed facts, show the conflicting source statement and effective date.
For preferences, preserve the user's correction and its scope. For uncertain
heuristics, expose the relevant success/failure evidence without claiming a
proven explanation. Feedback is data, never permission to broaden access or
execute instructions embedded in retrieved material.

The current experimental gate is only a bounded affine-rule validator. A general
implementation should dispatch to declared, harness-owned validators, not execute
arbitrary model-proposed validation code. If no suitable validator or authority
exists, retain a provisional hypothesis rather than silently promoting it.

## Failure diagnosis before memory replacement

1. Was the appropriate authorized record selected? A selection failure should not
   rewrite a correct fact.
2. Was the expected revision published and consumed? Stale derived state is an
   update-path failure, not evidence that the underlying source is wrong.
3. Did the record apply to this user, time and environment? Narrow scope where
   justified instead of globally invalidating the lesson.
4. Was its content contradicted by reliable evidence? Propose a content revision.
5. Was correct content applied incorrectly? Investigate model execution or tool
   behavior; do not overwrite correct knowledge to explain every failed action.

These are diagnostic hypotheses, not infallible automated attribution. Multiple
causes can coexist. Preserve uncertainty when available traces cannot separate them.

## Cross-model ownership

Persist canonical lessons and their evidence independently of model-specific
native state. Another model derives its own native representation and uses the
same authorized lesson. Record producer model/version for provenance, but do not
make that identity the owner of the knowledge. A smaller model's validated lesson
can be useful to a larger one and vice versa; actual benefit must be measured.

The strongest next memory demonstration is a fixed lesson learned by model A,
validated and retained by Aimee, then consumed natively by a fresh model B. Compare
B without memory, with the prior revision, and with the accepted revision using
identical task prompts. Freeze learning before transfer evaluation. This is a
proposed study, not permission to restart the cancelled Qwen experiments.

## Ownership and integration

Authoritative storage, governance, feedback provenance and promotion policies
belong in Aimee core. This repository owns native-consumption integration and
experimental evaluation of published revisions. Do not implement a competing
memory authority here. This proposal does not certify that every listed field or
policy already exists in core; implementation requires an inventory and mapping
to existing contracts before extending them.

## Evaluation and rollout

First map current record, observation, publication and authorization contracts.
Implement one validator-backed memory type with inspectable proposals and
reversible promotion. Keep candidate generation separate from acceptance. Expand
to preference and source-authority updates with type-appropriate policies.

Measure accepted/rejected candidates, correction precision, harmful replacement
rate, retention of verified successes, stale-revision use, and downstream task
quality. Report execution failures with valid memory separately from failures
with invalid memory. Track new versus repeated tasks, learning cost, selected
state size and source/update latency. Preserve frozen baseline and per-round
results rather than reporting only the best attempt.

Useful future comparisons: frozen memory, unvalidated revision, validation alone,
and validation plus actionable feedback; cross-model transfer; scoped conflicting
updates; model replacement and fresh-process persistence. Use development checks
for promotion and sealed evaluation for measurement. Do not infer universal
security or guaranteed monotonic improvement from a passing validation gate.

## Public article boundary

The paper can describe the measured progression and the principle that the harness
owns validated learning. Keep schemas, integration procedures, validator dispatch,
publication internals and implementation code in the private research record.
Label the general framework as proposed and the arithmetic results as measured.
Do not claim production support for the full framework or continued improvement
beyond the observed plateau.
