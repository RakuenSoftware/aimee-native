# Initial repository publication

2026-09-21. Branch: `feature/native-memory-publication`.
Destination: the existing private `RakuenSoftware/aimee-qwen` repository.

This initial branch preserves the Rust native-memory adapter and serving code,
Qwen-specific integration drivers, retained Python reference tests, historical
experiments (including invalidated approaches and negative results), native traces,
proposals, migration manifests, publication-latency evidence, and build instructions.

The public knowledge inputs are included as well:

- General KB v0/v1 inputs and their provenance.
- The complete 249,105-record v2 corpus as a deterministic 40,919,757-byte gzip,
  expanding to 318,559,559 bytes with the original recorded SHA-256.
- The exact pinned GeoNames source ZIP and attribution.
- Historical first-token logits and the small single-memory projection as research
  artifacts. These are not base-model weights or the current adapter design.

The [Aimee dependency snapshot](../../dependencies/README.md) captures 158 source
files across the 11 local Go packages required by the image helper, publisher,
and read ingress. Its manifest pins every file and explicitly records that the
snapshot includes uncommitted Aimee changes. This avoids depending solely on an
unpublished working tree to recover the experiment. Generic memory, governance,
authorization, and publication code remain maintained in Aimee; this archive is
not a second implementation or an Aimee branch publication.

Packaging validation:

- Rust `cargo test --locked --no-default-features`: 8 passed.
- From the extracted dependency snapshot: Go race tests passed for sparse memory,
  execution policy, image CLI, publisher CLI, and memory module.
- Qwen Go packages passed with a local module replacement pointing at that isolated
  snapshot; the seed-tool tests passed without the sibling working checkout.
- The compressed corpus expands to its pinned hash and byte count; source ZIP
  and source-document hashes match the existing source manifest.
- Credential-pattern checks cover files and nested research archives. Private
  local keys, credentials, caches, compiled targets, and base-model weights remain
  excluded. The remote repository's private visibility was checked before upload.

The existing full-model and full-Torch evidence remains in the individual reports;
packaging checks do not claim to repeat those expensive experiments. Historical
result bytes and hashes were preserved. See [publication latency](publication-latency.md)
for the latest actual Qwen and live Aimee measurements.
