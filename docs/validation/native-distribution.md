# Native distribution implementation checkpoint

2026-09-25. Implementation remains private in aimee-qwen. No customer release,
service deployment, new Qwen run or new model-quality result was produced.
This checkpoint includes the previously uncommitted prepared-native runtime on
which the new client build depends; it preserves its historical research paths.

## What changed

The standalone Rust launcher installs explicitly listed, signed client artifacts,
configures a scoped Aimee credential without exposing it in command arguments,
launches the intended certified runtime and supports rollback. Seven tests cover
signature rejection, content corruption, package boundaries, private credentials,
release sequencing, rollback and interrupted pointer publication recovery.
The real Aimee authentication/feed and release origin remain unconfigured.

A client-only feature removes offline preparation entry points from the shared
library, simplifies client errors and removes research timing metadata. Final
artifact inspection requires exactly nine dynamic exports and rejects debug
sections, private preparation symbols and source/build-machine paths. C++ path
remapping and dependency-symbol visibility were needed as well as Rust stripping.
This demonstrates those release controls, not resistance to a skilled analyst.

A private preparation cache keys on the complete ordered selection, all record
revisions, recipient/view, model, runtime profile, encoder and positional policy.
It coalesces concurrent requests and atomically publishes successful compiler
outputs. Five tests pass. It is a worker primitive, not yet a hosted service or
proof of record-wise composition for unseen selections.

A Torch-free prepared-store reader now shares the exact format declarations
with the existing compiler. It admits owned data off the serving path and then
provides immutable views without file access or hashing. A cross-path test checks
every byte of compiler-produced BF16 K/V for heterogeneous local/global layers.
This removes Torch from storage consumption, not yet from GPU/graph integration.

The pinned llama.cpp revision `e85e15cf6d810cd1268498c2e5b657bb3ece47bc`
builds with a generic in-process attention callback. The private provider loader
has version/lifetime and activation-failure checks; its interface fixture tests
pass. No encoding algorithm is added to the runtime patch. The first hook is
single-sequence, excludes compressed-attention-specific paths, and disables graph
reuse when active to avoid retaining a stale memory selection. Those restrictions
must be addressed and measured before a production-performance claim.

## Validation

- Full existing/new Rust library suite with Torch: **34 passed**.
- Torch-free library suite: **18 passed** (overlaps the full suite).
- Launcher: **7 passed**, plus Clippy with warnings denied.
- Release package assembler: **2 passed** using temporary test-only signing keys.
- Provider interface checks: load, isolated handles, activation rejection and
  unavailable-library failure passed. This is not an attention-quality test.
- Patched llama.cpp CPU library: CMake build passed.
- Client-only release: exact export allowlist, stripped-symbol and path audit passed.

The controlled build ran in CT101 on `.253`, using the existing Rust 1.98.1 and
Torch/ROCm toolchain; ordinary tests do not establish GPU serving performance.
The successful client audit is recorded with the binary's digest. Build/test logs
are under [artifacts/native-distribution-20260925](artifacts/native-distribution-20260925/).
No latency values or accuracy claims are inferred from compilation or these tests.

## Remaining release gates

The working DLPack library is not yet a ggml provider. Finish the device/graph
bridge, llama-server configuration and lifetime wiring, and integrate hosted
preparation with Aimee's actual authorized publication feed. The endpoint/hosting
choice is still pending owner input. Then run the Gemma GGUF parity, all-record
coverage, long-conversation, revision/isolation, cold/warm and clean-install gates.
The release assembler intentionally cannot sign a production package without
those private passing gate reports. Browser sign-in, platform installers,
hardware-specific model/runtime selection and automatic background updates also
remain work; the current launcher is a tested Linux control-plane foundation.
