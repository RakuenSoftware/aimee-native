# Signed public-release qualification, 2026-11-03

Release candidate: Aimee Native `0.3.4`, Aimee application `v1.0.2`.
Public publication remains pending. The reviewable source changes are in
[PR #11](https://github.com/RakuenSoftware/aimee-native/pull/11).

## Artifact and source identity

The [signed manifest](artifacts/public-release-20261103/signed-manifest.json)
and [detached signature](artifacts/public-release-20261103/signed-manifest.sig)
identify seven wheels, the complete corresponding-source archive, public key,
license, data notices, release guide and verifier. Read the external signed
manifest's `source_ref` for its authoritative source-archive revision; the source
archive can contain earlier validation receipts. The initial installation tests
used source revision `bff549fe7498f4f147267bd8b64bbaefa8eefd91`, preserved in the
[initial manifest](artifacts/public-release-20261103/signed-manifest-initial.json)
and [initial signature](artifacts/public-release-20261103/signed-manifest-initial.sig).
Final documentation/source packaging does not replace any executable payload.

The [wheel audit](artifacts/public-release-20261103/release-wheel-audit.json)
passes all five namespaces and Rust adapter symbols. The
[finalization proof](artifacts/public-release-20261103/finalization.json)
records hashes of every executable/code member retained from the qualified
AGPL `0.3.4.dev0` builds. Stable packaging changes version metadata, RECORD and
third-party notices; it does not reuse the old proprietary archived executables.
GPU payload qualification from the [earlier 5080 run](aimee-5080-20261103.md)
therefore remains tied to the same executable identities.

The pinned public key and independent-trust instructions are in the
[release guide](../releases/0.3.4.md). The private key remains outside the
repository and release assets. Verification authenticates exact manifest bytes,
then every listed file's size/hash; an unexpected version, wrong signature,
symlink, path escape or unlisted asset is refused before installation.

## Clean installation and signed replacement

A fresh Debian 13 container and independent CPython 3.12.16 virtual environment
were created on the authorized `.253` test host. Runtime installation used
vLLM 0.30.0, Torch 2.13.0+cu130, Transformers 5.22.1, Triton 3.7.1 and GGUF
0.19.0. No inherited Python site-packages were used.

The [signed installation report](artifacts/public-release-20261103/signed-install.json)
passes all four operations:

| Operation | Version | Real installed checks |
| --- | --- | --- |
| Clean installation | 0.3.4.dev0 | 51/51 |
| Upgrade | 0.3.4 | 51/51 |
| Rollback | 0.3.4.dev0 | 51/51 |
| Restoration | 0.3.4 | 51/51 |

Each operation independently verified the signed bundle, installed only its
seven listed wheels offline and passed `pip check`. Every model's Rust binding,
geometry rejection, CPU positions, license and console command ran in a fresh
process. Detailed receipts: [installation](artifacts/public-release-20261103/clean-install.json),
[upgrade](artifacts/public-release-20261103/upgrade.json),
[rollback](artifacts/public-release-20261103/rollback.json) and
[restoration](artifacts/public-release-20261103/restore.json).

Reproduce with `scripts/validation/signed-install.py`; the compatible runtime
must already be installed. Replacement is not atomic, does not migrate arbitrary
older caches and requires stopping/restarting serving processes. This test uses
the qualified development candidate as its rollback baseline.

After stable-wheel serving checks, a further signed rollback installed the
development candidate and executed all 13 E2B GPU/source lifecycle checks against
another fresh Aimee v1.0.2 stack. Its
[application gate](artifacts/public-release-20261103/rollback-gpu-release.json)
passed all 28 checks, including server-side revocation and refusal of subsequent
source reads. The [model receipt](artifacts/public-release-20261103/rollback-gpu-serving.json)
records actual recall, correction and retirement. Stable wheels were then
restored. This is a restart with fresh synthetic state, not proof of migration
for arbitrary older production caches.

## Stable-wheel GPU profiles

The [initial run](artifacts/public-release-20261103/serving-initial.json) passed
all 13 checks each for 12B, Qwen 27B FP8, E2B and E4B (52 total). A separate
encoder evaluation began using the shared GPU, leaving 12.07 GiB free against
the 26B profile's 13.69 GiB reservation. That startup was refused; the original
[failed aggregate gate](artifacts/public-release-20261103/release-initial.json)
and [resource observation](artifacts/public-release-20261103/resource-contention.json)
remain preserved. Unrelated services were left running.

A requested RAM/approximately 10 GiB GPU alternative was separately tested with
8 GiB CPU offload, pinned memory, UVA enabled and explicit weight parameter
selection. vLLM reported only 0.02 GiB offloaded; the process reached 12.15 GiB
GPU use and failed a further 208 MiB allocation. The configured utilization is
not a hard process cap. This GGUF/offload profile is unsupported. The
[profile](artifacts/public-release-20261103/ram-26b-profile.json),
[model failure](artifacts/public-release-20261103/ram-26b-serving.json),
[application result](artifacts/public-release-20261103/ram-26b-release.json) and
[sanitized observation](artifacts/public-release-20261103/ram-26b-observation.json)
retain the attempt. This complements the earlier uninitialized-parameter failure
with UVA disabled; available host RAM does not establish working GGUF offload.

## Source, notices and publication gates

[Data/archive notices](../../DATASETS.md) preserve public-reference attribution
and distinguish historical candidate metadata from new AGPL release artifacts.
The [history scan review](artifacts/public-release-20261103/secret-review.json)
covers all 420 prior reachable commits and nested archives. The additional
packaging commit has [zero detector findings](artifacts/public-release-20261103/packaging-secret-review.json).
These detector reviews identified no operational credential; raw reports remain
private. Original evidence bytes and historical paths were preserved.

Notices cover reachable locked Rust crates, bundled native dependency notices,
the Rust standard library, Cython 3.3.1 and the GGUF plugin. The
[Rust inventories](artifacts/public-release-20261103/runtime-notices.json),
[client inventory](artifacts/public-release-20261103/client-notices.json) and
[Cython provenance](artifacts/public-release-20261103/cython-provenance.json)
record inputs. Third-party licenses remain applicable.
The [notice review](artifacts/public-release-20261103/notice-review.json) and
[installed-byte checks](artifacts/public-release-20261103/installed-notices.json)
cover all nine expected notice files. The
[archive inventory](artifacts/public-release-20261103/archive-inventory.json)
records member names/sizes for 104 tracked archive containers; the only model
asset-name match is a safetensors index JSON, not checkpoint tensors.

The packaging/signature regression suite passes 13 tests. This includes a
notice-collector boundary test: symlinked license files cannot copy unrelated
operator files into a public notice bundle. Recollecting the actual runtime
crate notices produced the same reviewed bytes. CPU GitHub Actions
checks on PR #11 passed. Automatic review settings were not modified.
Final qualification/cleanup receipts and publication status are recorded below.
The owner's publication steps are GitHub private vulnerability reporting,
public visibility, tag/assets and anonymous download verification. The user
requested pushing the prepared branch and handling GitHub publication separately;
source preparation does not establish that those owner actions have occurred.
