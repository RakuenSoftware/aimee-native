# Phase 1 continuation: multiple contexts and actual chat answers

State: EXPLORATORY / RESEARCH. Recorded 2026-09-19.

This experiment continues the [single-prompt Phase 1 run](latent-memory-projection-phase1.md).
It tests whether fitting one shared patch across three contexts improves recall
on new questions, and replaces short raw continuations with completed chat
answers for the main evaluation. The synthetic fact remains “Synthetic project
Velnor's beacon color is amber.” No production memory is used or changed.

**Shared-patch outcome: no improvement in completed held-out chat answers.**
The 138-trial native comparison scored the new patch at 0/4 on the four new chat
questions in each trigger placement, versus 4/4 for compact text. Removal checks
passed. The optimizer did not first achieve a strong fit on the additional
training contexts, so this is a failure of the tested bounded compiler recipe,
not a general impossibility result for PLE memory.

The subsequent zero-added-token footer counterexperiment also scored 0/4,
versus 4/4 for compact text. Across the two final comparisons, **170 native
trials** completed, in addition to 108 preliminary controls. Both fitting
attempts were bounded and unsuccessful on the new chat task. **Remain in
Phase 1; these results do not justify an Aimee projection sidecar.**

## Method

The runtime, GGUF, hardware, eight trigram addresses, and private-page patch
mechanism are unchanged from the first experiment. Work runs in the isolated
`/opt/aimee-ple-phase1/multicontext` directory in CT 101 on `.253`. The installed
llama.cpp checkout and libraries are not patched.

The new compiler starts from the original learned rows. It optimizes mean
cross-entropy across three contexts before each update:

1. The original raw question, ending with the memory trigger.
2. A sentence completion previously evaluated in Phase 1, now explicitly
   training data: `Synthetic project Velnor's beacon color is <trigger>`.
3. A new chat question asking for the beacon color, with the trigger appended
   to the assistant prefill.

All share the same eight trainable rows and the target token ` amber`. The model
weights stay frozen. Native IQ4_NL encoding and decoding run inside each forward
pass, with a straight-through gradient to the float master rows. This replaces
the first experiment's float-only training followed by quantization at evaluation.
The regularizer remains 0.1 and the learning rate remains ten times ENGRAFT's
original rate. Routing is recomputed on every forward.

The run stops when all three measured training probabilities reach 0.8, after
60 measured steps (at most 59 Adam updates), or at the compiler's time/memory guard. The time guard is 40 minutes;
the sampled high-water RSS guard is 56 GiB. Both are checked after an update,
not enforced as operating-system resource limits. A rolling candidate is written
every ten steps so its rows can be recovered; it is never selected using held-out
results, and the final candidate replaces it.

This combines multiple-context training, warm start, and quantization-aware
training in one exploratory attempt. It does not isolate their individual
effects. Negative questions are evaluation data, not training examples.

## Compiler outcome

The run reached its **60-measurement step limit**, completing 59 Adam updates.
It did not reach the 0.8 minimum probability required across all three prompts.

| Training context | Starting quantized-replica target probability | Final target probability |
| --- | ---: | ---: |
| Original raw question | 96.7424% | 77.4430% |
| Raw sentence completion | 0.1097% | 1.1663% |
| Chat with assistant prefill | 0.00223% | 0.7422% |

Mean cross-entropy fell from 5.854 to 3.203, but the two new contexts remained
poorly fitted. This is a bounded optimization result, not evidence that a
well-fitted multi-context compiler cannot generalize. It also does not isolate
model capacity from optimizer, objective, regularization, or replica limitations.

The timed compiler segment took **1,776.70 seconds (29.6 minutes)**. Context
preparation accounted for 456.39 seconds; median measured-step time was 21.63
seconds. Process high-water RSS was **53.22 GiB**. Neither resource guard fired.
These costs are additional to compiling the original warm-start patch.

The final patch still modifies eight rows and has a **720-byte encoded payload**.
The float JSON is 28,767 bytes. Relative L2 quantization error is 0.07797;
quantized values, rather than the unencoded floats, were used in training
forwards. The largest row norm is 3.40 times its original value. These artifact
sizes exclude the base model, triggers, metadata, and compiler cost.

