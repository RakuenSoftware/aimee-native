# Native runtime read from Qwen activations

Date: 2026-09-20. Status: native read/return path demonstrated; query translation
is experimental and noisy. No tool-call implementation or adapter training.

The integration now starts inside the transformer after block 1. A native
module receives the block's hidden states, produces a lookup for existing
Aimee, and makes the returned memory states available to subsequent full-attention
layers in the same forward pass. The ordinary chat template is unchanged.

## Actual boundary

```text
Qwen block 1 output activations
    ↓
NativeAimeeRead(hidden_states)
    ↓ frozen embedding dictionary readout (experimental)
existing Aimee memory.search
    ↓ selected records, unchanged
separate frozen-Qwen encoding
    ↓ external K/V bank
Qwen full-attention layers in the continuing forward pass
```

Implementation: [native_read.py](../../integrations/qwen_aimee/native_read.py)
and [qwen_adapter.py](../../integrations/qwen_aimee/qwen_adapter.py).
The `native` adapter context accepts no user query. Neither messages nor input
token IDs are available to the native module. It receives only hidden states;
the model's existing input embedding rows supply a fixed translation dictionary.
The server still records the caller's question for debugging, but does not pass
it to this read interface.

The current text-based Aimee API cannot directly consume arbitrary Qwen vectors.
For this POC, each activation is mapped to its nearest frozen input embedding by
cosine similarity; the resulting IDs are decoded into the outgoing API query.
This conversion is inside the model adapter, not the prompt builder or a chat
tool loop. It uses no new parameters, optimizer, fact-specific parsing, selected
memory IDs, or fallback to the user's original question.

**This is a scheduled native read, not a learned recall policy.** It runs once
during the first forward pass. Decode reads the existing bank without another
Aimee call. It does not yet choose whether recall is necessary or initiate
additional reads during reasoning.

## Live results

The same frozen Qwen3.8-27B base and existing Aimee instance were used as in the
[direct-consumption experiment](qwen-aimee-direct.md). Ordinary HTTP requests
were sent to the serving process. No tool definitions, generated call syntax,
tool responses, or recalled facts were added to the generation prompt.

| Question | Answer | Actual Aimee IDs returned |
| --- | --- | --- |
| Home city of `unit-121330aded` | `Lima` | 6 |
| Preferred drink of `unit-b03646cbf4` | `oolong` | 5, 7, 3 |
| Drink, then city | `oolong;Lima` | 5, 7, 3, 6 |
| Home city of `unit-never-stored-9f24c6` | `unknown` | 5, 7, 2, 1 |
| Same combined question, memory disabled | `unknown` | No call |

The missing-entity lookup returned unrelated records, including existing
repository/deployment notes (IDs 1 and 2), rather than an empty result. The
model nevertheless answered `unknown`. No records were written or changed.

Enabled/disabled combined requests used identical 74-token generation prompts.
Other prompt lengths were 53, 54, and 56. Memory was separately encoded into
21, 62, 79, and 182 tokens respectively. These tokens were not appended to the
generation prompt or its main cache. There were 48, 48, 96, and 32 native bank
reads respectively, across the 16 full-attention layers.

## Query quality is the limitation

The query derived from the city activations was literally:

```text
q systemqAnswer usingq available memoryqq onlyqqq orqqqqq returnqqqqqqq Whatqq homeqq unitqqqq33qq?qqqqqqqqq
```

It preserved only 12 of 53 input token IDs at the corresponding positions.
The other enabled cases preserved 15/54, 21/74, and 14/56. The native readout
does not reconstruct complete entity identifiers reliably. Aimee found useful
records from the remaining fragments in this small store, which is not evidence
that this readout would route reliably over a large or ambiguous corpus.

The output demonstrates that the native runtime path can obtain and consume
useful Aimee memory. It does **not** establish a robust semantic query head,
deliberate model-initiated recall timing, or general recall accuracy. The earlier
prompt-query implementation must not be conflated with this activation readout.

## Representation and validation

The return path remains separately encoded text-derived K/V state. Aimee still
returns ordinary records, and frozen Qwen still tokenizes those records in an
independent encoding pass. This is not a text-free transport end to end or a
compact engram representation. It keeps memory text out of the main generation
context and keeps memory transport below the chat-format layer.

Eight structural tests passed, including:

- Native readout changes when its hidden-state input changes, without a query
  string or token IDs as inputs.
- Real tiny-Qwen forward passes invoke Aimee once and consume the returned
  bank later in that same pass; decode does not make extra calls.
- Native mode rejects externally supplied queries.
- Empty readouts do not report an API request and are not retried on decode.
- Request isolation, frozen weights, unchanged base behavior without memory,
  cache separation, and surfaced transport/capacity failures.

The initial seven-test run and the final eight-test run are both retained. The
only intervening implementation change corrected empty-readout accounting:
an empty readout now counts as an attempted native read, not an Aimee API call.
The initial live cases used `source-sha256.json`; the final source manifest is
`final-source-sha256.json`. After restarting with the final build, the combined
question was repeated with `recall_mode` omitted. It defaulted to `native` and
again returned `oolong;Lima`, with 96 native bank reads. The final deployed
source hashes match the local runtime files.

Raw requests/responses, exact native queries, hidden-state hashes, Aimee replies,
token/cache counts, outputs, source hashes, and structural test logs are in
[the artifact directory](artifacts/qwen-aimee-native-read-2026-09-20/).
[verification.json](artifacts/qwen-aimee-native-read-2026-09-20/verification.json)
summarizes checks against the recorded traces. These are narrow functional
checks, not a performance benchmark or an accuracy estimate.

The private server on `.253` now defaults to `recall_mode: native`.
`recall_mode: prefill` explicitly selects the old user-question-driven read for
comparison. The existing one-hour transient service and authenticated tunnel
are retained; no production Aimee API or chat-template changes were made.
