> Historical Python reference. Active serving is now implemented in Rust; see
> [the Rust runtime](../../docs/rust-runtime.md). Keep this code for parity tests.

# Direct Qwen ↔ Aimee adapter (experimental)

**Core POC established, including composition without preload.** Read the
[current baseline and analysis corrections](../../docs/validation/qwen-aimee-poc-baseline.md)
before interpreting older experiment failures or planning the next phase.

The adapter also supports the experimental [local sparse image reader](../../../aimee/server-go/modules/memory/sparse/README.md).
Use `--memory-image /path/to/image --image-reader /path/to/aimee-memory-image`
with the signed authorization and matching read gateway described below.
This pins the published local view once per model request and uses a persistent
local reader for covered reads, with authorized Aimee fallback for other reads.
Local-image mode retains the K/V bank
in CPU RAM and uses temporary device copies during attention.
The current reader is lexical and does not yet reproduce all Aimee retrieval
lanes; the memory conversion still uses a separate frozen-Qwen encoding pass.
See [local-image results and performance](../../docs/validation/aimee-local-sparse-memory.md).

This is a serial inference service, not the earlier oracle-memory experiment.
It accepts normal `/v1/chat/completions` requests. By default, it first preloads
Aimee-selected memories using the latest user message, then keeps native recall
active against the same request-local bank. The `attention` mode
connects Qwen's actual attention query to Aimee through
[attention_bridge.py](attention_bridge.py):

```text
Latest user message -> Aimee search -> preload the shared K/V bank

Qwen Q/K/V projection and native attention query
    -> adapter resolves addressed spans for existing Aimee search
    -> Aimee selects records
    -> adapter returns Qwen K/V states
    -> the requesting attention operation consumes those states
```

The request contains Qwen's projected, normalized, rotated query tensor, not
words guessed from hidden states or an adapter-generated rolling query. The
translator resolves the query's attention over its key slots to exact lexical
spans for Aimee's current text API. Token IDs identify key-slot contents; the
query tensor determines which spans are addressed. Changing the query while
holding that address metadata fixed changes the translated request in tests.

The return type is native key/value tensors. Qwen's original attention, gate,
and output projection consume them. Empty responses preserve base attention
math exactly. The main cache is neither rebuilt nor prefixed with memory tokens.
The first full-attention layer initiates reads in prefill and decode; subsequent
full-attention layers consume the returned bank. This is an extension of the
model's native attention read, not a generated tool command or a newly learned
deliberate-search policy. Its lexical translation remains experimental.

Results: [attention bridge report](../../docs/validation/qwen-aimee-attention.md).
Hybrid results: [preload plus native recall](../../docs/validation/qwen-aimee-hybrid.md).

Preload runs once, before the first main forward pass. It uses the same Aimee
client and frozen-Qwen conversion as native recall. Attention requests can read
the preloaded bank and extend or refresh it through Aimee; preloading never marks
native recall complete. Both paths preserve the returned records, keyed by ID.
Traces label preload as `prompt_preload` and native recall as
`qwen_attention_query`, with the bank IDs before and after each native lookup.

The earlier `native_tokens` comparison mode executes reads after block 1,
inside Qwen's forward
pass. The runtime records the exact tokens consumed by the model; prefill uses
the last 64 prefix tokens, and decode uses the last 64 generated tokens.
The native module converts those cues to queries for the existing authenticated
Aimee `POST /v1/memory/search` API. No chat messages or query strings are passed
to that module, and there is no generated tool-call protocol.
Aimee selects the records; the adapter preserves
the complete returned fact list and order. No memory IDs are supplied by the
chat caller, and there is no adapter-owned ranking, training, or domain logic.

Decode lookups default to whitespace boundaries so incomplete identifiers do
not immediately trigger broad searches. This is a deterministic lexical rule,
not a learned recall policy. Every selected record is cached by ID for the
duration of the request. A repeated ID refreshes its content; unchanged banks
reuse their encoding. Aimee is still consulted on each eligible read.

The older `native` mode uses the noisy nearest-embedding hidden-state readout;
`prefill` sends the latest user message. Both remain explicit comparison modes.
The integration boundary is the transformer runtime; token decoding is an
internal conversion for Aimee's existing text API, not a chat protocol. No mode
registers tools or alters chat templates. Adapter training is prohibited.

## Current Qwen-specific transformation

Aimee returns ordinary text records today. The adapter encodes those records
in an independent forward pass of the same frozen Qwen model. It retains the
resulting key/value states from Qwen's full-attention layers as a separate
memory bank. During the main generation, those layers read the bank using
their existing pretrained attention weights. The main recurrent state and
KV cache contain only the main sequence; memory state is not inserted into
that cache, and memory text is not appended to the generation prompt.

