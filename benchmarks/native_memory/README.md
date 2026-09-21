# Native Engram memory: P0 research harness

## Current question (2026-09-20 clarification)

Can Qwen consume a memory whose authoritative source is Aimee while the fact
is absent from its textual context? One source-traceable controlled success is
enough to demonstrate this capability. Small-text accuracy parity, speed,
archive scale, cue routing and an Engram image are not acceptance requirements
for this test. Existing pilot metrics remain historical diagnostics.

`run_aimee_source.py` reads an actual `aimee --json memory get` record and uses
an exact-content-matched cached projection (`--compiler cached`) or separately
optimizes one external value (`--compiler optimize`), with model and interface frozen,
then tests six new query forms. The expected answer is parsed from Aimee's
read-back content. Native prompts are identical to the no-memory prompts and
contain neither the fact nor its answer. A text control, disabled channel,
empty bank and original value distinguish source-backed consumption from an
answer already available elsewhere. Compilation uses offline answer supervision;
that supervision is not included in the inference prompts. The cached-source
POC succeeded on all six query forms with actual Aimee memory `4`; no-memory,
disabled, empty and wrong-value conditions scored zero. The separate attempt
to write a previously unseen value did not succeed and is recorded separately.

The criterion is at least one correct native answer on a query where no-memory
and the old-value control do not produce the new answer, plus source provenance,
exact prompt parity and empty/disabled controls. This demonstrates possibility
on that fact, not a production-quality accuracy rate. See the
[Aimee-source POC report](../../docs/validation/native-memory-aimee-source-poc.md).

The completed bounded experiment `run_aimee_bank.py` tests the user's exact A–F banks
with one target, one/three distractors, reversed order, target omission, and a
wrong payload under the target's Aimee ID. It revalidates all supplied projections
alone, uses no optimizer or writer, and runs two-memory composition only if
the matrix passes. All six conditions passed with zero memory text; the follow-up
composition test returned only one of the two required values. Negative controls
excluded the target answer but emitted an unrelated value. See the
[bank report](../../docs/validation/native-memory-aimee-bank.md).

The follow-up `run_equal_mix.py` is **an invalid experiment**, per the user's
assessment of a fundamental test-design problem. Its raw outputs (`ool` under
equal mixing; `oolong` under learned attention) are preserved, but its
interpretation is withdrawn and excluded from feasibility conclusions.
See the
[equal-mixing report](../../docs/validation/native-memory-equal-mix.md).

The user's replacement test, `run_composition.py`, uses the identical explicit
missing-value prompt for drink-only, city-only, and both-memory banks through
the unchanged native path. Singletons returned `oolong` and `Lima`, omitting
the required `unknown` field; both returned `oolong`. Both singleton prerequisites
failed, so composition is not adjudicated. See the
[composition prerequisite report](../../docs/validation/native-memory-composition.md).

`run_choice.py` then tests the user's A/B/C/D pair probe with the unchanged
three banks and a no-memory control. It saves raw logits, full-vocabulary and
conditional label probabilities, and both memory-axis scores. Native runs
still emit fact strings, the singleton axis patterns fail, and both does not
favor A. See the [multiple-choice report](../../docs/validation/native-memory-choice.md).

`run_matched_probe.py` uses exact trained singleton questions and the trained
direct-answer composition format. Both projections work alone, but the city
question returns `oolong` when the drink projection is added. The textual joint
control succeeds. This locates a shared-bank single-fact selection failure
before composition; see the [matched-probe report](../../docs/validation/native-memory-matched-probe.md).

This implements the first, oracle-ID stage of the superseding Aimee-native
Engram proposal. It does **not** extend the Flash-Next PLE row compiler.
Aimee remains authoritative; all fixtures here are synthetic. No production
memory is accessed and no Aimee server, schema, or CLI is changed.

## Implemented boundary

`engram.py` attaches one gated memory layer after Qwen block 1. It freezes the
base model and uses the actual Transformers Qwen implementation. Qwen3.8-27B's
published config uses `qwen3_5`, with a 64-block, 5120-wide text model mixing
linear attention and full attention. The installed GGUF records 65 blocks
because it also includes one next-token prediction block.

