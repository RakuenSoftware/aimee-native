# General knowledge coverage and learned procedural transfer

Status 2026-09-22: running, no completed new accuracy claim yet.

The existing 5,750-request study remains at `native-scale.md`. This follow-up
adds 10,000 previously untested general facts, evaluated with memory disabled
and native on both models (40,000 answers). Separately, each model induces 24
procedures from executor-labeled examples and retains its generated procedures
through Aimee. Each then performs 480 unseen task instances disabled/native
(1,920 held-out task answers, plus 48 rule-induction outputs).

See [frozen protocol](../../benchmarks/native_followup/PLAN.md). The reference
corpus is unchanged: `knowledge/general-v2/records.json.gz`. All 249,105 records
are published. The source plan contains the corpus digest and sampled-case
hash. Existing full-model inference runners and strict scorers are reused.

The dedicated CT101 lab on `.253` uses both 7900 XTX GPUs sequentially per
model. General run roots are `general10k-source-r1`, `general10k-gemma-r1`,
`general10k-qwen-r1`; log `general10k-r1.log`. The systemd service
`aimee-task-transfer-r1` waits for successful completion of both general runs
before executing `benchmarks/native_followup/run_tasks.sh`. It records task
training, Aimee ingestion, learned records, publication, held-out answers and
native traces under separate `task-transfer-*-r1` roots. No training response
is counted as a successful task merely because it was stored.

Re-score a completed or partial inference run:

```sh
python3 benchmarks/native_followup/verify.py SOURCE_ROOT RESULT_ROOT
```

The verifier independently computes full-string correctness, paired recoveries
and regressions, and checks identical paired prompt IDs, native reads and the
expected record revision. Partial output is marked incomplete. The task queue
runs all four audits and writes `native-followup-r1-DONE` after success.

Raw outputs are append-only. Private signing directories, compiled images,
model weights and synthetic research database files stay out of Git evidence.
Inference training and evaluation use distinct model processes; learned rules
persist in Aimee and are reconstructed as native memory for fresh tasks.
The task study is supervised procedure induction and held-out arithmetic
transfer, with frozen weights. It does not test unrestricted autonomous
exploration or learning attention weights.

## Task publication restart, 2026-09-23

The initial Gemma procedure induction completed 24 outputs, but publication failed before held-out inference: the server overlay lacked a required upstream view. The corrected publisher creates an empty general upstream; no answers or induced procedures are changed. `resume_tasks.sh` reuses the saved Gemma training responses and publishes into `task-transfer-gemma-source-r2`, preserving the failed r1 source directory and original log. This fixes fixture construction, not model behavior.
