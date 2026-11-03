# Rust native-memory runtime

> This guide covers the standalone Qwen research runtime. For current enrolled
> vLLM model installation use [usage](usage.md), and for the isolated Go
> dependency use [development](development.md). This research gateway is not
> the Aimee v1.0.2 source-release endpoint.


The Rust implementation owns the model adapter, attention-request translation,
read-only Aimee transport, credential gateway, native state cache, tokenizer,
text-only HTTP serving, and frozen Qwen text forward-pass orchestration.
Native libtorch supplies tensor/GPU kernels. Python and Transformers are not
loaded by the serving processes. The Go image reader and publication tools live in this repository.
Aimee authorizes the data before publishing the recipient's
image; neither the local reader nor the adapter reevaluates permission to read it.

## Connection preserved

1. Optionally preload the latest user query through Aimee.
2. At Qwen's first full-attention layer, translate its attention-addressed token
   positions into the Aimee query. Repeat during decode when enabled.
3. Accept only Aimee-selected, authorized facts; merge by canonical record ID.
4. Encode those facts in a separate frozen-Qwen pass. Keep its full-attention
   K/V states in RAM and provide temporary device copies to native attention.
5. Keep conversation token IDs, positions, and its ordinary cache separate.

There are no trainable adapter parameters, synthetic fact-specific vectors,
city/drink rules, or model writes. The separate encoding pass does tokenize
Aimee content; **zero memory tokens enter the main conversation prompt**. This
is the established native K/V connection, not a new learned engram codec.
Encoding reuse is bounded and keyed by the published generation, memory tokens,
and canonical record revisions within a process bound to one model. A changed bank is encoded separately;
the main conversation is not replayed.

## Build

Rust 1.98.1 is pinned. Cargo.lock pins dependencies. Release uses opt-level 3,
fat LTO, one codegen unit, stripped symbols, and no debug information.

```sh
export LIBTORCH=/path/to/native/libtorch
export LD_LIBRARY_PATH="$LIBTORCH/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
scripts/build-rust.sh
```

The research host has Torch 2.14/ROCm 7.2 native libraries inside its existing
Torch installation. tch 0.26 normally targets 2.13. That specific tested build
uses `AIMEE_TORCH_214_COMPAT=1`, which enables a small build-only compatibility
header for four removed legacy C++ functions and the explicit version-check
bypass. It is not a blanket compatibility guarantee for other Torch versions.
`build.rs` retains ROCm's kernel registration library when present. No Python
interpreter is needed to build against an already supplied libtorch directory.

The executable still depends on native Torch/ROCm shared libraries; it is not
a standalone static binary. The internal tch/libtorch FFI does not introduce a
public adapter C ABI. Packaging those native libraries is a separate deployment
step. Selective obfuscation and opaque binary tables are not implemented yet.

For the transport-only build, no libtorch is needed:

```sh
cargo build --release --locked --no-default-features
```

## Run

`aimee-native gateway --help` and `aimee-native serve --help` list all flags.
Run the credential gateway under a separate OS identity with exclusive access
to the upstream mTLS keys. Run the model under an unprivileged identity with
only its recipient-specific published image and gateway Unix socket. No local
grant, verification key, subject, or policy epoch is required. The model must not
receive unrestricted private source stores or issuer credentials. The gateway exposes identity, memory search, and authorization-bound canonical
reference resolution. None permits knowledge writes.

```sh
aimee-native gateway \
  --socket /run/aimee/search.sock \
  --config /private/remote.conf --ca /private/ca.pem \
  --cert /private/client.crt --key /private/client.key \
  --image-reader /bin/aimee-memory-image --memory-image /authorized/image \
  --authorization /authorized/grant.json --authority-key /authorized/issuer-public.hex \
  --subject MODEL_SUBJECT --policy-epoch POLICY_EPOCH

aimee-native serve --model /models/qwen --placement /config/placement.json --int8 \
  --read-gateway /run/aimee/search.sock --read-authority AUTHORITY \
  --image-reader /bin/aimee-memory-image --memory-image /authorized/image \
  --trace-dir /private/model-traces --encoding-cache-mib 256
```

The listener is loopback-only on 18793. This initial port supports serial,
non-streaming, greedy text chat; batch, tools, vision, sampling, and alternate
chat templates are rejected/unsupported. The checkpoint's installed template
hash is checked before loading. Native libtorch inference replaces the Python
forward pass; this is not yet a llama.cpp integration or optimized GPU runtime.

