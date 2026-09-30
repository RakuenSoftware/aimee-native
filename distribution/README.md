# Aimee Native distribution

All implementation, preparation, experiments and packaging remain in the private
`RakuenSoftware/aimee-qwen` repository. Aimee owns authoritative memory,
permissions, selection and scoped publication.

## Distribution boundary — portable plugin, 30 September

The product is the compiled Aimee vLLM plugin connected to Aimee. Users provide
an existing supported vLLM/PyTorch/GPU runtime. Distribute the plugin wheel,
Rust consumer library, runtime-compiled GPU operations, and the client
connection/configuration support. Preparation remains with Aimee's private
service. Do not require a fork or ship the upstream operating-system/runtime
image as a mandatory product dependency.

The pinned container is a build and validation fixture. Its bundled Broadcom
network driver is not an Aimee plugin dependency, and reviewing redistribution
of that entire image does not gate the plugin release. Retain that review only
for any separately proposed distribution of the image itself.

The existing container-based installer and three-model test evidence below
remain historical implementation evidence. They do **not** establish completion
of standalone plugin installation. The new [standalone distribution](vllm/STANDALONE.md)
bundles the compiled plugin components into one wheel and runs the existing Rust
Aimee connection directly in the supported vLLM environment. Gemma12, Gemma26
and Qwen27 have each passed live native-memory queries through this path. The earlier 0.1.1 wheel targeted one ROCm/GPU build. Version 0.2.0 removes that
restriction: GPU operations compile through the installed CUDA/HIP runtime, the
tensor bridge has no ATen or GPU-library link, and the GGUF extra uses upstream
Triton code without an optional architecture-specific binary. The vLLM interface
range remains explicit. See [portable validation](../docs/validation/portable-plugin-20260930.md)
for execution versus compilation coverage. The same wheel also passed
[physical RTX 5080 validation](../docs/validation/cuda-5080-20260930.md), including
216 exact memory activations and live Gemma12 consumption. Preparation remains in Aimee.

## Runtime decision: unmodified vLLM

The active integration is [vLLM](vllm/README.md), through upstream's external
attention backend registry and worker subclass configuration. **No forks, source
patches or monkey-patching.** The llama.cpp patch/provider are abandoned research
artifacts, not part of the distribution or implementation plan.

The current end-user flow is documented in [Standalone Aimee vLLM plugin](vllm/STANDALONE.md): install the wheel, connect Aimee, then serve your existing model.

The historical signed model/container installer flow was:

```
aimee-native connect https://your-aimee-endpoint
aimee-native install <certified-model-id>
aimee-native run
```

The Rust installer now targets `bin/aimee-vllm`, a compiled native store library,
and certified model artifacts. `run` consumes a publication-installed
`serving.json`, supplies the installed model/library paths, and binds loopback.
It never forwards credentials through process arguments. A missing serving
configuration fails explicitly. The controlled private preview uses a dedicated TLS origin, immutable registry
digest and new signing authority. See the [live release record](../docs/validation/native-live-release-20260926.md)
for the supported profile, installation commands and measured limits.
The [latency follow-up](../docs/validation/native-latency-20260926.md) documents
packed activation and resident private preparation, with exact-image results
and the remaining cold-path performance limits.
The [Rust runtime follow-up](../docs/validation/native-runtime-ownership-20260926.md)
records native activation ownership, lossless GPU transport, exact preparation
reuse, and the Python/framework boundary that remains.
The [streaming follow-up](../docs/validation/native-streaming-20260926.md) adds
parallel/pipelined reads and per-upload staging accounting.

## Implemented

- External vLLM native attention with request isolation, ragged batches, tensor
  parallelism, separate memory banks, unchanged text positions and prompt tokens.
- Rust store admission and activation through the installed tensor runtime; no encoder in serving.
- Revision pinning, explicit catalog refresh, graceful withdrawal for new requests.
- Single-command private vLLM server launcher using the unmodified package.
- Signed installer, atomic installs, rollback and release sequence protection.
- Preparation cache keyed by the full ordered records/revisions, authorization
  view and model/runtime/encoding identities; background publication primitive.
- Restricted artifact packaging and mandatory release evidence gates.

Full-model Gemma validation has passed recall, isolation, three-record composition
and publication replacement. See the vLLM validation record for exact coverage.

