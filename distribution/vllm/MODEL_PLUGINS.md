# Dedicated model plugins

Five model-specific plugins use exactly the same `aimee-native-runtime` version;
installing a plugin installs that dependency. The two small-model plugins are
0.3.3 release candidates, with the qualified hardware scope described below.
Install the plugin for your model:

| Model | Installable package | Command |
|---|---|---|
| Gemma4 12B | `aimee-gemma4-12b` | `aimee-gemma4-12b` |
| Gemma4 26B A4B | `aimee-gemma4-26b` | `aimee-gemma4-26b` |
| Qwen 3.8 27B | `aimee-qwen3-8-27b` | `aimee-qwen3-8-27b` |
| Gemma4 E2B | `aimee-gemma4-e2b` | `aimee-gemma4-e2b` |
| Gemma4 E4B | `aimee-gemma4-e4b` | `aimee-gemma4-e4b` |

The original three shared Linux x86-64 / CPython 3.12 candidates are in
[`../release/candidates/shared-model-plugins-0.3.2-20261004`](../release/candidates/shared-model-plugins-0.3.2-20261004).
These wheels require glibc 2.39 or newer and exactly vLLM 0.30.0. Their
[recorded execution gates pass on the RTX 5080 host](../../docs/validation/native-memory-shared-runtime-20261004.md). From the release wheel directory:

```sh
python -m pip install --find-links /path/to/release-wheels \
  "aimee-gemma4-12b[gguf]==0.3.2"
# Other choices: "aimee-gemma4-26b[gguf]==0.3.2" or "aimee-qwen3-8-27b==0.3.2"
```

The original 0.3.0 build-1 candidates have an installer metadata defect: their
GGUF extra is not visible to pip. The 0.3.2 build-2 artifacts have corrected metadata and their own current
installation, enrolled lifecycle, execution and deployment evidence. The
original GPU results remain historical evidence for the older artifacts.
Use the model-specific console command; the compiled CLI is not launched with
`python -m`.
Each model package contains its dedicated Rust adapter entry point, has its
own module namespace, and defaults to its own bundled native library. The
console command selects only that model's vLLM plugin. Co-installing packages
does not overwrite another plugin's files.

For normal use, enroll with Aimee's standard client, then connect the chosen
plugin to that existing profile. The plugin stores the profile path, not another
bearer or private key. For example:

```sh
aimee-gemma4-12b connect-aimee --aimee-home /absolute/path/to/enrolled-profile
# Set VLLM_API_KEY in the process environment or a private service environment file.
aimee-gemma4-12b serve --config serving.json
```

`--root /absolute/path` before either subcommand selects a separate managed
plugin instance. `serve` requires a nonempty `VLLM_API_KEY`, binds the actual
enrolled recipient, and serves on loopback. Every selection checks the current
authorized source again, including a warm cache hit. Cold or changed source is
prepared through the resident model while admission is withdrawn; no second
model is loaded. Only one bounded bank is activated for the selected source.
A changed client identity requires reconnecting and restarting the instance.
This enrolled path reads authorized personal memory through Aimee's native
source endpoint. Shared organization memory requires its separate core
authorization and selection contract.

The serving config supplies local model files and memory budgets. GGUF serving also binds
`gguf_weights`, `gguf_weights_sha256` and `gguf_weight_profile`; the supported
GGUF loader dependency must be installed in the vLLM runtime. Memory prepared
for a different model, checkpoint, precision or position protocol is rejected.
The enrolled path supplies its private catalogue, recipient and control sockets.
The dedicated plugin fills its adapter binding; an explicit different binding
fails before serving. Qwen requires its complete attention and recurrent prefix.
The older direct `--config` command is retained for controlled prepared-bank
validation; a manually supplied catalogue does not establish Aimee authorization.

Gemma memory preparation observes the stock model at ordinary positions. Its
Rust adapter maps the live conversation after the memory prefix. No negative
position IDs or changes to Gemma/vLLM's rotary cache are required. Existing
negative-position Gemma publications must be re-encoded.

`aimee-native-runtime` supplies one Rust connection/selection/supervision
binary and one copy of the vLLM framework bridge: admission, lifecycle control,
preparation, scheduling, storage/cache readers, tensor operations and telemetry.
The model wheels contain small registration/command/import bindings plus their
own Rust library and checked binding contract. They do not duplicate the common
compiled bridge or connection binary. A process binds exactly one plugin;
co-installation does not combine model adapters into a generic adapter.