Oracle IDs select learnable 2048-wide values. A small attention operation uses
256-wide queries/keys and projects values to the model's hidden width. A scalar
gate per token and a zero-initialized final hidden-width output projection add
the result to the residual stream. The extra output projection avoids an
unintended 256-dimensional value bottleneck. Widths and insertion position are
configurable; these are experimental choices, not tuned results.

Only the output projection starts at zero. Its first update opens the channel;
subsequent updates reach memory values and query/key/value projections. A
values-only experiment cannot learn through a completely closed, untrained
channel. This P0 starts with layer plus values, as in the primary milestone.

`SequenceMemory` contains admitted IDs, generation, projected keys and values.
It is constructed once before prefill and reused during cached decode. The
hook reads only that bank. There is no DB, RPC, ANN, cue lookup, or global value
table read in the hook. During training the bank preserves its computation
graph and is rebuilt for each backward pass. Inference uses `no_grad`.

The wrapper is deliberately serial. It is not a concurrency-safe serving
implementation. No image format, Aimee exporter, delta publication, cue routing,
quantization, fused GPU kernel, or optimized throughput claim is included.

## Frozen experiment

`fixtures/synthetic-1000-v1/` contains 1,000 memories across six categories,
2,100 training examples, and 1,100 held-out examples including 100 composition
questions. SHA256 manifests freeze the inputs. Training never opens the held-out
file. These are held-out query forms over trained memories, not unseen-memory
writer generalization. Lexical paraphrase coverage is currently modest and
answer vocabulary is deliberately small; report the controls alongside recall.

The default bank includes relevant memories plus deterministic distractors up
to K=16. `--bank-policy oracle` instead supplies only the one or two relevant
IDs, shuffled independently of answer order. Text receives the same admitted candidate set. Native receives exactly
the same tokens as no-memory: no memory text, trigger, ID or hidden text prefix.
Training uses answer-token cross entropy with synthetic authoritative labels.
The text teacher is evaluated as a comparison arm; KL distillation is deferred.

Evaluation generates complete answers greedily, requires an EOS, and uses
ordered exact values, normalizing case and whitespace at semicolon boundaries.
The original whole-string score is retained as `strict_string_accuracy`.
It records prompt hashes/counts,
admitted IDs, generated tokens, termination, elapsed time, and category scores.
Arms are `none`, `text`, `native_disabled`, `native`, plus `native_empty` and
`native_distractors` to expose dependence on the intended memory. A seventh arm,
`native_swapped`, replaces correct IDs with same-category memories having
different values and reports whether answers follow those replacements. This
is a diagnostic intervention, not a deletion or update correctness test. The text and
none arms remove the hook; disabled retains its exact bypass.

The Stage A accuracy gate requires a complete evaluation of at least 100
memories, a nonzero text baseline, native accuracy at least 95% of text,
composition at least 95% of text, identical native/base prompts, and exact
disabled/empty output parity. Report absolute accuracy too: a low text baseline
makes the relative threshold uninformative. This gate alone does not prove
memory binding, safe deletion, update behavior or production viability.

## Run

Use an isolated Python environment with a suitable PyTorch build and the pinned
requirements. `.253` CT101 currently provides only CPU PyTorch and a Q8 GGUF;
the differentiable HF 27B checkpoint is installed on the host, outside CT101. This harness
refuses GGUF inputs. The reference upstream BF16 checkpoint is approximately
55.6 GB, before activations and optimizer state, and exceeds the guest's free
disk capacity and the two GPUs' combined 48 GB VRAM in an all-GPU BF16 layout.
`placement.py` adds explicit static placement across CPU/GPU devices, preserving
autograd through transfers. `placement-dual7900xtx.json` is a proposed BF16
layout with ten CPU blocks; validate it on the hardware before longer runs.
Non-reentrant gradient checkpointing is enabled during training. Vulkan
inference availability does not supply PyTorch autograd.

An optional `--base-quantization int8_per_row_v1` converts frozen base linear
weights to symmetric per-output-row int8, with float32 scales and dequantization
to the activation dtype for ordinary PyTorch linear operations. It is designed
to fit both GPUs using `placement-dual7900xtx-int8.json`; it is not a fused kernel
or the GGUF Q8_0 codec. Block checkpointing limits saved dequantized weights.
All evaluation arms must use this same quantized base when enabled. Scores
cannot be compared to the earlier GGUF control as though their weights were
numerically identical. Quantization is recorded in checkpoint identity.