Request fields: `messages`, `max_tokens`, `temperature: 0`, `stream: false`,
`aimee_memory`, `preload_memory`, `decode_recall`, `recall_mode: "attention"`,
`reuse_encoding`. Memory limits are server configuration, not model-controlled
scope. Unknown request fields are rejected. Traces contain authorized memory
and require the same protection as that memory; files are mode 0600.

Publication must consume Aimee's existing authorization decision. Research fixture
grants validate physical filtering only; they do not implement production
membership evaluation. Rich episode/evidence response codecs are not yet supported.
Permission changes require Aimee to replace or withdraw the delivered projection.
The publisher must also remove obsolete files and stop active consumers when
immediate withdrawal is needed. A local permission check cannot revoke knowledge
already delivered. See [the corrected boundary](validation/published-local.md).

## Verification

```sh
cargo test --locked --no-default-features
cargo clippy --locked --no-default-features --all-targets -- -D warnings
# Build the Go reader/fixture issuer as described in the repository README.
RUST_QWEN="$PWD/target/release/aimee-native" \
  PYTHONPATH=integrations/qwen_aimee python3 -m unittest -v test_authorized_gateway
# Offline numerical reference; requires the historical Python test dependencies.
python scripts/validate_rust_parity.py \
  --binary target/release/aimee-native --output /private/rust-parity
```

Python reference code and historical tests remain for regression comparison.
They are not part of Rust serving. See the [port validation report](validation/rust-port.md)
for measured results and limits.

## Layered general knowledge and personal memory

Use one combined Aimee-authorized image built from the general release, optional
KB enrichment, and server-local memories. `--memory-image` names this resolved
snapshot; no second adapter policy or parallel KB store is needed.
The updated Go reader must support `serve-published`. Recompile older images to
include the small serving descriptor in their manifest. Rebuild it alongside the
Rust binary. Canonical namespace/ID/revision travels with every consumed fact
and is visible in traces, so equal numeric IDs from different layers stay distinct.
See the [starter KB](../knowledge/general-v0/README.md) and
[layered validation report](validation/layered-kb.md).

The default model path (no `--authorization`) starts `serve-published`, pins the
current image once per request, and performs local reads without a gateway
identity round trip or per-read signature checks. Local hits already carry their
canonical references. Misses use the existing authorized Aimee fallback. The
privileged research gateway retains its existing credential/egress configuration;
it is not involved in successful local reads. Supplying the four legacy grant
flags selects the historical guarded reader for compatibility and regression tests.

`--memory-image` also accepts a managed recipient directory created with
`install-published`. The publisher can replace or withdraw it without rewriting
the adapter configuration. New requests open the current generation; the native
encoding cache is cleared on generation changes or publication loss. Local
updates do not need to match the remote gateway's image generation: its binding
is discovered independently on an actual fallback. See
[delivery commands and measured lifecycle tests](validation/local-delivery.md).


## Restricted Aimee fallback

For the new restricted upstream, add `--upstream-namespace aimee-published` to
`gateway`. It obtains the candidate restriction from the verified Go image
reader, requires Aimee's acknowledgement, and retains exact egress checks.
An old upstream that ignores the restriction fails closed. Omitting this flag
retains the legacy broad-search/egress-check behavior for compatibility.

The Aimee-facing ingress is `aimee-memory-read`, built from this repository:

```sh
aimee-memory-read --socket /private/aimee-read.sock \
  --bus /var/lib/aimee/server-module-bus.sock \
  --namespace aimee-published --principal GRANTED_PRINCIPAL
```

Run it as an explicitly admitted Aimee bus identity. Its socket is owner-only;
only the privileged read gateway should reach it. Configure the Rust gateway
with `--upstream-unix /private/aimee-read.sock --upstream-namespace aimee-published`.
The model gets only the gateway's socket and its authorized image. The ingress
is server/user-scope only and does not evaluate membership or issue grants.
The current research setup admits principal 200 only on the disposable instance.
See [results and limits](validation/restricted-kb.md).

## Current public KB expansion and encoding diagnostics

The expanded reference release contains 249,105 objects. See
[the scale/follow-up report](validation/kb-scale-followup.md) for measured lookup
cost, approved cue routing, native answer tests and the outstanding production
approval-issuer integration.