Each dedicated Rust adapter owns its accepted geometry, position mapping and
publication compatibility. The recurrent model's adapter additionally owns its
recurrent layout and seeding policy. Shared code consumes these contracts rather
than defining model geometry or manipulating stock rotary caches. Common Python
code exists only where vLLM/Torch/Triton require framework integration; Cython
compilation does not count as a Rust implementation.

Build all five with `distribution/release/build-model-plugins.py`. For the full
set, pass `--models gemma4-12b gemma4-26b qwen3-8-27b gemma4-e2b gemma4-e4b`
to the finalizer and wheel auditor. Their default selection preserves the original
three-model release workflow. The private builder needs a
pinned complete Rust source snapshot, its lockfile/native bridge, Cython and the
C++ toolchain. Clients need the resulting wheel and supported vLLM runtime.

See [the adapter ownership design](../../docs/proposals/pending/model-dedicated-native-plugins.md)
for the implementation boundary and validation requirements. Earlier published
shared-plugin releases remain historical artifacts; their validation does not
establish execution coverage for these new packages.

## Small-model 0.3.3 release candidates

E2B and E4B each have a dedicated Rust adapter and use the existing shared runtime
and thin CLI/registration/ABI bindings. Rust supplies the shared-K/V layer-source
mapping. The model binding observes upstream K/V tensors for shared layers and
maps the small models' per-layer GGUF input weights. Only their replicated
input gate/projection matrices are materialized as BF16.

The [0.3.3 candidate directory](../release/candidates/model-plugins-0.3.3-20261006)
contains all five model wheels and the corrected shared runtime. Every model
pins `aimee-native-runtime==0.3.3`. The builder defaults to 0.3.3. These unsigned
model candidates preserve every executable payload byte and permission from
the qualified 0.3.2 inputs. Shared runtime build 4 adds the exact-checkpoint Q4
native capture profile by rebuilding six modules. Build 5 replaces only its
GGUF loader to support explicit text-only Qwen configurations. Both build reports
record the changed executable members. The original promotion report and
historical 0.3.2 evidence retain their versions, paths and hashes.

[Qualification and installed-candidate checks](../../docs/validation/gemma4-small-20261006/README.md)
cover both small adapters on CPU, RTX 5080 and 7900 XTX. Each small model passed
27/27 extended native lifecycle checks on CUDA and ROCm with the corrected shared
runtime. The 240-token memory spans two 128-token prefill chunks. The checks
include correction, retirement, streaming, concurrency, real source outage and
recovery, recipient rejection and server revocation. The release interface
accepts the pinned public vLLM version 0.30.0 with vendor suffixes such as
`+rocm723`; other public versions are rejected.

Larger native smokes passed 18/18 each: Gemma4 12B Q8_0 and 26B Q3_K_M on one
7900 XTX, and Qwen 27B FP8 with 18 GiB CPU offload on RTX 5080. The current
enrolled launcher/capture qualifies one GPU. The installed gfx1100 stack rejects
Qwen's required FP8 capture arithmetic, so the CUDA result does not qualify that
path on the AMD cards. Signing, manifest inclusion and published-release
installation remain release gates.

### Qwen Q4 on ROCm

Qwen's text-only Q4_K_M GGUF uses a local `qwen3_5_text` configuration with
`architectures: ["Qwen3_5ForCausalLM"]` and the matching tokenizer. A nested
multimodal `qwen3_5` configuration still requires its vision projector. The loader
does not silently convert that configuration to text-only.

Bind `gguf_weights_sha256` to the actual local checkpoint, set
`gguf_weight_profile` to `Q4_K_M` and `gguf_matrix_backend` to `triton`, and enable
`enable_hybrid_native`. Install the pinned `vllm-gguf-plugin==0.0.5+triton` loader
alongside the model plugin and shared runtime. The Q4 path retains eager,
synchronous, single-GPU execution and rejects a mismatched capture profile.

Use a 256 MiB native-memory device budget for the short recall fixture. Its
complete attention/recurrent state exceeds 128 MiB even for one small record.
This budget is separate from model weights and vLLM's KV cache. Exceeding the
configured budget refuses admission.

[Qwen's Q4 native-memory smoke](../../docs/validation/qwen-q4-rocm-20261006/README.md)
passed cold and warm recall, warm bank reuse and unauthenticated inference
denial on one 7900 XTX with zero CPU weight offload, using runtime 0.3.3 build 5.
The report records the exact NAS checkpoint, tested configuration, runtime wheel
and remaining diagnostics.