## Historical container certification and supported-profile limits

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
That container distribution requires a supported host GPU driver and container runtime.
The standalone plugin requires only the supported existing vLLM environment.
The live Aimee account endpoint now authenticates and delivers scoped native
artifacts. Client enrollment and an operator-approved publication are required;
the release does not grant access to an entire user or general knowledge base.

Preparation stays server-side. Users receive approved local representations and
a compiled consumer. Owning the machine still permits inspecting usable tensors
and binary behavior; binary packaging raises the cost of reconstruction rather
than guaranteeing secrecy.

The active work order and acceptance criteria are in
[the vLLM release plan](../docs/proposals/pending/vllm-release-plan.md).

## Automatic remote client follow-up

The launcher now authenticates native bootstrap during `connect`, supports
private-CA/mTLS enrollment, and can own the complete broker/container lifecycle
from a signed `runtime/profile.json`. A clean client has passed automatic native
memory download, Gemma answers, signed upgrade and rollback without manually
installed banks/catalogs. The private Go handler delegates actual preparation and
approval to Rust; authoritative identity/release resolution remains in Aimee.

See [the remote delivery report](../docs/validation/native-remote-delivery-20260925.md).
That report records the earlier lab distribution. The subsequent
[live release record](../docs/validation/native-live-release-20260926.md) covers
real account authentication, private preparation, dedicated signing and the
normal launcher. Public redistribution and untested hardware remain outside
this controlled private-preview release.

The [current integration and certification report](../docs/validation/native-production-20260926.md)
records the maintained Aimee ingress bridge, private Unix service, current-account
binding, complete Gemma engineering workloads and dependency remediation.
[Deployment instructions](service/DEPLOYMENT.md) keep all native delivery and
preparation implementation here; Aimee contains only the authenticated bridge.

## Building the enrolled launcher

Build `distribution/launcher` with `cargo build --release --locked`, supplying
`AIMEE_RELEASE_URL` and the Ed25519 `AIMEE_RELEASE_PUBLIC_KEY` at build time.
For a private PKI, set `AIMEE_RELEASE_CA_PEM` to the public CA PEM contents.
The private CA must include critical `basicConstraints=CA:TRUE` and
`keyUsage=keyCertSign,cRLSign`; verify its leaf with `openssl verify -x509_strict`.
Never embed the signing private key or a client identity. The normal build
rejects lab manifests; `lab-release` is only for isolated validation.

`connect` accepts `--ca-file` and `--client-identity` for the Aimee account.
For a private address with a different certificate hostname, use
`--connect-address IP:PORT`; the HTTPS endpoint hostname is still verified.
The bearer is read from stdin and never forwarded to the runtime container.
The release CA is scoped to the installer and its OCI pull, not the host trust
store. Signed profiles bound whole-container memory as well as native-bank
budgets; the tested profile uses 48 GiB and normal container security defaults.

## Beta follow-up, 26 September

[Private beta instructions](beta/README.md) describe the signed profile and remaining
external-distribution gate. [The vLLM comparison](../docs/validation/vllm-stream-validation-20260926.md)
records 336/336 paired responses and separated activation timing.
[Load and connected validation](../docs/validation/beta-validation-20260926.md)
adds 2,048 concurrent pressure answers and 64 live Aimee answers.
The original [SWE learning protocol](../benchmarks/swe_learning/PROTOCOL.md)
and its stopped run are preserved. The repaired 16-task, three-round study is
complete (1/16 control, 2/16 in each of three native rounds). The separate
32-task paired follow-up completed at 5/32 control versus 4/32 native, with one
lost Requests success. A corrected source representation reproduced that
previously passing patch in a full native agent run and passed its official
grade. The matched text arm also passed, while the fresh control failed.
All ten selected retained-success attempts passed. These targeted checks repair
the observed source-reproduction regression; the original 32-task outcome
remains unchanged and does not establish broad learning improvement. The
[current release work record](../docs/validation/release-readiness-20260928.md)
identifies the corrected candidate, runtime recovery changes, exact evidence
and outstanding release gates. The 12B candidate has completed its recorded
signed installation/update/rollback checks. Separate Gemma4 26B and Qwen3.8
27B release candidates are undergoing their own signed lifecycle and coding
validation; 12B evidence does not certify them. See the
[larger-model report](../docs/validation/larger-model-native-20260928.md).
Earlier signed-release
results do not by themselves certify this replacement candidate.
