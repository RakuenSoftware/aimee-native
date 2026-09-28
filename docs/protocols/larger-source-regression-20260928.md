# Larger-model source-procedure transfer and regression validation

Frozen before these model-specific coding outcomes are observed. This is a
selected regression/transfer check, not a random sample or population learning
effect estimate. Prior task-selection and source outcomes remain visible in
`larger-release-followup-20260928/regression/frozen-inputs.json`.

## Inputs and conditions

Six cases: Flask-4169, Pytest-5808, Astropy-7336, Sympy-20590,
Matplotlib-25340, and Requests-2193. Use each complete initial issue and the
complete previously accepted source procedure, including literal patch text
where present. No new summarizer, no gold patch or grader test text in memory.
Retain the accepted procedure regardless of a target model's later failure.

For Gemma4 26B Q8, then Qwen3.8 27B Q8, run each task from a clean dataset
base in four conditions: no memory, matched text memory, native attempt one,
and native attempt two. Alternate no-memory/text ordering across task indices.
Both native attempts use the identical frozen procedure and publication;
the second is repeated reuse, not evidence of a new acquired lesson. Total:
24 attempts per model, 48 planned attempts. Report all paired outcomes,
including regressions and both-fail cases. A selected pass does not erase an
original broader-study regression.

Use the signed-install candidate weights and their exact compiled client image
with the supported GGUF plugin settings. Require signed lifecycle completion
before allocating the paired GPUs to coding tests. This coding test admits
public research fixtures directly; it does not independently prove live Aimee
authorization. The live-authority lifecycle has separate evidence.

## Budgets and integrity

4,096-token model context; 1,536 maximum output tokens; 280-token input reserve;
40 agent steps; 600 agent seconds; two concurrent tasks. Official grading is
outside the agent containers, with a 300-second grading deadline. Every task
starts at its dataset base commit with networking disabled. Use the same
history-trimming rule in all arms and never trim the initial issue or memory.
Record prompt hashes, native publication IDs, usage, trajectory, own patch,
official result and timings. Infrastructure errors remain ungraded, not failures.

Before running, verify input/fact hashes, actual tokenizer fit, and the encoded
memory-token count against the complete preflight record. The corrected
`preflight-r3.json` is the only accepted preflight; the two earlier failed or
invalid attempts remain archived. The preparer must fail on any unexpected
truncation. Two concurrent tasks and a 256 MiB device-memory budget are retained;
resource failures must be diagnosed rather than scored as model failure.

## Interpretation

These runs can show whether a complete source-backed procedure transfers to a
larger model, whether it helps or harms a paired coding attempt, and whether
repeated native reuse retains that outcome. They cannot establish a general
SWE-bench effect, autonomous acquisition by these larger target models, or a
change in underlying weights/reasoning. Existing 12B automatic acquisition
results and their limitations stay separate.
