# Direct Qwen ↔ existing Aimee adapter

Date: 2026-09-20. State: experimental live integration, initial functional checks passed.

The frozen Qwen3.8-27B serving process successfully used records returned by the
existing Aimee service to answer both individual and combined memory questions.
The adapter has no trained parameters, loads no legacy memory projections, and
does not supply memory IDs to Aimee. These were ordinary HTTP chat requests to
the running inference server, not an oracle supplying memories to a benchmark.

## Implementation actually tested

Runtime: [integrations/qwen_aimee](../../integrations/qwen_aimee/README.md).

1. Caller submits normal chat messages.
2. Qwen's first forward-pass hook sends the latest user message to existing
   authenticated `POST /v1/memory/search`, with a fixed result limit of four.
3. Aimee returns its selected records. The adapter preserves every returned
   fact and its order; it does not rerank or interpret drink/city fields.
4. The same frozen Qwen encodes those records in a separate forward pass.
5. Qwen's existing full-attention layers read the resulting external K/V bank
   while answering the caller. The generation prompt is unchanged.
6. The request's memory bank is cleared on completion or error.

This is a deterministic, Qwen-specific conversion of current Aimee responses.
It uses pretrained Qwen attention, not the earlier separately trained adapter
or learned memory table. The base model uses the existing research weight-only
int8 linear implementation across two Radeon 7900 XTX GPUs. Model identity:
`Qwen/Qwen3.8-27B`, revision
`1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`; installed architecture is
`qwen3_5`. Package versions, config, and deployed source hashes are retained in
[runtime.json](artifacts/qwen-aimee-direct-2026-09-20/runtime.json).

## Observed answers

All requests used greedy decoding, the same frozen model, and this system message:

> Answer using the available memory. Return only the requested value or values. If unknown, return unknown.

| Request | Adapter disabled | Adapter enabled | IDs selected by Aimee |
| --- | --- | --- | --- |
| Home city of `unit-121330aded` | `unknown` | `Lima` | 6, 7, 4, 3 |
| Preferred drink of `unit-b03646cbf4` | `unknown` | `oolong` | 5, 7, 3, 4 |
| Drink, then city; semicolon-separated | `unknown` | `oolong;Lima` | 5, 6, 7, 8 |
| City, then drink; semicolon-separated | Not run | `Lima; oolong` | 5, 6, 7, 8 |

The city question was repeated with the adapter disabled after these requests;
it again returned `unknown`. Aimee returned distractors as well as the relevant
facts. Both combined questions received the same records in the same order,
but Qwen followed the requested output order.

The relevant authoritative records already existed in Aimee:

- ID 5: `The preferred drink of unit-b03646cbf4 is oolong.`
- ID 6: `The home city of unit-121330aded is Lima.`

No Aimee mutation, adapter training, value-table lookup, or base-model training
was performed for these requests. Four enabled requests succeeded; this small
set is a functional demonstration, not an accuracy estimate or broad evaluation.

## Verification

Raw caller requests/responses and per-request server traces are in
[the artifact directory](artifacts/qwen-aimee-direct-2026-09-20/).
[verification.json](artifacts/qwen-aimee-direct-2026-09-20/verification.json)
records the checks against those traces:

- Enabled/disabled city, drink, and joint requests had identical generation
  prompt token IDs: 53, 54, and 74 tokens respectively. Neither answer value
  appeared in those prompts.
- The separate memory encodings used 80, 82, and 75 tokens respectively.
  These are additional computation and external attention state, not free or
  compressed memory. They are not included in the API's main-prompt token count.
- Enabled requests read the bank at all 16 full-attention layers during
  generation: 48 recorded reads for each singleton, 96 for each joint answer.
- Main cache length equaled prompt length plus generated length minus one;
  the separately encoded memory tokens were not appended to that cache.
- Traces include the exact query, exact Aimee response, admitted IDs, encoding
  length, generation token IDs, and output. Source hashes match the deployment.

Four structural tests also passed on the installed tiny Qwen implementation:
response preservation and cache separation; exact base behavior with empty
memory and request isolation; surfaced service failures; and rejection of
oversized responses instead of silent truncation. These unit tests are separate
from the full-model live results above.

## What this establishes and what it does not

This establishes that an untrained model-specific adapter can connect the
existing Aimee retrieval API to frozen Qwen's native attention and produce
correct answers from live Aimee records, including two-record composition,
without adding their text to the generation prompt.

The result is specific to an **external K/V representation of separately encoded
text**. Qwen does tokenize and process the memory text during that independent
encoding pass. The bank expands what attention can read; it is external context
in that computational sense. This is not evidence for a compact latent vector,
a generic engram format, or independence from memory length. The earlier learned
projection results must not be conflated with this different representation.

Recall currently starts once at prefill using the latest user message. It is
not an autonomous semantic request emitted by Qwen during reasoning. Multi-turn
query construction, mid-generation recall, updates/deletions during an active
request, broad factual coverage, and long-term scaling remain untested here.

The prototype is serial, uses one configured Aimee identity, supports fact
responses up to 2,048 encoding tokens, and rejects unsupported episode windows.
No performance gate was applied. Raw elapsed times are retained only as run
metadata; this was not a latency benchmark.

## Running instance

Started on `.253` as transient `aimee-qwen-direct.service`, with a one-hour
runtime limit. Runtime files are under `/opt/aimee-qwen-adapter/`; the model is
under `/opt/aimee-native-p0-training/model`. The listener is loopback port 18792,
forwarded to this workstation's `127.0.0.1:18792` for these requests. The existing
Aimee endpoint is reached through an authenticated SSH tunnel with verified TLS,
the registered client certificate, and bearer credentials. Credentials are kept
outside this repository and outside recorded artifacts. The tunnel and transient
service must still be running for this endpoint to remain available.
