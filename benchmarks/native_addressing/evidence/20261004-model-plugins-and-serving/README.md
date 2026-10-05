# Dedicated model-plugin and serving evidence

`raw.tar.gz` contains public fixture metadata, executable/source identities,
validation rows, operational/performance reports and retained attempt logs.
It excludes credentials, model weights and native tensor payloads.
`archive.json` records the archive digest and size; `SHA256SUMS.json` inside the
archive verifies all remaining members. `independent-recheck.json` records
recomputed audits using archived source and inputs.

See [the validation report](../../../../docs/validation/native-memory-serving-and-model-plugins-20261004.md).
The separately [packaged wheels](../../../../distribution/release/candidates/model-plugins-20261004/)
have their own byte/code-identity audit. Historical evidence directories remain
unchanged; superseded results are retained and distinguished by their profiles.
