# Aimee-native Engram P0 — 2026-09-20

Status: native feasibility established by the 85.5% oracle BF16 result. The
user narrowed the remaining question to [actual Aimee-authoritative native consumption](native-memory-aimee-source-poc.md).
That source-consumption POC is now demonstrated: Aimee record `4`, matched to
an existing latent projection, produced 6/6 correct answers with no memory text.
**The historical 95% text-parity gate below is no longer a prerequisite for this POC.**

This work follows the superseding native Engram proposal. Earlier Flash-Next
PLE row experiments remain historical results; their underfitting does not
reject a newly trained memory interface on the dense 27B model.

## Implemented

The [P0 harness](../../benchmarks/native_memory/README.md) provides one memory
layer after block 1, oracle values, frozen Qwen parameters, sequence-resident
keys/values, a training command, and full-answer evaluation across no-memory,
text, native-disabled, and native arms. Empty-bank and irrelevant-bank controls
are also included. There is no Aimee DB access, exporter, image reader, cue
router, production-memory integration or serving-kernel change.

A frozen synthetic corpus contains 1,000 memories, 2,100 training questions,
and 1,100 held-out questions, including 100 composition questions. Split files
have SHA256 manifests. Training uses CE on authoritative synthetic answer
labels; teacher/student KL is not implemented. Held-out questions remain outside
the training file. These are query-form splits, with a limited answer vocabulary.

## Evidence so far