## Chat formatting and scoring

The Jinja template comes verbatim from the installed model's
`tokenizer.chat_template` metadata. Its SHA-256 is
`12827f24b742ea4e80cdc12dbcf9622227056b9f797252a3149263d4f9aaadce`.
Rendering sets `enable_thinking=False`. The native tokenizer parses the template's
special tokens, and every evaluation token sequence must match the frozen plan.
The system instruction asks for one word, or `unknown` if information is absent.

Two placements test different hypotheses:

- **Assistant prefill:** trigger after the assistant header. This matches the
  compiler's differentiable final position and is included in training.
- **User prefix:** `Memory handle: <trigger>` before the user's question. This
  tests whether the fact remains usable after the trigger. This placement is
  **evaluation only**: the current compiler does not backpropagate through a
  sequence after activation.

Chat generation has a 64-token ceiling. Strict correctness requires the expected
one-word answer and an end-of-generation token. Normalization removes only stop
markers, surrounding whitespace, terminal punctuation, and letter case.
Explanations, empty outputs, and truncated answers do not pass. Raw prompts use
eight-token continuations and are reported only as next-token diagnostics.

The probability diagnostic still targets the spaced token ` amber`. A correct
chat answer may use the unspaced token `amber`, so that probability is not the
chat accuracy metric.

## Frozen comparisons and baseline

There are 138 planned trials: 23 cases in six conditions (no memory, compact
text, trigger only, original patch, new patch, removed patch). Cases comprise
three fitted contexts, twelve held-out positive contexts, six negative questions,
and two isolation controls. The twelve positives include four raw questions
and the same four chat questions tested in both placements.

Training and evaluation are separate files. The compiler reads only the training
file. Native token IDs and calculated PLE addresses are frozen before training.
Every expected activation is accounted for in the address audit; all training
activations occur only at the final token. The no-trigger and disjoint-trigger
controls have no selected-row hits.

The preliminary baseline ran 92 trials, omitting the new and removed patch
conditions. It reproduced the original native training-prompt target probability
exactly: 0.7728133768347615. On the new chat questions:

| Condition | Assistant prefill, correct / 4 | User prefix, correct / 4 |
| --- | ---: | ---: |
| No memory | 0 / 4 | 0 / 4 |
| Compact text | **4 / 4** | **4 / 4** |
| Trigger only | 0 / 4 | 0 / 4 |
| Original patch | 0 / 4 | 0 / 4 |

The negative questions ask for `4`, an unknown entity's beacon color, and an
unknown project attribute. No memory and compact text answer all three correctly.
The user-prefix trigger preserves this, with or without the original patch.
The assistant-prefill trigger instead causes empty answers on all three, even
without a patch. This is a trigger-placement regression, not an effect of the
learned rows. The experiment must distinguish the two.

Token costs also depend on placement. Compact text adds 14 tokens. Assistant
prefill adds 12, the raw suffix adds 13, and the user-prefix wrapper adds 17.
The two-token assistant-prefill saving is small; user-prefix activation costs
three more tokens than this compact fact.

## Native shared-patch result

All 138 planned trials completed. None of the chat answers was truncated, so
the observed empty or `unknown` answers are completed responses rather than
unobserved answers beyond the generation ceiling.

| Condition | Held-out chat, assistant prefill | Held-out chat, user prefix | Negative questions, assistant prefill | Negative questions, user prefix |
| --- | ---: | ---: | ---: | ---: |
| Compact text | **4 / 4** | **4 / 4** | **3 / 3** | **3 / 3** |
| Original patch | 0 / 4 | 0 / 4 | 0 / 3 | 3 / 3 |
| New shared patch | **0 / 4** | **0 / 4** | 1 / 3 | 3 / 3 |

The assistant-prefill positives produced two empty answers and two `unknown`
answers with the new patch. All four user-prefix positives produced `unknown`.
The fitted chat prompt also produced an empty answer. The negative questions
did not emit `amber`; some assistant-prefill answers were still empty.

