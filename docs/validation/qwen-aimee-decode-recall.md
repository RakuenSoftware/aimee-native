# Earlier runtime-token decode experiments

Date: 2026-09-20. These are preserved diagnostic results, not evidence that
Qwen originated a native attention request. That boundary is now implemented
separately in [the attention bridge](qwen-aimee-attention.md).

Four synthetic records were stored and read back through existing Aimee:

| ID | Content |
| --- | --- |
| 9 | The linked ledger for project-d4a92c is ledger-6b8f31. |
| 10 | The lookup phrase for ledger-6b8f31 is saffron otter. |
| 11 | The linked ledger for project-f09e67 is ledger-c73d25. |
| 12 | The lookup phrase for ledger-c73d25 is cobalt badger. |

Both questions requested the ledger identifier followed by its lookup phrase.
The initial Aimee search returned only the link record, with a fixed result
limit of one. Records were never supplied by ID to the inference runtime.

With a lookup on every generated token, chain 1 answered
`ledger-6b8f31\nsaffron otter`; chain 2 answered `ledger-c73d25\nunknown`.
The positive result was weak: record 10 arrived on the ambiguous generated
prefix `ledger-`, before the full identifier existed. Chain 2 received record
12 on `ledger-c73` but did not use its phrase. Both prefill-only controls
returned the correct ledger followed by `unknown`. Memory-disabled controls
returned `unknown`.

A second version waited for whitespace before dispatching a decode lookup.
In both chains it retrieved the correct phrase record from the complete
model-generated ledger identifier. Both answers still ended in `unknown`.
Thus successful transport at decode was not sufficient for successful late
consumption in these runs. No cache replay was implemented or tested.

These versions constructed lookup cues from the runtime token stream. They
were superseded as the default because that is not the native attention-query
contract requested by the user. No training was performed in either version.

Raw requests, responses, exact recall steps, record store/read receipts, source
hashes, and 11-test/12-test structural logs are retained in
[the artifact directory](artifacts/qwen-aimee-decode-recall-2026-09-20/).
The `source-sha256.json` manifest identifies the every-token version;
`boundary-source-sha256.json` identifies the completed-word version. Earlier
failures and the qualified positive result remain intact.