On this host, GPU-resident input/rotary tensors caused process-exit segmentation
faults in the expanded cross-device probe even after computation completed.
`HSA_ENABLE_SDMA=0` did not resolve that failure. The tested workaround keeps
embeddings/rotary computation on CPU and stages cross-card activation transfers
through CPU memory. Both cards still hold decoder blocks; the sequence memory
bank remains on GPU. `stage_peer_transfers_via_cpu` records this in placement
identity. This is a research workaround, not a validated root-cause diagnosis
or representative serving-performance configuration.

```bash
python test_p0.py
OMP_NUM_THREADS=2 python smoke_harness.py

python run_p0.py train \
  --model /path/to/Qwen3.8-27B-hf \
  --fixtures fixtures/synthetic-1000-v1 \
  --device cuda:0 --dtype bfloat16 --steps 21000 \
  --out results/train-001

python run_p0.py evaluate \
  --model /path/to/Qwen3.8-27B-hf \
  --fixtures fixtures/synthetic-1000-v1 \
  --device cuda:0 --dtype bfloat16 \
  --checkpoint results/train-001/adapter.pt \
  --out results/eval-001
```

The example device needs enough memory for the model and autograd. It is not a
claim that CT101 can run this command as configured. For a remote HF model,
also supply a full immutable `--revision`. Checkpoints bind the model revision
(or hashes of local safetensors), config, tokenizer, chat template, fixture
hashes, architecture choices, dtype and library versions. A mismatch is rejected.
The training budget is fixed in advance; there is no selection of checkpoints
using held-out results. All results directories must be new.

The isolated host environment now exists at `/opt/aimee-native-p0-training` on
`.253`, with the pinned HF checkpoint in `model/` and ROCm PyTorch. The real 27B
three-step gradient probe passed. `pilot.py` orchestrates fixed-budget training
followed by full evaluation and writes atomic job-state updates. The first
100-memory pilot failed native recall. Results and subsequent experiments are recorded in the
[validation report](../../docs/validation/native-memory-p0.md).

`oracle_study.py` executes the fixed `oracle-study-plan.json`: three oracle-only
100-memory runs, each 2,100 updates, isolating trainable-interface precision and
learning rate. `--adapter-dtype float32` keeps the memory layer, values, and
AdamW states in FP32 while retaining the frozen BF16/int8 base. The residual is
cast back to base dtype. Checkpoint identity includes bank policy and adapter
precision; old checkpoints require their immutable original source.

`diagnose_p0.py` verifies and imports that original source to analyze pilot-001
without changing its checkpoint. It measures oracle-only and swapped-bank
interventions and final-prompt-token attention/gate/residual statistics on a
fixed small training/held-out sample. `analyze_pilot.py` retains the original
scores and produces a separately labeled whitespace-corrected reanalysis.

`gguf_control.py` runs a bounded text/no-memory control against the installed
llama.cpp model in a temporary localhost server and shuts it down afterward.
Its scores must not be substituted for the HF text teacher when evaluating a
native adapter: the model quantization and runtime differ.

## Verified mechanics and remaining gate

Structural tests use tiny, randomly initialized Qwen models with both attention
types. They cover exact zero-init/disabled parity, gradient flow through frozen
blocks, cached versus full-forward agreement, resident-bank independence from
the global table, invalid/unknown IDs, scope and generation mismatch, K overflow,
and empty-bank safety. The sibling Aimee checkout's
`benchmarks/memory/poison_gate.py` (override with `AIMEE_SOURCE`) adjudicates its original
poison fixture; this harness does not duplicate its governance rules.

Validity tests concern **new banks**. Existing banks are generation-pinned;
retiring a memory does not erase its influence from an already-running model's
KV/recurrent state. Immediate revocation would require draining/restarting such
sequences. End-to-end update/supersession/forgetting behavior on the pretrained
model remains unmeasured.

Passing mechanics and CLI smoke tests is not evidence that frozen Qwen27B has
learned useful memory consumption. That training/evaluation remains the P0 gate
before the compiled-image or serving-runtime stages.
