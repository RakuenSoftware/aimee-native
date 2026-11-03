# Aimee Native public release preparation

Prepared 2026-11-03 against repository commit
`4cf24fc4f38ebbb8c785a3ba51fbc3847aed0e05`.
Canonical repository: https://github.com/RakuenSoftware/aimee-native.
This change prepares the source tree; it does not publish a release, change
repository visibility or certify rebuilt GPU plugins.

## Identity and license

The current Go module is `github.com/RakuenSoftware/aimee-native`; the Rust
package, default runtime executable and shared library are `aimee-native`,
`aimee-native` and `libaimee_native.so`. Rust imports use `aimee_native`.
Build scripts and the gateway service now consume those names. The separately
built enrolled launcher already uses the command `aimee-native`; install the
runtime gateway and launcher into their respective deployment locations.

Source is licensed under [GNU AGPL version 3](../LICENSE)
(`AGPL-3.0-only`). Cargo manifests, the development bridge and generated model
plugin/runtime wheel metadata carry that license. New wheels include LICENSE
and the canonical repository URL. Third-party notices and dataset/model
licenses remain applicable. The earlier closed-source proposal is superseded.
Publish exact corresponding source, build instructions and dependency notices
with new binary artifacts; do not relabel archived wheels as new AGPL builds.

Model-specific names such as `aimee-qwen3-8-27b`, the `QwenAimeeAdapter` class
and `integrations/qwen_aimee` remain model identifiers. Archived reports,
results, source snapshots, candidate wheels, hashes and historical `/opt/`
runtime paths retain their original bytes/names, including `aimee-qwen`.
The dependency pin and move/split manifests remain provenance records.

## Build prerequisites

Clone this repository as `aimee-native`. Rust 1.98.1 and Cargo.lock are pinned.
The documented CPU check is:

```sh
cargo test --locked --no-default-features
cargo test --manifest-path distribution/launcher/Cargo.toml --locked --features model-plugin-client
python3 -m unittest discover -s distribution/release -p 'test_*.py' -v
```

The Go compiler/readers depend on separately maintained Aimee packages, using
`../aimee/server-go`. Use the exact revision in
[dependencies/aimee-source.json](../dependencies/aimee-source.json).
That pin is a research reproduction dependency, not a production server release
recommendation. The historical dependency archive lacks current APIs and cannot
replace it. A newer sibling checkout requires separate compatibility checks;
do not copy Aimee's authoritative implementation into this repository.

Standalone external Go builds remain gated on access to the required Aimee
source revision and its redistribution terms. Go's module directive here is
1.26.7; a newer sibling may require a newer compiler and dependency graph.
CPU CI deliberately does not claim coverage for that external dependency or GPU
execution. Plugin installation and qualified hardware profiles are documented
in [MODEL_PLUGINS.md](../distribution/vllm/MODEL_PLUGINS.md).

## Validation in this preparation

- Rust CPU runtime: 39 tests passed (35 library, 4 executable).
- Launcher/model client: 28 tests passed across unit and integration suites.
- Python packaging contracts: 4 passed. The development wheel was built and
  inspected for `License-Expression: AGPL-3.0-only`, the exact LICENSE bytes
  and canonical repository URL.
- Authorization boundary: 30 passed, zero skipped, using the renamed Rust
  gateway and real compiled Go image reader/fixture issuer.
- Go race suite: passed using an isolated extraction of the pinned Aimee revision
  and a temporary modfile; the sibling working tree and checked-in go.mod were
  not altered for that substitution.
- The Go export test previously required a specific SQL alias and active-only
  filtering even though the authoritative API exports raw lifecycle metadata.
  The failure was reproduced on the unchanged baseline. The assertion now checks
  the parameterized selected-ID predicate; empty/invalid selection protections
  remain covered. No exporter or authorization behavior changed.

Full model/GPU validation has not been repeated for these renamed binaries.
Existing GPU evidence certifies only the artifact identities recorded with it.

## Credential and archive review

Gitleaks 8.30.1 scanned all 417 commits reachable from the fetched refs and the
working tree, including nested archives to depth 4. The history scan reported
2,473 matches; the archive-aware tree scan reported 736. These are detector
matches, not confirmed leaked credentials. Review identified hexadecimal
source/cache digests (2,453 history; 691 tree), Python tokenizer identifiers,
command-line properties, a model field name, public IANA service text and a
published vulnerability advisory's demonstration EC key and filename.
The advisory is GHSA-ffqj-6fqr-9h24, retained in the original OSV evidence.
No operational credential was identified by these scans. No broad detector
allowlist was added and no archived evidence was rewritten. Scanning cannot
establish rights to redistribute datasets or prove that all private information
is absent; review those source inventories before exposing repository history.

Reproduce the scans with a trusted Gitleaks binary:

```sh
gitleaks git --redact --log-opts='--all' .
gitleaks dir --redact --max-archive-depth 4 .
```

These commands currently exit nonzero for the documented matches. Review
findings privately; never commit unredacted scan reports. A tree scan excludes
ignored build outputs and Git metadata by default. Branches not fetched and
server-side release assets require their own review.

## Final publication gates

1. Review public source/history and third-party dataset/archive redistribution
   scope, including the separately owned Aimee dependency.
2. Enable GitHub private vulnerability reporting and preserve automatic Codex
   reviews. These settings were not changed by this source update.
3. Build fresh versioned artifacts from the renamed AGPL source, bundle the
   exact corresponding source, license and notices, and record hashes/signatures.
   Do not reuse the archived candidate hashes for rebuilt executables.
4. Run clean installation, signed upgrade/rollback, enrolled authorization and
   GPU/model checks for those exact artifacts on each advertised profile.
5. Publish the approved tag/assets and verify an external download, signatures,
   dependency installation and links. Mark unsupported profiles explicitly.

The existing candidate packages and older release reports remain evidence for
their recorded versions. No new production authorization or performance claim
is made by a repository rename.
