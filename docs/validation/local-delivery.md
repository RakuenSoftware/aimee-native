# Publisher-controlled local KB delivery

Date: 2026-09-20. Builds on [direct published reads](published-local.md).

The publisher can now install, replace, withdraw and clean up a recipient's
local image through explicit operations. The model and adapter remain read-only.
These operations transport knowledge already approved by Aimee; they do not
evaluate permissions or add local authorization to reads.

## Implemented behavior

`install-published` copies only objects reachable from a compiled recipient
snapshot. Unreachable publisher files, previous generations, credentials and
source-side extras are not delivered. The complete staged copy is checksum-checked
and opened before the active pointer changes. The destination must be a new or
managed delivery directory, never an arbitrary source directory.

Replacement uses an expected-generation comparison and an atomic pointer change.
A shared/exclusive filesystem lock coordinates pointer/open/cleanup, only during
request pinning and publication. Ordinary lookups acquire no publication lock.
Existing requests retain their open snapshot files. New requests see the new
generation; superseded snapshot directories are unlinked by the publisher.

`withdraw-published` removes the active pointer and payload directories.
`prune-published` recovers abandoned staging or obsolete generations without
deleting the active generation. Existing requests may finish against already-open
files; immediate withdrawal still requires the publisher to stop active consumers.
This is filesystem cleanup, not secure erasure of SSD blocks or prior outputs.

The reader closes its previous files on replacement or failed pin. The Rust
adapter now drops reusable native K/V cache entries when its generation changes
or a new request finds the publication unavailable. No model training, neural
selection, or memory-encoding changes were introduced.

Local publication and remote Aimee identity are now independent. A local hit never
contacts the gateway. On the first actual miss in a request, the adapter obtains
the existing remote binding and uses it for fallback and reference resolution.
Changing the local KB no longer requires that the remote gateway have the same
publication ID. Remote result/binding mismatches still fail the request. This
preserves the existing remote authorization boundary without making it a
prerequisite for reading delivered local data.

## Commands

Run these as the trusted publisher, after Aimee has compiled the authorized
recipient snapshot. `reader-gid` supplies filesystem read access to the model's
OS group; it does not decide which knowledge the model is allowed to receive.

```sh
# Initial install; output directory must not already be an unrelated directory.
aimee-memory-image install-published \
  --root /publisher/compiled-recipient \
  --output-root /model-data/recipient --reader-gid 989

# Replacement; OLD_VIEW comes from the prior operation's JSON result.
aimee-memory-image install-published \
  --root /publisher/next-compiled-recipient \
  --output-root /model-data/recipient --expected OLD_VIEW

# No local credentials or grant files:
aimee-memory-image serve-published --root /model-data/recipient

# Publisher withdrawal and interrupted-publication cleanup:
aimee-memory-image withdraw-published --root /model-data/recipient --expected CURRENT_VIEW
aimee-memory-image prune-published --root /model-data/recipient
```

The last command assumes the publication has been withdrawn; when one is active,
pass `--expected CURRENT_VIEW`. These commands intentionally do not download an
arbitrary URL or grant themselves access to an Aimee source store. Authenticated
network distribution and production automatic exporter/event wiring remain
integration work. The new operations are the local installation endpoint for
that publisher, not a new Aimee server or model-write API.

## Full-corpus measured test

On `.253`, the actual release Rust binary and Go reader ran as the unprivileged
`aimee-auth-native` account. No gateway was available at its configured path.
The complete public corpus contained 13,261 records, with approximately 12.7 MB
of compiled objects. All **13,261/13,261** reads returned exactly the expected
content and canonical namespace/ID/revision.

| Operation | Observed time |
|---|---:|
| Initial installation, including integrity validation | 0.714167 s |
| Replacement and obsolete-file cleanup | 0.722854 s |
| First request opening the replacement index | 314.929797 ms |
| Publisher withdrawal and payload cleanup | 4.397806 ms |
| Steady Rust → local lookup, median | 0.0562815 ms |
| Steady Rust → local lookup, p95 | 0.119638 ms |

The 256 timing queries use the same seed as the prior local benchmark. Lookup
measurements are warm and serial. Publication timing excludes canonical source
construction and Aimee approval/compilation; it includes copying, validation,
fsync and cleanup. This version copies a complete snapshot, not an incremental
wire transfer. A publisher holds the exclusive lock during installation, so a
new pin can wait for that operation; an already-pinned request remains usable.

The update changed the SSH entry to an explicitly labeled synthetic test value
and removed the telnet entry in an isolated publisher copy. The public source
artifact stayed byte-identical. The existing request still read the original
entry; the next request read the replacement. The retired entry was not served.
Direct scanning found neither obsolete factual body in the recipient directory,
and withdrawal left zero snapshot directories. No private production memories
or production services were involved.

The first launch attempt failed before any lookup because the unprivileged
libtorch process inherited inaccessible `/root` as its working directory. The
driver now launches from the readable recipient directory. That failed
installation was withdrawn before the successful rerun.

## Verification and limits

Go race tests cover physical cleanup, unchanged active data after corrupt input
or a stale publisher operation, raw-source rejection, abandoned-stage recovery,
and four concurrent readers during ten replacements. Recovery tests simulate
abandoned directories; this is not a power-loss fault-injection campaign.

Five real Rust/Go integration tests cover credential-free local reads, managed
updates/withdrawal, absent fallback, direct directory replacement compatibility,
and independent remote fallback across local updates. The remote portion uses
an explicit Unix protocol fixture; it is not a new live Aimee policy test.
Historical gateway tests also remain passing. A release build with libtorch
passes the native-cache lifecycle test and four canonical-identity tests.

The transport benchmark preceded the final remote-binding separation; its binary
hashes are recorded in `summary.json`. Final integration tests exercise that
separation. No new 27B answer-accuracy claim is made in this step; the last full
model result remains 32/34 from the preceding report.

[Raw results](artifacts/local-delivery-2026-09-20/) and
[the reproducible driver](../../benchmarks/general_kb/delivery_probe.py) are kept
with the Qwen integration repository. Model-independent implementation remains
in Aimee's sparse-image package and CLI.
