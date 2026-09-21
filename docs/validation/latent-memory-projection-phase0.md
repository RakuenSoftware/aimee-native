# Latent memory projection: Phase 0 runtime capability report

State: EXPLORATORY / RESEARCH. Recorded 2026-09-19.

**Decision: proceed to an isolated Phase 1 runtime prototype, with conditions.**
The target model and hardware are available. Sparse byte overlays can be applied
and removed from the real PLE table in an isolated process. The installed runtime
has no projection interface, and neither knowledge compilation nor semantic
forgetting has been demonstrated. No Aimee memory integration is justified yet.

DB1/DB2 remain authoritative; any future overlay is disposable derived state.
This investigation used model metadata and synthetic identifiers only.

## Inspected target

| Component | Observed identity |
| --- | --- |
| Host / guest | `root@192.168.1.253`, Proxmox CT `101`, hostname `llama101` |
| Runtime | `/opt/llama.cpp`, clean checkout `972d2313bc0bf0a45f634f77d95c9fb03aeab12c`, upstream ggml-org remote |
| Binary | `build/bin/llama-server`, `0.4.1-dev`, build 1, GNU 14.2.0 |
| Hardware | i7-14700K; two Vulkan RX 7900 XTX devices, 24,560 MiB each |
| Guest memory report | 64 GiB; no swap; cgroup `memory.max` reported `max` |
| Models | Flash-Next `UD-Q4_K_XL` (4 shards) and `UD-IQ4_XS` (3 shards) |
| Download manifest identity | `unsloth/Qwen3.8-Flash-Next-GGUF`, revision `38bb39ee97821de2c9009abb7e93950eec396e66` |
| Model storage | `/opt/models`, 31 GiB free at inspection |
| Existing inference processes | None observed before or after the probes |

Manifest identities are recorded claims from the downloads. Full model-shard
hashes were not recomputed. The probe reads GGUF metadata, tokenizes through the
installed library, and samples table rows; it does not load inference weights.

Both quantizations contain the same *layout*:

- Architecture `qwen4exp`; PLE at zero-based layer 1.
- Bigram and trigram addressing, eight heads each, sixteen rows per token.
- `per_layer_token_embd.weight`: 320,001,536 rows of 160 values.
- **Actual table type: IQ4_NL (GGML type 20), 90 bytes per row**, even in the
  model whose overall name says `UD-Q4_K_XL`.
- Table size 28,800,138,240 bytes (about 26.82 GiB).
- Table is in shard 2, at byte offset 682,453,280 for Q4_K_XL and
  528,499,744 for IQ4_XS.
- PLE convolution kernel 4, dilation 3: nine positions of convolution history,
  in addition to downstream model state.

## Capability results

| Phase 0 question | Result | Evidence level |
| --- | --- | --- |
| How is lookup exposed? | Internally computed token-history hashes feed an I32 row tensor, then `ggml_get_rows`; there is no public PLE endpoint. | Installed source inspection |
| Arbitrary row override? | Absent from installed runtime. External NLTM overlay code successfully replaced selected bytes in an isolated mapping of the real model. | Source inspection plus live byte probe |
| Direct row activation? | No installed C API or HTTP option found. A seam exists between `set_input` and the gather, but needs implementation. | Source inspection; not implemented |
| Patch format? | External `PLEOVLY1` version 1 container supports row IDs and opaque payload bytes. IQ4_NL payloads of 90 bytes worked for byte substitution. | Parsed and applied locally |
| Unload/reload? | Apply, replace, remove, and re-add passed; sampled original bytes restored. Fresh model-context behavior remains untested. | Live byte probe; not semantic forgetting |

Source anchors in the installed revision:

