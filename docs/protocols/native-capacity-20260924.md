# Active native-memory capacity and interference

Frozen before outcomes, 24 September 2026. Requested follow-up to review feedback.
This is the first additional pressure study; corpus-scale selection and live
revision interference need separate fixtures and are not implied by this study.

## Question

How does accurate use of a target fact change when more independently retained
records are simultaneously supplied to attention? Keep checkpoint, target query,
scoring, paired record order and decoding fixed. This measures consumption under
interference, not a learned-parameter equivalent or semantic-retrieval accuracy.

## Design

Gemma first, using the existing BF16 dual-7900-XTX runtime. Sample 625 targets from
the frozen 10,000-question general cohort and use all 625 original personal facts
from the renewed research publication. Seed 2026092417 fixes target selection,
distractors, target positions and condition order before any model outputs.
Each target receives one no-memory answer and paired native/text answers at
working-set sizes 1, 4, 16, 32 and 64: 11 answers per target, 13,750 primary answers.
The target fact is always included. Distractors are other distinct records;
prefer matching source/scoring categories and randomize ties. Distractor sets
are nested, with record order shuffled independently at each size and held
identical across delivery conditions. Questions remain the original frozen ones.

Every record is independently read through the existing authorized publication
reader. Union the selected records without modifying their content or revisions.
The complete ordered union reaches either native ingestion or the text prompt.
This controlled union bypasses unrestricted selection deliberately: record
selection errors cannot be mistaken for native-consumption errors. Selection
latency includes all serial record reads and is reported separately from inference.
The no-memory request includes only a one-record selection probe for validation;
its model receives no fact. Do not treat full harness latency as equal selection
work across working-set sizes or conditions.

A frozen copy of the earlier instrumentation worker uses an explicit 8,192-token
native encoding guard and disables reuse. There is no truncation: exceeding the
guard, OOM or another runtime error stops the campaign and preserves the row.
Report that operational boundary and partial denominator; never omit failures
or retry a smaller set under the same run ID. Raising this guard is configuration
of the research consumer, not a claimed architecture limit. No model weights or
memory-integration algorithms are changed.

## Measurements and interpretation

Retain all answers, record refs/hashes, prompt token IDs, native encoding tokens,
actual bank bytes, GPU allocator peaks, preparation, TTFT and total times. Verify
identical native/no-memory conversations, same ordered facts in native/text, and
unchanged parameter counters. Score using existing frozen rules. Report every
size and source separately, with gains/losses relative to size one and paired
text controls. Use the target as the paired unit; do not count repeated sizes as
independent observations. Report target-position effects descriptively.

Three targets per source exercise every size in an instrumentation gate, separate
from the scored cohort. Gate passage depends on instrumentation and faithful
record delivery, not answer accuracy. Retain smoke outcomes separately. Fresh
processes isolate each source and scored run. General and personal archives,
canonical records and the currently running baseline remain unchanged.

## Execution

Wait for the current native-versus-text campaign to finish successfully. Run
personal smoke, general smoke, personal main and general main, serially. Pin
source commits, driver hashes, source case hashes and publication manifests.
This batch tests Gemma; Qwen expansion and corpus-scale selection require their
own frozen follow-up protocols. No results are assumed before completion.
