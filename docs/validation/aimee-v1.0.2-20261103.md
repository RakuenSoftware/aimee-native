# Aimee v1.0.2 compatibility and documentation audit

Date: 2026-11-03. Repository baseline: `3c4aebd`; validation used the working
changes documented here. Target application: **Aimee v1.0.2**, commit
`204d4e55828993a7683cb2610fb4165e44cabb9f`, verified as the latest published
release on this date. [Release target](../../dependencies/aimee-release.json).

The enrolled native-memory interface passes against the real released application.
All five freshly built model bindings connect through its ordinary thin-client
enrollment. The current runtime consumes `POST /v1/native/primitive`; the retained
Go research utilities use a separately pinned historical source dependency.

## Executed checks

| Check | Result | Evidence |
|---|---|---|
| Rust CPU runtime | 39 passed | [CPU suite](artifacts/aimee-v1.0.2-20261103/cpu-tests.log) |
| Rust launcher/model client | 28 passed | [Launcher tests](artifacts/aimee-v1.0.2-20261103/launcher-final-tests.log) |
| Go research commands and race suite | All packages passed; six commands and fixture issuer built | [CPU suite](artifacts/aimee-v1.0.2-20261103/cpu-tests.log) |
| Python adapter/reference | 62 passed, no skips | [CPU suite](artifacts/aimee-v1.0.2-20261103/cpu-tests.log) |
| Packaging and source staging | 5 passed | [CPU suite](artifacts/aimee-v1.0.2-20261103/cpu-tests.log) |
| Source CLI configuration | 6 passed | [CPU suite](artifacts/aimee-v1.0.2-20261103/cpu-tests.log) |
| Source vLLM bridge CPU modules | 85 passed, 2 explicit skips; three upstream-dependent modules excluded | [Results](artifacts/aimee-v1.0.2-20261103/bridge-cpu.json), [log](artifacts/aimee-v1.0.2-20261103/bridge-cpu.log) |
| Fresh wheels | Five model wheels plus shared runtime built and finalized | [Build](artifacts/aimee-v1.0.2-20261103/build-manifest.json), [finalization](artifacts/aimee-v1.0.2-20261103/finalization.json), [audit](artifacts/aimee-v1.0.2-20261103/model-audit.json) |
| Installed wheels / real Rust ABIs | 51 passed | [Results](artifacts/aimee-v1.0.2-20261103/installed-models.json) |
| Installed vLLM version guard | Eight accepted/rejected version cases passed | [Test](artifacts/aimee-v1.0.2-20261103/compiled-interface.log) |
| Small-model shared K/V capture | 5 passed per small model | [E2B](artifacts/aimee-v1.0.2-20261103/gemma4-e2b-fresh-capture.json), [E4B](artifacts/aimee-v1.0.2-20261103/gemma4-e4b-fresh-capture.json) |
| Device-kernel compilation | 21 kernel/target combinations compiled; zero executed | [Results](artifacts/aimee-v1.0.2-20261103/kernel-compile.json) |
| Disposable mTLS / broker | Passed pin, rotation, source replacement and denial checks | [Log](artifacts/aimee-v1.0.2-20261103/tls-client-tests.log) |
| Actual released Aimee | 27 checks passed; stack cleanup passed | [Results](artifacts/aimee-v1.0.2-20261103/release-result.json), [verdicts](artifacts/aimee-v1.0.2-20261103/release-verdicts.log) |

The two source-bridge skips are actual GPU attention execution and the installed
vLLM request-schema check. The excluded modules require installed upstream vLLM
middleware, the upstream GGUF loader, or its GPU worker/hybrid model state. CPU
fixtures exercise adapter/control contracts; they do not certify those upstream
runtime implementations. The compilation matrix covers CUDA SM80/89/90/120 and
HIP gfx942/1100/1201 with attention and two decoder kernels.

## Real application and environment

Testing ran on `.252` / `pvetest`, an Intel Alder Lake-N host without a supported
CUDA/ROCm GPU. Source tests and wheel builds used a fresh Python 3.12 container.
The real application ran in a separately created Debian 13 guest with standard
Docker, using the shipped v1.0.2 Compose and Vault bootstrap helpers unchanged.
Both the application API and dashboard were restricted to guest loopback.
[CPU environment](artifacts/aimee-v1.0.2-20261103/cpu-environment.json) and
[standard Docker / exact image identities](artifacts/aimee-v1.0.2-20261103/standard-docker-environment.json).