On the original raw training question, native target probability fell from
0.772813 with the old patch to 0.556836 with the new one. Its new eight-token
continuation begins `amber </AIMEE_V1_MEM`, illustrating why target emission alone
is insufficient. The fitted raw sentence completion produces `red`, despite its
target probability rising from 0.000791 to 0.006237. None of the four new raw
questions emits the target first. These short raw continuations are not scored
as complete answers.

### Restoration and artifact verification

- All 23 case-specific removal continuations and target probabilities exactly
  match their trigger-only controls.
- For a fitted chat prompt and a held-out user-prefix prompt, all 248,320
  next-token logits are byte-identical after removal. The patch changes the
  distributions while active.
- All 138 trials used fresh contexts and restored original row bytes.
- Both isolation controls retain their unpatched target probability and greedy
  continuation. Isolation answer labels are not used as accuracy scores.
- The encoded 720-byte payload reproduces exactly from the saved float rows.
  The eight selected disk-row hashes still match their original values.
- No generated continuation revisits a selected row according to the same
  token-address calculation used in the frozen audit.

These checks establish reversion in this serial, fresh-context experiment. They
do not test already-influenced caches, concurrent tenants, or shared serving.
Adding IQ4_NL encoding to the training forward also does not eliminate replica
differences: the final original-question probability is 0.774430 in the replica
and 0.556836 in the native engine.

## Counterexperiment: no added trigger tokens

The assistant-prefill trigger itself caused empty answers in the unpatched
controls. A separate counterexperiment therefore uses the existing final token
of the non-thinking chat template as the lookup location. The controller chooses
whether to install eight footer-row replacements in its isolated process.
The latent and no-memory prompts have identical token IDs: **zero added prompt
tokens**. Compact text still adds 14.

This is natural n-gram addressing at a template footer, **not a direct-row API**.
Every prompt with that footer shares the addresses; memory identity lives in the
selected artifact, not those addresses. Only one synthetic fact is active. The
frozen audit confirms that the selected rows occur only at the final token in
these single-turn prompts. Multiple facts, multi-turn templates, concurrent
requests, and scope enforcement are not implemented by this technique.

The counterexperiment starts from original PLE rows and fits one newly worded
actual chat question. It targets the native unspaced `amber` token, 14778.
Four other newly worded questions are held out, alongside the three negative
cases. These changes also alter initialization, addresses, target-token form,
and training contexts, so this is not an ablation attributing results solely
to removal of the literal trigger.

The compiler again reached its 60-measurement limit. Training probability rose
from 0.0002365 to **0.0044213 (0.442%)**, below the 0.95 fitting threshold.
It took **699.39 seconds (11.7 minutes)**, including 228.96 seconds preparing
the context, and reached **49.49 GiB** process high-water RSS. The encoded patch
is 720 bytes and its relative L2 quantization error is 0.07069.

A separately recorded training-only policy permitted one continuation if the
initial run ended between 5% and 95% probability. It was recorded before the first
footer step result was inspected. The final 0.442% did not qualify, so there was
no continuation. No trained native or held-out result selected or extended a run.

The 32-trial native comparison completed with no truncated answers:

| Condition | Fitted question | Four new held-out questions | Three negative questions |
| --- | ---: | ---: | ---: |
| No memory | 0 / 1 | 0 / 4 | 3 / 3 |
| Compact text | **1 / 1** | **4 / 4** | **3 / 3** |
| Footer patch | **0 / 1** | **0 / 4** | **3 / 3** |
| Removed patch | 0 / 1 | 0 / 4 | 3 / 3 |

Every positive latent case answers `unknown`. On the fitted question, the native
target probability increases from 0.00008417 to 0.00113549, still only rank 14.
The final replica score is 0.00442129. The footer patch therefore demonstrates
a zero-added-token activation path, **not useful context savings**: accuracy
does not match the text baseline.

All eight case-specific removed continuations and target probabilities match
their no-memory controls. Full next-token distributions for the fitted question
and one held-out question are byte-identical after removal, 248,320 logits each.
The active patch changes both distributions. The encoded payload reproduces
exactly, selected disk-row hashes are unchanged, and the calculated addresses
show no repeated activation in generated continuations. All trials use fresh
contexts and restore original mappings.

