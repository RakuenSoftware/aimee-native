# Distribution fulfillment work record

This record separates collected delivery material from unresolved work. The
historical count of 79 uncollected OS source/version pairs is an inventory
count, not 79 independently established release blockers. Missing files named
`LICENSE` or `copyright` likewise do not establish missing component notices.

## Material ready to accompany the candidate

- [Consolidated notices](artifacts/consolidated-notices-20260928/): 588 unique
  texts, 591 OS package records, all 277 third-party Python package references,
  and shared license texts. Aimee's private package notice ships separately.
  Upstream-only qualifications for Mooncake and OpenTelemetry remain explicit.
- [Collected OS source bundle](artifacts/larger-source-collection-20260928/bundle.json):
  818 files, approximately 1.38 GB, covering 263 exact source/version pairs.
  This includes the historical compiler, curl and PyJWT sources resolved after
  the first index scan. Archive hashes and source-file checksums are retained.
- [ROCgdb source and build identity](artifacts/rocgdb-source-collection-20260928/):
  the matching ROCm release source tree and its build instructions are retained.
  This does not claim reproducible binary identity.
- Existing Rust dependency notices and model-specific notices remain bound to
  the signed candidate artifacts.

## OS notice reconciliation

[Installed-file inspection](artifacts/os-notice-relationships-20260928/) and
[component mapping](artifacts/os-notice-reconciliation-20260928/) resolve the
meaning of the 28 missing package-local notice filenames:

| Packages | Evidence and treatment |
|---|---|
| 23 split SDK/runtime packages | Their component notices are already retained. The mapping records exact installed versions, package metadata and notice hashes. It is not a file-by-file licensing determination. |
| 3 ROCm metapackages | Each owns only a nine-byte version marker. Dependencies retain their own records. |
| AQLProfile | Matching ROCm release notice collected separately. |
| Broadcom `bnxt-rocelib` | Header notices retained, including differing SPDX expressions. Review of the compiled vendor payload remains open. |

The remaining source inventory includes permissively licensed components and
packages already distributed as source/header files. A blanket requirement to
obtain every upstream source tree is not used as a release criterion. Python's
notice explicitly distinguishes GPL compatibility from distribution under GPL;
a keyword match against that notice cannot determine a source-delivery gap.

## Work still required for external distribution

1. Finish the compiled vendor payload review for `bnxt-rocelib`, using its own
   notice and installed-file evidence. Do not assume one header covers every
   binary or replace its exact version with unrelated upstream source.
The source/version inventory is now reconciled below. The unresolved vendor
payload remains explicitly open; the inventory reconciliation is not blanket
legal clearance of every shipped file.
Recipient delivery of the collected notices and source archives is complete on
the controlled origin, as verified below. This establishes access to the collected
material; it does not resolve the two remaining component-review items.

This work is separate from the GPU/runtime functional gates and from the
aspirational microsecond performance target. Normal signed lifecycle evidence
supports the controlled private candidate; this record does not announce public
availability or claim completed external fulfillment.

## Controlled-origin staging

`distribution/release/stage-distribution-addenda.py` verifies the three fixed
archive digests before exposing them at `/third-party/20260928/` on the existing
controlled TLS origin. It leaves signed model manifests and channels unchanged.
`verify-distribution-addenda.py` checks the served manifest against the local
staged bytes, then downloads every archive with certificate validation and
checks its complete size and SHA-256. The [delivery test passed](artifacts/distribution-addenda-delivery-20260928/delivery-verification.json)
for all three complete archives (1,444,925,152 bytes total). This proves recipient
access on the controlled origin, not completeness of the collected material.

The [AQLProfile/component notice supplement](artifacts/supplemental-notice-delivery-20260928/)
is also served at `/third-party/20260928/supplements/`. Both complete files passed
TLS download, byte-count and SHA-256 verification. This supplements the existing
archives without replacing their verified bytes.

## Exact Python source supplement (29 September)

The previously unavailable Debian patch/build archive for installed
`python3.12 3.12.13-1+jammy1` was recovered from its exact Launchpad publication.
Together with the retained DSC and upstream archive, all three files match the
recorded sizes and SHA-256 values; the source archives match the retained DSC.
The historical failed retrieval report and original source bundle remain unchanged.

The [complete source set and delivery evidence](artifacts/python-source-delivery-20260929/)
are served at `/third-party/20260928/python-source-20260929/`. Recipient testing
downloaded all three files (27,447,197 bytes) through authenticated TLS and
verified their full sizes and hashes. DSC signature authentication and
reproducible binary identity are not claimed. This closes the exact Python
source-collection gap without changing any runtime or signed candidate.

## Source/version reconciliation (29 September)

The [reconciliation ledger](artifacts/source-reconciliation-20260929/report.json)
accounts for all 342 installed OS source/version pairs:

| Treatment | Pairs |
|---|---:|
| Exact source set delivered | 264 |
| Matching ROCgdb release source and build instructions delivered | 1 |
| Retained component notices; no separate source gap established | 71 |
| Version-marker metapackages | 3 |
| Ionic installed payload consists of source/scripts/configuration | 1 |
| RDMA provider with file-scoped dual-license notices | 1 |
| Broadcom compiled vendor payload terms unresolved | 1 |

This supersedes use of the historical 79-pair collection gap as a current
work queue. The 71 component entries retain their notice hashes, including
split-package relationships and the separate AQLProfile supplement. Their
MIT/BSD/Apache-family notices do not establish a requirement to collect every
upstream source tree. The GPL references in LLVM/Comgr/OpenMP notices concern
the LLVM compatibility exception; they are not a declaration that those
components are GPL-licensed.

RDMA notices distinguish provider/library files, packaging, and individual
kernel headers. The ledger preserves that distinction instead of applying
a GPL keyword match to the entire vendor library. Ionic's installed payload
inspection found source/scripts/configuration, with no ELF or static archive.
ROCgdb's release source delivery retains its existing qualification: it is not
a reproducible-binary attestation.

The remaining concrete vendor question is the exact `bnxt-rocelib 235.2.86.0`
compiled payload. The original package, repository inventory, and header
notices have been inspected; package-level terms or matching vendor source
remain unavailable in the collected evidence. No public-distribution clearance
is inferred from this reconciliation.