The application test used a temporary owner and normal invitation/certificate
enrollment. It verified populated unique source records, committed correction
and revision changes, application restart, and revoked-client refusal. Each of
the five installed model bindings authenticated through its real compiled shared
client. Content consisted of two synthetic personal-memory records. The test
used Aimee's native memory backend and ordinary source-release route.

No Gemma/Qwen checkpoint or GPU inference was used. The normal Aimee embedder
image was part of its application stack. The full Python structural suite creates
random tiny Qwen models. No production account, memory store, grant or service
was modified. Organization-memory release remains a separate core contract.

The local wheel version is `0.3.4.dev0`, an unpublished validation identifier.
Wheels include AGPL metadata and exact LICENSE bytes. Their checks cover native
symbols, binding hashes, co-installation, model-geometry rejection, CPU positions,
console entry points and dependency metadata. Finalization preserved executable
payload bytes. These unsigned development builds require their own GPU lifecycle,
complete dependency/notice, signature and clean-download gates before release.

## Corrections made

- Initial standalone `connect-aimee` used a separate CA-trust client, while later
  reads used the shared exact-leaf pin policy. It now consumes the same enrolled
  profile reader and pin verifier as the model client. The TLS test now models
  the real profile: an owner-only `remote-ca.pem` containing the server leaf.
  It covers an IP endpoint with a different SAN, client/token rotation, wrong
  pin refusal, changed source and denied access. TLS handshake signatures remain
  verified. The real release check also passes with this corrected executable.
- The root Cargo manifest now declares the five adapter features already selected
  by the wheel builder, allowing direct feature selection without unknown-feature
  warnings.
- The model builder stages its Rust/code inputs explicitly, avoiding workspace
  caches, evidence and model files. A source-staging regression test covers that
  boundary and the historical-snapshot toolchain fallback. The default source is
  this repository.
- Source tests now isolate mocked worker/sampling dependencies and runtime metadata.
  The upstream request-schema assertion is a separate explicit dependency check.
  The unbound source module's existing behavior is retained and documented.
- The legacy Go dependency is extracted from its exact historical Git revision into
  an ignored directory, without switching or editing a sibling checkout. Current
  Aimee source has retired that raw export/restriction API:
  [inventory](artifacts/aimee-v1.0.2-20261103/legacy-api-inventory.json).
- Current installation, protocol, configuration, operations, source builds and
  reproduction commands now have dedicated guides. A local-link checker covers
  the maintained documentation entry points and runs in CI. Historical evidence,
  source archives, paths and result hashes remain unchanged.

## Failed attempts and their disposition

The first filesystem race run hit the stream test's five-second deadline while
image extraction and release compilation competed for the container filesystem.
[Original output](artifacts/aimee-v1.0.2-20261103/cpu-tests-contended.log) is retained.
The complete suite passed with fixture temporary directories on the task's
RAM-backed bind. This is a test filesystem detail, not a storage-performance or
power-loss durability result.

The host's Docker-LXC compatibility layer initialized a home volume as root-owned
and represented named tmpfs volumes as disk storage. The released application
correctly refused model identity initialization. A diagnostic true-tmpfs bind
passed that check but database readiness still failed in that backend. Those
attempts were destroyed; the passing release check used standard Docker in a
fresh guest. No core guard was disabled. The initial standard-Docker harness read
only stdout when bootstrap credentials were on stderr; it now captures both
privately. [That failed harness result](artifacts/aimee-v1.0.2-20261103/release-harness-stderr-failure.json)
is retained separately from the passing run.

## Reproduce and remaining scope

Follow [development](../development.md) for the CPU suite, installed wheel checks,
compilation-only matrix and real-release harness. [Usage](../usage.md) documents
normal installation and operations; [compatibility](../aimee-compatibility.md)
records the application versus legacy source boundary.

Fresh GPU inference, all upstream vLLM/GGUF integration tests, signed artifact
lifecycle and public download/install checks remain release gates. Earlier GPU
results belong to their recorded artifact hashes. Temporary guests, containers,
images, volumes, networks, credentials and scratch files created on `.252` were
removed and their absence verified. The host Docker Hub image required its
canonical `docker.io/library/python:3.12-trixie` reference for removal;
[the initial receipt](artifacts/aimee-v1.0.2-20261103/cleanup-first-pass.json)
records that intermediate state. The final
[cleanup receipt](artifacts/aimee-v1.0.2-20261103/cleanup.json) confirms removal.
