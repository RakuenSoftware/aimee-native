# Private runtime image

The build context is an explicit binary allowlist, never the repository root.
Build the Rust client with `distribution/release/build-vllm-client.sh`, compile
client modules with `distribution/release/build-vllm-wheel.py`, and export native
GPU kernels through the private profile-validation run. Then:

```sh
# Run with the target image's Python 3.12.
python3 -m pip download --only-binary=:all: --require-hashes \
  -r distribution/container/runtime-requirements.lock -d /build/runtime-wheels
python3 distribution/container/context.py \
  --wheel /build/aimee_vllm-0.1.0-cp312-cp312-linux_x86_64.whl \
  --library /build/libaimee_qwen.so --kernels /build/certified-bank \
  --gguf-wheel /build/vllm_gguf_plugin-0.0.5-cp310-abi3-linux_x86_64.whl \
  --runtime-wheels /build/runtime-wheels \
  --output /build/client-context
podman build -t aimee-native:private-preview /build/client-context
```

The GGUF wheel is built **unmodified** from upstream commit
`e2b8ad532b8b5ea175100202c30430c1d2b5e6a8` inside the pinned ROCm base image with
`PYTORCH_ROCM_ARCH=gfx1100 MAX_JOBS=4 pip wheel --no-build-isolation --no-deps .`.
`gguf==0.19.0` is the pinned reader. Only `aimee_native` is enabled as a vLLM
entrypoint: the upstream GGUF plugin's monkey-patching entrypoint is excluded.
Our registered loader receives the local GGUF path through vLLM's supported
`--model-loader-extra-config`, with HF config/tokenizer sidecars as the model path.

Runtime configuration selects TP2, eager scheduling, context 2,048 and batch-token
limit 256 for the current Gemma/gfx1100 binary bank. The CLI reads `gguf_weights`
when selecting the quantized profile. Other shapes fail explicitly rather than
shipping a private-source JIT fallback. Public vLLM kernels may still JIT normally.

Mount model/config files read-only, the approved local publication directory
read/write, and the serving configuration read-only. Pass `/dev/kfd` and the two
GPU render nodes, host IPC and the supported host GPU driver. Earlier nested-LXC probes used disabled cgroups and an unconfined seccomp profile.
The 2026-09-26 exact-image probe instead sets a 48 GiB memory limit, records the
actual cgroup limit/current/peak, and uses the default seccomp profile. These are
separate environments; neither substitutes for the supported customer-host checks.

`artifacts.json` records build-context digests. The eventual signed release must
reference a registry **manifest digest**, not the local image configuration ID.
Model redistribution approval, a release registry, signing and clean-machine
installation remain required. Upstream licenses are included; full transitive
license/SBOM review remains a release gate. No encoder or preparation service is
included in the client image.

## OS and Python dependency fixes

`os-packages.lock` pins the Ubuntu package updates separately from the matched
ROCm/vLLM stack. The build consults only Ubuntu's main sources file for those
updates; vendor source fragments are excluded. Missing pinned versions fail the
build. Record and certify the resulting image digest before publishing it.
`runtime-requirements.lock` pins public Python wheel hashes; supply its complete
wheel directory to the context generator with `--runtime-wheels`.
