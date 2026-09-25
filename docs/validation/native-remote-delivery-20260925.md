# Native remote delivery and automatic client lifecycle, 2026-09-25

This follow-up closes the manually seeded client-catalog gap in the preceding
[production follow-up](vllm-production-20260925.md). It does **not** mark the
production release gates complete. Account authorization in these transport
experiments is an explicitly synthetic lab enrollment. The existing live Aimee
connection authenticates, but its native bootstrap route currently returns 404.

## Implemented boundary

`memory/nativepublication` supplies a mandatory-auth-resolver HTTP handler and
private glue to the actual Rust preparer. The resolver must obtain current Aimee
identity and release policy before choosing a recipient and preparation template.
It must change its scope binding when release policy changes. No query-supplied
recipient, publication ID, source path or permission is accepted. This code does
not issue a release grant or replace Aimee's enrollment policy.

The authenticated bootstrap returns the recipient/model/config identity. Selection
returns the complete ordered record/revision list and a short-lived download
lease. Downloads and final approval require current authority. Policy changes,
expiry, revocation, incomplete selections and disconnected clients fail closed.
Preparation concurrency, lease count, response sizes and artifact sizes are
bounded. SHA-256 descriptors are cached for immutable prepared artifacts; neither
these hashes nor download file operations run in attention.

The Rust host broker owns authenticated download, immutable disk admission and
coordinated worker activation. It compares the entire working set, not one record.
It verifies new download bytes, checks the existing receipt for immutable reuse,
and rechecks approval after activation. Already downloaded bytes do not grant
continued access. Credentials stay outside the inference container. Total retained
prepared-file size is bounded by the configured disk budget; exhaustion rejects
a new installation rather than silently dropping records. Automatic disk eviction
is not implemented in this broker.

The private Rust preparer now supports `--check`: fresh selection and approval
without encoding or opening its preparation cache. An optional operator-owned
`gateway` enables the existing `LocalFirst` authoritative fallback contract.
Canonical references and fresh approval remain required. Non-fact contextual
windows and incomplete context are rejected rather than silently reduced to a
partial native fact bank. This is not a claim that every complex Aimee operation
has a native tensor representation.

## Clean client: no harness-installed native memory

The compiled launcher now authenticates `connect` against native bootstrap before
saving credentials. It supports a private CA and enrolled client PEM identity.
An unsuccessful connection preserves the previously working identity.

A signed `runtime/profile.json` supplies matched model identity and resource
defaults. `run` creates an empty paused catalog, starts the private host broker,
and launches the digest-pinned unmodified vLLM image. The first request selects,
downloads and activates its working set. A poisoned runtime cannot resume through
selection; an ordinarily paused runtime can resume only after the publisher's
coordinated activation succeeds. The launcher owns child shutdown and excludes
concurrent runtimes using the same installation. No encoder is shipped.

On CT110, the harness installed only the launcher and enrollment credentials;
it did not copy a native bank, catalog or serving configuration. Signed model
release 3 installed through HTTPS, then answered all three requested facts on
both the first and reused request. Release 4 changed the signed host-memory
budget from 256 MiB to 128 MiB. Upgrade and rollback both restarted and answered
correctly. Rollback retained sequence high-water 4.

| Stage | First answer | Reused answer | Prompt tokens | Selected records |
|---|---:|---:|---:|---:|
| Fresh installation | correct | correct | 32 | 3 |
| Upgrade to release 4 | correct | correct | 32 | 3 |
| Rollback to release 3 | correct | correct | 32 | 3 |

These are six distribution/lifecycle answers, not six new independent accuracy
experiments. They complement the previous matched Gemma BF16/Q8 matrices and
32-record tests. Their roughly 1.3–3.0 second HTTP durations include answer
generation; they are not native application latency measurements.

