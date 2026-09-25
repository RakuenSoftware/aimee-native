# Closed-source Qwen memory adapter

State: long-term distribution requirement accepted; implementation approach
proposed. The user considers the initial native-memory POC sufficient and wants
the adapter distributed as a closed-source binary that is extremely difficult
to reverse engineer. This document does not claim that the current Python POC
provides that protection.

## Product boundary

Distribute the proprietary implementation as a compiled native library loaded
inside the inference runtime, with a narrow, versioned interface. A minimal
binding may connect the host runtime to that interface. Rust is now the preferred
implementation language, following the user's refinement; supported runtime
versions and the exact tensor bridge remain engineering decisions.

```text
Qwen forward pass / attention
              ↕
    narrow runtime binding
              ↕
 proprietary native adapter
              ↕
 authorized Aimee / local KB
```

The library remains in the native forward-pass path. Binary distribution does
not turn native memory into a chat-template feature, tool call, or per-token
out-of-process tensor transport. A separate read gateway can retain its existing
credential-isolation role.

Keep request translation, Qwen-specific state conversion, memory-bank management,
and native injection inside the proprietary implementation where feasible. The
binding should express tensor ownership, shape, dtype, device, execution stream,
session lifetime and compatibility rather than reimplementing those internals.
A C-compatible ABI is the initial candidate; opaque handles avoid exposing C++
or Rust implementation types. Host callbacks required for frozen model execution
must also be bounded and versioned. Those calls and tensors remain observable
to someone controlling the host runtime.

The adapter stays untrained and read-only. Aimee still owns learning, retrieval
selection, authoritative knowledge, governance, authorization and publication.
Closing the source does not move any of those responsibilities into the adapter.

## What protection can mean

