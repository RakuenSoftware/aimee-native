# INT8 native-memory consumption validation

Validation recorded 4 October 2026. This retests quantized native consumption
under the same frozen instruction profile that passed the BF16 serving study:
`complete-hybrid-entity-resolution-system-v1`.

**INT8 passes the current instruction-bound consumption gate: 432/432 exact answers.**

| Condition | Correct / scored |
|---|---:|
| Online native memory | 144 / 144 |
| Matched online text memory | 144 / 144 |
| Strict-prepared native memory | 144 / 144 |

Merisol and Osreth outpost questions pass at sixteen and forty-eight turns in
both native and text conditions, and in strict-prepared native serving. No wrong
answers appear in any part of this completed matrix.

The older INT8 implicit-alias result of 135/144 remains a failed historical gate
under its older consumption contract. These new observations are a separate test,
with the current general entity-resolution instructions frozen before INT8 scoring.
No identities, alias facts, task answers or per-task instructions were added.
The result does not isolate quantization as the cause of the historical failure:
the original contract, prefix framing and execution configuration differ.

## Matrix and independent verification

There are 48 frozen task IDs and 47 distinct questions; two missing-entity tasks
intentionally have the same question, answer and empty selection. The matrix is
online native memory, matched online text memory and strict-prepared native memory,
each at zero, sixteen and forty-eight prior turns: 432 scored observations.
Each native phase includes 135 selected-bank observations and nine empty selections.
Empty selections use ordinary instructions and must answer `unknown`.

The real published reader selects the exact frozen canonical records. Its source
view, facts, task mapping and instructions are identical to the BF16 study's
selection document, over the same 100,018 physically verified public records.
Online text controls receive those same source facts in their system message.
Offline preparation binds the complete instruction digest and checkpoint identity;
strict serving must record zero encoding passes.

The independent audit verifies all **432 trace hashes**, recomputes exact answers
and Cartesian coverage, checks canonical namespaces/identities/revisions and native
source content, and verifies the actual instructions and facts in text-control
prompts. All 144 prepared observations report **zero serving-time encoding**.
All 144 paired online/prepared native answers agree. The resumed source protocol,
placement identity and four replay traces are checked separately. The audit
reproduces exactly from the archived evidence, with no checkpoint or prepared
payloads required for that verification.

## Executed configuration and retained capacity failure

Only the RTX 5080 executes the 64-layer checkpoint, with immutable revision
`1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`. The Rust research loader quantizes
matrix weights rowwise into signed INT8 with per-row scales, then reconstructs
weights in the activation dtype for matrix multiplication. Embedding and non-matrix
weights retain checkpoint precision. This validates that particular INT8 weight
path; it is not a general result about other quantization formats or serving engines.

The initial placement keeps twenty layers' matrices on device and offloads the
remaining forty-four. All 192 zero/sixteen-turn answers and the first native
forty-eight-turn answer pass. The next text control fails with a CUDA OOM while
allocating 2,543,845,376 bytes with about 1.4 GB free. That run remains `incomplete`,
not a failed-answer score and not a completed quality gate.

The continuation stores eight additional layers' matrices in host memory: twelve
resident, fifty-two offloaded. All layer computation and the head remain on the
5080; embedding is on CPU. Quantized weights, arithmetic, binary, checkpoint,
questions, facts and instructions remain unchanged. Four replay observations
(first task at zero turns and Osreth outpost at sixteen turns, native/text)
verify the same answers and canonical selections before continuing. Their traces
are retained separately from the 432 scored cells. The retained 193 original
cells keep their exact trace bytes and hashes, and both placement identities are
recorded explicitly. The resumed service has a 64 GiB host cap and no swap;
the initial service has a 56 GiB cap. No unrelated workload is stopped.

A harness preflight was interrupted before scoring to correct its empty-selection
instruction-hash expectation. A subsequent resume preflight produced the correct
Orinth answer but tripped a list/tuple comparison; that comparison was corrected.
These preflights and their executed sources remain separate evidence, without
being added to the quality denominator.

The recurrent storage audit verifies every checksum and base/positioned entry:
36 entries share eighteen payloads, using 2,788,687,872 bytes versus
5,577,375,744 entry-summed bytes. Sharing saves **2,788,687,872 bytes (50%, 2.60 GiB)**.
This is an immutable-storage saving; private evolving request state consumes
additional memory.

## Evidence and decision

The executed research runtime uses Torch **2.14.0+cu130**, CUDA build 13.0 and
Python 3.13.5. Its binary SHA-256 is
`8c30a9410187e7e5ef69111017926f90487f47e2d8160d780fedd93099e10370`;
the Rust model and adapter sources match the previously validated final binary.
Forty offline Python tests pass, including rejection of false scores, duplicate
matrix cells, wrong revisions, changed traces and prepared encoding. Existing
Rust and serving validation is retained separately; the serving tests are for the
BF16 integration, not an INT8 vLLM test.

The completed test service exits successfully and the RTX 5080 returns to idle
(2 MiB allocated, 0% utilization). Transient unit resource properties are reclaimed
after exit; the accepted launch parameters and the runner's finite-cgroup guard
are recorded separately from post-exit defaults.

Evidence is in [`20261004-int8-consumption`](../../benchmarks/native_addressing/evidence/20261004-int8-consumption/).
The raw archive contains 895 source/text/metadata members and has SHA-256
`a0dc29351465319b357f1770adc6d20db7b038dd4aaa1b61fda1aef568598e4e`.
It excludes checkpoint weights, recurrent/attention payloads, compiled binaries
and private signing material. All sixty historical evidence files and the prior
BF16 completion archive retain their original hashes.

Retain the current instruction-bound INT8 research path as passing this finite
consumption matrix. Its older failed contract remains unpromoted.
Historical failed scores remain unchanged. No production deployment, general alias
accuracy, low-latency certification, archive-independent semantic search or
quantized vLLM serving claim follows. The learned-router experiment remains
unpromoted; lossy state and native writes remain declined.