- [`qwen4exp.cpp:170`](https://github.com/ggml-org/llama.cpp/blob/972d2313bc0bf0a45f634f77d95c9fb03aeab12c/src/models/qwen4exp.cpp#L170): lazy table creation.
- [`qwen4exp.cpp:1069`](https://github.com/ggml-org/llama.cpp/blob/972d2313bc0bf0a45f634f77d95c9fb03aeab12c/src/models/qwen4exp.cpp#L1069): predecessor/EOS handling and row hashing.
- [`qwen4exp.cpp:1188`](https://github.com/ggml-org/llama.cpp/blob/972d2313bc0bf0a45f634f77d95c9fb03aeab12c/src/models/qwen4exp.cpp#L1188): gather and downstream gated PLE contribution.

The runtime's `--override-tensor` selects a buffer placement; it does not supply
replacement values. Its `--spec-ngram-*` options are speculative decoding, not
PLE addressing. Merely passing a proposed PLE flag or putting a patch alongside
the model does not activate an overlay in this installed build.

## Trigger experiment: the proposed suffix aliases

Using the installed tokenizer with `add_special=false`, `parse_special=false`,
we tokenized 100 identifiers, memory IDs 4800 through 4899, in each of two forms.
The probe calculated final-token addresses using the installed source's hash,
including uint64 overflow semantics. These are computed addresses, not an
instrumented inference trace.

| Trigger scheme | Tokens each | Distinct final sixteen-row sets | Pairwise overlap, 4,950 pairs |
| --- | ---: | ---: | --- |
| `<AIMEE_MEM_<id>_V1>` | 12 | **1** | All 4,950 pairs share all 16 rows |
| `<AIMEE_V1_MEM_<id>>` | 12 | 100 | 450 pairs share 8 rows; 4,500 share none |

For `<AIMEE_MEM_4817_V1>`, the last three token IDs are `[2258,16,29]`.
They encode the common suffix and contain no memory-specific information.
Changing the ID therefore cannot change its final-token bigram/trigram hashes.
The ID-at-end variant retains only the final two digits in the trigram window;
it is not a general allocator either. Earlier trigger positions can differ, so
this result specifically rejects **final-position addressing** with the proposed
suffix; it does not claim identical full-sequence activations.

Before compilation, a trigger allocator must check actual tokenizer output,
selected token positions and head addresses, and interactions with the entire
prompt, including template boundaries. Unique strings or cryptographic memory
IDs do not guarantee unique PLE rows. User scope must also participate in any
allocation identity when IDs are not globally unique. A trigger is not a secret
or an authorization capability: users can type it, and natural text can collide.

## Overlay experiment and its limits

We pinned the external implementation at
[`ortegaalfredo/llama.cpp-NLTM@8d5adc2`](https://github.com/ortegaalfredo/llama.cpp-NLTM/blob/8d5adc2f2ff3ae715100257eeeb3bec61eb1726c/src/llama-ple-overlay.cpp)
and compiled only its overlay implementation into a standalone probe linked
against the installed llama.cpp library. The production checkout and binary were
not patched. GGUF files were opened read-only; writes went to private mappings.

On Q4_K_XL shard 2, two adjacent rows starting at row 1,413,931 passed:

1. Apply payload A and observe both rows.
2. Replace with B and observe both rows.
3. Delete the probe's patch, reload, and recover the original bytes.
4. Recreate the patch with C, reload, then remove and restore again.
5. Verify the next untouched row, a separate mapping, and sampled disk bytes.

The same sequence passed starting at row 19, whose first row crosses a 4 KiB page
boundary. These payloads were arbitrary byte patterns, **never used for inference**.
The replacement test explicitly invalidated the recorded mtime, so it establishes
replacement mechanics, not reliability of automatic change detection. Whole-file
hash equality was not measured; disk checks covered the sampled rows.

The external format has a 128-byte header: magic, version, GGML type, row width,
bytes per row, record count, manifest length, and tensor name; JSON metadata
precedes records of little-endian u64 row ID plus raw row bytes. The writer's
documented examples use Q8_0; the installed table uses IQ4_NL. The current
`gguf-py` IQ4_NL class provides decoding but no `quantize_blocks` implementation,
and the injector's `RowCodec` requires encoding. Phase 1 needs a validated native
IQ4_NL encoder or an explicitly evaluated float overlay gather path. Changing
the whole model quantization would confound the comparison.

The packaged injector patch at
[`ngram-knowledge-injector@b50c789`](https://github.com/ortegaalfredo/ngram-knowledge-injector/tree/b50c7892bf34915fe7dfae2409700c41248b0bb8)
also failed `git apply --check` against the installed source, at CMake and loader
contexts. No patch was applied. This is not a drop-in installation.

## Governance implications from runtime inspection

The external fork calls reload inside `decode`, rather than enforcing one
immutable overlay generation per request. Its reload mutex serializes the reload
operation, not all model evaluation. Reload errors are logged and suppressed.
Neither that hook nor its row reversion clears existing KV, recurrent, or PLE
convolution state. These observations are from source inspection, not a live
concurrent inference test.

Consequently, global hot swapping does not establish Aimee's required scope,
revocation, or forgetting guarantees. A row patch being absent is insufficient
if a reused context already contains its influence. A request can also hash to
patched rows through ordinary text without any Aimee-selected activation.

For Phase 1, use one isolated worker, serialize experiments, pin each overlay for
the whole evaluation, and recreate the complete model context after changes.
Disable prompt reuse and exclude stored prompt/session state from later trials.
For eventual shared serving, require explicit request/sequence activation and
cache identity tied to the overlay generation, scope, and model identity. No
global overlay may substitute for Aimee's eligibility decision.

Projection metadata should bind checkpoint/shards, tokenizer, GGUF table type
and dimensions, head hash constants, runtime/gather implementation, compiler,
trigger allocation, scope, source hashes, and overlay digest. Bundle projections
need every member dependency. A mismatch must reject activation or fall back to
text. The external file's manifest alone does not enforce those checks.

Direct activation is technically plausible at the row-index or gathered-vector
input, but still needs a defined token position, head layout, and state lifetime.
Bypassing trigger strings does not prove zero token cost, arbitrary fact capacity,
or a useful compiler. Learned base PLE entries and Aimee overlays must remain
distinguishable so inactive overlays cannot alter ordinary model lookups.

## Phase 1 handoff

The next milestone is one synthetic, nonce-valued fact, with a frozen checkpoint,
validated trigger allocation, and a minimal isolated runtime hook. Measure paired
no-memory, compact-text, trigger-only/no-patch, and trigger-plus-patch conditions
over held-out paraphrases. Record compilation time, quantization error, injected
tokens (including triggers), correctness, and latency. Training prompts are not
evaluation prompts.

After successful injection, compare the removed-overlay condition to a clean
no-overlay baseline using entirely fresh model state. Then test supersession,
unselected triggers, adversarial literal triggers, and a second memory immediately.
Do not define forgetting as suppressing facts the base model already knows or
facts still present in conversation text. Test loss of the injected contribution
with nonce facts, including cached-context negative controls.

This run establishes runtime mechanics and specific blockers. It makes **no
claim** about recall accuracy, compiler feasibility, semantic forgetting, model
generation throughput, or context savings. Production schemas and recall
assembly were untouched.

## Artifacts

- [Reproduction instructions and probes](../../benchmarks/memory/latent_projection/README.md)
- [Q4_K_XL metadata, tokens, and computed rows](../../benchmarks/memory/latent_projection/results/2026-09-19/q4-metadata-triggers.json)
- [IQ4_XS metadata, tokens, and computed rows](../../benchmarks/memory/latent_projection/results/2026-09-19/iq4-metadata-triggers.json)
- [Overlay results](../../benchmarks/memory/latent_projection/results/2026-09-19/overlay-results.json)
- [Run identity](../../benchmarks/memory/latent_projection/results/2026-09-19/environment.json)

The reusable remote work directory is `/opt/aimee-ple-phase0` inside CT 101.
No model server was started, and no inference runtime was replaced.
