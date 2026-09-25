# Fork-free vLLM distribution: path to a private preview

The runtime decision is settled: unmodified, version-pinned vLLM plus a private
extension and Rust memory runtime. No llama.cpp fork or vLLM fork is planned.
The existing Gemma BF16 integration has passed GPU and HTTP correctness checks.
This plan distinguishes working integration from a finished customer release.

## Target user experience

One platform installer or container, one Aimee connection configuration, and one
start command. The package owns the matched runtime, private extension, Rust
library, model profile and defaults. Users do not compile kernels, edit tensor
settings or patch their inference engine. The service presents the ordinary
OpenAI-compatible API. A trusted gateway selects approved publications; end users
should not need to choose internal publication IDs per request.

A GGUF alone cannot install an inference extension or connect its memory runtime.
The current demonstrated model is BF16 safetensors. Certify the first optimized
model artifact against this baseline; GGUF remains a format-validation task,
not the mechanism that activates native memory. Do not advertise support for
arbitrary GGUF-consuming programs without their own supported integration.

## Work order and acceptance criteria

1. **Device cache and backpressure.** Rust owns a per-rank native-bank byte budget,
   idle-bank LRU policy and active-request protection. The Python boundary owns
   GPU tensor allocation and follows Rust plans. Verify eviction/reload on Gemma,
   rejected oversubscription without silent memory loss, and partial-upload
   failure handling. Then add ingress reservation/backpressure so oversubscription
   rejects/queues a request before worker execution rather than stopping a worker.
   Include temporary allocation, pointer tables, model KV cache and allocator
   reservation in total-device sizing; bank payload accounting is not total VRAM.
2. **Authoritative publication integration.** Wire the existing scoped Aimee
   export/publication lifecycle into preparation and native catalog delivery.
   Bind recipient, model/quantization identity, all selected records and revisions.
   Test replacement, withdrawal, expiry, disconnected clients and denied requests.
   Add coordinated multiworker activation; a failed rank must not leave traffic
   running against mixed revisions. Follow Aimee's actual revocation policy.
   Deployment endpoint/host and authenticated feed contract remain inputs, not
   values to invent. The existing research fixture is not authority.
3. **Preparation reuse and synchronization.** Connect the existing Rust cache to
   the real preparation worker. Keep preparation, integrity checks and updates
   outside attention. Measure reuse for real selected working sets, changes to
   one record, offline access and misses that must go back to Aimee. Do not assume
   arbitrary independently prepared banks are composable without validation.
4. **Protected platform package.** Build the sensitive client implementation as
   compiled artifacts; keep encoding and preparation hosted/private. The current
   source-based Triton development plugin cannot be the shipped protected product.
   Pin a complete matching GPU-driver/runtime image, then audit installed contents,
   exported symbols, licenses, embedded source/debug paths and update rollback.
   Binary packaging increases reverse-engineering effort, not secrecy guarantees.
5. **Performance and model certification.** Compare native and same-record text
   paths with fixed work and quality. Separate preparation, cold storage,
   activation, GPU transfer, attention, first-token and decode latency; report
   cold/warm distributions and sustained concurrent load. Check context savings
   over long conversations, every selected record, eviction pressure and model
   quantization parity. No microsecond claim from a build or recall test.
6. **Signed preview distribution.** Provision release origin, signing authority
   and certified model catalog. Ship through the existing signed installer only
   after the real release gates pass. Validate fresh install, one-command startup,
   connection, upgrades and rollback on a clean supported machine.

## Current cache step

The policy is implemented in `src/device_cache.rs` and consumed through the
Torch-free Rust client ABI. Idle banks may be evicted; active-request revisions
remain pinned. Unchanged decoding batches do not invoke the planner. No file
verification or integrity scan is added to attention. The policy accounts for
bank tensor payload bytes per GPU rank; it does not call `empty_cache` or force
Torch's allocator to return reusable allocations to the driver.

An oversized active working set currently fails closed inside the worker.
Production ingress backpressure is still required for graceful admission. A
failed GPU upload poisons the cache and requires worker restart, so partial plans
cannot silently be served. Disk streaming/host residency remains a separate step:
the current catalog is still admitted into host RAM.
