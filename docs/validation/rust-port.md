# Rust port validation — 2026-09-20

The Qwen/Aimee connection runs in Rust on the real 27B checkpoint with native
libtorch/ROCm. The Rust adapter and gateway require no Python interpreter. The
adapter remains untrained; Aimee supplies and authorizes the memories.

## Live 27B results

On 192.168.1.253, two 7900 XTX GPUs, frozen per-row INT8 weights, the same
74-token conversation prompt was used for all successful composition/control
runs. The authorized research records were existing Aimee IDs 5 and 6. The
image contained **no approved local read contracts**, so each memory lookup
fell back to the actual remote Aimee through the Rust credential gateway.
No production memories were created or modified.

| Case | Result | HTTP | Observed elapsed |
|---|---|---:|---:|
| Memory disabled | `unknown` | 200 | 2.269 s |
| Native, cold encoding | `oolong;Lima` | 200 | 4.804 s |
| Native, reused encoding | `oolong;Lima` | 200 | 4.330 s |
| Native attention recall, preload disabled | `oolong;Lima` | 200 | 4.126 s |
| Unauthorized record | Rejected | 502 | 0.213 s |
| Authorized read after denial | `oolong;Lima` | 200 | 4.253 s |
| Request attempts scope expansion | Rejected | 400 | 0.002 s |
| Revocation with cached native states | Rejected | 502 | 0.003 s |

**8/8 checks passed.** These are individual port-validation observations, not a
latency benchmark or a speedup claim. Native outputs have five generated tokens;
the no-memory control has one. Do not compare those elapsed values as equivalent
work. The attention-only run reused a previously encoded bank after retrieving
its matching authorized content; it did not preload memory from the user prompt.

All successful runs have zero memory facts/tokens inserted into the main prompt.
Cold native encoding performs one separate model pass; reuse performs zero.
Native runs perform 96 full-attention memory reads across prefill and decode.
Main cache length is 79 (74 prompt + 5 answer tokens before EOS), excluding the
separate memory bank. The attention-only trace records six model-attention
requests and no prompt-preload request. Every returned memory is ID 5 or 6.

The model and gateway run under separate OS identities. The model cannot access
upstream credentials or fixture signing keys. Process maps show no `libpython`
or `libtorch_python`. The shared native libraries happen to reside inside the
existing Torch installation; that filesystem location is not an interpreter
dependency. The test driver and numerical reference still use Python offline.

[Raw live responses and traces](artifacts/rust-port-2026-09-20/live/results.json),
[trace checks](artifacts/rust-port-2026-09-20/live/trace-checks.json), and
[runtime audit](artifacts/rust-port-2026-09-20/live/runtime-audit.json) retain the
measured evidence, binary hash, size, and library maps.

## Numerical parity and enforcement

The actual Transformers Qwen text model generates deterministic tiny-model
references; the Rust process independently reads the same safetensors and runs
baseline, native-prefill, and cached-decode passes. The adapter's memory bank
is preserved separately from the main cache.

- Six configurations: FP32, BF16, INT8/BF16, each with 4 and 65 prompt tokens.
  The longer input crosses the 64-token gated-delta chunk boundary.
- All 18 logit comparisons pass their declared tolerances: 2e-5 FP32 and
  0.005 BF16 (absolute and relative).
- Largest FP32 absolute difference: 1.49e-7. Largest BF16/INT8 difference:
  0.00390625. BF16 results are numerically close, not bit-identical.
- Every main-cache length equals prompt length plus one decode token.
- Six existing authorization transition cases pass with both the gateway and
  local-first client replaced by Rust: local revocation, local narrowing,
  expiration, remote revocation, revocation during upstream lookup, and atomic
  rejection/recovery after a mixed unauthorized response.
- Rust unit tests and Clippy pass. The full Torch build is included in Clippy.

[Numerical results](artifacts/rust-port-2026-09-20/numerical-parity.json) and
[authorization tests](artifacts/rust-port-2026-09-20/authorization-tests.txt)
provide the raw checks. `scripts/validate_rust_parity.py` reproduces numerical
comparisons without training or live-memory mutation.

## Scope and remaining work

This proves preservation of the established connection in Rust for the tested
checkpoint and research grant. It does not establish broad Qwen-family support,
production authorization issuance, full Aimee response-codec coverage, batching,
optimized kernels, or production deployment readiness.

The checkpoint config identifies its text architecture as `qwen3_5_text`; the
port validates that architecture and the installed chat-template hash instead
of inferring compatibility from the product/model label.

The first GPU launch failed because the ROCm kernel-registration library was
not retained by torch-sys linking. `build.rs` now explicitly retains
`libtorch_hip`. tch 0.26 also needs the documented, build-only compatibility
header for this host's Torch 2.14. Those are native build dependencies, not
Python bridges.

Release enables optimization level 3, fat LTO, one codegen unit, and stripped
symbols. The final live-tested executable is 7,720,640 bytes, dynamically linked.
Opaque tables, selective obfuscation, packaging of native libraries, and broader
runtime compatibility remain unfinished. The retained Python implementation
is a regression reference, not the active Rust serving path.

See [build and run instructions](../rust-runtime.md). No public adapter C ABI
or trainable adapter was introduced. Aimee's Go image reader remains external
and authoritative for image enforcement; this port does not copy its policy.

The final release was rebuilt after correcting the HTTP token-limit finish
reason and repeated the same eight live checks successfully. Its [final
responses](artifacts/rust-port-2026-09-20/live-final/results.json) and
[binary audit](artifacts/rust-port-2026-09-20/live-final/runtime-audit.json)
identify the shipped local artifact, `.local/bin/aimee-qwen`, also retained at
`/opt/aimee-qwen-rust/target/release/aimee-qwen` on the research host.
All six authorization tests and 18 numerical comparisons also passed against
that final release. The temporary model/gateway services were stopped and the
research grant was left revoked after validation.
