# Gemma native transcript composition candidate — 6 October 2026

The installed Gemma 0.3.2 integration prepares a closed stock system turn
containing the configured instructions and canonical facts. Its enrolled caller
then submits a fresh system/user chat containing the same instructions.
The actual installed stock Gemma tokenizer emits a BOS for both transcripts.
Concatenating the prepared bank and the entire request therefore duplicates the
BOS and instruction turn. This is a token-composition defect; this audit did not
run a GPU quality evaluation or claim a particular answer-score effect.

## Explicit candidate contract

`profile.json.composition.format = gemma-context-bound-chat-prefix-v1` names a
new transcript contract while preserving `native-prefix-absolute-v1` absolute
positioning and the existing sliding-window kernel. Preparation derives two
separate prefixes through the installed stock tokenizer: the bank prefix has
instructions plus canonical facts; the removable request prefix has instructions
alone. The incoming request never needs to contain canonical memory text.

The profile binds exact removable request tokens and their digest, bank token
digest, instruction digest, tokenizer/config/template file digests and configured
model revision. Existing Rust publication hashes incorporate the new profile;
admission checks the exact serialized profile bytes against the immutable
publication model/key and bank tokens. Existing Rust checkpoint/config/weights,
precision and runtime checks remain in force.

For a selected new-profile Gemma bank, the first message must be a matching
string system instruction followed by a conversation. The original messages go
through stock vLLM rendering. An instance-owned hook on vLLM 0.30.0's
`OpenAIServingChat.render_chat_request` verifies the actual rendered engine
`TokensInput` begins with the exact prepared request prefix and removes only
those tokens. Every user, assistant, task delimiter and generation token remains.
The new contract is text-only; embedding/multimodal inputs and populated token
position metadata fail before engine generation. Bad render-boundary and stale
catalog requests produce stock error responses. Shutdown and exceptional
lifespan exit restore the owned handler.

Legacy Gemma banks are not reinterpreted. They require explicit
`gemma_composition: legacy-independent-chat-v1` to retain the previous contract.
Otherwise a new context-bound artifact is required. Default Gemma preparation
uses a new broker cache-key namespace so old receipts cannot be reused for an
unchanged working set. Qwen hybrid prefix rendering, instruction verification,
message removal, positioning and cache-key formula remain unchanged. Empty
source selections retain the ordinary request transcript.

## Provenance

Isolated branch: `fix/gemma-native-prefix-composition`, checkout
`/home/virant/dev/aimee-gemma-prefix-composition`.
Clean shared source base: `54aec3da2b775fab3b5e6f586695eddaa869f2fd`.
Baseline reconciliation commit: `bf9e9cf`.

The immutable 0.3.2 evidence archive under
`benchmarks/native_addressing/evidence/20261004-shared-model-runtime/raw.tar.gz`
contains the release source and compiler-input SHA inventories. Unchanged
adapter, kernel, control, cache-identity and model-adapter source match that
inventory. Launcher `main.rs` and `local_delivery.rs` were reconciled from local
source only after their bytes matched the archived release hashes. The portable
bridge was populated from its matching released bytes; the inherited sparse
checkout omitted it from the initial working tree. Shared packaging code starts
from the clean committed shared base, which includes post-build packaging fixes;
it is not represented as byte-identical release compiler input.

The separately validated coherence retirement repair is composed from
`/home/virant/dev/jmlr-validation-runs-20261004/coherence-fix-source-r2`:

- `distribution/launcher/src/broker.rs` SHA-256
  `dab1bdb1d105a952e14d1454d8ee2bdaf73a24cc32fe00fafa4df409b324b414`.
- `distribution/launcher/src/model_broker.rs` baseline SHA-256
  `2069c40c4c65c99bb1d97467a7f7ff97967a272ffaaee86aa1c84a6d3153507a`.

Released local wheels match the archived installed deployment manifest:

- Gemma 12B 0.3.2 build 2:
  `33e4c156d4d3e8e6639f87be72444a65bb41dac37bba2763c27020dab2e485a7`.
- Gemma 26B 0.3.2 build 2:
  `baf623cbd7f8270aafaae4956c106f7de672ef7ca46b2044eab391e50323f308`.
- Shared runtime 0.3.2 build 2:
  `a3c42174676713cc8b60b8da1fd0c2f13b983a169dd03b3bdaf2241384c490f4`.

The read-only live inspection found the configured service inactive, with Qwen
hybrid selected. The installed Gemma plugins and shared runtime remain present.
No service, deployment, package, model, GPU, training or frozen release artifact
was changed.

## Verification scope