Chat requests can select `memory_encoding: "content" | "keyed" | "json"`.
This controls only serialization into the separate frozen-Qwen native encoder;
it never appends a memory block to the generation prompt. The adapter performs
no domain-specific rewriting or training. Trace records include the encoding
format and publication generation for diagnosis.

Independently encoded memory keys are relocated to rotary positions `[-M,-1]`
before each native read; conversation positions stay unchanged. Native recall
addressing and memory consumption use the same placement. Cached bank keys remain
in their original encoding coordinates, so reuse cannot accumulate rotations.
This corrects the old overlapping memory/conversation coordinate ranges. It does
not rebuild the conversation cache or change the memory values. See the
[keyed/planet/drink investigation and regression tests](validation/keyed-encoding.md).

Normal requests need no positioning option. Traces report `memory_before_prompt`
and the effective `memory_position_offset`. Research-only controls require
starting the server with `--enable-memory-diagnostics`; otherwise the server
rejects diagnostic fields. Those controls are:

- `memory_diagnostics`: 0–32 generation steps of logit/attention tracing.
- `diagnostic_candidates`: up to 16 strings; reports the log probability of each
  string's **first token**, without adding candidates to the prompt.
- `memory_before_prompt:false`: reproduce the old overlapping-coordinate path.
- `memory_position_shift`: fixed offset in [-8192,8192] when before-prompt
  placement is explicitly disabled.
- `memory_encoding:"keyed-neutral" | "keyed-suffix"`: controlled encodings.

Diagnostic traces may contain the full authorized memory text and token IDs;
keep their storage within the recipient's existing authorization boundary.

Publisher commands live in Aimee's generic CLI, not the model process:

```sh
aimee-memory-image sync-published \
  --root /publisher/canonical-source --output-root /model-data/recipient \
  --authorization /publisher/aimee-issued-approval.json \
  --authority-key /publisher/aimee-authority-public.hex \
  --subject RECIPIENT --policy-epoch EPOCH --reader-gid MODEL_GROUP --watch 30s

# When an authenticated Aimee publication endpoint has been wired:
aimee-memory-image fetch-published \
  --endpoint https://AIMEE_HOST/APPROVED_PUBLICATION_ROUTE \
  --ca /publisher/aimee-ca.pem --cert /publisher/client.pem \
  --key /publisher/client.key --bearer-file /publisher/bearer \
  --root /model-data/recipient --reader-gid MODEL_GROUP --watch 30s
```

The HTTP path above is a placeholder for the real authenticated API mount; no
production route or approval issuer is implied by this example. The generic
handler requires an authorization resolver and refuses operation without it.
Authentication happens during publication/download, never on local model reads.

### Experimental independent record encodings

`serve --enable-record-encoding` permits the request field
`"memory_encoding_granularity": "record"`. The default is `"bank"` and keeps the
existing combined-bank encoder. A server without the flag rejects record mode.

Record mode separately encodes each Aimee-selected canonical fact with the frozen
model and keeps the resulting K/V in CPU RAM. Each record retains its original
encoder coordinates in the cache. At attention read, its keys receive a single
rotary translation into a disjoint slice before the prompt; values are unchanged.
The flattened token-address list follows the same record order as the K/V slices.

Cache identity includes publication binding, namespace/ID/revision, exact encoder
tokens, format and granularity. Model/tokenizer identity is fixed by the running
process; the cache is not persisted across restarts. Working-set growth reuses its
unchanged record tensors even when `reuse_encoding: false` disables the optional
cross-request cache. That flag does not force unchanged active records to be
encoded at every decode step. `--encoding-cache-mib` bounds the shared LRU cache,
not the model weights or the active sequence bank.

Recall events expose `records_encoded`, `tokens_encoded`,
`record_working_set_hits`, `record_cache_hits` and `encoding_elapsed_ms`. The latter
includes cache lookup/assembly bookkeeping as well as encoder execution. The
complete-bank path also reports elapsed encoding/cache time when its bank changes.

This is not the Aimee change stream. Publication changes still clear the entire
shared cache, as do withdrawals. See the [incremental update design](proposals/pending/incremental-kb-updates.md)
for the required authorization and generation contract before selective reuse
across publications. Independent encoding changes encoder context, so quality
must be measured; do not assume it is numerically equivalent to joint encoding.
