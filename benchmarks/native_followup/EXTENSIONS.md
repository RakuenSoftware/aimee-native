# Frozen extension protocol, 2026-09-23

Authorized after the completed five-round study. Existing results remain unchanged.
Gemma 4 12B is the evaluation model; Qwen 3.8 27B contributes candidate knowledge.
All inference uses existing frozen checkpoints and 32-token output budgets.

Order and budgets:
1. Matched transfer: existing first-round candidate outputs frozen, own accepted
   memory versus own plus validated Qwen candidates, each with disabled control.
   24 workflows × 20 inputs × 2 conditions × 2 publications = 1,920 requests.
2. Structured transformations: seed 2026092401, 24 private workflows selecting
   and ordering two of four fields, joining with one of three separators, and
   changing case conditional on a flag. Six training examples and four withheld
   development-validation examples per workflow; 20 sealed evaluation records.
   Full-string, case-sensitive scoring. Conservative declared rule grammar;
   unsupported output rejected, never repaired. Original candidate text retained.
   Same frozen candidates compared own/shared: 1,920 evaluation + 48 learning.
3. Six one-round component arms from identical saved round-two plateau:
   validation-only baseline, prior-history addition, additional observations,
   worked-example transfer, Qwen contribution, and all four combined. Each has
   960 evaluation requests and 24 Gemma learning requests; only contributor and
   combined also have 24 Qwen learning requests. Total 5,952. Development checks
   use available training evidence. No evaluation answers enter learning. These
   one-shot component effects do not establish all higher-order interactions.
4. Three predetermined affine replications, seeds 2026092402–2026092404. Sample
   new function sets independently, use distinct workflow IDs, fresh initial
   memory, and sealed evaluation inputs. Five rounds each, fixed observation
   schedule and existing combined protocol, 5,040 responses per seed = 15,120.

Total planned extension requests: 24,960. GPU jobs execute sequentially.
No numerical performance threshold determines whether a replication is included.
Unlike exploratory earlier stopping rules, these replications complete all five
rounds even if accuracy falls. Stop on runtime or integrity failure and preserve
partial outputs; repair orchestration without changing observed model responses.

Repeated numeric inputs across independently sampled functions are allowed; the
new function sets and identities define replications. Original training and
sealed evaluation input ranges stay disjoint. Structured record values are drawn
independently. Scoring normalizes whitespace only for structured outputs; letter
case and separators are required to match exactly. Malformed, unknown, empty or
truncated answers are incorrect and remain in the denominator.

Report workflow-level mean effects and paired differences, gains and losses, and
per-seed trajectories, alongside aggregate task accuracy. Confidence intervals
must resample workflows, not individual correlated task answers. Three seeds are
limited evidence of stability, not a population-wide guarantee. The deterministic
short-output setting constrains inference. Contributor attribution is retained;
no claim of changed reasoning weights or independent discovery by Gemma.

This is a private research protocol. Source, fixture grammar, validation and
runtime internals do not belong in the public article distribution.
