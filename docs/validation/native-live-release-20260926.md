# Controlled private preview: live Aimee and signed distribution

This record completes the six-workstream **private-preview** acceptance scope
for the certified Linux/ROCm dual-7900XTX profile. It is not a public release,
all-hardware certification, or a claim that cold memory activation takes
microseconds. Earlier lab records remain intact; their credentials and signing
keys were not promoted into this release.

## What is deployed

The actual Aimee v0.4.5 frontend now mounts the authenticated native-delivery
bridge. Aimee retains account authentication, authoritative source publication
and restricted fallback selection. All native preparation, compilation, delivery,
packaging and runtime implementation remains in aimee-qwen. The memory-owner
restriction backport applies approved references **before** search limits and
returns the enforced receipt; the native gateway does not fabricate approval.

The live source is an explicitly approved set of three synthetic canaries stored
through the normal Aimee API. It is not a release of unrelated user memory or the
entire general knowledge base. The canary publication has a seven-day explicit
expiry; operators must renew or replace the approved release for longer use.
It does not silently extend itself. A dedicated read-only database role can select
only the three approved source rows. The enrolled client has a separate mTLS
identity and bearer; the workstation's original bearer was not copied to the
compiler or client.

The compiler runs privately on a separate CPU host using a restricted SSH key,
pinned host key, fixed command, bounded transport, serialized work and process
cleanup. It returns the complete ordered working set. Encoding and preparation
are absent from the client package. Aimee policy, record revisions, selection
order and model/runtime identities remain part of preparation identity.

## Acceptance evidence

| Workstream | Evidence and result |
|---|---|
| Cache/backpressure | Exact r13 BF16 and Q8 certification: 480/480 answers across matrix, concurrent and streaming requests; 32-record Q8 suite: 112/112. Per-rank native peak 9,551,872 bytes under the pressure-test budget; total cgroup peaks 28.35/27.52 GB under 48 GiB. |
| Live authority | Enrolled request 200; invalid bearer 401; unbound certificate and forged principal 403; revoked certificate rejected during TLS. Expired, withdrawn and disconnected publications deny cached preparation. |
| Preparation and synchronization | Real source replacement changed the view/key and produced the new vault value on the GPU. Reuse, recovery and actual owner-restricted fallback passed; all three records reached native consumption. |
| Protected package | Exact r13 compiled consumer audited; explicit 18-file artifact allowlist, model and dependency notices, no hosted encoder or credentials. Image remains unmodified pinned vLLM plus the private extension. |
| Model/performance certification | 592/592 controlled engineering answers, complete selected records, long conversations, quantization, resource telemetry and separated cold/warm/attention timing. These are engineering workloads, not population accuracy. |
| Signed distribution | Dedicated non-lab release identity and immutable registry digest; normal launcher fresh install, update and rollback each passed 2/2 GPU answers against live Aimee; release high-water sequence remained 2 after rollback. |

The service supervision probes passed real process termination: delivery's socket
directory survives restart, the owned stale socket is recovered, follower death
withdraws the current image, and fallback reconnects after the upstream socket
changes. These operations occur outside attention. The deployment's normal
Compose override preserves the bridge and socket mount.

## Exact release

- Model catalog ID: `gemma4-12b-q8-native` (Gemma 4 12B Q8_0 GGUF).
- Upstream vLLM commit: `ced6857afa0ea7b2e3f0846a62e1394e90f15607`.
- Image: `192.168.0.126:5445/aimee-native@sha256:4c1bbba066a23f55ff18c0d27569833879be4073cc43273cd3990ddeb09cc52f`.
- Exact image config: `87d4ee28688c4862d2fe0bb8980fd4375d91950155c6699736c47a2bb93fc8d6`.
- Artifact-set SHA-256: `74f4c73376b35081c2eb5d62a4b1d9671c53d2fa3e9b75334cf10326577888d3`.
- Release public key: `5d14ca247841adcc1130a4d95b82ead12ba699c03f2ba45f2f47524abde0c6c2`.
- Origin: `https://192.168.0.126:8445` on the private network.

