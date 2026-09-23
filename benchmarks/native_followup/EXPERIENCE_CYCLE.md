# Fresh five-round Gemma experience study

Authorized 2026-09-23: implement all four proposed improvements and run five fresh
Gemma rounds. Start only after the final actionable-feedback run finishes. Do
not resume the cancelled Qwen evaluation or reasoning-budget branches.

All four changes are bundled:

1. Retain each model's previous candidates and the evidence for failure/success.
   Compact observations pass through actual Aimee extraction/store/export; exact
   candidate provenance remains in the private ledger and is included in learning.
2. For unresolved procedures, acquire one additional executor observation per
   round from a predeclared pool (2,3,5,6); successful procedures keep original
   observations. This is targeted acquisition, not optimized information gain.
3. Reuse a validated worked example from a different workflow in subsequent
   learning. The lesson includes examples and the accepted procedure; it is not
   a hardcoded answer for the target workflow or a claimed learned universal method.
4. Qwen contributes candidates based on the same learning evidence. Choose a valid
   Gemma candidate first, otherwise a valid Qwen candidate, otherwise the retained
   rule. Archive producer and decision. Gemma consumes the chosen rule natively.

Fresh campaign: 24 new Birch workflow identifiers, same underlying affine task
functions as the previous study, and a new frozen sample of 20 inputs per workflow
from 200..399. No prior accepted workflow rules initialize round 1. This is not a
new distribution of task functions and is not five independent replications.
Each round has 24 Gemma learning requests, 24 Qwen contributor requests and 960
Gemma paired evaluation requests: 5,040 total. Learning uses the existing 32-token
budget. No expanded reasoning experiment is included.

Evaluation prompts and 480 cases stay fixed across rounds. Evaluation answers
and pass/fail feedback are not fed to learning; the executor provides separate
training examples only. Candidate checks use all currently observed training
examples. Qwen's valid candidate can directly become a shared memory, making
producer attribution essential when discussing Gemma performance. No proposal
is silently repaired into the oracle's rule. Derived selection files are labeled
as such and never counted as model responses.

Report native vs disabled performance, valid rules, execution failures with valid
rules, candidate acceptance/rejection, and producer attribution. Stop on a decline
in completed round success. The bundled intervention cannot isolate the causal
contribution of each of its four components. Repeated evaluation is still not
independent replication. Raw candidates, decisions and outputs are immutable.

Learning-stage experience is supplied in text; accepted task procedures are
published through Aimee and consumed natively at evaluation. Do not claim native
consumption of every intermediate learning artifact. This is an experimental
integration, not implementation of the entire general memory-learning proposal.
