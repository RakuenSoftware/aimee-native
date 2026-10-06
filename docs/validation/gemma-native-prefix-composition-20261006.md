# Gemma native transcript composition candidate — 6 October 2026

Latest follow-up: `a149fa9` / `ee7bb8c` introduce the review-only
`gemma-context-bound-chat-prefix-v2` contract below. The earlier v1 CPU result
did not reproduce vLLM's actual content conversion; retain those historical
receipts as superseded preparation evidence. No successful paired GPU result
has been established yet.

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
The additive reviewed executor revision is `executor-manifest-r2.json`, SHA-256
`91181da13170cabcd50390e29738195b1faf4eb07c7ce75f2300b313d00b9c9c`.
It preserves the original executor and adds exact inherited serving-config
identity plus exclusive NAS evidence creation. Existing identical frozen inputs
are verified and skipped; a differing existing artifact or receipt is rejected.
The final additive executor is `executor-manifest-r3.json`, SHA-256
`a750758d717b1a6e5855f5fe3a6e9995ceeaef46d7641e3a791ae0e88ddc3ac0`.
It retains r2 and removes final stdout writes after artifact hashing, so the
queue log's sealed hash remains valid. The initial passive queue was stopped
with no children and no inference to apply this executor-only correction.
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

## Actual request-renderer follow-up

Recovery r4 loaded the released Q4 model successfully and returned `ready`
through an empty catalogue. Its exact stock-token assertion failed before any
paired bank capture. The actual vLLM 0.30.0 renderer detects OpenAI list content
for this template; Gemma adds a trailing system-content space in that branch.
The actual empty request contained 55 tokens, whereas the direct raw-string
Transformers template check contained 54. The failed receipt and raw response
are retained under `gpu-results-recovery-r4`; GPU release is verified.

Preparation now receives the configured serving handler's actual
`HfRenderer.render_messages` callback. It obtains both the capture text and
the actual stock tokens and rejects text that cannot reproduce those tokens.
There is no direct-tokenizer fallback in the preparation API. The new v2
profile rejects earlier candidate v1 banks, and the Rust working-set cache
namespace changes to v2. Existing legacy opt-in and the Qwen path remain as
documented above.

The compiled candidate2 Python wheel is sealed privately with SHA256
`3f9a315eb81279a0f1fd74f9aee0b8c8e4ac29f5f21cf43cbb4ed51fc7d1ce70`.
Only the composition and preparation modules, wheel version and RECORD differ
from candidate1. All other module binaries, notices and the corrected-coherence
client binary are retained. Twenty-eight compiled tests pass without skips,
including actual Rust-backed admission tests. Actual installed vLLM CPU
rendering passes all six frozen cases, plus empty context and multiple turns:
bank lengths 191/109/354/312/146/236, request prefix 37, and task suffixes
21/26/28/22/25/19. These checks initialize no CUDA context.

The broker v2 namespace change is source-only pending a capacity-safe Rust
rebuild. The next controlled adapter test explicitly does not execute broker
enrollment or its working-set cache. Its retained client binary SHA256 is
`fc3725af30ee4e4aea1e801447a9ecf7dcbf07adce102748dc244344f92f9366`.
Do not describe this Python wheel as a complete rebuilt broker bundle or a
completed production fix.

The sealed prospective recovery r6 uses the same checkpoint, configuration,
cases, decoding and unchanged kernel. Its empty-selection expected token IDs
come from the configured installed vLLM renderer. The executor activates only
the private empty catalogue before checking health; this resolves paused-start
readiness without operator intervention. The short Optane IPC path binds at
89 bytes. Actual binding, spawn and CPU renderer preflights pass. Protocol
SHA256 is `b9afea47b08b7d4e0b6c93be3c164de761c1c9fc726ebb13a71c74b28532bf1a`,
executor manifest `7544361b5501022756af84a5e8b3ba3c060169a805fcf9771896d40830b5c839`,
source freeze `8f36c8ec3cfdcab7a27543ec4de88197b7e7d3a15f05868c88542b274d0fbb38`.
Unlaunched r3 and r5 prospective mistakes remain preserved separately.