The signed manifest IDs are
`2da7163d8b338b7e243a4adfb39cf4bf041517101a662d82d7e2914dd04fe863`
(sequence 1) and
`ee1f20cfcb2da696ad8559968e6949aa2462749f5ebbce91ed7ad09cb3ab25c2`
(sequence 2). Rollback restored sequence 1 while the active vault value stayed
28461 and the anti-downgrade high-water mark stayed 2. The client was then
restored to sequence 2.

Gate reports bind the exact artifact set, model and runtime commit to retained
private evidence. The clean candidate exercised identical artifact bytes; final
normal-launcher results cover the signed manifests. Release sequence 2 uses the
same runtime/artifacts to exercise installer transaction and rollback behavior;
it does not imply a new model or performance result.

The bootstrap binary is available under
`/bootstrap/linux-x86_64/aimee-native` with a detached Ed25519 signature and
`identity.json`; SHA-256 is
`2fab42f593e26a51334c3e34cdfc5ee7c9e3e87932b68a1573450ba6c32df693`.
The public CA and verification key are retained with the evidence.
Distribute them through the trusted operator channel rather than
trusting a key downloaded beside an unverified binary.

## Client operation

Provision the compiled launcher and an enrolled account identity through the
private operator channel. The supported host needs Podman, ROCm-compatible GPU
access, two 24 GiB 7900XTXs, 48 GiB available RAM and disk space for the model,
container image and two retained releases. The launcher embeds the release public
key/CA. Neither a compiler nor a source checkout is required on the client.

```sh
aimee-native install gemma4-12b-q8-native
aimee-native connect https://your-aimee-endpoint \
  --ca-file account-ca.pem --client-identity account-identity.pem < scoped-token
aimee-native run
```

The private test deployment uses `https://localhost:8743` with
`--connect-address 192.168.1.100:8743` to preserve its existing certificate name.
TLS verification stays enabled. The normal loopback OpenAI-compatible API is
available on port 8080. Repeating `install` applies a newer signed release;
`rollback` restores the previous runtime without rolling back current memory
authority. No caller-selected internal bank IDs or hand-installed banks are
required. The launcher pulls the immutable image with installation-local CA
trust, preserves normal container security and sets the 48 GiB memory limit.

The first bootstrap download exposed a missing CA key-usage extension under
Python 3.13's strict validation. The CA certificate was corrected with the same
key, the launcher rebuilt and re-signed, and strict TLS plus detached signature
verification passed. The runtime artifact set did not change. A final GPU run with the rebuilt
launcher also passed 2/2; the signed lifecycle checks total **8/8** answers.
All four native services and the actual Aimee frontend were healthy at closure.

## Measurements and limits

Preparation reuse was 12.642 ms including the control-plane subprocess and
approval. A previously unseen **ordered** fallback working set took 42.617 seconds
including CPU preparation and generation; its repeat took 1.888 seconds including
generation. Changing order intentionally changes the cache key. This is not a
microsecond preparation path.

Three-record cold activation median/p95 was 26.65/27.68 ms; warm activation was
6.35/6.60 ms. The 32-record bank measured 122.36/130.17 ms cold and 31.47/33.13 ms
warm. Resident lookup median was 0.54 microseconds. Attention dispatch and
end-to-end inference are separate again. **The cold-path microsecond target is
not met**, and no universal latency advantage is claimed.

In the matched stream tests, native memory used 36 prompt tokens against 89 for
text, or 948 against 1,001 after 48 dialogue pairs. The wide bank saved 586 prompt
tokens per request. Native memory still consumes memory bandwidth, storage and
attention computation even though it does not occupy those prompt positions.

The private-preview package review retains known dependency limitations, including
the isolated TorchScript crash outside the certified text interface and unpatched
OS findings without an available vendor fix. It does not clear public container
redistribution or arbitrary checkpoint execution. Binary packaging raises the cost
of reconstruction; it cannot guarantee secrecy on a customer-owned machine.

## Records

See [the live evidence directory](artifacts/native-live-release-20260926/), its
SHA-256 index, and [the exact-image certification](native-production-20260926.md).
The live rollout does not revise or erase earlier failed experiments. No signing
private key, account bearer, database credential or model weight is stored here.

## Performance follow-up

The subsequent [latency follow-up](native-latency-20260926.md) preserves this
release as the baseline and records packed activation, resident preparation and
the next signed release. The measurements above remain the original results.
