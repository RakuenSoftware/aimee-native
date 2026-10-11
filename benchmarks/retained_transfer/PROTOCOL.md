# Retained and transferable learning through native memory

Protocol v1, 11 October 2026. This linked study supersedes the broad expansion
roadmap as the next primary experiment. No linked-study inference has occurred.

## Object and claims

The transferred object is newly acquired knowledge as an explicit record, never
a donor tensor. Frozen receivers prepare their own execution state. The test is
one complete experience → acquisition → admission → session termination →
retention/transfer cycle, without additional training in any executed component.
C1 is fidelity and shorter request text; C2 is retained held-out learning; C3/C4
are cross-session and cross-model use. C5 is cost versus **uncached context** on
the same records. Prefix caches are mechanism precedents, not benchmark arms.
Existing lifecycle, SQuAD and counterfactual evidence is supporting evidence.

## Frozen construction

Three invented language fragments, 20 constructions per language, 60 families.
Each family has eight training pairs, twenty held-out phrases and eight separate
calibration phrases. Noun, verb and adjective vocabularies are disjoint across
these three splits within each family. Every arm has the identical full lexicon.
The generated languages use family-specific word order and particles/affixes.
They test controlled construction induction, not acquisition of an unrestricted
natural grammar. No affine fixture is reused.

The learner writes a JSON record with a single `output_template` field. Its
three placeholders represent target-language noun, verb and adjective lexicon
entries. This transparent hypothesis class makes true-rule diagnostics
reproducible. It restricts the induction task and must be stated in the paper.
Receivers themselves apply the record by model inference: the evaluator never
computes an answer for them. Record text is never rewritten for a receiver.

Generate separate learner, calibration and evaluator exports; freeze their
hashes, protocol, executed source and checkpoint identities before inference.
The learner request builder reads only the learner export. The API exposes no
file or tool access. Log every complete request and independently audit its
inputs after acquisition. This proves what was sent, not host-level isolation.

## Calibration and acquisition

Before acquisition, run None on the eight calibration phrases per family per
receiver. A family is excluded from the primary cohort if **any** receiver gets
at least two of eight correct. Freeze the exclusion ledger before acquisition;
never use held-out performance to choose families and never replace excluded
families. Report all sixty as a secondary analysis and the actual eligible n.

Learner: pinned Gemma4-12B checkpoint/runtime, all weights and active state on
the RTX5080. Eight examples per family, no held-out inputs or oracle rule.
Maximum three proposals per family, greedy decoding, 512 proposal output tokens.
For each proposal, a separate inference call applies it to the same eight
training inputs, requesting eight answers, maximum 512 output tokens. Admission
requires valid schema and at least **7/8 exact outputs**. Invalid JSON or a
failed call is logged as an unsuccessful attempt; there is no silent repair.
Retry feedback states the match count, with the original examples, never hidden
answers. Stop at the first admission. Preserve all first proposals for the
Unvalidated arm. Missing admissions remain results, not oracle substitutions.

Write admitted record content, source session, validation counts, version and
SHA256 through the canonical store's authorized admission interface. An export
alone is not evidence of canonical admission. Retain the store receipt and
read-back hash. Terminate and wait for the learner process before evaluation;
record process group, PID, start/end and weights/source identities.

## Receiver arms and separation

Learner as fresh receiver; Gemma4-E2B; Qwen3-0.6B; Qwen3.5-0.8B hybrid.
Pin exact repository IDs, revisions, precision, runtime and architecture from
actual artifacts; do not infer checkpoint identity from a display label.
Seven arms: None, Native, Text, Replay, Oracle-native, Unvalidated-native,
Shuffled-native. Missing records yield None-equivalent requests and remain in
the denominator. Oracle is evaluator-only and is never used for acquisition.
Unvalidated uses the first candidate; its comparison measures validation plus
retry, not the isolated effect of a binary validator.

Within each language, use a deterministic hash-ordered cyclic derangement of
admitted records for Shuffled. With fewer than two admissions there is no valid
occupied shuffled comparison: report that endpoint unavailable, not a null-bank
content control. Report matching-versus-shuffled on the occupied subset too.

Three fresh process repetitions per model; each receiver process is distinct
from the producer and every other receiver. Randomize family and arm order from
fixed seeds. Reset request state between inputs. Twenty inputs per family/arm.
No donor history, activations or weight deltas cross sessions. The only adaptive
shared object is the canonical record; static task definitions/lexicon are
identical experiment inputs. At most one family's active bank is resident;
prepare once and reuse for its twenty inputs, then retire it. Passive artifacts
may live on NAS; active inference never offloads to CPU.

Native and Text serialize identical record content at identical positions.
Prefix plus suffix token identity must be audited before scoring. A full-prefix
profile may include fixed instructions/lexicon in preparation; count and report
these separately. It does not prove mid-generation hot-plugging or independent
multi-record composition. Hybrid state is ordered prefix continuation, not
composable attention banks. No trained projection, fuser, retrieval or adapter.

## Cost and accumulation

Caching disabled in Text and Native request engines; native explicitly reuses
prepared state. Batch one, same hardware/output cap, greedy decoding, warm-ups
excluded. Request TTFT includes selection/attachment; end latency includes last
output. Log engine prefill, task prompt tokens, current/peak GPU bytes, resident
bank bytes, preparation wall time and prefill, runtime version, timestamps and
GPU residency. Power telemetry is descriptive unless its temporal resolution
supports per-request energy integration. Do not call fewer prompt tokens fewer
GPU bytes. Report cost including preparation and the empirical break-even (or
no break-even) for every receiver.

Secondary ten-turn episodes use ten distinct admitted families. Text retains
record blocks; Native binds only the current record. Preserve identical public
transcript policy and log indirect output influence. If fewer than ten eligible
admissions exist, report the shorter episode and its limitation. Plot tokens
carried, quality, prefill and latency by turn. No guaranteed positive C5 result.

## Endpoints and analysis

The family, not a request or process repeat, is the unit. Average dependent
process repetitions before inference; retain per-process results. Primary:
learner Native−None and Native−Shuffled >0; each of three smaller receivers
Native−None >0; all four Native−Text >−0.03 non-inferiority. This is nine
hypotheses, with Holm correction over the declared accuracy endpoints.
Use paired Wilcoxon signed ranks for superiority (Pratt zeros, all-zero p=1),
10,000 fixed-seed family bootstrap draws stratified by language for intervals.
For non-inferiority, test the mean paired difference at the frozen margin using
a family resampling null, and report its lower confidence bound; do not treat a
rank test of zero as a non-inferiority test. Report exact agreement plainly if
intervals degenerate. Bootstrap uncertainty is conditional on three generated
languages, not a population of all languages.

Replay is characterization, not a learning-success condition. Oracle recovery
is undefined when Oracle−None ≤0. Report acquisition, bad admission, execution
and native-realization failures per family. No scored rerun to select a better
outcome. Mechanical failures are preserved, excluded and corrected additively.

## Required artifacts and gates

`acquisition_log.jsonl`, canonical `records.jsonl`, `responses.jsonl`,
`summary_tables.csv`, `results_ledger.md`, `manifest.json`; complete API payloads,
validation outcomes, store receipts, process receipts, token IDs and weight/
runtime hashes. No positive paper statement until these reconcile.

Gates: generator split tests; executed-path no-training audit; exact IDs/physical
GPU fit; token/state fidelity on non-scored mechanical fixtures; frozen commit;
calibration and frozen exclusions; acquisition and termination; seven-arm
fresh-session scoring; statistical/residency audit; paper update.
