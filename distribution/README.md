# Aimee Native distribution

All implementation, preparation, experiments and packaging remain in the private
`RakuenSoftware/aimee-qwen` repository. Aimee owns authoritative memory,
permissions, selection and scoped publication.

## Runtime decision: unmodified vLLM

The active integration is [vLLM](vllm/README.md), through upstream's external
attention backend registry and worker subclass configuration. **No forks, source
patches or monkey-patching.** The llama.cpp patch/provider are abandoned research
artifacts, not part of the distribution or implementation plan.

The working private command is `aimee-vllm --config /path/config.json`.
The longer-term signed installer experience remains:

```
aimee-native connect https://your-aimee-endpoint
aimee-native install <certified-model-id>
aimee-native run
```

The Rust installer now targets `bin/aimee-vllm`, a compiled native store library,
and certified model artifacts. `run` consumes a publication-installed
`serving.json`, supplies the installed model/library paths, and binds loopback.
It never forwards credentials through process arguments. A missing serving
configuration fails explicitly. No endpoint, release origin, signing key or
production feed has been invented or provisioned.

## Implemented

- External vLLM native attention with request isolation, ragged batches, tensor
  parallelism, separate memory banks, unchanged text positions and prompt tokens.
- Rust Torch-free store admission and immutable views; no encoder in serving.
- Revision pinning, explicit catalog refresh, graceful withdrawal for new requests.
- Single-command private vLLM server launcher using the unmodified package.
- Signed installer, atomic installs, rollback and release sequence protection.
- Preparation cache keyed by the full ordered records/revisions, authorization
  view and model/runtime/encoding identities; background publication primitive.
- Restricted artifact packaging and mandatory release evidence gates.

Full-model Gemma validation has passed recall, isolation, three-record composition
and publication replacement. See the vLLM validation record for exact coverage.

## Remaining external-preview gates

Hosted authoritative publication wiring and a deployment endpoint; production
admission backpressure and host streaming; clean-machine runtime image; latency
and sustained-load certification; certified quantization/GGUF if selected; and
closed-source plugin packaging/disclosure audit. The private Python/Triton source
package must not be shipped as the promised protected binary release.

The Rust launcher/package layout does not itself bundle a working Python/ROCm
installation. A platform runtime bundle or image is required before clean install
can pass. Release gates remain closed until actual evidence exists. A source
plugin working in the lab is not a finished customer installer.

Preparation stays server-side. Users receive approved local representations and
a compiled consumer. Owning the machine still permits inspecting usable tensors
and binary behavior; binary packaging raises the cost of reconstruction rather
than guaranteeing secrecy.

The active work order and acceptance criteria are in
[the vLLM release plan](../docs/proposals/pending/vllm-release-plan.md).
