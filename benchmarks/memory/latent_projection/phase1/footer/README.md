# Phase 1 counterexperiment: existing chat-footer activation

Recorded outcome: 0/4 correct held-out answers, versus 4/4 for compact text.
Removal and the three negative controls passed. See the
[continuation report](../../../../../docs/validation/latent-memory-projection-phase1-multicontext.md)
and [results and verification](results/2026-09-19/evaluation-001/analysis-verification.json).

This tests one synthetic fact without a literal memory trigger. It replaces
eight trigram rows read at the existing final token of the model's non-thinking
chat template. The no-memory and patched prompts have **identical token IDs**.
An isolated controller chooses whether to install the patch for each serial
trial; every trial has a fresh context and restores the original mappings.

This is natural template addressing with process-local row substitution. It is
**not a direct-row activation API**. Addresses are shared by all prompts with
this footer, and are not memory identities. Only one fact/patch is active here.
Multiple facts, multi-turn prompts, shared serving, and scope enforcement need
different work. The frozen audit rejects any selected-row hit before the final
token in these single-turn prompts.

The compiler is the unchanged `../multicontext/train_multi.py`, using its native
IQ4_NL straight-through objective. Here it starts from **original table rows**,
uses one actual chat training question, and targets the unspaced native token
`amber` (14778). The previous attempt targeted ` amber` after an artificial
assistant prefix. This counterexperiment changes initialization, addresses,
training contexts, and target-token form; it is not a causal ablation isolating
only trigger removal.

Four newly worded chat questions are held out. Three negative cases test
arithmetic, another entity, and another attribute. Four conditions per case
(none, compact text, patch, removed) produce 32 final trials. The 16 preliminary
controls omit patch and removed. All answers use the same strict complete-answer
scoring as the multi-context experiment, with a 64-token ceiling.

The initial run has 60 measured steps, a 0.95 training threshold, and the same
resource guards as the previous attempt. `continuation-policy.json` permits at
most one additional training-only run if the initial run hits its step limit
with probability in [0.05, 0.95). That policy was saved before any footer training
step result was inspected. A continuation starts from the last rows with fresh
Adam state and unchanged settings. No trained native result or held-out score
selects or extends a run. These are exploratory, small-sample comparisons.

## Reproduce in CT 101

The workspace is `/opt/aimee-ple-phase1/footer`. It reuses the parent venv and
codec, and the compiled runner, tokenizer, template, and compiler in the sibling
`multicontext` directory. Preserve the pinned parent dependencies.

```sh
../venv/bin/python protocol.py \
  --template ../multicontext/chat-template.jinja \
  --inspection /opt/aimee-ple-phase0/iq4-metadata-triggers.json \
  --hash-helper /opt/aimee-ple-phase0/probe_phase0.py \
  --tokenizer ../multicontext/tokenize-json \
  --model /opt/models/Qwen3.8-Flash-Next-UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf \
  --out frozen-reproduction
OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 ../venv/bin/python ../multicontext/train_multi.py \
  --training frozen-reproduction/training.json \
  --inspection /opt/aimee-ple-phase0/iq4-metadata-triggers.json \
  --warm-start frozen-reproduction/cold-rows.json --codec ../codec-validation.so \
  --model-dir /opt/models/Qwen3.8-Flash-Next-UD-IQ4_XS --out run-reproduction
```

Apply the recorded continuation policy using only that run's `result.json`
before native evaluation. If continuing, pass its `overlay.json` as `--warm-start`
to one new run, using the same frozen training input and a fresh output directory.
`configuration.json` records the actual initialization hash; the training input's
`warm_start` description names the initial stage. Use the last permitted run's
path in place of `run-reproduction` below. The verifier accepts the initial or
the explicitly supplied continuation initialization hash.

```sh
python3 evaluate.py --plan frozen-reproduction/evaluation.json \
  --inspection /opt/aimee-ple-phase0/iq4-metadata-triggers.json \
  --overlay run-reproduction/overlay.json --runner ../multicontext/runner \
  --out evaluation-reproduction
../venv/bin/python analyze_verify.py --run run-reproduction \
  --evaluation evaluation-reproduction --frozen frozen-reproduction \
  --inspection /opt/aimee-ple-phase0/iq4-metadata-triggers.json \
  --codec ../codec-validation.so \
  --hash-helper /opt/aimee-ple-phase0/probe_phase0.py
```

For a continuation, also pass `--initialization path/to/preceding/overlay.json`
to the verifier. The compiled 720-byte payload and original selected disk rows
are checked independently, as are full-logit removal equality and zero added
latent prompt tokens. Model files and the installed runtime stay unchanged.