This is an experimental deterministic conversion, not a proven universal
memory representation. Memory text **is processed by Qwen in the separate
encoding pass**. It is therefore a text-derived latent side channel, not a
claim that the model never tokenizes memory or that memory attention has zero
cost. Future Aimee-produced engrams can replace that extra encoding pass.

No legacy P0 adapter checkpoint or learned memory table is loaded. The adapter
has no learned parameters. The only weights used are Qwen's base-model weights.
For the available two-GPU machine, the server uses the existing research
weight-only int8 implementation and CPU-staged device transfers, now contained
in this runtime directory. It does not import a benchmark runner.

## Responsibility and tracing

- Request: default `attention` mode uses Qwen's real query tensor at its first
  full-attention operation. In the earlier `native_tokens` mode, an `nn.Module` invoked after block 1 forms
  cues from the runtime token stream. It accepts no external query. Lookup can
  happen during prefill and decode; this is **not** a learned decision about
  whether recall is needed. `decode_recall: false` makes the matched prefill-only
  control. The older `native` and `prefill` modes still read only once.
- Aimee: the existing service handles selection and returns its ordinary reply.
- Adapter: authenticated I/O, deterministic Qwen-state conversion and delivery.
- Model: its pretrained attention consumes the returned states and generates.

Attention-mode traces include the native query shape/hash, layer, addressed
spans with source positions and scores, and exact translated request/response.
Other request traces include every recall's phase, forward-step index, exact cue IDs,
query, complete Aimee response, resident IDs, and bank update/reuse status.
The older `native` mode additionally records activation shape/hash and readout.
All modes record the main
prompt token IDs, separate encoding token count, native read count, sequence
cache length, and output. This permits transport failures to be distinguished
from state conversion or consumption failures. It does not conflate a successful
API call with successful factual recall.

## Run

Use Python with PyTorch and the installed Transformers Qwen3.5/3.8 support:

```sh
python serve.py \
  --model /path/to/Qwen3.8-27B \
  --placement placement-dual7900xtx-int8.json \
  --aimee-config /private/remote.conf \
  --aimee-ca /private/remote-ca.pem \
  --aimee-client-cert /private/client.crt \
  --aimee-client-key /private/client.key \
  --trace-dir /private/request-traces
```

`remote.conf` contains the HTTPS origin and bearer on separate lines. Certificate
verification and hostname verification are enabled. With a server certificate
issued for localhost, use an authenticated tunnel to the existing service rather
than disabling verification. The inference listener binds only to `127.0.0.1`.
It inherits the identity of the configured Aimee credentials and is not a
multi-tenant serving implementation.

`GET /health` reports readiness. `POST /v1/chat/completions` accepts text-only
messages, `max_tokens` (1–512), and greedy decoding (`temperature: 0`). Streaming
is not implemented. `aimee_memory: false` bypasses the connection for comparison.
The default Aimee result limit is four; it is configured once at startup.
`recall_mode` defaults to `attention`; use `native_tokens` for the earlier
rolling-token lookup, `native` for the earlier hidden
readout or `prefill` for the original direct-consumption implementation.
`preload_memory` defaults to true in attention mode; set it false for native
recall alone. `aimee_memory: false` disables both paths. Preload is only supported
in attention mode; legacy modes retain their previous defaults.
`decode_recall` defaults to true; set it false to suppress decode-time lookup
while retaining prefill native recall and any prompt preload.
In `native_tokens` mode only, `decode_cue_boundary` defaults to `whitespace`; `every_token` reproduces the
initial unbuffered decode experiment. Native contexts reject an externally
supplied native query. Prompt preloading is a separate, explicit `preload_query`
argument in the Python adapter and never masquerades as an attention request.

The service rejects unsupported episode windows and oversized memory responses
instead of silently dropping or reranking them. Reads are synchronous. Each
changed bank is separately encoded by frozen Qwen. No latency target is applied.
The resident bank is a request-local cache, not a new authority: immediate
revocation of previously consumed state during an active request is not
implemented or established by these tests. A later query's omissions are not
interpreted as deletions. New requests start empty and consult Aimee again.

## Tests

