# Model plugin candidates — 4 October 2026

Three separate Linux x86-64 CPython 3.12 wheels, version 0.3.0 build 1. Each ships
one dedicated Rust adapter. `audit.json` verifies wheel RECORDs, entry points,
namespace isolation and exported native symbols. `finalization.json` hashes every
executable member against the tested build before dependency metadata was added.
The fourth wheel is the pinned upstream GGUF loader required by the Gemma extra.

See [installation and ownership](../../../vllm/MODEL_PLUGINS.md). These are local
release candidates; this directory does not record publication to a package index.

[The validation report](../../../../docs/validation/native-memory-serving-and-model-plugins-20261004.md)
records full-model execution and deployment checks for these candidate bytes.