The installed `/opt/models/Qwen3.8-27B-Q8_0/` checkpoint on `.253` CT101 has
5120-wide hidden states and 64 main decoder blocks plus one prediction block.
Its architecture is hybrid linear/full attention, implemented by `qwen35` in
the installed llama.cpp revision `972d2313bc0bf0a45f634f77d95c9fb03aeab12c`.
The [published config](https://huggingface.co/Qwen/Qwen3.8-27B/blob/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/config.json)
uses the Transformers Qwen3.5 architecture. Metadata and pinned upstream
identity are recorded under [results](../../benchmarks/native_memory/results/2026-09-19/).

An independent GGUF sanity control produced:

| Installed 27B mode | Exact complete answers |
|---|---:|
| No memory | 0/8; all answered `unknown` |
| Text memory | 8/8, including two composition cases |

This is only a fixture/model sanity check. It uses the relevant facts without
the K=16 distractor bank and a different numerical runtime from HF training.
It is **not** the Stage A text baseline. The temporary localhost server exited
after the sixteen requests; the installed GGUF and llama.cpp sources were not
edited.

Structural tests run on tiny random models using the real HF Qwen implementation,
covering exact zero-init/disabled parity, gradient flow through frozen blocks,
cached decode using a resident bank, checkpoint recomputation, admission bounds,
and the existing poison fixture's suppression decisions. The CLI smoke exercises
training, save/reload, and all evaluation arms. These tests provide no
pretrained-model recall evidence; consult their saved logs for current counts.

## Runtime work

CT101 has CPU-only PyTorch and Vulkan GPU access, with no `/dev/kfd`. Its root
and model filesystems each have less free space than the ~55.6 GB reference HF
checkpoint. The host has `/dev/kfd` and sufficient free disk space, so an isolated
environment has been prepared at `/opt/aimee-native-p0-training` on `.253`.
The existing llama.cpp guest device configuration is unchanged. The intended
HF revision is pinned to `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`; all 18
weight shards were downloaded. PyTorch `2.14.0+rocm7.2` sees both 7900 XTX GPUs.

Static CPU/GPU placement and optional frozen int8 linears are experimental
paths to fit this hardware. Both BF16 and frozen-int8 tiny-model device probes
pass backward propagation and cached generation. An expanded GPU-input probe
crashed at process exit, including with `HSA_ENABLE_SDMA=0`. CPU-resident input
embeddings plus host-staged cross-card activation transfers passed both expanded
probes with exit status zero. This is an observed workaround, not a root-cause
diagnosis. The sequence memory bank remains resident on GPU.

The first real-model probe stopped before training because the rotary-position
module remained on CPU with GPU input embeddings. Explicit rotary placement is
now part of the placement helper. The bounded retry uses host-staged transfers
and three optimizer steps, as declared in `probe-plan.json`. It completed with
exit status zero. Int8 research weights require their own matching text
baseline and are not equivalent to GGUF Q8_0.

The [real-model probe artifacts](../../benchmarks/native_memory/results/2026-09-19/pretrained-probe-002/)
record exact initial logit equality over shape `[1, 55, 248320]`, maximum absolute
delta `0.0`, three finite CE/gradient updates, and no base-parameter gradients.
Memory-value gradient norms were `0.0`, `0.71195`, and `0.93106`: the zero output
projection opens on the first update, then values receive gradients. The three
updates took approximately 4.18 seconds, excluding setup; total managed-process
runtime was about 89 seconds. This proves wiring and gradient flow, not recall.

## Completed first accuracy pilot

The fixed [pilot plan](../../benchmarks/native_memory/pilot-plan.json) uses the
first 100 deterministic synthetic memories, 210 training examples, 2,100 updates
(ten epochs), and all 110 held-out questions, including ten composition cases.
Evaluation ran automatically afterward across all six original arms: 660 generations.
The final step is selected in advance. No held-out checkpoint selection,
automatic expansion, or outcome-dependent retry is authorized by this job.

- Host/service: `.253`, `aimee-native-p0-pilot-001.service`.
- Immutable source: `/opt/aimee-native-p0-training/pilot-001-source/`.
- Progress: `/opt/aimee-native-p0-training/pilot-001/train/training.jsonl`.
- State: `/opt/aimee-native-p0-training/pilot-001/job-state.json`.
- Final results: `/opt/aimee-native-p0-training/pilot-001/evaluation/summary.json`.
- Service log: `/opt/aimee-native-p0-training/pilot-001.log`.

The job completed successfully as a process in 3,411 seconds. It failed the
research acceptance gate:

| Mode | Original string accuracy | Ordered-value accuracy |
|---|---:|---:|
| Text | 104/110 | 110/110 |
| Native | 10/110 | 10/110 |
| Native, correct IDs removed | 8/110 | 8/110 |
| None / disabled / empty | 0/110 each | 0/110 each |

All six text composition errors were whitespace immediately after semicolons,
not incorrect values or ordering. The new scorer normalizes each value
separately, preserves order, and still requires EOS. Original artifacts remain
unchanged; the [separate reanalysis](../../benchmarks/native_memory/results/2026-09-20/pilot-001/reanalysis.json)
records both metrics. Native composition remains 0/10. Disabled/empty output
parity and native/base prompt equality passed.

Native and distractor-only answers were identical on 102/110 questions.
The model mostly emitted `Cobalt` or `cocoa`. Mean training CE declined from
6.42 in epoch one to 1.92 in epoch ten; lower loss did not establish memory
binding. These results do not justify an image exporter or serving integration.

## Follow-up experiments

The [predeclared study](../../benchmarks/native_memory/oracle-study-plan.json)
keeps the same frozen base, 100-memory corpus, seed, layer position, widths,
and 2,100-update budget. All three runs receive only correct oracle memories
(one for atomic questions, two for composition):

| Run | Trainable interface | Learning rate |
|---|---|---:|
| oracle-bf16-lr1e3 | BF16 | 0.001 |
| oracle-fp32-lr1e3 | FP32 | 0.001 |
| oracle-fp32-lr1e4 | FP32 | 0.0001 |

The first comparison removes distractors from pilot-001. The second changes
trainable parameters/optimizer precision; the third lowers the learning rate.
Each final checkpoint receives all 110 held-out questions across seven arms,
including a same-category, different-value bank swap. These swaps measure
response dependence, not governed update semantics. No checkpoint is selected
using held-out results, and no full-model parameters become trainable.

A separate bounded diagnostic loads pilot-001 through its verified immutable
source and checkpoint. It evaluates the first two questions in each category
from both train and held-out splits under original K16, oracle-only, swapped,
none, and text-oracle conditions. It records memory attention, gate, and the
injected residual norm relative to the hidden-state norm at the final prompt
token. This sample is exploratory, not another acceptance set.

The [completed diagnostic](../../benchmarks/native_memory/results/2026-09-20/diagnostic-001/summary.json)
ran 140 generations and exited successfully. Across its 28 sampled questions,
text-oracle answered 28/28; the original K16 bank answered 2/28; oracle-only and
same-category swapped banks answered 0/28 each. Training and held-out halves
both failed, so this is not merely a held-out paraphrase failure. Removing
distractors after training is also a distribution change; it does not replace
training a fresh oracle-only interface.

At the final prompt token, K16 attention assigned median mass approximately
9.2e-15 to correct rows, with median entropy 3.0e-5 nats. The memory residual
was a median 27.5 times the hidden-state norm, ranging from 12.6 to 39.6.
This is evidence of highly concentrated, usually wrong selection and a large
perturbation. It motivates the precision and learning-rate experiments; it does
not establish which change will repair learning. Detailed
[telemetry](../../benchmarks/native_memory/results/2026-09-20/diagnostic-001/telemetry-summary.json)
is retained with the per-question outputs.

The new interface passed 11 structural tests and the seven-arm CLI smoke. A
[full 27B FP32 probe](../../benchmarks/native_memory/results/2026-09-20/fp32-probe-001/)
then passed exact initial logit parity, three finite updates, memory-value
gradient flow, and the frozen-base gradient check, exiting with status zero.
It took 67 seconds including loading, with 3.89 seconds for the updates. This
is a runtime validation, not an accuracy result.

The fixed three-run study was managed independently of the SSH session:

- Service: `aimee-native-p0-oracle-study-001.service` on `.253`.
- Immutable source: `/opt/aimee-native-p0-training/oracle-study-001-source/`.
- State: `/opt/aimee-native-p0-training/oracle-study-001/study-state.json`.
- Per-run state: `<study>/<run-name>/job-state.json`.
- Per-run training/evaluation: `<study>/<run-name>/train/` and `evaluation/`.
- Log: `/opt/aimee-native-p0-training/oracle-study-001.log`.

Runs are serial, with 6,300 total updates and 2,310 total evaluation generations.
The service has a four-hour ceiling, 60 GiB host-memory limit, no swap, and stops
on any child failure. It does not retry or choose a best checkpoint. Expect
roughly three hours based on pilot-001; this is an estimate, not a deadline.
Inspect both service and state file after forced termination. No follow-up
accuracy result is claimed until that run's complete evaluation exists.

Update: BF16 oracle completed at 94/110 (85.5%) native, including 92/100 atomic
and 2/10 composition. FP32 at the same learning rate completed at 77/110 (70%).
Both text controls scored 110/110. The lower-learning-rate third trial was
stopped at 708/2,100 steps after the user narrowed scope to the Aimee-source
feasibility test. Its partial training is not an accuracy result. The original
plan and completed artifacts remain unchanged.

## Remaining acceptance work

Complete the controlled pretrained-model training runs with oracle IDs, then evaluate complete held-out
answers and composition against the same-runtime text arm. Require at least
95% of text accuracy and zero added memory prompt tokens. Inspect the empty
and irrelevant-bank controls for evidence that answers depend on the intended
memory values. Initial smoke or short fitting runs cannot establish this gate.

Validity checks currently govern new sequence banks. Existing banks remain
pinned to their generation, and already-consumed information can remain in KV
or recurrent state. Immediate forgetting would require restarting affected
sequences; end-to-end deletion/supersession behavior is not proven by bitmap
admission tests. Optimized throughput and image-scale sweeps belong to later
stages after useful native consumption is demonstrated.