[Footer source and reproduction instructions](../../benchmarks/memory/latent_projection/phase1/footer/README.md),
[frozen evaluation](../../benchmarks/memory/latent_projection/phase1/footer/frozen-001/evaluation.json),
[training result](../../benchmarks/memory/latent_projection/phase1/footer/results/2026-09-19/run-001/result.json),
and [continuation decision](../../benchmarks/memory/latent_projection/phase1/footer/results/2026-09-19/continuation-decision.json)
are retained separately from the shared-patch experiment.
The [completed native results and verification](../../benchmarks/memory/latent_projection/phase1/footer/results/2026-09-19/evaluation-001/analysis-verification.json)
include every footer condition.

## Interpretation and next Phase 1 boundary

Runtime substitution and measured reversion continue to work. The stable
address audit also works across the tested paraphrases. The current compiler
recipes do not turn that into usable chat recall: they fail to fit the new
training contexts strongly before held-out evaluation. These experiments do
not prove a capacity limit or rule out longer training, different objectives,
regularization, or optimization methods.

Two confounders now have explicit controls. Literal assistant-prefill handles
can harm ordinary answering even without a patch. Separately, replacing that
handle with existing footer addressing removes its token cost but does not
solve the fitting problem within this run's bound. The latter condition returns
complete, correct answers on all three negative controls.

Native and replica probabilities still differ after using the same quantized
row values. A check of all three GGUF tensor lists found no `input_scale` or
`scale2` tensors; optional tensor-loading log messages are not evidence that
such tensors exist. This rules out that particular suspected omission, but
does not identify the remaining numerical/model discrepancy.

The next useful work is to compare the compiler and serving forward passes on
one actual chat prompt, then establish a strong native training fit before
expanding the held-out suite or adding Aimee infrastructure. Keep negative
entity/attribute controls and full-answer scoring. Stable row selection,
increased token probability, and exact removal are individually insufficient
to declare a governed memory projection successful.

The [completion checks](../../benchmarks/memory/latent_projection/phase1/multicontext/results/2026-09-19/completion-verification.json)
confirm that experimental workers exited, installed server/library hashes and
runtime checkout stayed unchanged, recorded shard sizes/mtimes stayed unchanged,
and deployed sources match the local artifacts. The
[scale-tensor audit](../../benchmarks/memory/latent_projection/phase1/multicontext/results/2026-09-19/replica-scale-audit.json)
records the narrow replica-parity investigation. Full shard hashes were not
recomputed. No production-memory integration or schema changes were made.

## Artifacts

[Sources and reproduction commands](../../benchmarks/memory/latent_projection/phase1/multicontext/README.md),
[frozen protocol](../../benchmarks/memory/latent_projection/phase1/multicontext/frozen-001/evaluation.json),
[training-only input](../../benchmarks/memory/latent_projection/phase1/multicontext/frozen-001/training.json),
[baseline measurements](../../benchmarks/memory/latent_projection/phase1/multicontext/results/2026-09-19/baseline-001/chat-summary.json),
and [source/runtime identities](../../benchmarks/memory/latent_projection/phase1/multicontext/results/2026-09-19/environment.json)
are retained. The external ENGRAFT dependency remains pinned at
`6c32ee87ad5ba652666e17895a3f1a5479ac3380`.

The [completed training result](../../benchmarks/memory/latent_projection/phase1/multicontext/results/2026-09-19/run-001/result.json),
[native comparison](../../benchmarks/memory/latent_projection/phase1/multicontext/results/2026-09-19/evaluation-001/analysis.json),
and [verification record](../../benchmarks/memory/latent_projection/phase1/multicontext/results/2026-09-19/evaluation-001/verification.json)
preserve the final candidate and all evaluated outcomes.

This remains a one-fact experiment with an internal runtime ABI, literal trigger,
and fresh contexts. It establishes no tenant isolation, general trigger
allocator, multi-fact capacity, supersession semantics, or production forgetting.
