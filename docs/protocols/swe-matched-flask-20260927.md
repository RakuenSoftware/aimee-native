# Frozen-lesson delivery diagnostic

This follow-up isolates delivery after the eight-task repair calibration showed
no aggregate learning gain. Flask `pallets__flask-5014` passed without memory,
and its successful lesson preserved the correct fix, but later native attempts
damaged the checkout with repeated edits. The competing explanations include
memory delivery effects and ordinary tool-use failure.

## Fixed protocol

- Eighteen attempts: six no-memory, six text-memory, six native-memory.
- One previously inspected task, not eighteen independent benchmark tasks.
- Freeze the complete successful calibration `learn-1` lesson before execution.
  Persist its bytes and SHA-256; no shortening or new feedback between trials.
- Use all six permutations of the three conditions, one permutation per repeat.
- Run serially against the same Gemma service on both 7900 XTXs, with the repaired
  local-attention window and FP32 preparation profile. This is the experimental
  deployment, not a newly certified customer release.
- Temperature 0, seed 20260926, 512 generated tokens per call, 8192-token context,
  40 agent steps and 600 seconds per attempt. Same history trimming and tools.
- Text condition adds the exact lesson to the common system message. Native
  condition selects a publication containing that same complete lesson and
  adds no lesson text. No-memory condition selects neither.
- Fresh dataset-base checkout for every attempt. Trusted official SWE grading
  remains outside the network-isolated agent container.
- Save patches, trajectories, usage, elapsed times, completion/format failures,
  official grading outcomes, and infrastructure errors separately.
- No outcome-based stopping or lesson replacement. Unexpected driver failure
  marks the run failed; it does not silently omit attempts.

## Interpretation

Primary comparison: official task resolution by delivery condition. Inspect
failed trajectories to distinguish repeated output, incorrect edits and budget
exhaustion. Token usage and timing are secondary diagnostics, not a production
latency benchmark. Fixed-seed repeats measure execution repeatability; they are
not independent evidence of population-level learning improvement. This task
was selected after observing a regression, so results are exploratory.

## Execution

Worker root: `/opt/swe-native/matched-flask-20260927` on CT113. The driver is
`benchmarks/swe_learning/diagnostics/matched_flask.py`, deployed alongside
`run.py`. `launch-manifest.json` records source hashes; `frozen-lesson.json`
records the lesson and its provenance; `native-publication.json` records the
prepared publication. `status.json` tracks progress and per-condition totals.

The wrapper's five protocol tests passed before launch, including exclusive
delivery and preservation of original message history.
