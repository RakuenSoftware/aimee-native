# Shared-runtime model plugin candidate

Linux x86-64 / CPython 3.12, version 0.3.1 build 2. The three model
plugins depend on exactly `aimee-native-runtime==0.3.1`, which pins
`vllm==0.30.0`. Gemma's `gguf` extra selects the included upstream
`vllm-gguf-plugin==0.0.5+triton` wheel.

One runtime wheel contains the connection binary and common vLLM bridge.
Each model wheel contains its own Rust adapter and small plugin bindings.
Dependency notices are included as wheel metadata. Finalization preserves
all tested executable members, binding contracts, and executable file modes.
`audit.json` checks namespaces, adapter exports, dependency versions and
all RECORD hashes. `finalization.json` binds original and finalized code.

These are candidates undergoing the final live release gates. Existing 0.3.0
GPU results remain historical evidence; they do not establish validation of
this package layout. Follow the [plugin instructions](../../../vllm/MODEL_PLUGINS.md)
for the installation and enrollment contract.
