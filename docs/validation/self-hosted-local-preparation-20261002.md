# Self-hosted local preparation check, 2 October 2026

The current private `feature/native-distribution` branch changes `aimee-native
serve` to reuse standard Aimee thin-client enrollment. The server returns a
versioned, model-neutral selection through `/v1/native/primitive`; the inference
host compiles all selected records with its local model weights, writes the
native bank with the portable Rust writer, and rechecks selection before
activation. The server never downloads the model.

The source-row protocol passed an mTLS test using an enrolled client
certificate and bearer token. The Rust launcher suite passed 23 library and 3
CLI tests, including a two-record local bank, cache reuse, rejection when a
source revision changes, and cache identity changing when checkpoint bytes
change. The portable writer reproduced the previous Gemma4
12B BF16 bank exactly: 26 memory positions, 8,945,664 tensor bytes and the
same dictionary digest. The installed consumer opened that bank and activated
96 segments on an RX 7900 XTX. Python 3.12 compiled encoder extensions build
and import in the installed vLLM runtime. A 0.2.3 test wheel assembled, passed
the wheel audit, and installed in a separate environment inside that runtime.

The first test wheel caught a real build-host mistake: its launcher required
glibc 2.39 and would not start in the supported Ubuntu runtime. The launcher
was rebuilt against glibc 2.34, then installed successfully. Wheel assembly
now rejects any bundled ELF requiring a newer glibc version. After the latest
launcher change, the wheel was rebuilt and audited with SHA-256
`a9000ade44a52e408635caa7224fb1b299a0f4f9644a2afe08ecc8660a4a213f`.
This is a local candidate, not a published release asset.

The full vLLM answer check remains pending because another active process is
using most of one RX 7900 XTX. Initial local encoding also currently requires
Hugging Face safetensors on the inference host even when the serving path uses
GGUF weights. GGUF-only initial encoding is not yet validated. These are
release gates; passing local bank activation alone does not establish live
answer correctness for the final wheel.
