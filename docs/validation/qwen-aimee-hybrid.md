# Prompt preload plus native Qwen recall

**Interpretation correction:** composition already worked in the earlier
untrained adapter and also succeeds here with preload disabled. Preload is not
shown to fix composition. See the [baseline and handoff](qwen-aimee-poc-baseline.md)
for the distinction between retrieval-limited tests and consumption tests.

Date: 2026-09-20. Implemented and tested on the full frozen Qwen3.8-27B on
`.253`, connected to the existing authenticated Aimee service. Prompt preload
and native attention recall now populate the same request-local memory bank.

## Behavior

The default chat request performs one Aimee search using the latest user message
before Qwen's main forward computation. The adapter converts the returned facts
to Qwen K/V states. Qwen's existing attention bridge then remains active during
prefill and decode, reading, extending, or refreshing that same bank.

Both paths use the existing Aimee client and state conversion. Aimee selects the
records. The adapter preserves them by ID, refreshes repeated IDs, and reuses an
unchanged encoding. It adds no fact-specific logic or trained parameters.

Preload events are explicitly labeled `prompt_preload`; attention-originated
events remain `qwen_attention_query`. Native events record bank IDs before and
after lookup. A preload is never reported as a Qwen-originated request.

Here native recall retains the [attention bridge's meaning](qwen-aimee-attention.md):
Qwen's projected attention query controls the adapter's lexical translation to
Aimee search. It is not a newly trained deliberate-search policy. The translator
and Qwen state conversion are unchanged in this implementation.

## Live requests

These were ordinary HTTP chat requests to the running adapter service, using
existing Aimee records, greedy decoding, and a 32-token output limit. No memory
IDs or answer values were supplied to the chat endpoint. All requests used the
same frozen model and a four-record Aimee result limit. Earlier attention tests
used a one-record limit, so this is not a controlled comparison to those runs.

| Request | Mode | Answer | Prompt searches | Native searches |
| --- | --- | --- | ---: | ---: |
| Home city | Hybrid default | `Lima` | 1 | 3 |
| Preferred drink | Hybrid default | `oolong` | 1 | 3 |
| Drink, then city | Hybrid default | `oolong;Lima` | 1 | 6 |
| Same joint question | Native only | `oolong;Lima` | 0 | 6 |
| Same joint question | Legacy prompt-only control | `oolong;Lima` | 1 | 0 |
| Same joint question | Memory disabled | `unknown` | 0 | 0 |

The joint hybrid preload received IDs `[5, 6, 7, 8]`. The first native request
saw exactly that bank; subsequent Aimee replies extended it to
`[5, 6, 7, 8, 10, 12, 9]`. The desired drink and city are records 5 and 6.
Qwen performed 96 native bank reads across six forward steps and sixteen
full-attention layers. All four joint modes had the same 74-token main prompt.

These results establish coexistence and successful consumption of the shared
bank. They do not show an accuracy advantage for preloading: native-only and
prompt-only controls also answered correctly. Some returned records were
irrelevant to these questions; the adapter did not filter Aimee's selections.
No two-step lookup condition was imposed.

## Verification

All 18 structural tests passed, including new checks for preload-before-native
ordering, bank extension, same-ID refresh, decode continuation, empty preload,
failure cleanup, and unchanged base weights. Existing native-only tests also
passed.

Live traces verify one preload followed by native requests, memory values absent
from the main prompt, zero added memory prompt tokens, and main-cache lengths
equal to prompt tokens plus generated tokens minus one. The latter accounts for
the final generated token not needing another forward pass. Local source hashes
match the deployed Python and placement files.

Memory text is still encoded in an independent frozen-Qwen forward pass to
produce the side bank. It is not appended to the generation prompt. Changed
banks are re-encoded; the main Qwen cache is never replayed or rebuilt.
These checks establish a functional prototype, not latency or scale viability.

## Controls and deployment

The experimental service is `aimee-qwen-hybrid.service` on `.253`, listening on
loopback port 18792. It retains the one-hour experimental runtime limit. The
previous `aimee-qwen-decode.service` was stopped to release the GPUs and port.
The previous deployed source was preserved as `attention-v1-src` on that host.
Production Aimee was not modified, and no new memory fixtures were created.

- Default: `recall_mode: attention`, `preload_memory: true`, `decode_recall: true`.
- Native only: `preload_memory: false`.
- Disable both: `aimee_memory: false`.
- Suppress decode lookup: `decode_recall: false`; prefill native recall remains.
- Legacy prompt-only comparison: `recall_mode: prefill`.

The legacy prompt-only control retains its old `qwen_native_prefill_hook` event
label, so its response has one total recall call but zero new `preload_calls` and
zero `native_recall_calls`. Its bank IDs are in the event rather than the legacy
mode's unused `resident_facts` field. This control is not the hybrid path with
native recall turned off.

The bank remains a request-local snapshot. New requests consult Aimee afresh;
immediate revocation of already-consumed state within an active request remains
unimplemented. Capacity overflow and unsupported episode windows surface as
errors rather than silently discarding records.

Implementation: [adapter](../../integrations/qwen_aimee/qwen_adapter.py),
[server](../../integrations/qwen_aimee/serve.py),
[structural tests](../../integrations/qwen_aimee/test_adapter.py).
Evidence: [requests and traces](artifacts/qwen-aimee-hybrid-2026-09-20/),
[verification](artifacts/qwen-aimee-hybrid-2026-09-20/verification.json),
[test output](artifacts/qwen-aimee-hybrid-2026-09-20/structural-tests.txt),
[runtime and source hashes](artifacts/qwen-aimee-hybrid-2026-09-20/runtime.json).
