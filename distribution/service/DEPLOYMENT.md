# Private native delivery behind Aimee

The maintained bridge belongs to Aimee; the service and all preparation code
belong to `aimee-qwen`. The bridge requires Linux and runs **after** Aimee's
ordinary per-request bearer, certificate-grant and capability checks. It forwards
only the resulting principal, hex encoded, over an operator-owned Unix socket.
It does not pass client identity headers or credentials to the preparation worker.

Build `cmd/aimee-native-delivery` against the pinned authoritative dependency in
`dependencies/aimee-source.json`. Deploy the bridge-enabled Aimee server and the
private service under the same service UID. The supplied systemd unit uses the `aimee` account; match its numeric UID
to the frontend, including container user-namespace mappings. The delivery
service defaults its expected peer UID to its own UID. Share only `/run/aimee-native` with the frontend, set
`AIMEE_NATIVE_SOCKET=/run/aimee-native/delivery.sock`, and keep the directory 0700
and the socket 0600. No new public port is needed. Disable the feature by removing
that environment setting. Ordinary Aimee routes remain available.

Install an operator-owned, non-group/world-writable `/etc/aimee-native/bindings.json`:

```json
{
  "schema": 1,
  "bindings": [{
    "principal": "<principal attested by Aimee>",
    "release_policy": "/etc/aimee-native/releases/recipient.json",
    "publisher_uid": 1000,
    "preparer": {
      "binary": "/opt/aimee-native/bin/native-prepare",
      "template": "/etc/aimee-native/preparation/recipient.json",
      "profile": {
        "schema": 1,
        "recipient": "<released recipient>",
        "model": "<certified model identity>",
        "model_config_sha256": "<64 lowercase hexadecimal characters>"
      }
    }
  }]
}
```

The release file is Aimee's `MemoryReleasePolicy`, the same current policy used
by the scoped publisher. `publisher_uid` names that policy's authorized local
consumer; it is separate from the frontend peer identity. The preparation template
must use that recipient's publisher/reader and the certified model. This registry
routes existing grants; it neither issues a grant nor infers permission from
search access. Replace files atomically. Every request rereads current bindings
and validates the current release with Aimee's policy implementation. Leases also
bind the model, recipient, preparation configuration and release digest.

On expiry, withdrawal, missing policy, binding changes or disconnected authority,
delivery is denied. A final post-download approval is still required. Previously
downloaded bytes do not restore permission. Download checks and policy file reads
are control-plane operations; none run in attention.

The service supervisor owns stale-socket cleanup after a crash. The supplied
systemd unit preserves the frontend-mounted directory and recovers only a dead
owned socket; the daemon itself refuses to unlink an existing listener.
The private compiler and its dependencies are server-side deployment inputs,
not customer-package contents. Keep prepared artifacts in `/var/lib/aimee-native`.

Validation must include the live enrolled account, current release and deployed
Aimee frontend. `test_native_bridge.py` exercises the actual C bridge and Go service
with temporary grants; it is deliberately not labeled production authorization.

## Runtime dependencies

