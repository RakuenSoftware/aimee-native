# Larger runtime third-party source bundle

This work is independent of the unresolved native-memory latency requirement.
No normal release promotion or redistribution approval is asserted here.

The exact runtime image is
`56e44a78b4ddbb228d5728311a709ee8118acc51f685b9f0e428a809b5ad2935`.
Its installed-package inventory contains 591 OS packages and 278 Python
packages. Notice collection retained 556 distinct files; unresolved notice
associations remain explicit in the collection manifest.

The source planner ran inside a disposable instance of that image. It enabled
Ubuntu source indexes only, using the image's archive/security repository
configuration, without installing/upgrading any package. It resolved exact
installed source versions using APT:

- 342 distinct source-package/version pairs.
- 259 resolved in the queried Ubuntu indexes.
- 83 unresolved, including ROCm/vendor packages, PPA packages and unavailable
  historical Ubuntu versions. These require their actual source origins; a
  newer version is not a substitute.
- 805 unique downloadable files, totaling 1,175,432,948 bytes.

The bounded four-download collector is running in CT101 as process 379311 at
this checkpoint. Each file is size checked and verified against the strong
SHA-256/SHA-512 checksum returned by APT; archives are not unpacked or executed.
Eight GiB of filesystem headroom is reserved before starting. Files remain on
the lab host at `/opt/aimee-large-release-validation/os-source-download-r1`;
source tarballs are not committed to the private Git repository. Final hashes
and failures will be recorded after completion.

Source availability and download completion are not equivalent to completing
all corresponding-source/build or notice obligations. Vendor/PPA sources,
Python/binary-component source requirements and remaining notice associations
still require reconciliation. The collector does not grant release approval.

[Exact source plan](artifacts/larger-os-source-plan-20260928/report.json) ·
[Notice collection](artifacts/larger-third-party-notices-20260928/manifest.json)

Reproduction tools:
`distribution/release/plan-os-sources.py` and
`distribution/release/fetch-os-sources.py`.

## Historical Ubuntu/PPA publication lookup

Exact Launchpad publication records were found for five versions absent from
the active Ubuntu source indexes: curl `7.81.0-1ubuntu1.27`, PyJWT
`2.3.0-1ubuntu0.3`, GCC 13 `13.4.0-6ubuntu1~22~ppa2`, GCC 16
`16-20260315-1ubuntu1~22~ppa1`, and Python 3.12 `3.12.13-1+jammy1`.
The records come from Ubuntu primary, ubuntu-toolchain-r/test, and deadsnakes/ppa.
Each returned source-package name and version was matched exactly; source file
URLs were obtained from that publication's API. These five now have retrieval
locations, but are not part of the 805-file APT-verified download or a completed
corresponding-source bundle. No source version was substituted.

[Publication records and source URLs](artifacts/larger-launchpad-source-plan-20260928/report.json).
Reproduction: `distribution/release/resolve-launchpad-sources.py`.

A separate collector is now fetching those five exact historical/PPA source
sets at `/opt/aimee-large-release-validation/launchpad-source-download-r1`
(CT101 process 379510 at launch). It checks the DSC source identity/version and
its SHA-256 entries for dependent files. DSC OpenPGP signatures are retained but
not verified by this collector; this distinction stays explicit in its report.
No source is unpacked or executed. Results are pending.


The first historical-source collector completed unsuccessfully: all five
Launchpad file requests returned HTTP 503 before any source description was
retrieved. Its [failure report](artifacts/larger-launchpad-download-failure-20260928/report.json)
is preserved. A separate retry uses official package-pool fallbacks for the exact
GCC 13, GCC 16 and PyJWT versions; their DSC endpoints were independently read
successfully. The retry runs at `launchpad-source-download-r2` (CT101 process
379529 at launch), preserving the original publication URL and any fallback
error in each file record. Curl and Python 3.12 have no validated fallback yet.
No newer source version is substituted and no signature-verification claim is
added. The retry remains in progress at this checkpoint.