## Actual engine-input follow-up

Recovery r6 was interrupted only in its owned cgroup after a foreign service
started a GPU child during a transient empty-device interval. Recovery r7
therefore also requires that whole foreign service to be terminal before
acquiring the original GPU lock. Both failed attempts and raw responses remain
preserved. No foreign process was stopped.

Recovery r7 loaded the unchanged released model, passed the 55-token empty
fallback, captured and Rust-published the actual 191-token first bank, and
returned `food security` on the paired full-text request. Native admission
rejected before kernel execution because stock vLLM adds `arrival_time` to its
text TokensInput. The bank tokens exactly matched the full-text prompt prefix;
this attempt provides no successful native-generation result.

Candidate3 preserves that declared timestamp alongside the existing token and
cache-salt fields. Multimodal, embedding and positional metadata remain denied.
Only composition, wheel version and RECORD differ from candidate2; preparation,
kernel and bundled client are unchanged. The sealed wheel SHA256 is
`ce14f2abe92479142c4208194dc2cb1fa28faf11f9df39b3f15133e6acff6f94`;
source archive SHA256 is
`1e507f3b83701f3d1f1c2eb533077322901d786d2a21d98f3287a7d7b95e4009`.
Twenty-nine compiled tests pass without skips. CPU validation calls actual
installed `process_for_engine`, preserves its timestamp, and verifies all six
bank/suffix boundaries. CUDA remains uninitialized.

Prospective recovery r8 binds that candidate, unchanged science and model
settings, short Optane paths and terminal-service guard. Its four CPU renderer,
spawn, IPC and binding checks pass. Protocol SHA256 is
`01d9fe3ad994f86b2e99f10266e2f05d7b6f4b04c31e42fa0d88b7098a04f871`,
executor manifest
`0b1875d4c9048c49790dedd2ed93f647cdc482d20e1bacadcf59aeab1ed44d72`,
and source freeze
`1f5b2e676c5cd2cc10b38941ce23d8e7ae29bd40e2594cc911c5beb0bf1f7ebb`.
It has not yet produced a GPU result. Broker execution is still explicitly
excluded, and the v2 broker namespace remains source-only pending rebuild.

## Completed controlled adapter and bundle checks

Recovery r8 subsequently passed actual GPU execution. Completion receipt
SHA256 is `b4675377428f68b8bf84783dc013fd55388642816f2cdc35551b1eb98a377116`.
All six diagnostic text/native greedy output IDs match, with identical scores
(5/6 EM; the sixth has F1 2/3 on both paths). Both canonical revisions have
EM 1. Eight actual published-bank plus native-suffix token proofs, successful
native-kernel traces, empty selection, stale-context denial and failed
preparation recovery pass. Model/config/tokenizer/source hashes are unchanged;
the owned service stopped and GPU release is verified. An independent
reviewer validated the sealed structural receipt and hashes.

The v2 broker has now been rebuilt from the sealed candidate source with
pinned Rust 1.98.1, offline and locked, on the workstation's large filesystem.
All 27 Rust tests pass. The new client SHA256 is
`47583282d2278741ded4183df7707183855366a72760eeca2df876fbaa82a3ce`.
Actual ELF requirements reach GLIBC 2.39; the target's GLIBC 2.41 loader and
private-binary `--help` checks pass without starting a service.

Candidate4 combines that client with unchanged candidate3 compiled Python
modules, kernel and notices. Only client/version/RECORD bytes differ. Its wheel
SHA256 is `1e6d6f30bf076f5ab9920b8c51c80fafb771b15bb167cdd2edf102d1af7aac38`.
The compiled 29-test suite passes without skips from a private NAS extraction,
with CUDA uninitialized. The GPU result applies to candidate3 adapter modules;
the broker rebuild is verified separately by CPU tests and target ABI checks.
No enrolled broker end-to-end test or production deployment is claimed.

All canonical NAS publications and raw results remain preserved. Only inactive
owned r8 Optane duplicates were removed after exact canonical hash verification
and repeated checks for open references; its cache was archived and verified.
The earlier failed attempts remain immutable.
