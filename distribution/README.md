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
configuration fails explicitly. An isolated TLS release origin, registry and
lab signing key now exercise delivery. Production identities remain unconfigured.

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

## Current validation and remaining gates

Compiled client modules, binary native kernels and the pinned ROCm container now
pass full-model smoke checks. Q8_0 GGUF loading also passes without invoking the
upstream GGUF dependency's patching entrypoint. Rust ingress admission and
coordinated multiworker refresh are implemented; 512 concurrent pressure requests
returned correct isolated answers. See [the release validation record](../docs/validation/vllm-release-20260925.md)
for protocols, artifacts and limitations.

The private preparation/follower bridge is implemented against existing Aimee
publication interfaces. Automatic selection now uses the actual scoped reader
and requires an exact match for every selected record and revision. A miss can
invoke the private preparer; it never silently substitutes a one-record bank.
Disk-backed catalogs retain verified immutable mappings and fault selected pages
on demand, releasing mapped RSS after GPU transfer. OS page cache is separate.

See [the production follow-up record](../docs/validation/vllm-production-20260925.md)
for disk pressure, automatic selection, real preparation, clean-install results,
and the remaining authenticated deployment and certification work.

For container releases, the signed artifact set can include `runtime/image.json`
containing `image` (an immutable registry reference with `@sha256:` digest) and
`model_config` (the packaged `models/config.json`). The launcher mounts approved
memory and model files and runs the matched image through Podman. Model/tokenizer
sidecars remain necessary alongside GGUF. A digest-pinned image is published in
the isolated lab registry. This is not a customer production release.

Lab builds require the explicit `lab-release` feature and `lab_only` manifest
marker; normal launchers reject them. Production gate evidence must match the
exact packaged artifact set, not merely the upstream runtime commit.
The compiled client still needs a supported host GPU driver and container runtime.
Remote account authentication and native-artifact delivery must be finished
before the advertised connect/install/run workflow is customer-ready.

Preparation stays server-side. Users receive approved local representations and
a compiled consumer. Owning the machine still permits inspecting usable tensors
and binary behavior; binary packaging raises the cost of reconstruction rather
than guaranteeing secrecy.

The active work order and acceptance criteria are in
[the vLLM release plan](../docs/proposals/pending/vllm-release-plan.md).
