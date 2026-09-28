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
