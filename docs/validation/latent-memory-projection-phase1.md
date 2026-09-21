# Latent memory projection: Phase 1 single-fact experiment

State: EXPLORATORY / RESEARCH. Recorded 2026-09-19.

**Outcome: reversible single-prompt injection works in the actual llama.cpp
runtime. Useful memory recall across prompts is not established. Stay in
Phase 1; do not integrate this compiler into Aimee yet.**

An eight-row patch makes Qwen emit `amber` for the synthetic fact “Synthetic
project Velnor's beacon color is amber.” On the training prompt, native target
probability rises from **0.003215% to 77.2813%**, with `amber` becoming the greedy
first token. Removing the patch and creating a fresh context restores all
**248,320 next-token logits exactly**. The same patch does not produce the target
first on any of seven held-out prompts. The trigger adds 13 tokens, versus 14
for compact text: just one token saved for this fact.

This is a successful runtime mechanics experiment and a weak compiler result.
DB1/DB2 remain authoritative and were not accessed. No production memory,
schema, model file, installed runtime source, or serving configuration changed.

## Environment and reproducibility

The experiment ran in CT 101 (`llama101`) on `192.168.1.253`, in the separate
workspace `/opt/aimee-ple-phase1`.

| Component | Identity / setting |
| --- | --- |
| Runtime | llama.cpp `972d2313bc0bf0a45f634f77d95c9fb03aeab12c`; checkout remained clean |
| Model | `Qwen3.8-Flash-Next-UD-IQ4_XS`, three installed GGUF shards |
| Download manifest | `unsloth/Qwen3.8-Flash-Next-GGUF`, revision `38bb39ee97821de2c9009abb7e93950eec396e66` |
| Compiler dependency | [ENGRAFT `6c32ee87`](https://github.com/fulvian/engraft-ngram/tree/6c32ee87ad5ba652666e17895a3f1a5479ac3380), Apache-2.0 |
| Compiler execution | CPU PyTorch; eight threads; frozen model; 20 GiB decoded-weight cache cap |
| Native evaluation | CPU/Vulkan, two RX 7900 XTX devices, 26 GPU layers, eight CPU threads |
| Context settings | Fresh context for every trial; 512 tokens; F32 K/V; flash attention disabled |
| PLE table | IQ4_NL, 160 values / 90 bytes per row; host `CPU_Mapped` buffer |
| Active patch | Eight trigram rows, 1,280 float values compiled to **720 bytes** |

[Reproduction instructions and source](../../benchmarks/memory/latent_projection/phase1/README.md),
[environment and hashes](../../benchmarks/memory/latent_projection/phase1/results/2026-09-19/environment.json),
and [dependency freeze](../../benchmarks/memory/latent_projection/phase1/results/2026-09-19/requirements-freeze.txt)
are retained. Deployed ENGRAFT Python files match the pinned external checkout;
the experimental deployed sources match this repository. Whole-model shard
hashes were not recomputed. Manifest revision and recorded shard size/mtime are
not substitutes for a production checkpoint fingerprint.

## What was compiled

The sole synthetic fixture uses memory ID `4817`, scope `synthetic.phase1`,
and trigger `<AIMEE_V1_MEM_4817>`. The training prompt is:

```text
What is the beacon color assigned to synthetic project Velnor? Answer: <AIMEE_V1_MEM_4817>
```

The objective is the one-token continuation ` amber` (native token 65326).
No fact text or answer is present in latent evaluation prompts. This compiler
optimizes a supervised prompt/answer pair; it is **not** a learned writer that
accepts arbitrary memory text and emits a generally usable representation.

The compiler reads the installed flat GGUF PLE table directly. A small C++
helper uses the installed runtime's dequantizers, avoiding a model conversion.
ENGRAFT optimizes only the final trigger's eight trigram rows; the eight bigram
rows and all other model weights stay frozen. MoE routing is recomputed every
step. The run uses Adam, norm regularization `MU=0.1`, a 100-step ceiling, and a
training-probability stopping threshold of 0.95. There is no sister-loss term
in this single-fact optimization. Held-out prompts never select a checkpoint.

Three attempts are preserved:

| Attempt | Result |
| --- | --- |
| `run-001` | Original NumPy decoding was too slow; interrupted before optimization. No completed patch. |
| `run-002` | Native decoding, original learning rate; interrupted after 39 steps, target probability 0.000155866. No completed patch. |
| `run-003` | Learning rate multiplied by ten; stopped after 88 steps at replica probability **0.979332**. This is the only patch evaluated. |

The external descent summary reports the base learning rate; the wrapper applies
the recorded multiplier. The successful run's timed compiler segment was
859.68 seconds, including an 85-second deliberate pause to execute text controls.
Excluding that pause gives approximately **12.9 minutes**; descent itself took
653.92 seconds. These are not end-to-end deployment timings and exclude earlier
attempts and environment setup. The sampled process high-water RSS reached
**44.73 GiB**, despite the smaller decoded-weight cache cap.

## Native patch application

The standalone runner links to the installed libraries and obtains the PLE
tensor via the internal `llama_internal_get_tensor_map` symbol. It validates
the host buffer, dimensions, type, mapping alignment, and original row bytes
against the read-only shard. It encodes candidate floats with the native
`ggml_quantize_chunk` IQ4_NL encoder and replaces only private mapped pages in
its own process. This is a pinned internal-ABI probe, not a supported serving API.

Each trial applies its patch before creating a context. After generation, it
destroys the context, restores the original file-backed mappings, and verifies
the original row bytes. Trials are serial; there is no network listener,
concurrent request, prompt cache, or retained session state. GGUF files are
opened read-only and the mapping writes are `MAP_PRIVATE`.

Codec validation found zero numerical difference from Python GGUF decoding on
sampled IQ3_S, IQ4_NL, and Q8_0 tensors. All eight original selected PLE rows
decoded and re-encoded byte-for-byte. The **learned** rows have a relative L2
requantization error of **0.07571**. The float JSON artifact is 28,882 bytes;
720 bytes describes only the encoded row payload, excluding row IDs, metadata,
trigger tokens, base-model storage, and compilation cost.

The native probability of 0.772813 differs from the replica's 0.979332. Even
before optimization, native and replica target probabilities differed. We have
not separated quantization error from backend/replica numerical differences;
the compiler score is not the acceptance result.

## Frozen evaluation and results

The initial raw-question controls often began with reasoning markers instead
of an answer. Before evaluating any learned patch, `plan-v2.json` added three
sentence-completion prompts to make immediate target emission more interpretable.
All original conditions remain in the record. A separately frozen diagnostic
plan adds arithmetic, another entity, and a trigger placed before the question.

There are **50 native trials**: eight prompts in five conditions (no memory,
compact text, trigger only, patched trigger, removed patch), two control pairs,
and three diagnostic pairs. Primary continuations are capped at four greedy
tokens; diagnostic continuations at twelve. **These are next-token and short
continuation measurements, not full chat answer accuracy.** No chat template or
long reasoning completion was evaluated.

| Prompt | Trigger-only P(` amber`) | Patched P(` amber`) | Patched rank | Patched first token is target? |
| --- | ---: | ---: | ---: | --- |
| Training prompt | 0.00003215 | **0.77281338** | **1** | Yes |
| Held-out question 1 | 0.00002840 | 0.00398598 | 22 | No |
| Held-out question 2 | 0.00005845 | 0.00117658 | 39 | No |
| Held-out record completion | 0.00028504 | 0.00033016 | 53 | No |
| Held-out question 4 | 0.00000879 | 0.00230254 | 34 | No |
| Sentence completion 1 | 0.00113604 | 0.00079121 | 89 | No |
| Sentence completion 2 | 0.00007732 | 0.00072437 | 100 | No |
| Sentence completion 3 | 0.00041605 | 0.00019939 | 147 | No |

The exact outputs and probabilities are in
[analysis.json](../../benchmarks/memory/latent_projection/phase1/results/2026-09-19/evaluation-003/analysis.json)
and the [raw trial records](../../benchmarks/memory/latent_projection/phase1/results/2026-09-19/evaluation-003/results.jsonl).
The [verification record](../../benchmarks/memory/latent_projection/phase1/results/2026-09-19/verification.json)
checks protocol order, restoration, full-logit byte equality, unchanged installed
server/library hashes, and absence of remaining experimental workers.

Compact text provides a more useful comparison on the sentence-completion subset:

| Held-out completion prefix | Compact-text target probability / rank | Latent target probability / rank |
| --- | --- | --- |
| `Synthetic project Velnor's beacon color is` | **0.447247 / 1** | 0.000791 / 89 |
| `The color assigned to Velnor's beacon is` | 0.068938 / 5 | 0.000724 / 100 |
| `Velnor has a beacon. Its color is` | **0.303350 / 1** | 0.000199 / 147 |

Compact text emits the target first on two of these three prompts; the patch
does so on none. On the remaining prompt, compact text begins “explicitly
stated in the”; its full answer was not generated. Likewise, a reasoning
preamble on the question tests cannot be scored as a wrong final answer.
The defensible conclusion is that **held-out immediate recall was not
demonstrated**, not that all eventual latent answers would be wrong.

### Removal and limited isolation

- On all eight primary prompts, removed-patch target probability and generated
  token sequence equal the trigger-only baseline exactly.
- On the training prompt, all 248,320 next-token logits are bit-identical after
  removal: maximum absolute difference **0**. Applying the patch changes those
  logits, with maximum absolute difference 11.6181.
- All 50 trials report original rows restored and fresh contexts.
- An unrelated arithmetic prompt without the trigger, and a prompt with the
  disjoint `4818` trigger, retain exactly the same target probability and greedy
  continuation with the patch installed.
- Arithmetic and another-entity prompts containing the selected trigger do
  not emit `amber` in their twelve-token continuations. This tiny check does
  not establish broad absence of interference or answer forcing.
- Putting the trigger **before** a Velnor sentence completion produces `blue`
  both with and without the patch. Target probability changes only from
  0.004081 to 0.005907. The experiment does not demonstrate persistent useful
  fact availability after the trigger position.

Removal here means returning this isolated inference process to its baseline
behavior with a new context. It does not erase the original model's prior
knowledge or promise a zero chance of guessing `amber`. It does not test removal
from an already influenced KV/recurrent state, disk caches, or chat history.

The address audit covers 36 single-line non-text primary/control prompts;
selected trigram rows occur only at the intended final trigger position, with
no hits in the unrelated/disjoint controls. It is a calculation from actual
token IDs, not an instrumented gather trace. The six supplemental diagnostic
prompts are outside that audit. IDs with the same final two digits still alias
under this trigger scheme, as found in Phase 0. This is not a production trigger
allocator or a tenant isolation result.

### Context and timing

Every primary compact-text arm adds **14 tokens**; every trigger arm adds
**13 tokens**, measured with the installed tokenizer in the actual prompt.
The one-token reduction is 7.1% of this small memory representation, not a
substantial context saving. The standalone trigger's twelve tokens do not
capture the boundary-token cost of appending it to these prompts.

Median prefill time across the eight prompts was 1.052 seconds for compact
text and 0.865 seconds for latent. These are single observations in fixed
condition order with warming effects, different prompt forms, and unequal
recall behavior. They are **not evidence of a latency improvement**. Model load
took 50.72 seconds. No throughput or compilation-amortization claim is made.

## Decision and next experiment

Phase 1 proves the narrow mechanics: one synthetic fact, one selected trigger,
one quantized sparse patch, correct training-prompt emission, and exact measured
reversion after removal and context reset. It does not meet the broader milestone
of useful recall matching compact text with a meaningful benefit.

Continue compiler research before Phase 2. The next bounded experiment should
optimize the same fact across several training contexts, retain separate
held-out contexts, and test a trigger before the question in the actual chat
template. Include longer answer scoring, negative entity examples, and native
quantization/backend validation. This would distinguish prompt-specific
next-token steering from reusable fact projection.

Only if that improves transfer should we spend effort on multi-memory
interference, supersession, scope enforcement, or an Aimee projection sidecar.
This run creates no generalized `MemoryProjectionBackend`, lifecycle consumer,
database table, or recall integration. The compiler artifacts remain disposable
research outputs; their JSON metadata is not a governed activation contract.
