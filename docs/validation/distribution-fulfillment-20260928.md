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
2. Reconcile component-specific source requirements with the retained source
   archives and build material. Preserve any concrete missing component in the
   final delivery inventory; the numerical collection gap alone is insufficient.
3. Deliver the notices and applicable source archives alongside the candidate
   through the release endpoint. The local research archives are not themselves
   proof that a recipient can obtain the material.

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
checks its complete size and SHA-256. The delivery test is running; successful
staging alone is not recorded as a passed recipient-download check.
