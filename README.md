# Aimee–Qwen native memory integration

This repository owns Qwen's native integration with Aimee memory, its experiments,
tests, design documentation, and validation evidence. It was moved from the
sibling `aimee` repository on 2026-09-20.

The current adapter delivers Aimee-selected records through Qwen's attention
states without inserting memory text into the main conversation. The adapter
does not learn or authorize knowledge. Aimee remains authoritative for memory,
governance, authorization, and updates. Persistent local images and reusable
native states reside in RAM/disk, with temporary device copies for attention.

## Start here

- [Publication latency: immutable base, overlays, and measured update reductions](docs/validation/publication-latency.md)

- [Live incremental publication and native cache retention](docs/validation/incremental-publication.md)

- [Independent record encoding: measured reuse and streaming boundary](docs/validation/record-cache.md)
- [Aimee-driven incremental local KB updates](docs/proposals/pending/incremental-kb-updates.md)

- [Canonical-name cue correction and native answer regressions](docs/validation/canonical-cues.md)
- [Native-memory positional bug, correction and keyed/drink regression evidence](docs/validation/keyed-encoding.md)
- [249,105-object scale study and publication/lookup follow-ups](docs/validation/kb-scale-followup.md)
- [Expanded public corpus and approved cues](knowledge/general-v2/README.md)

- [Publisher-controlled installation, updates and withdrawal](docs/validation/local-delivery.md)
- [Published local reads: authorization before delivery](docs/validation/published-local.md)
- [13,261-object general KB and full-Qwen results](docs/validation/general-kb.md)
- [General reference corpus and official sources](knowledge/general-v1/README.md)
- [Rust adapter and serving setup](docs/rust-runtime.md)
- [Rust port validation](docs/validation/rust-port.md)
- [Passing combined KB/memory run with restricted Aimee retrieval](docs/validation/restricted-kb.md)
- [General KB and Aimee memory integration](docs/validation/layered-kb.md)
- [Starter general knowledge corpus](knowledge/general-v0/README.md)
- [Historical Python reference](integrations/qwen_aimee/README.md)
- [Established native-consumption baseline and corrected interpretations](docs/validation/qwen-aimee-poc-baseline.md)
- [Local knowledge-base architecture](docs/proposals/pending/aimee-local-sparse-memory.md)
- [Measured local-first results and limitations](docs/validation/aimee-local-first-memory.md)
- [Authorization-specific images and full-Qwen checks](docs/validation/aimee-authorized-memory.md)
- [Latest authorization transition fixes and unresolved policy dependency](docs/validation/aimee-authorization-transitions.md)
- [Closed-source binary distribution and reverse-engineering resistance](docs/proposals/pending/closed-source-adapter.md)

Authorization belongs to Aimee before publication. The model receives only the
recipient's approved projection and reads it without local grant checks. The new live publisher supports an explicit server-owned exact-record release
policy and actual Aimee source updates. Broader organization-policy integration
remains unfinished; older reports used fixture approvals. Local checks cannot protect data already delivered to the recipient.
Rich evidence, episode, and graph responses need authorized release codecs.

## Repository boundary

| Here: `aimee-qwen` | Sibling: `aimee` |
|---|---|
| Qwen attention/runtime adapter and transports | Authoritative memory and governance |
| Qwen serving integration and local-first client | Model-independent image compiler and reader |
| Qwen experiment drivers and validation artifacts | Canonical authorization policy |
| Qwen integration tests and research fixture issuer | General Aimee benchmarks and poison fixtures |

The experimental image dependency currently needs the sibling working checkout;
it is not yet a published standalone package. `go.mod` uses a local replacement
for that reason. An [archival dependency snapshot](dependencies/README.md) also
preserves the required Aimee sources and supports isolated builds; it is not a
second maintained implementation. The fixture issuer is research-only and must not be installed
inside a model's security boundary.

## Build and test

The active serving implementation is Rust. See [Rust build/run instructions](docs/rust-runtime.md).
The Python commands below run the retained reference and regression tests.

Run from this repository root, alongside `../aimee`:

```sh
mkdir -p .local/bin
go -C ../aimee/server-go build -o "$PWD/.local/bin/aimee-memory-image" ./cmd/aimee-memory-image
go build -o .local/bin/aimee-issue-fixture ./benchmarks/local_memory

export AIMEE_IMAGE_READER="$PWD/.local/bin/aimee-memory-image"
export AIMEE_FIXTURE_ISSUER="$PWD/.local/bin/aimee-issue-fixture"
python3 -m unittest discover -s integrations/qwen_aimee -v
```

The full suite needs a suitable PyTorch build and Transformers; the tested
research environment uses Torch 2.14 and Transformers 5.17. Dependencies are
listed in [requirements](benchmarks/native_memory/requirements.txt). Full model
weights are unnecessary for the structural suite, which uses tiny Qwen models.

The authorization-boundary tests run without PyTorch:

```sh
PYTHONPATH=integrations/qwen_aimee python3 -m unittest -v \
  test_authorized_gateway test_local_first.AuthorizationBindingTests
```

Historical P0 tests are separate from the current adapter suite:

```sh
python3 -m unittest discover -s benchmarks/native_memory -p test_p0.py -v
```

They read Aimee's existing poison fixtures from `../aimee`; set `AIMEE_SOURCE`
to override that fixture checkout. They do not retrain the current adapter.

## Historical evidence

`benchmarks/native_memory` and `benchmarks/memory/latent_projection` retain the
earlier experiments, including approaches superseded by the current adapter.
`benchmarks/local_memory` contains the local/remote and authorization probes.
Reports explain invalid comparisons and corrected interpretations.

Archived results keep their original bytes, source hashes, and historical
machine paths. Those paths describe where a run happened, not the current
repository layout. [The move manifest](docs/repository-move-2026-09-20.json)
records every moved file's hash before cross-repository path updates.
The [relocation report](docs/validation/repository-move.md) records the passing
42-test adapter suite and 11 historical tests from the new layout.
