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


## Record-delivery validity gate (before campaign start)

The driver sends the full ordered expected canonical identities and revisions to
the worker. The worker verifies the union against that list before inference,
sets the native recall limit to the complete set size, and requires the native
bank-construction event to contain every fact ID in that order. It reconstructs
the complete encoding token sequence and checks both the recorded sequence and
the actual model encoder call against it. Bank shapes are recorded before cleanup;
at least one native bank must retain the full sequence. Local-window layer bank
lengths are recorded rather than assumed equal to full-attention bank lengths.
Each installed bank must be observed at the attention cache boundary, with the
same key/value tensor objects and nonzero added native positions. The observer
does not modify tensors or scores. These checks apply before a run is considered
valid, including instrumentation smoke and every scored request.

Seven CPU regression checks include the historical failure modes: returning one
record, returning only four, encoding only one, truncating encoder input, wrong
revision and reordered bank. Failed delivery marks the run INVALID and stops it;
it is a harness/runtime failure, not evidence against memory composition or
native-memory accuracy. Raw rows and errors remain available. Actual GPU-path
validation remains gated on the queued smoke run; CPU checks are not GPU results.
