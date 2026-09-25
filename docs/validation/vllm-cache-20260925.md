# Bounded native device cache — 2026-09-25

The fork-free vLLM integration now uses a Rust-owned device residency policy.
Budget and LRU decisions are in `src/device_cache.rs`; Python executes GPU
allocation/eviction and keeps tensor owners alive. No storage reads, hashes or
encoding are introduced in attention. The planner runs when request membership
changes, not on unchanged decode steps.

## Tests

- Four Rust tests pass: pinned-bank protection, idle LRU eviction, eviction/reload,
  overflow/revision/duplicate rejection and unchanged residency after rejection.
- Three ABI/ownership bridge tests pass: pointer-owner clearing before eviction,
  active-set overflow without eviction, and poisoned-cache handling after a failed
  upload. Four existing request identity/revision tests also pass.
- Real Gemma BF16 on both RX7900XTXs, TP2, unmodified vLLM0.30.0: alpha → beta →
  alpha, with budget9,551,872 bytes per rank. Banks require9,551,872 and9,191,424
  bytes per rank, so they cannot coexist under the configured budget.
- Responses:68731 →94268 →68731, all correct. Every request uses26 prompt tokens.
- Each rank records three uploads and two evictions. Peak resident native-bank
  payload is9,551,872 bytes, within budget throughout the observed transitions.
- Stripped Rust client export audit passes: seven allowed store/cache ABI exports,
  717,248-byte tested library. No preparation entry points.

Raw logs and JSON are in [artifacts](artifacts/vllm-cache-20260925/).
This extends the [initial integration validation](vllm-native-20260925.md).

## Practical limits

The budget measures native-bank tensor payload, not total VRAM. Model weights,
text KV, pointer tables, transient allocations and Torch allocator reservations
need separate headroom. Eviction releases bank ownership and invalidates pointer
tables; it does not force Torch to return reusable allocation blocks to the driver.

All active request revisions remain pinned, including preempted requests. If the
active set cannot fit, the worker fails closed; production admission/backpressure
must prevent that case before scheduling. A GPU allocation/upload failure poisons
the cache and requires worker restart; partial upload state cannot be served.

Host RAM still admits the current catalog. GPU-resident retired revisions are
included in host replacement budgeting, so their buffers are not falsely counted
as freed. This is not an on-demand disk streaming implementation or a latency
benchmark. The synthetic test establishes eviction/reload correctness, not
production throughput or long-running operational stability.
