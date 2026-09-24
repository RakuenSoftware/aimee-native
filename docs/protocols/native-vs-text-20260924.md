# Matched native-memory versus text-delivery comparison

Status: Gemma instrumentation smoke passed; full campaign prepared for launch.
Earliest GPU start authorized by the user: 2026-09-24 12:00 Europe/Amsterdam
(10:00 UTC). Do not interrupt another workload. Gemma first, then Qwen.

## Question and paired conditions

Does native consumption differ from putting the identical selected records into
the prompt, at fixed checkpoint, question, record revision, decoding and scoring?
Selection is held constant. This study does not measure retrieval quality.

1. No memory: original question and existing model-specific instruction.
2. Text delivery: identical selected record content supplied as factual context.
3. Native delivery: identical selected records through the existing native path.

Keep the question and non-memory instruction identical across conditions. Record
full token IDs and record/revision hashes; text delivery necessarily adds tokens.
Freeze the serialization and delimiters before scoring. Do not include expected
answers or evaluation feedback except facts genuinely present in selected records.
Run the same runtime/weight format for all conditions within each model.

## Workloads and ordering

Use the existing frozen 10,000-question general-knowledge set and the 625
synthetic personal facts, plus the frozen 480-task procedural evaluation with
one fixed accepted publication. Do not continue learning during this comparison.
Keep prior raw archives immutable and write fresh per-request observations.

Begin with an instrumentation smoke test, not counted in the final scores.
Counterbalance delivery-condition order using a recorded seed. Report each
workload separately. Gemma is the first model; Qwen follows sequentially.

## Measurements

Record correctness, complete answer, generated tokens, conversation input tokens,
selected canonical bytes, model-specific native bytes, preparation time, transfer
where separately observable, time to first generated token, generation duration,
total request duration, and peak device allocation per GPU. Synchronize device
work at measurement boundaries. Do not label total duration as first-token time.
Do not equate zero additional prompt tokens with zero compute or serving cost.

Run a separate timed subset with repeated measurements for cold derived-state
preparation, warm reuse and record corrections. Exclude checkpoint startup from
steady-state serving measurements and report it separately. Clear request state
between independent accuracy cases. Distinguish disk/OS warmth from derived-state
cache warmth. Include an ordinary text-prefix-cache condition if the runtime
supports valid reuse; otherwise mark that comparison unavailable rather than
claiming it was tested. Log actual cache hits, not merely configuration switches.

Report paired accuracy gains/losses, latency distributions and total costs at
matched quality. Cluster procedural uncertainty by workflow. Record failures,
timeouts and missing telemetry, without silently removing them from denominators.
Do not assign a monetary token price to local native computation. Report resource
measurements first; any financial model must state its price assumptions.

## Launch gate

Before starting on the two 7900 XTXs: confirm local time is at or after the
release, check that both devices are free, freeze driver/source/fixture hashes,
and verify that the text condition actually disables native injection and the
native condition inserts no memory text into the conversation. Validate scoring
and telemetry on the smoke cases before the full run. A busy device delays the
run; do not kill or preempt the current user's workload.

## Frozen launch details

Primary workload order is procedures (480), personal (625), then general (10,000),
for 33,315 primary responses per model. Gemma finishes before Qwen starts. Source
paths and the fixed 2026092412 condition-order seed are in campaign.sh/drivers.
No experimental result is used to choose a subsequent condition or fixture.

The Gemma worker performs one published-record selection and gives the identical
response to text serialization or native ingestion. The selected source revision
must match the frozen case. The no-memory control does not receive the selected
knowledge, although its harness telemetry includes the common selection probe.
Report model-request time separately to avoid attributing that probe to inference.
Native preparation is timed separately with synchronized device boundaries.

The reuse diagnostic uses the first 32 frozen cases per workload, one warmup
and five repeats per condition. Gemma includes a verified reusable text prefix
whose boundary is the token prefix shared with an unrelated sentinel question;
it does not cache the task answer or question suffix. Its prefix cache resides
on device; native reusable state resides in host RAM. Include these placements
in the cost interpretation. Main accuracy runs disable derived-state reuse.
Cold means fresh derived state, not a flushed filesystem cache.

Qwen uses the existing non-streaming Rust server. Total request duration and
encoding-event times are available; time to first token and allocator peaks are
unavailable. Its API resets the conversation cache per request, so a text-prefix
cache comparison is not supported in this run. Do not present warm Qwen native
versus uncached text as a comparison against all text-serving optimizations.

These runs measure the archived research integrations. They are not a benchmark
of a newer production-local precomputed representation. Corrections/update-cost
experiments are a separately scoped follow-up, not implied by these static-image
comparisons. No results from the instrumentation smoke count toward reported
accuracy. Each run refuses an existing output directory; previous artifacts remain
unchanged. Invalid output halts the campaign and preserves partial rows.
