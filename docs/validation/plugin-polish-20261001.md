# Plugin polish in progress — 1 October 2026

This record distinguishes implemented source changes from the already published
0.2.1 wheel. The signed 0.2.1 artifact is unchanged.

## Completed in source

- The standalone guide now installs 0.2.1 and explains that its authorized
  empty-selection response requires a matching hosted service.
- Aimee's admission middleware can replace caller-supplied `cache_salt` with a
  trusted vLLM prefix-cache namespace derived from recipient, complete
  catalogue digest and publication. Cached text K/V depends on native memory
  in preceding layers, so a revision or different bank must change this key.
  The native metadata builder avoids the unsupported upstream cascade path while
  retaining ordinary prefix-cache block lookup.
- An optional asynchronous scheduling path synchronizes the previous GPU forward
  before retiring request pins, pointer-table owners or native banks.
- Optional compiled execution permits CUDA/HIP graph mode `NONE` or `PIECEWISE`.
  The latter captures model segments while native attention remains outside
  graph replay. Full native-attention graph capture remains rejected.
- V2 runner support was investigated and remains explicitly blocked. In vLLM's
  current V2 implementation, `execute_model_state` is assigned after forward;
  native attention needs request identities during forward. The launcher rejects
  V2 rather than risking a bank/request mismatch. Other optional paths default
  off pending installed-wheel validation.
- The private wheel builder now compiles the new cache-identity module into a
  distinct 0.2.2 candidate; it cannot overwrite the signed 0.2.1 artifact.
- A live mixed-concurrency probe is prepared in
  `distribution/vllm/tests/polish_matrix.py`. The existing
  `http_release_probe.py` tests publication replacement and withdrawal;
  the new local control-plane test covers a refresh while a request is active.

## Verification completed without a GPU

Eight focused CLI, cache-identity, concurrent admission, refresh-drain and
GPU-event ordering tests pass with Python 3.14 test doubles. Python compilation
and `git diff --check` pass for the edited files. These are code-path checks, not
execution or performance results on vLLM with a GPU.

The reviewed pinned upstream vLLM source accepts `cache_salt` in chat and
completion requests, carries it into the first prefix-block hash, and permits
`PIECEWISE` capture with an attention backend reporting no full-graph support.
This source review does not establish runtime compatibility with Aimee's new
optional paths.

## Hardware validation pending

At the last check, `ssh root@192.168.0.253` returned `No route to host` and
the host did not answer ICMP. There is no local GPU runtime. Therefore the
following results have **not** been obtained:

1. Install a newly built wheel containing these source changes into unmodified
   vLLM, and rerun native, empty-selection and restart checks on Gemma 12B/
   RTX 5080, Gemma 12B and 26B/RX 7900 XTX, and Qwen 27B/RX 7900 XTX.
2. Run the mixed native/empty concurrent probe on each final profile, plus a
   publication revision and withdrawal while requests are active. Compare
   answer isolation, request status and GPU memory before/after.
3. For each serving option, run paired baseline/option workloads, including
   same prompt under different banks and after a revision. Record prefix-cache
   hits, exact answers, tokens, startup/JIT time, throughput, first-token and
   full-response latency. Test combinations only after individual options pass.
4. Verify the vLLM log's **resolved** graph mode. A requested piecewise mode
   can fall back to `NONE`; a startup success alone does not prove capture.
   Confirm native attention remains outside the captured segments.

Do not publish these source changes as a supported replacement for 0.2.1 or
claim a speedup until the installed candidate and GPU comparisons pass.
