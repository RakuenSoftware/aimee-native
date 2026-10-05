# Isolated RTX 5080 serving environment

The host deployment uses `/opt/aimee-native-serving`, an independent Python
virtual environment, immutable release directories, a publisher-owned catalogue,
and the `aimee-native-serving.service` unit. It listens on the operator's private
host address at port 18950. API credentials are generated on the host and stored
with mode 0600 in `credentials.env`; they are never part of a release or evidence
archive. The control socket is `/run/aimee-native-serving/control.sock`, mode 0600.

The virtual environment consumes the existing pinned CUDA runtime through a
read-only package path. This is a dependency, not a copied installation: retain
`/var/lib/aimee-large-release-validation/cuda-5080-20260930/env` and its Python
base. Prefix admission binds the vLLM, Torch and Triton versions. The service
uses only CUDA device 0, the RTX 5080. Its memory limit is 56 GiB, with no swap;
failed starts are rate limited. Startup verifies the quantized weight checksums
and authenticated model/control readiness. The separate 512 MiB executable
tmpfs holds JIT outputs because this host's `/run` is mounted without executable
mappings. Model weights and immutable prefixes are persisted on the NAS.

This environment initially serves public synthetic canary facts. Deployment
is not an organization-wide memory grant. Private content must enter through
the existing Aimee release policy and publication path with its recipient,
resource, revision, expiry and withdrawal bindings. Neither a catalogue label
nor a public fixture establishes that approval.

## Supported quantized native profile

The complete hybrid prefix path uses a serialized FP8 checkpoint with dynamic
activations, BF16 attention/convolution state, and FP32 recurrent state. The
native prefixes are captured offline from that same vLLM engine. Model identity
binds checkpoint revision, config (including the weight provenance manifest),
tokenizer, and arithmetic profile. BF16 encoder states cannot be admitted as
FP8 engine states. This profile is text-only and eager synchronous V1; model
compilation, prefix caching, speculative decoding and multimodal inputs remain
outside the complete hybrid contract.

`benchmarks/native_addressing/serialize_fp8_checkpoint.py` creates a new private
checkpoint directory from local source weights. It records per-shard source and
output hashes and never changes the originals. `capture_engine_prefixes.py`
then prepares closed system prefixes from approved canonical facts. Capture
requires an offline-only worker, one GPU and one exclusive request. The HTTP
launcher rejects capture configuration, and the worker RPC rejects capture in
a deployed service.

## Operations

On `.253`, inspect the service without printing credentials:

```sh
systemctl status aimee-native-serving
journalctl -u aimee-native-serving -n 50
systemctl restart aimee-native-serving
```

Stage changes in a new immutable release directory and a new catalogue. Retain
the prior release, configuration, catalogue and prefixes. Switch `current` and
configuration while the service is stopped, then start it and require readiness
plus native canary success. For rollback, restore those prior pointers and
configuration and perform the same checks. A prefix never crosses arithmetic
profiles merely because the architectures have the same dimensions.

Publication withdrawal/refresh goes through the private Unix control socket;
refresh drains requests and validates the replacement catalogue on every rank.
A failed refresh remains closed and requires a supervised restart if worker
state is uncertain. API requests cannot choose a weight profile or enable the
offline write/capture path.

The current deployment launches the installed `aimee-qwen3-8-27b` plugin with
its bundled dedicated Rust library through `launch.py`. Gemma packages have
their own entry points and adapters; see [installation](../MODEL_PLUGINS.md).
[The release validation](../../../docs/validation/native-memory-serving-and-model-plugins-20261004.md)
records the executed checkpoints, operational checks and rollback evidence.