Assume a determined customer-side analyst can inspect files, instrument the
runtime and examine CPU/GPU memory. The attainable objective is to increase the
time, expertise and cost needed to understand or reproduce the proprietary
implementation. Do not promise that a locally executing binary is unrecoverable.
OWASP describes obfuscation and anti-tampering as additional resistance and
explicitly notes that sufficient time and budget can defeat them.
[OWASP resilience](https://mas.owasp.org/MASVS/11-MASVS-RESILIENCE/),
[obfuscation limits](https://mas.owasp.org/MASTG/knowledge/generic/MASVS-RESILIENCE/MASTG-KNOW-0111/).

Protecting source implementation, preventing unauthorized KB access, and
preventing an independent implementation are different objectives. An analyst
may reproduce observable behavior without recovering our source. Authorized
knowledge and tensors delivered to an owner-controlled host cannot be kept
secret from that host merely by hiding the adapter implementation.

## Proposed release protections

1. Port the proprietary runtime path to Rust, with a small native interoperability
   shim where the inference runtime requires one. Packaging Python into an
   executable is not the intended final
   protection boundary. Native compilation alone is insufficient.
2. Export only the public ABI. Use release optimization, appropriate link-time
   optimization and hidden internal visibility; remove debug information and
   unnecessary development metadata from distributed artifacts. Retain private
   symbols internally for support. These reduce incidental disclosure, not
   observability of executing code. See
   [Clang visibility](https://clang.llvm.org/docs/LTOVisibility.html).
3. Evaluate selective obfuscation of proprietary transformations and control
   flow. Measure its effectiveness and its costs before adopting it. Avoid
   distorting tensor kernels or adding per-token protection overhead without
   evidence. No obfuscator vendor or transformation pipeline is selected yet.
4. Sign release artifacts and manifests; verify them in the controlled install
   and update path. Keep signing keys outside the distributed product. Signing
   establishes origin/integrity for a trusting verifier; it does not conceal
   code or prevent a host owner from patching their own runtime.
5. Produce separate internal diagnostics and customer release artifacts. Do not
   ship research scripts, internal traces, private symbols, source maps or
   fixture signing tools as part of the commercial binary package. Authorized
   support diagnostics should remain possible.

Anti-debugging or runtime integrity checks are optional, measured additions.
They can interfere with profiling, ROCm/CUDA tooling and support, and are not
allowed to become the authorization boundary. Binary encryption that decrypts
on an owner-controlled machine is likewise not a confidentiality guarantee.

## Preferred Rust release design

Build a Rust `cdylib` with a small C-compatible ABI and opaque session/bank
handles. Keep Qwen request translation, state conversion orchestration and bank
management in Rust. Use an explicitly supported runtime/tensor bridge for model
execution and device operations; do not rewrite the entire inference engine or
assume LTO can optimize through prebuilt runtime libraries.

Starting release profile for evaluation:

```toml
[profile.release]
opt-level = 3
lto = "fat"
codegen-units = 1
strip = "symbols"
debug = 0
incremental = false
```

These are optimization and packaging controls, not an obfuscation system.
Benchmark fat LTO against ThinLTO rather than assuming the more expensive link
always produces faster serving. Preserve the small required dynamic export set;
stripping is not a replacement for an export allowlist. Inspect the final
library's symbols, strings and metadata. Remap source paths where appropriate
and avoid detailed proprietary panic messages in the release artifact.
[Cargo profile semantics](https://doc.rust-lang.org/cargo/reference/profiles.html).

Keep matched symbol/debug artifacts privately through a release pipeline that
captures them before final stripping. The `debug = 0` profile above alone cannot
produce full private debugging information; that pipeline must deliberately
generate and separate it when needed. Production ABI errors use explicit status
codes. Decide the panic policy separately: `panic = "abort"` terminates the host
process, which matters for a library inside an inference server. With an unwind
strategy, contain Rust panics at the ABI boundary and retire affected state;
do not allow unwinding through an ordinary C boundary. Foreign runtime
exceptions also need containment in their owning shim.
[Rust FFI boundaries](https://doc.rust-lang.org/nomicon/ffi.html).

Represent proprietary static mappings/layout data as versioned binary tables
without descriptive internal names. Validate sizes, offsets, compatibility and
integrity before use. Opaque encoding impedes casual inspection; it does not
make tables cryptographic secrets. The runtime necessarily exposes usable
values during execution. These tables describe model-specific transformation
data, not a second knowledge or authorization policy engine. Mutable knowledge
and learned state remain Aimee-owned.

Apply obfuscation only to a short, explicitly reviewed list of routines whose
implementation warrants protection. Keep ordinary transport, authorization
enforcement, tensor ownership and numerical kernels straightforward to audit.
Evaluate each protected routine against an ordinary optimized build for output
parity, resistance and cost. Optimization can change or remove transformations,
so inspect the final LTO-linked, stripped artifact; source-level obfuscation
alone does not establish what protection survived compilation.

Maintain an ordinary optimized reference build and a protected release build.
Run the same native-memory and authorization regression suite against both.
Protection must preserve the accepted POC semantics and must not introduce
adapter training, adapter-owned memory selection or hidden update behavior.

## Authorization remains independent

Aimee must authorize KB materialization and remote results independently of the
adapter's claimed identity or integrity. Preserve authorization-specific images,
scope-limited credentials, signed publications, denial propagation and cache
partitioning. A patched adapter must not acquire broader authority merely by
removing a local check. Production policy issuance and revocation propagation
remain the dependencies recorded in the authorization reports.

Never embed authority signing keys or organization-wide access credentials in
the proprietary binary. Knowledge export must be restricted before the model
process receives it, whether its adapter is open or closed source.

## Evidence required before calling it hard to reverse engineer

First establish native-library parity with the accepted POC: native requests,
preload, multiple returned memories, composition, disabled-path behavior,
authorization denial and update/cache behavior. Use the current tests as the
reference; no adapter retraining is part of this port.

Then evaluate an ordinary release binary and a protected release under the same
defined analyst time budget. Include binary inspection, runtime tracing, ABI
interception, recovery of a selected proprietary transformation and attempts to
build a compatible substitute. Record recovered information and effort, as well
as functional parity, latency, throughput, binary size and supportability.

The commercial acceptance threshold requires a concrete adversary and budget;
no numerical resistance claim is established today. A compiler flag or successful
symbol stripping is not an adequate result. Independently review the exact
release artifact rather than relying on obfuscator marketing.

## Current state

`RakuenSoftware/aimee-qwen` was verified PRIVATE on 2026-09-20. The private repo
retains the POC, test fixtures and historical evidence. No repository visibility,
license or release publication was changed by this design update.

The subsequent [Rust implementation](../../rust-runtime.md) now preserves the
native connection with an optimized, LTO-linked, stripped executable.
[Live validation](../../validation/rust-port.md) covers real Qwen composition,
preload, attention-initiated recall and authorization enforcement. Selective
obfuscation, opaque tables and a reverse-engineering resistance evaluation remain
future work. Public interfaces and documentation can be scoped separately when
the distribution contract is settled.

## Distribution implementation checkpoint (2026-09-25)

The [private distribution implementation](../../../distribution/README.md) now
includes a signed Rust launcher, client-only library build and binary audit,
preparation-cache primitive, Torch-free store reader, and pinned llama.cpp hook.
[Validation and remaining gates](../../validation/native-distribution.md) distinguish
working components from the unfinished ggml provider, hosted preparation feed
and end-to-end release validation. No public or production release has occurred.
