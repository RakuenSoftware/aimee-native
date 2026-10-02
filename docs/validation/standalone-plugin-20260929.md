# Standalone vLLM plugin — 29 September

**The deliverable is the Aimee plugin plus an Aimee connection.** Version 0.1.1
is available on the controlled release origin. It installs into an existing
supported vLLM environment; it does not distribute or launch the ROCm/vLLM
runtime image. No vLLM fork, source patch, model download, Rust toolchain, or
manual native-library/kernel installation is required by the client.

The [installation guide](../../distribution/vllm/STANDALONE.md) documents the
supported Python 3.12 / ROCm 7.2.3 / two-RX-7900-XTX profile. This is not a claim
of compatibility with arbitrary vLLM versions or NVIDIA builds.

The subsequent [full coding-workflow comparison](standalone-coding-20260929.md)
tests the installed wheel on repository repair tasks against no-memory and
text-memory conditions, with fresh native repeats and separate official grading.

## Artifact and delivery

- Wheel: `aimee_vllm-0.1.1-1-cp312-cp312-linux_x86_64.whl`, **3,143,773 bytes**.
- SHA-256: `935ad0fd307883bba31338686cc57df63e5f2f4afacff34a8b2c9fcd80cf85b3`.
- [Download](https://192.168.0.126:8445/plugins/rocm723-gfx1100/0.1.1/aimee_vllm-0.1.1-1-cp312-cp312-linux_x86_64.whl).
- [Manifest](https://192.168.0.126:8445/plugins/rocm723-gfx1100/0.1.1/manifest.json).

Both wheel and manifest have detached Ed25519 signatures using the existing
release identity. Full TLS downloads and signature checks passed. The optional
GGUF dependency also passed full size/hash verification. These are private
origin downloads, not a PyPI publication.

The wheel contains compiled integration modules, the Rust consumer and
connection executable, seven matched attention kernel profiles, notices, and
two small public registration/bootstrap Python modules. It contains no private
encoder/preparation source, model weights, operating system, or runtime image.
The separate 2,058,566-byte GGUF loader dependency uses the `0.0.5+rocm723` build
identifier. Its 132 non-metadata assets are unchanged from the previously tested
upstream ROCm wheel; only package metadata identifies the build flavor. The
extra pins its URL and SHA-256. This prevents pip treating a same-version CUDA
wheel as the required ROCm build. Version 0.1.1 also upgrades earlier 0.1.0
Aimee development wheels instead of silently leaving their contents installed.

## Live validation

Tests installed the wheel into the upstream vLLM environment, rather than using
the image with Aimee already installed. The isolated test environments were
containers for laboratory management only. The installed command does not
invoke a container manager; the inspected serving environment had no Podman
executable. Existing model files were mounted as test inputs, not installed by
the plugin. The upstream vLLM attention backend files matched the original image.

| Model | Live native-memory queries | Prompt tokens per query |
|---|---:|---:|
| Gemma4 12B | 2/2 passed on final 0.1.1 wheel | 27 |
| Gemma4 26B | 2/2 passed | 27 |
| Qwen3.8 27B | 2/2 passed | 26 |

Each query required the same three authorized canary facts. These are repeated
integration checks, not independent task samples or a new knowledge benchmark.
The request text contained the question, not the memory facts. Earlier task and
recall studies retain their original scopes and results.

Gemma26/Qwen used the preceding packaging revision. A byte-for-byte comparison
binds every plugin code, native library, and kernel asset from those runs to the
published wheel. The subsequent differences are distribution version and
GGUF dependency metadata. Gemma12 additionally passed after installing the
final version and retagged, code-identical ROCm dependency.

Additional checks:

- Fresh authenticated `connect` passed for every model run. Model configuration
  hashes remain bound to the Aimee-authorized native model.
- Deliberately pairing a Qwen native profile with the Gemma configuration failed
  before inference with `installed model configuration mismatch`.
- Interrupting a 512-token stream triggered restart of the owned standalone
  model process (PID 456 to 806). The next query returned all three facts;
  measured recovery through the successful answer was 81.443 seconds.
- The serial Rust suite passed 18 unit tests and both integration tests. Two
  Python CLI tests passed. Wheel metadata, every RECORD digest, executable
  permissions, source exclusions and kernel membership passed inspection.
- Test coordinators completed and restored/retained the normal compiler service.

The [evidence archive](artifacts/standalone-plugin-20260929/) contains raw reports,
compressed logs, package/delivery audits, and checksums. Initial failures are
retained: a host-built executable required newer glibc, the first optional-extra
metadata was malformed, and unqualified dependency selection chose a CUDA wheel.
The executable was rebuilt in the supported environment and dependency metadata
corrected. An initial parallel Rust run hit a process-lock test failure; the
process/lifecycle suite passed when serialized. Upstream JIT candidate rejection
and shutdown diagnostics remain visible in the successful model logs.

## Kernel reuse

vLLM continues to execute the model, ordinary attention without a native bank,
and text-cache updates. Its tested Triton attention interface consumes one paged
K/V cache; it does not accept the separate native-bank pointer table used here.
Its FlashAttention cascade helper rejects sliding windows. Therefore neither is
a drop-in replacement for this Gemma-compatible native-memory path. The plugin's
small kernel combines native and text attention under a shared normalization
while preserving visibility and independent text positions.

Further upstream-kernel reuse is possible work on the integration/layout, not a
reason to fork vLLM or distribute its runtime. The current kernels are internal
wheel assets. This release preserves the tested memory mechanism rather than
substituting text injection or changing its attention semantics.

## Release recommendation

Use the standalone plugin for the documented controlled preview. Keep the
pinned ABI/hardware profile and existing evidence limits explicit. Cold-memory
microseconds remain aspirational, not a release blocker. The old Broadcom
redistribution question belonged to the abandoned whole-runtime distribution
boundary and does not gate this plugin artifact. No broader autonomous coding
or model-weight reasoning improvement is inferred from these installation tests.
