# Documentation map

## Current product

| Need | Guide |
|---|---|
| Install a model plugin, enroll, serve and call it | [Usage and operations](usage.md) |
| Understand the Aimee release/API boundary | [Aimee compatibility](aimee-compatibility.md) |
| Build, test and reproduce validation | [Development](development.md) |
| Review licensing, signatures and publication gates | [Public release](public-release.md) |
| Inspect dedicated plugin layout and qualified model profiles | [Model plugins](../distribution/vllm/MODEL_PLUGINS.md) |
| Report a vulnerability | [Security](../SECURITY.md) |
| Contribute source or reports | [Contributing](../CONTRIBUTING.md) |

The current serving path is the installed dedicated model command, shared Rust
client, enrolled Aimee source primitive and unmodified vLLM. Use the guides above
for that path. Native/Cognee/Hillock selection in Aimee chooses its memory backend;
it does not select a local model plugin or change model-adapter geometry.

## Research and implementation history

[The research index](research-index.md) links measured results and limitations.
[Distribution implementation](../distribution/README.md),
[the original vLLM bridge](../distribution/vllm/README.md),
[the standalone Rust Qwen server](rust-runtime.md),
[the Python reference](../integrations/qwen_aimee/README.md), and
[sparse image tools](../memory/sparse/README.md) retain their implementation
contracts. Their direct database exports, fixture issuers, private preparation
services and historical container installers are separate from current enrolled
plugin installation. Historical dates, claims, paths and artifact hashes are
preserved; later reports identify corrections.