`python test_adapter.py` checks actual tiny Qwen forward passes: unchanged base
behavior with empty/no memory, callback invocation, exact response preservation,
separate sequence cache, frozen weights, state cleanup, and surfaced failures.
Native checks cover query dependence on activations, same-forward memory reads,
the old mode's prefill-only behavior, rejection of external queries, and empty
lexical readouts. Runtime-cue checks cover decode-time delivery, exact generated
token cues, completed-word dispatch, the prefill-only control, failure cleanup,
frozen weights, cache separation, and bank reuse. Attention bridge checks cover
query-dependent translation, special-token address metadata, exact base math
with empty memory, and delivery to the same requesting attention operation.
Hybrid checks cover preload-before-native ordering, a shared bank, ID refresh,
decode continuation, empty preload, failure cleanup, and unchanged base weights
and main cache length.
These structural tests do not establish pretrained-model recall; the full-model
decode experiments are recorded in
[the decode recall report](../../docs/validation/qwen-aimee-decode-recall.md).
The earlier native-layer requests are recorded in
[the native read report](../../docs/validation/qwen-aimee-native-read.md).
The earlier prefill implementation is recorded in
[the live integration report](../../docs/validation/qwen-aimee-direct.md).


## Diagnostic profiling

`--profile` records synchronized wall spans for search, memory encoding, bank
copies, and query translation, plus first-token and inter-token times. It adds
measurement overhead and is not a production throughput mode. `--host-memory`
retains the bank in RAM for either source. `--keepalive` requests HTTPS connection
reuse; the tested endpoint closes each response connection.

For an explicitly configured serial experiment, `--compare-backends` permits
both local-image and remote credentials. Requests may choose `memory_backend`
`local` or `remote`; they cannot supply a path or credentials. This makes matched
delivery profiling possible in one loaded model. **Equal returned facts do not
make the underlying readers equivalent**; see the local-image validation report.

## Local-first reads and read-only deployment

`--local-first --read-authority ID` uses published exact-request decisions from
`--memory-image`; any uncovered, expired, unavailable or invalid source falls
back to Aimee. Publication replaces the active decision set. A request pins its
image generation, so this does not revoke states already consumed mid-request.

`--encoding-cache-mib N --host-memory` retains bounded frozen-model native banks
in RAM. Every use first performs an eligible memory read; the cache cannot choose
or activate records. Keys include ordered IDs and encoded content. The model is
fixed for this process lifetime; there is no cross-model persistent tensor cache.
`reuse_native_states: false` disables reuse for a comparison request. No adapter
training or local semantic learning occurs.

Run `read_gateway.py` under a separate credential-bearing identity and configure
`serve.py --read-gateway /path/to/read.sock`. The gateway permits only search,
never arbitrary proxying or writes. Give the model identity read access to the
image and socket, no image/directory write access, and no credential access. A
separate Aimee-controlled publisher owns generation changes. Writable model
runtime caches and traces must be outside the knowledgebase. API shape alone is
not a permission boundary; operating-system access must also be restricted.

Canonical knowledge objects remain independent of model-native projections.
The current CPU bank cache is a disposable serving artifact, not authoritative
memory or a portable latent representation.

## Authorization-bound serving (required)

Normal `serve.py` now requires an authorized `--memory-image`, `--authorization`,
`--authority-key`, `--subject`, `--policy-epoch`, and `--read-gateway`. These are
trusted startup configuration, never model/request fields. Direct authority
credentials in the model process are rejected. The image reader verifies its
signed grant before model weights load; the gateway binding must match. Native
state cache keys include the authorization identity.

The gateway runs under a separate identity with the authority connection and
an independently verified copy of the same authorized image. It validates every
fallback result before delivery. A complete rejection preserves transport
framing, so a later permitted request can still succeed. Writes, scope changes,
foreign bindings and unsupported rich payloads fail closed. Empty authority
results also return unavailable, rather than exposing a distinct unauthorized-
versus-missing record status.

The current grant format approves exact canonical serving fields and optional
complete read decisions. Metadata, aliases, edges and history do not enter the
model image automatically. Episodic/graph/evidence payloads need a richer Aimee-
authorized response codec; they are currently rejected, not silently simplified.
Use a separate filesystem identity or equivalent isolation for different grants.
Keep traces and native state caches inside the same authorization boundary.

Grant files are rechecked on reads. Revocation tested here means changing the
trusted grant file; automatic propagation from production Aimee policy is not
implemented. Already emitted answers cannot be revoked, and no immediate
mid-token erasure guarantee is made. On an authorization change, create a fresh
image directory and model session rather than reusing old filesystem contents.

See [authorization validation](../../docs/validation/aimee-authorized-memory.md).

## Authorization transition regression tests

Explicit denials from either reader are terminal for the current request;
transport failures may still fall back to the independently authorized gateway.
Run `test_authorized_gateway` with `AIMEE_IMAGE_READER` and
`AIMEE_FIXTURE_ISSUER` pointing at the built Go reader and research fixture issuer.
It checks local/remote grant skew, revocation during an upstream read, narrowed
and expired grants, and atomic rejection of mixed responses. The upstream is a
controlled protocol fixture; this does not test production grant issuance.
See [the transition report](../../docs/validation/aimee-authorization-transitions.md)
for commands and the remaining Aimee authorization dependency.
