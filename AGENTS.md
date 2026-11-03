# Aimee Native integration ownership

Use `RakuenSoftware/aimee-native` for all model/Aimee memory integration code, experiments,
tests, design notes, validation reports, and associated evidence. Do not add
those files back to the sibling `aimee` repository.

This repository also owns sparse-image compilation/readers, publication and
read-ingress executables, source-row projection, and their integration tests.
The sibling `../aimee` owns authoritative storage, governance, authorization
policy, scoped source-row export, and the shared read-restriction contract.
Consume those core components as dependencies; do not copy their implementation here.

The current adapter is read-only and untrained. Memory learning, authorization,
selection, and updates belong to Aimee. Historical trained-projection experiments
remain under `benchmarks/` as research evidence, not the current adapter design.

Start with README.md and the latest authorization-transition report. Preserve
archived result bytes and historical runtime paths/hashes; document corrections
in reports rather than rewriting experiment evidence. Never commit authority
credentials, private signing keys, model weights, or private production memory.

Use the documented test commands. Research fixture grants do not establish
production authorization integration. Keep that distinction in results.

Current source licensing is AGPL-3.0-only. Preserve third-party notices and
archived release metadata. New binary releases must include the license and
corresponding source for the exact build. See `docs/public-release.md`.
