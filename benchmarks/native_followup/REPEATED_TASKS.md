# Repeated task learning: attempts 2–5

Authorized 2026-09-23, before additional results. Starts after the original study
and its verification finish. Retains attempt 1 and no-memory results unchanged.

Each model learns again from its previous stored procedure and the 20 previous
responses per workflow, with binary executor success/failure feedback. Original
three training examples remain available. Expected evaluation answers and gold
rules are never supplied to the learning prompt. Model outputs are persisted
through the same real Aimee ingestion/publication pipeline without rule repair.
All workflows run each round, including successful ones, so regressions remain
visible. Each subsequent round builds on its own model's preceding round.

Evaluate the identical 480 task inputs with unchanged task prompts, both disabled
and native, in a fresh process per model/round. Prior-attempt feedback appears in
the learning request only; task inference receives learned procedures natively.
Expected answers are used by the scorer only. Native traces and frozen-parameter
checks retain the original validation protocol. Report per-round success, gains,
regressions and persistence; do not report best-of-five as fifth-round accuracy.

This tests improvement on repeated tasks. After attempt 1 these inputs have
contributed binary feedback and must not be described as unseen/held-out inputs.
It does not isolate feedback from repeated procedure induction or establish
weight learning. An unchanged-memory retry control would be needed to isolate
that causal contribution from rerun variability.

Budget: four additional rounds × two models × (24 learning requests + 960 paired
evaluation requests) = 7,872 requests. Stop on pipeline failure, preserve all
artifacts, and repair orchestration without editing recorded model responses.
