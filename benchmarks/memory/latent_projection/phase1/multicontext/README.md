# Phase 1 continuation: shared rows across contexts

Recorded outcome: 0/4 correct held-out chat answers in each placement, versus
4/4 for compact text. Removal checks passed. See the
[continuation report](../../../../../docs/validation/latent-memory-projection-phase1-multicontext.md)
and [complete results](results/2026-09-19/evaluation-001/analysis.json).

This isolated experiment warm-starts from the original Phase 1 patch and fits
the **same eight trigram rows** to three contexts: the original question, a
sentence completion previously tested in Phase 1, and one new chat prompt.
Those three contexts are training data here. Newly worded prompts form the
held-out set. No Aimee memory service is read or changed.

The chat template is extracted verbatim from the installed GGUF. Rendering uses
Jinja2 with `enable_thinking=False`; native tokenization parses special tokens.
The assistant-prefill condition appends the trigger after the rendered assistant
header. A distinct evaluation condition places `Memory handle: <trigger>` before
the question in the user message. **User-prefix placement is not trained by this
compiler**, whose derivative still enters at the final token. Its transfer is
tested explicitly rather than presumed.

`protocol.py` freezes separate training and evaluation files, complete native
token IDs, and an address audit. The optimizer reads only the training file.
`train_multi.py` takes the mean cross-entropy loss across all three contexts
before each Adam update. The existing frozen CPU replica is unchanged. Rows are
encoded and decoded through the native IQ4_NL implementation during each forward
pass, with a straight-through derivative to the float master rows. Prefix states
are reusable because the audited selected rows do not occur before the last
training token. Routing is recomputed on each forward.

Limits: 60 measured steps (at most 59 Adam updates), stop when all three training target probabilities reach 0.8,
40 minutes of measured compiler time, and a sampled 56 GiB process RSS high-water
guard. The RSS guard checks after an update, so it is not an allocation limit.
The selected output is the measured pre-update candidate at stopping; intermediate
checkpoints are not selected on held-out results. It uses the prior patch as a
warm start, ten times ENGRAFT's original learning rate, norm regularization 0.1,
eight CPU threads, and a 20 GiB decoded-weight cache cap.

These changes are combined in one exploratory attempt. The result does not
independently identify the contribution of warm start, multiple contexts, or
quantization-aware training.

## Run in CT 101

Sources reside at `/opt/aimee-ple-phase1/multicontext`. The parent contains the
original `train.py` adapters, pinned ENGRAFT package, dedicated venv, codec
library, and original `run-003/overlay.json`. See the parent README for those
dependencies. Use fresh output directories and run training and inference
sequentially.

```sh
g++ -std=c++17 -O2 -Wall -Wextra \
  -I/opt/llama.cpp/include -I/opt/llama.cpp/ggml/include \
  -I/opt/llama.cpp/vendor/nlohmann runner.cpp \
  -L/opt/llama.cpp/build/bin -lllama -lggml -lggml-base \
  -Wl,-rpath,/opt/llama.cpp/build/bin -o runner
g++ -std=c++17 -O2 -Wall -Wextra \
  -I/opt/llama.cpp/include -I/opt/llama.cpp/ggml/include \
  -I/opt/llama.cpp/vendor/nlohmann tokenize_json.cpp \
  -L/opt/llama.cpp/build/bin -lllama \
  -Wl,-rpath,/opt/llama.cpp/build/bin -o tokenize-json
../venv/bin/python protocol.py --template chat-template.jinja \
  --tokenizer ./tokenize-json \
  --model /opt/models/Qwen3.8-Flash-Next-UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf \
  --inspection /opt/aimee-ple-phase0/iq4-metadata-triggers.json \
  --hash-helper /opt/aimee-ple-phase0/probe_phase0.py --out frozen-reproduction
OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 ../venv/bin/python train_multi.py \
  --training frozen-reproduction/training.json \
  --inspection /opt/aimee-ple-phase0/iq4-metadata-triggers.json \
  --warm-start ../run-003/overlay.json --codec ../codec-validation.so \
  --model-dir /opt/models/Qwen3.8-Flash-Next-UD-IQ4_XS \
  --out run-reproduction
python3 evaluate.py --plan frozen-reproduction/evaluation.json \
  --inspection /opt/aimee-ple-phase0/iq4-metadata-triggers.json \
  --previous ../run-003/overlay.json --overlay run-reproduction/overlay.json \
  --runner ./runner --out evaluation-reproduction
python3 analyze.py evaluation-reproduction --plan frozen-reproduction/evaluation.json
```

The native runner preserves the previous private-page implementation and fresh
context/restoration checks. Its only changes are selectable special-token
parsing, a larger generation ceiling, and recording end-of-generation status.
Every native tokenization is checked against the frozen protocol. It is still
an internal-ABI research probe, never a concurrent serving backend.

## Scoring

There are 138 frozen trials: 23 cases times six conditions (no memory, compact
text, trigger without patch, original patch, new patch, removed patch).

- Three cases are fitted contexts; twelve are held-out positive contexts
  (four raw, four chat with assistant prefill, four chat with user prefix).
- Six negative cases test arithmetic, an unknown entity, and an unknown
  attribute in both chat placements. They are evaluation only.
- Two isolation cases test no trigger and a disjoint trigger. Their meaningful
  measure is equality with the corresponding unpatched prompt, not answer
  accuracy. The frozen general answer labels are not used to assess isolation.
- Raw completions have an eight-token ceiling and are next-token diagnostics.
- Chat answers have a 64-token ceiling. Strict correctness requires the expected
  normalized one-word answer and an end-of-generation token. Only stop markers,
  surrounding whitespace, and terminal punctuation are removed. An explanation,
  refusal, empty continuation, or unfinished answer is not an exact match.
- `amber` presence is recorded separately to expose contamination. It does not
  substitute for correct answering. The diagnostic target token is ` amber`;
  a correct chat response can instead start with the unspaced token `amber`.
- Full next-token distributions are saved for one fitted chat prompt and one
  held-out user-prefix prompt, each before patching, with patch, and after removal.

The literal trigger is neither a general address allocator nor an authorization
capability. IDs sharing its suffix still collide. This experiment does not
establish scope, supersession, multi-fact composition, or production forgetting.