The tested image is
`192.168.0.126:5443/aimee-native@sha256:0cf11ca631198e3ee5a76a0d2f49ade58f46d6950e721ed022447f2a74aaaf92`.
Release IDs are recorded in the raw lifecycle reports. These releases explicitly
carry `lab_only`; the production launcher still rejects that marker.

## Actual private preparation through HTTPS/mTLS

The real scoped reader, Rust preparer and approval-only path passed all transport
cases: connection, complete three-record download, cached reapproval, denied final
approval, denied cached delivery, wrong credentials, wrong recipient, preservation
of the old identity after a failed connection, and rejection of offline reuse.
The final successful transport probe includes the actual private preparation
boundary; it does not simply return a preselected JSON fixture.

The initial real-preparer transport attempt exposed a private-path decoding bug:
`root` must be decoded from private compiler output while remaining absent from
public delivery JSON. That distinction is now explicit and covered by a regression
test. The failed r2 report remains in the evidence directory; r3 passed after the
fix. A previous fixed-artifact transport test is labeled separately.

A separate fresh-publication test prepared three records using the actual CPU
compiler, then replaced the compiler command with a nonexistent executable and
selected a nonexistent cache directory. `--check` still approved the identical
three-record identity and created no cache directory. Preparation took about
39 seconds; approval-only took about 6 ms in that single run. Neither number is
a controlled latency distribution or an attention-path measurement.

The optional fallback protocol probe uses the actual local reader and Rust
preparer with a synthetic remote gateway. It checks complete three-record
fallback, partial-reference rejection, wrong authorization binding, changes
between selection and approval, missing context, extra contextual windows, and
an unconfigured gateway. It is not evidence of live production remote grants.

## Dependency audit findings

The OSV scan of the preceding resolved inventory covered 496 Python/Rust package
entries and returned advisory matches for ten entries. Raw advisory records are
preserved. Matches are not ten confirmed exploitable runtime vulnerabilities:
`paste` is an unmaintained-package advisory, OS-packaged Python modules require
Ubuntu backport reconciliation, and the inventory includes optional Rust targets.
The recorded Torch advisory lists a fix at 2.13.0; this runtime contains an
upstream ROCm 2.12 development build. Its exact patch ancestry and reachability
need reconciliation before security clearance. Flash-attention's checkpoint
loader advisory likewise requires assessment against the fixed GGUF-serving
surface. No public release gate was marked passed by ignoring those findings.

A new installed inventory was captured from the exact r9 image. This is inventory
and review evidence, not a completed license/security clearance. Production
signing/origin identity, authoritative account-to-release mapping, and actual
production API mounting remain unconfigured. The code deliberately rejects an
unbound resolver instead of substituting lab identity.

## Evidence and remaining acceptance

Raw reports, failed attempts, probe snapshots and advisory responses are in
[the evidence directory](artifacts/native-remote-delivery-20260925/).
Component validation includes Go tests (with the native delivery package under
the race detector), 13 Rust launcher unit tests and its installer lifecycle test,
19 client CPU tests with the Rust library enabled (no skips), nine private-service
tests, and two package tests. The client wheel remains compiled and source-free.

The six workstreams have the following remaining acceptance boundaries:

1. Device cache/backpressure: previously tested; automatic client uses the same
   budgeted Rust cache. Bank payload budgets are not total VRAM/RAM accounting.
2. Authoritative publication: hosted transport and real preparation are wired;
   live Aimee account/release routing still needs deployment integration.
3. Preparation/fallback: reuse, approval-only and record-only remote fallback are
   implemented; production gateway enrollment must use the existing authority.
4. Protected package: binary client and hosted encoder separation are maintained;
   dependency/license findings remain open for production release.
5. Certification: prior matched model/quantization/working-set results remain
   identified as such. This follow-up adds transport and lifecycle validation,
   not a complete new performance certification of every r9 artifact/profile.
6. Distribution: clean authenticated lab install, automatic delivery, upgrade
   and rollback pass. Production endpoint/signing identities and final release
   evidence gates are not supplied by a successful lab test.
