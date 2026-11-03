# Aimee Native

[Aimee Native](https://github.com/RakuenSoftware/aimee-native) connects supported
local models to Aimee-selected personal memory through model-native state.
Memory is kept outside the chat prompt. Aimee owns authentication, source
selection, authorization and updates; this repository owns model-specific
adapters, local preparation, native storage and serving integration.

The current product uses five dedicated model plugins with one shared Rust
connection/runtime and the unmodified vLLM framework. The Python Qwen adapter,
standalone Rust Qwen server and Go publication tools are retained research paths.

## Documentation

- [Install, enroll, configure and operate a model](docs/usage.md)
- [Aimee v1.0.2 compatibility and protocol](docs/aimee-compatibility.md)
- [Build and test from source](docs/development.md)
- [Documentation map](docs/README.md)
- [Public release preparation and outstanding gates](docs/public-release.md)
- [0.3.4 candidate, signatures and rollback](docs/releases/0.3.4.md)
- [Aimee v1.0.2 validation on .252](docs/validation/aimee-v1.0.2-20261103.md)
- [RTX 5080 execution on .253](docs/validation/aimee-5080-20261103.md)
- [Research results and historical validation](docs/research-index.md)

The current application compatibility target is **Aimee v1.0.2**, the latest
published release checked on 2026-11-03. The enrolled runtime uses
`POST /v1/native/primitive`; it needs neither a Go source checkout nor a second
model on the Aimee server. GPU serving requires a qualified vLLM/model/hardware
profile. CPU and protocol tests do not establish GPU qualification.

## Models

| Model | Package and console command |
|---|---|
| Gemma4 E2B | `aimee-gemma4-e2b` |
| Gemma4 E4B | `aimee-gemma4-e4b` |
| Gemma4 12B | `aimee-gemma4-12b` |
| Gemma4 26B A4B | `aimee-gemma4-26b` |
| Qwen 3.8 27B | `aimee-qwen3-8-27b` |

See [qualified profiles and installation](docs/usage.md). Model weights are
supplied separately and are never committed here. Qwen consumes its complete
attention and recurrent prefix; Gemma uses its dedicated attention adapter.

## Source and authority boundary

| This repository | Aimee core |
|---|---|
| Dedicated model adapters and vLLM integration | Authentication, authorization and memory selection |
| Local model-native preparation and caches | Authoritative storage, governance and updates |
| Sparse-image research tools and source projection | Scoped source release and shared policy contracts |
| Experiments, tests and preserved evidence | Application deployment and memory backend selection |

The runtime reads the existing enrolled thin-client profile and rechecks
current source authority for warm reuse. Delivered data is visible to the model
host. Research fixture grants do not establish production authorization, and
personal-memory support does not imply shared organization-memory support.

## License and evidence

Current source is [GNU AGPL version 3](LICENSE), `AGPL-3.0-only`.
[Third-party notices](THIRD_PARTY_NOTICES.md), [data and archive notices](DATASETS.md) and model
licenses remain applicable. New binary releases require their exact corresponding
source, license and notices. Archived binaries retain their recorded metadata.

Archived reports, runtime paths, result bytes, source snapshots and hashes remain
unchanged. The [move manifest](docs/repository-move-2026-09-20.json) and
[split report](docs/validation/repository-split.md) record the original ownership
move. Their September Aimee source pin is for research reproduction. Prepare it
with the [development instructions](docs/development.md); replacing it with a
modern sibling checkout does not restore APIs retired by Aimee.
