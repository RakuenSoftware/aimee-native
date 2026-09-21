# Qwen native attention ↔ Aimee adapter

**Historical report; interpretation clarified 2026-09-20.** The chained lookup
failures below never delivered the second required record. They do not establish
a composition failure. The subsequent native-only run with a four-record
retrieval limit successfully returned `oolong;Lima`. See the
[current baseline and corrections](qwen-aimee-poc-baseline.md); original results
below remain preserved.

Date: 2026-09-20. Implemented and exercised against the full frozen Qwen3.8-27B
and the existing live Aimee service. Singleton consumption works. The two-step
retrieval tests remain unsuccessful.

## Implemented contract

```text
Qwen's projected attention query
    -> adapter translates addressed content into Aimee search
    -> existing Aimee retrieves governed memory
    -> adapter translates records into Qwen K/V states
    -> the requesting Qwen attention operation consumes the response
```

[attention_bridge.py](../../integrations/qwen_aimee/attention_bridge.py) defines
`NativeAttentionRequest`, `AimeeAttentionBridge.read`, and
`NativeAttentionMemory`. The request contains the actual query tensor produced
by Qwen's `q_proj`, `q_norm`, and rotary-position operation, together with its
key/value address space. The response contains native key/value tensors.

The first full-attention layer (block 3 in the installed Qwen architecture)
invokes the bridge during both prefill and decode. Its requesting attention
operation consumes the result immediately. Subsequent full-attention layers
read the corresponding returned states. The original Qwen gate, output
projection, and base weights are preserved.

Here **native request means Qwen's actual attention read**, extended to external
memory. It is not an emitted command, a tool call, a reconstructed hidden-state
sentence, or a new learned deliberate-search policy. Unlike the earlier
runtime-token experiment, the query tensor controls translation: holding key
address metadata constant and changing the query changes the outgoing search.

## Translation

The current Aimee endpoint accepts text. The bridge computes the requesting
query's attention over its key slots, including resident memory when present,
and resolves the addressed slots to exact lexical spans. The current fixed
translation averages head attention for the last query position, selects the
twelve highest-scoring word spans, and sends them in source order to existing
`POST /v1/memory/search`. It does not rank or select Aimee memories itself.

This deterministic translation is experimental, not a generally established
semantic equivalence between attention queries and search queries. The runtime
token IDs are key-slot address metadata; they are not a rolling-window query or
a caller-supplied retrieval instruction. Byte offsets preserve identifiers even
when generated token segmentation differs from canonical tokenization. Added
tokens explicitly marked special are excluded, including Qwen's `im_start`,
which is not present in its `all_special_ids` list in this installation.

Aimee selects one record per call in these tests. Returned records are cached
by ID within the request without local ranking. Changed content is encoded in
a separate frozen-Qwen pass; unchanged bank content reuses its existing states.
All memory state is derived from those returned records. No adapter training,
optimizer, learned selector, fact-specific logic, or legacy projection table
is involved.

The memory text is processed in that separate encoding pass. It is not appended
to the generation prompt or main cache. This remains a text-derived K/V
representation, not a compact engram or a claim of text-free transport.
The main cache is never rebuilt. Chat construction and templates are unchanged.

## Live results

Normal HTTP chat requests used greedy generation. No memory IDs were supplied
to the runtime. The deployed default is `recall_mode: attention`.

| Request | Native result | Memory-disabled result |
| --- | --- | --- |
| Home city of `unit-121330aded` | `Lima` | Does not supply the city; reports no information |
| Preferred drink of `unit-b03646cbf4` | States that the drink is `oolong` | Does not supply the drink; reports no information |
| Project `project-d4a92c` → ledger → phrase | `ledger-6b8f31`, then `unknown` | `unknown` |
| Project `project-f09e67` → ledger → phrase | `ledger-c73d25`, then `unknown` | `unknown` |

The city native run made three attention-originated calls and received ID 6.
The drink run made nineteen and received ID 5. The native query shapes were
`[1, 24, 49, 256]` / `[1, 24, 50, 256]` at prefill and `[1, 24, 1, 256]`
during decode. Bank reads occurred at all sixteen full-attention layers.

The two-step tests made eleven and ten native requests respectively. Their
translated queries kept retrieving the first link record (IDs 9 and 11).
They **never received the second phrase record** (IDs 10 and 12) in this mode.
Thus these failures currently lie in the attention-query-to-search translation;
they are not evidence of failure to consume a second record that arrived.
Prefill-only controls also returned the ledger followed by `unknown`.
The city disabled control was repeated with the same 48-token generation cap
as its native counterpart; it still supplied no city and reached the cap while
explaining that it had no information. The drink disabled control likewise
reached its 32-token cap. These are recorded observations, not completed-answer
format scores. The final two-step prefill-only controls were repeated on the
deployed build with identical prompts and generation budgets.

The prior token-driven decode experiments did sometimes retrieve the second
record, but used a different request mechanism. Those results are preserved in
[their own report](qwen-aimee-decode-recall.md) and are not counted as native
attention-query successes here.

## Verification and artifacts

Sixteen structural tests passed, including exact base attention output for empty
Aimee responses, response consumption by the same requesting forward pass,
decode callbacks, query-dependent translation with unchanged address metadata,
special-token handling, frozen weights, main-cache separation, and cleanup.
Real Qwen tokenizer checks cover Unicode, control tokens, and noncanonical
generated segmentation.

Enabled and disabled requests have identical main-prompt token IDs. None of the
memory values or tool-call protocols appears in those prompts. Main cache length
equals prompt length plus generated length minus one, with no memory prefix.
Every recorded recall has origin `qwen_attention_query`, a native tensor
shape/hash, addressed spans/positions/scores, and the exact Aimee request/reply.

[Artifacts](artifacts/qwen-aimee-attention-2026-09-20/) contain requests,
responses, server traces, package versions, source hashes, and test logs.
[verification.json](artifacts/qwen-aimee-attention-2026-09-20/verification.json)
records checks against the traces. The `deployed-source-sha256.json` manifest
matches both local files and the running build. Earlier manifests/runs are
retained; the final change excluded explicitly special added tokens.

The private `.253` service is `aimee-qwen-decode.service`, currently serving this
attention bridge on loopback port 18792 with the existing authenticated Aimee
connection. It has the previous one-hour runtime limit. This remains a serial,
single-identity prototype; no production Aimee endpoints were changed. The
request-local bank does not implement mid-request revocation of previously
consumed records. These tests establish neither broad retrieval accuracy nor
production throughput.