Eight standalone composition tests pass. Twenty-seven candidate and existing
preparation/admission/authentication tests pass against the actual installed
Python dependency environment on the private host, with candidate modules loaded
in memory. This includes a Gemma admission-to-renderer flow, capacity release,
nonmatching instructions, empty selection, unchanged Qwen hybrid behavior,
revision isolation, literal markers, multiple task roles, text-only validation
and hook restoration.

The actual installed Gemma tokenizer also verifies exact token identity for
empty and nonempty instruction contexts and a multi-turn task containing literal
special-token markers: bank plus candidate task suffix equals the complete
memory-text control transcript. No model weights were loaded.

A synthetic publication through the actual installed Rust Gemma adapter verifies
cross-language publication identity (96 segments, 2 positions, 688,128 payload
bytes) and rejects altered profile bytes. Temporary synthetic artifacts were
removed. This check found and corrected an initial Python sorted-JSON assumption:
the Rust build uses serde `preserve_order`, so validation now hashes the exact
profile bytes rather than reserializing them.

The compiled candidate worker RPC and real capture constructor accept the
versioned dict envelope with the actual pinned Rust adapter. Device-capability
metadata was mocked to avoid initializing CUDA. The actual stock vLLM
`OpenAIServingChat.render_chat_request` instance method also accepts the hook
and its text `TokensInput` output. `torch.cuda.is_initialized()` remained false.

The trusted CT101 Rust 1.98.1 toolchain compiled the shared client with
`--locked --offline`, isolated `CARGO_HOME` and `CARGO_TARGET_DIR`. All 27 launcher
library tests pass, including the new cache namespace and the preserved coherence
retirement tests. The entire shared runtime was compiled using the established
Cython 3.1.4 packaging directives, then all 27 Python tests passed against the
extracted compiled candidate modules. The review-only wheel is
`aimee_native_runtime-0.3.2+gemma.prefix.candidate1-cp312-cp312-linux_x86_64.whl`,
3,060,986 bytes, SHA-256
`295c4861b59ecc46faf56a9e62449c27285ccc3f6e9cf1806e381a4bbb2b7817`.
Released runtime notice/license bytes were preserved and wheel RECORD hashes
were checked. Its local version labels an isolated review artifact; no installed
release dependency pin was changed.

The candidate source archive, inventory, wheel, build/test logs and CPU checks
are retained under the private NAS directory
`/mnt/pve/backup/aimee-experiments/root-evacuation-20261005-r1/gemma-composition-candidate-r1`.
Build/test work stayed on the existing Optane filesystems, with task footprint
below 10 GiB and physical storage reserve above 90 GiB. No new daemon, mount,
storage volume, package installation or deployed-service operation was used.

No full HTTP server execution, GPU answer evaluation or replay of the 218-case
coherence matrix was performed. Those remain separate candidate validation gates.

## Frozen adapter integration follow-up

The private `gpu-validation/protocol.json` freezes a controlled-source actual
vLLM Gemma 12B Q4_K_M adapter integration, using six previously selected SQuAD
cases. It exercises resident capture, Rust immutable publication, candidate
admission/rendering and unchanged native attention. It does not claim enrolled
authority/broker end-to-end coverage. The actual supported released checkpoint
is retained; BF16 weights or another model family are not substituted.

Protocol SHA-256 is
`0e8ff8850e71f353ac45b547644a37674bd065e8223188f80a9ab98c203dac22`;
executor manifest SHA-256 is
`8030e0b37b3875001212e3fb226ffeb6383c8e388bcf9d609c7ac8d9428f7f40`.
The source freeze binds installed adapter/library, compiled candidate modules,
config/tokenizer, GGUF weights and GGUF loader files. Six actual stock-tokenizer
case checks and the installed binding/compiled runtime/test registration smoke
check pass without initializing CUDA. The request uses the same stock
`enable_thinking=False` template option as preparation.

The passive owned unit is `jmlr-gemma-prefix-integration-20261006-r1.service`.
It must wait for the full corrected SQuAD verified completion, independently
verify its source/result hashes and original GPU lock, and find no GPU users
before inference. Its output root is the private candidate NAS directory's
`gpu-validation/`; completion is `verified-completion.json`. Success requires
actual returned prompt token IDs, native-route call traces, two immutable
canonical revisions, empty selection fallback, stale context denial, failed
preparation recovery, unchanged identities and GPU release after owned cleanup.
Greedy outputs and EM/F1 are diagnostic; no six-gold correctness assertion is
made. Disagreements remain recorded for investigation. Legacy HTTP admission
is explicitly not exercised in this GPU fixture; actual compiled admission
CPU tests cover that denial.

The 1024-token request-prefix validation bound follows the existing preparation
bank budget `min(1024, max_model_len - 128)`. No new longer successful preparation
contract is admitted by the existing capture path. The closed context-only
request prefix and the memory-extended bank prefix are separate token sequences.
