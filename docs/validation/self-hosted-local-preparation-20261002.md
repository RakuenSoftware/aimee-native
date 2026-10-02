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

The RX 7900 XTXs were occupied, so a separate RTX 5080 served Gemma4 12B
using the same locally prepared two-record bank. A no-memory control answered
that it needed the missing context. With native memory, the model answered
"The project codename is Halcyon, and the owner prefers blue notebooks."
Both requests reported 34 prompt tokens; the two facts were not inserted as
prompt text. The temporary CUDA server was stopped after the check. This is a
live consumer check using the established vLLM plugin path and the new bank;
it does not yet exercise the complete enrolled broker lifecycle from the final
wheel on a GPU.

An enrolled mTLS broker integration test did exercise the host lifecycle with
two selected records: it activated the initial bank, replaced it after Aimee
changed a record revision, and returned an error instead of a publication after
the server revoked access. The test used a fake compiler and control socket, so it checks the
authorization and replacement flow rather than GPU execution.

The next encoder revision accepts GGUF-only model directories on the inference
host. With a Gemma4 12B Q8 GGUF and no safetensors, it prepared a two-record
bank with 26 memory positions and 8,945,664 tensor bytes. The same GGUF served
on the RTX 5080: the no-memory control asked for the missing facts, while the
native request answered both facts correctly; each request used 34 prompt
tokens. For Qwen3.8 27B Q8, all 850 text-model tensors were mapped from the
GGUF and sampled restorations agreed with safetensors within expected
quantization error. The GGUF-only encoder then prepared a two-record Qwen
bank with 21 memory positions and 1,376,256 tensor bytes. A live Qwen GGUF
consumer check has not run in this revision because the available RTX 5080
cannot hold its 28 GB GGUF and both RX 7900 XTX GPUs are occupied by other
tests. The subsequent installed 0.2.3 candidate ran the complete path on the
RTX 5080: disposable enrolled Aimee thin client, mTLS primitive retrieval,
local GGUF-only preparation, publication, live vLLM consumption and authority
withdrawal. Gemma4 12B answered both selected facts correctly with 34 prompt
tokens, and a request after revocation returned HTTP 503. The first integrated
attempt exposed two packaging problems, both fixed before this passing check:
resolving the virtualenv Python symlink lost installed extensions, and the
clean serving environment lacked Accelerate. The candidate now preserves the
virtualenv path and declares `accelerate>=1.15,<2` and `gguf>=0.19,<0.20` as
dependencies. The final public asset still needs offline staging and an
external clean install from its published URL.