The client image uses `distribution/container/runtime-requirements.lock`. Download
its public wheels with the target runtime's Python 3.12 and `pip download
--only-binary=:all: --require-hashes -r runtime-requirements.lock`, then give that
directory to `distribution/container/context.py --runtime-wheels DIRECTORY`.
The context generator checks every wheel's metadata and hash and rejects missing,
extra or mismatched packages. The image installs them without network access.
Existing image inventories retain superseded OS distribution metadata; use the
recorded active-import paths as well as inventory versions when reviewing findings.

## Managed preparation on a separate host

`remote_compile.py` keeps the CPU model and private encoder on the preparation
host. Use a dedicated SSH account, a pinned host key, and an `authorized_keys`
entry with `restrict,command="... remote_compile.py worker --config ..."`.
The frontend command is fixed operator configuration; requests cannot supply an
SSH destination, executable or model directory. Model identity, request size,
artifact lengths and a serial preparation lock are enforced before returning
artifacts. The caller's Rust preparer performs admission and current-publication
reapproval. None of these operations run in attention.

The worker configuration supplies `model_revision`, `state`, `library` and a
fixed `compiler` argv. The frontend supplies a fixed `command` argv. Protect
both configurations against group/world writes. Install the compiler, publisher
module and publisher-enabled library only on this private host. The client
package contains the consumer library extracted from the certified image.

The publisher service consumes an encrypted systemd credential named `database`.
Use a separate read-only database login with CONNECT permission and access only
to the released source rows. Its schema/search path, TLS server name, recipient,
base image and Aimee release policy must agree. The example units use the
`native-preview` recipient and must be provisioned for the actual recipient.
`credential_exec.py` passes the credential directly to the owner-dependent Go
publisher without a shell or a credential on the command line.

## Restart and authority lifecycle

The frontend bind-mounts `/run/aimee-native`. Preserve that directory's inode
across delivery restarts. `RuntimeDirectoryPreserve=yes` and the startup-only
`recover_socket.py` remove a dead owned socket without deleting an active socket,
a symlink or a regular file. Do not replace the mounted parent directory.

The follower withdraws its model-facing image before starting and after stopping,
including an unclean process exit. Delivery is bound to that follower's lifetime;
the follower brings delivery back after it restarts. Cached bytes remain separate
from current approval. `withdraw_image.py` invokes the existing owner CAS command.

The restricted fallback gateway mounts only Aimee's Unix socket. Install the
matching `.path` watcher for the **host source path** so replacing Aimee's listener
restarts the gateway and refreshes the socket bind. This prevents a pinned old
socket inode from leaving fallback unavailable after a frontend restart.

Aimee 0.4.5 needs the narrow owner-side restricted-search backport as well as the
C delivery bridge. Ordinary search without an enforced restriction receipt is
rejected; do not forge the receipt in a proxy. The source owner filters permitted
IDs before ranking and limiting, then returns the enforced receipt. These changes
belong to Aimee; all preparation and serving integration remains in this repository.

The deployed frontend performs its existing audit-ledger verification before
opening its listener. Set rollout readiness deadlines from the actual ledger
size and observed startup duration. Do not disable verification to shorten a
rollout. The native bridge candidate needed more than the initial 90-second
window on the existing 5.9 GB ledger; rollback was exercised and the longer
readiness window admitted the healthy candidate.

### Persisting the deployed frontend

On the controlled preview host, `compose.override.yaml` points to the explicit
`compose.native-preview.json` overlay. Ordinary `docker compose up` therefore
preserves the bridge image and owned socket mount. The original image and
`compose.native-rollback.json` remain available for deliberate rollback. Do not
replace an existing deployment override without merging its settings.

### Resident private preparation

`resident_compile.py` keeps the CPU model/tokenizer loaded. By default it creates
a fresh KV cache; optional Rust-planned reuse clones an approved exact prefix. It is a private compiler-host service, never a client
component. Install `aimee-native-compiler.service` and an operator-owned
`resident.json` with `model`, `model_revision`, `library`, `state`,
`max_memory_tokens` and `threads`. The documented host uses 12 CPU threads and a
60 GiB service memory ceiling. It trades persistent model residency for avoiding
per-request Python/model startup. Model-specific preparation still takes seconds.

After the daemon reports `ready`, add `resident_socket` to the existing forced-SSH
worker configuration. Preserve the old worker configuration for rollback. The
worker still checks the exact model identity and streams the same bounded
artifacts; it does not accept client paths or commands. The Unix socket is 0600
and checks the peer UID. Jobs are serialized, outputs are daemon-owned temporary
files, and failures do not become prepared-cache hits. Remove `resident_socket`
to return to the one-shot compiler. A service restart reloads the model; it does
not grant continued authority to old publications.

The Rust preparation cache, authorization revalidation, ordered record keys and
complete-working-set requirements are unchanged. Separate preparation timing
from storage activation and generation. Do not run CPU preparation benchmarks
concurrently with model startup and describe the result as isolated latency.

### Rust-planned preparation reuse

The private compiler can optionally load `reuse_library`, built with
`--no-default-features --features preparation-service`. This library is private
service code and must not enter the client package. Rust binds the previous
complete computational state to recipient/view/model/runtime/encoding/position
identity and requires equal total token length before permitting prefix reuse.
The framework creates a fresh cache from cloned prefix tensors; no prior request
cache is mutated. The final publication still contains every selected record.

Only one previous state is retained, bounded by `max_memory_tokens`. Length or
scope changes force full evaluation; unsupported cache layouts also fall back.
Removing `reuse_library` disables reuse while preserving the resident model.
Aimee authorization and preparation-cache publication checks remain mandatory.

The daemon logs only token counts for reuse (`tokens`, `reused_prefix_tokens`,
`evaluated_tokens`), alongside elapsed times. Selected text and tensor contents
are not included in these events. Changing an authorized view forces full
preparation, including when the view changes as part of a knowledge update.

### Larger-model preparation profiles

Gemma 26B and Qwen 27B use the private `bounded_text_fp32` backend. Their
recorded successful smoke comparisons use `position_policy: "negative"`.
Set the resident configuration explicitly:

```json
{
  "preparation_backend": "bounded_text_fp32",
  "compute_dtype": "float32",
  "position_policy": "negative",
  "encoding_revision": "bounded-fp32-negative-v1"
}
```

These fields supplement the operator-owned checkpoint path, library, state
path, thread budget, token budget and exact `model_revision`. Match
`position_policy` and `encoding_revision` in the Rust preparation template.
The resident daemon rejects mismatches before evaluating the model. Its logs
include the evaluated memory-position policy, but never selected text. Bind
release/profile identity to the checkpoint configuration and encoding revision;
do not reuse artifacts from the earlier nonnegative Qwen experiment.

This backend uses supported CPU offload hooks and evaluates a complete selected
working set in FP32. It exports BF16 native banks and publishes through the
existing Rust library. Do not configure `reuse_library` for this backend:
prefix reuse is not implemented there. Larger-model checkpoint preparation is
private server work; it is not shipped in the client image and is not a
microsecond memory-application operation. Validate the specific checkpoint
through the resident socket before changing the live preparation binding.

The signed client `runtime/image.json` supports `gguf_matrix_backend` and an
optional `mm_proj` artifact path. The tested Gemma 26B Q8 profile uses `triton`;
the Qwen 27B Q8 profile uses `cuda` (the plugin's fast-kernel selector, including
on ROCm) with its signed projector GGUF. The launcher verifies projector
membership in the release manifest and resolves its installed path. These
settings belong to the release; the user only chooses the model and connects
to Aimee. They do not imply that all larger-model release gates have passed.

### Multiple private preparation profiles

The fixed SSH worker may retain its existing `model_revision` and
`resident_socket` while adding a `profiles` map from exact model identity to an
absolute, operator-owned worker configuration path. Each selected configuration
must carry the same model identity and cannot contain another routing map.
Unknown identities, writable configurations and mismatched identities are
rejected before contacting a compiler. Requests cannot supply paths or commands.
The existing default model follows the original route.

This routes private preparation only. It neither grants memory access nor
changes account enrollment: the Aimee release policy, preparer template and
bootstrap profile must still agree on the selected model. Stage new profiles
with isolated cache roots and validate approved preparation and reuse before
changing a live account binding.
