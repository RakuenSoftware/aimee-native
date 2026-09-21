# Phase 1: one synthetic fact

Recorded outcome: **reversible training-prompt injection works; held-out useful
recall is not established**. See the
[Phase 1 report](../../../../docs/validation/latent-memory-projection-phase1.md)
and [native results](results/2026-09-19/evaluation-003/analysis.json).

The [continuation report](../../../../docs/validation/latent-memory-projection-phase1-multicontext.md)
adds [multi-context training](multicontext/README.md) and an
[existing-footer counterexperiment](footer/README.md). Both preserve measured
reversion but fail the new held-out chat tasks within their recorded bounds.

Experimental, isolated process only. No DB1/DB2 reads or writes, production
runtime patch, or production recall path. The synthetic fact is:

> Synthetic project Velnor's beacon color is amber.

`train.py` optimizes eight trigram rows using the
[ENGRAFT compiler](https://github.com/fulvian/engraft-ngram/tree/6c32ee87ad5ba652666e17895a3f1a5479ac3380)
at commit `6c32ee87ad5ba652666e17895a3f1a5479ac3380`. The external code is Apache-2.0;
it is an explicit dependency, not vendored here. The adaptations read the
existing flat GGUF table and use native llama.cpp dequantization. No GGUF
conversion or extra copy of the model is required.

`runner.cpp` links against the installed llama.cpp library, obtains the PLE
tensor through its **internal** tensor-map function, and applies private
copy-on-write row mappings between serial trials. It quantizes float candidate
rows to the existing IQ4_NL type using `ggml_quantize_chunk`. Every trial gets a
new llama context; it is destroyed before all modified pages are restored and
the next trial starts. No network listener or request concurrency exists.

This internal ABI is pinned to llama.cpp
`972d2313bc0bf0a45f634f77d95c9fb03aeab12c`. It is a probe, not a portable projection
backend. The trigger is only checked against this test set; numeric IDs with the
same suffix can collide. Do not treat it as a general allocator or authorization
mechanism.

## Build and run

The existing workspace is `/opt/aimee-ple-phase1` inside CT 101 on `.253`.
The following commands run there, with these sources copied in and the pinned
external repository's `engraft/` package on `PYTHONPATH` (the recorded workspace
contains an unmodified copy of that package). Create a dedicated Python venv
with CPU PyTorch, NumPy, gguf, SciPy, and tokenizers. See the recorded package
freeze for exact versions.

```sh
g++ -std=c++17 -O2 -Wall -Wextra \
  -I/opt/llama.cpp/include -I/opt/llama.cpp/ggml/include \
  -I/opt/llama.cpp/vendor/nlohmann runner.cpp \
  -L/opt/llama.cpp/build/bin -lllama -lggml -lggml-base \
  -Wl,-rpath,/opt/llama.cpp/build/bin -o runner
g++ -std=c++17 -O2 -shared -fPIC -I/opt/llama.cpp/ggml/include codec.cpp \
  -L/opt/llama.cpp/build/bin -lggml-base \
  -Wl,-rpath,/opt/llama.cpp/build/bin -o codec.so
OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 venv/bin/python train.py \
  --codec ./codec.so \
  --inspection /opt/aimee-ple-phase0/iq4-metadata-triggers.json \
  --model-dir /opt/models/Qwen3.8-Flash-Next-UD-IQ4_XS \
  --tokenizer /opt/aimee-ple-phase0/tokenize \
  --out run-reproduction --steps 100 --lr-multiplier 10
python3 evaluate.py --plan plan-v2.json --extra-plan diagnostics.json --runner ./runner \
  --model /opt/models/Qwen3.8-Flash-Next-UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf \
  --inspection /opt/aimee-ple-phase0/iq4-metadata-triggers.json \
  --overlay run-reproduction/overlay.json --out evaluation-reproduction
python3 analyze.py evaluation-reproduction
```

Run compiler and native evaluation sequentially. Do not replace a loaded codec
shared library in place while training. Fresh output directories prevent mixing
runs. The memory cache is capped at 20 GiB, but total process memory also includes
mapped weights, live autograd tensors, and model state; it is larger than that
cache cap.

## Protocol and interpretation

- `plan.json` preserves the initial protocol. Its raw question prompts frequently
  produce a reasoning preamble, so a four-token continuation is not an answer
  accuracy metric.
- `plan-v2.json` adds three held-out sentence-completion prompts. It was frozen
  before any trained overlay evaluation. All 44 trials are retained; the
  addition was motivated by the initial no-overlay controls, not latent results.
- Conditions: no memory, compact text, trigger without patch, trigger with patch,
  and removed patch. Two additional pairs test an unrelated prompt and an
  alternate trigger whose rows are disjoint from the selected trigram rows.
- `diagnostics.json` adds six separately frozen trials: arithmetic, another
  entity, and a trigger preceding the question. Here `amber` probability measures
  contamination for the first two pairs; it is not an accuracy score. Their
  `correct_first_token` fields are null. All prompts were frozen before native
  overlay evaluation.
- Each trial records target-token probability/rank, four greedy generated tokens,
  prompt token IDs, prefill timing, fresh-context status, and restoration status.
  Full training-prompt logits are saved for trigger-only, latent, and removed
  conditions so restoration can be checked beyond one answer token.
- Training uses float rows and a CPU replica. Evaluation requantizes the eight
  changed rows to IQ4_NL in the real Vulkan/CPU runtime and records quantization
  error. A high compiler probability is not a native-engine success criterion.
- The compiler's reported base learning rate must be multiplied by
  `compiler-config.json`'s `lr_multiplier`; the optimizer wrapper applies that
  multiplier. No held-out prompt participates in optimization or checkpoint
  selection.
- The active payload is eight rows of 90 bytes, or 720 bytes; the float JSON
  compiler artifact is larger. This does not include model memory, trigger
  tokens, provenance, or compilation cost.
- This probe establishes neither general chat recall nor production forgetting,
  shared-worker scope isolation, capacity, latency improvement, or a reusable
  projection ABI. The report must distinguish these from the measurements.

The results directory preserves aborted setup/search attempts as well as the
completed attempt. An interrupted attempt is not a measured compiler failure.
