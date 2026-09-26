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

The service supervisor must own stale-socket cleanup after a crash. The supplied
systemd RuntimeDirectory has the same lifetime as the service and is removed on
stop/restart; the binary refuses to unlink a possibly live existing listener.
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
