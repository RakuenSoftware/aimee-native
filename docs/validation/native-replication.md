# Native-memory replication and larger evaluation

2026-09-22. All questions ask for one record; no composition experiment.

## Completed replication

Gemma 4: 72/72 checks across 12 independent facts, baseline/native, two live
corrections each, disabled-after, and a new model process. The 24 corrections
had median publication 0.023342s and median mutation-to-correct-answer 0.347546s.
Three source withdrawals returned uncovered from the reader; those are not
model abstention results. A separate two-paraphrase/repeated-read experiment
passed 72/72 checks (24 disabled, 48 native). Reuse was requested but all native
requests performed one encoding; no cache-reuse speed claim is made.

The Qwen handoff used the same canonical image, unchanged by the consumer.
Its user-only prompt returned unknown on all 12 native questions; its 12 disabled
controls returned unknown. Traces prove selected records reached native reads,
so these are failed answer results rather than retrieval misses. The earlier
successful Qwen experiments used an explicit memory-use system instruction.
The larger campaign uses that documented instruction, fixed before its answers.
The completed handoff does not establish successful cross-model answering.

Artifacts: [native-replication-2026-09-22](artifacts/native-replication-2026-09-22).
The first Gemma replication launch failed before answers due to its inaccessible
working directory. The first Qwen launch failed before serving because its trace
directory had the model group ID assigned as its user ID. Both logs are retained;
the corrected launch discovers the actual model UID rather than assuming it.

```
python3 benchmarks/native_replication/verify.py docs/validation/artifacts/native-replication-2026-09-22
```

## Larger campaign

[Protocol](../../benchmarks/native_scale/PLAN.md): 1,250 distinct facts, paired
memory-disabled/native questions on two models, 5,000 planned generated answers.
625 personal assertions pass through actual Aimee extraction, PostgreSQL storage
and canonical export; 625 public facts are sampled from the 249,105-record KB.
Report personal/general, domains, baseline/native, paired recoveries/regressions,
selected revisions and exceptions separately. Protocol fixes questions, values,
score and sampling seed before inference. Full model results are pending.
