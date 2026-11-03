# Install and operate an enrolled model plugin

## Requirements and release status

Use Aimee v1.0.2 with an enrolled standard thin-client profile. The application
release target and wire contract are in [Aimee compatibility](aimee-compatibility.md).
The application holds source memory; the inference host supplies its own model
weights, matching tokenizer and model configuration.

The recorded plugin profile is Linux x86-64, CPython 3.12, glibc 2.39+ and
vLLM **0.30.0**, including qualified vendor suffixes such as `+rocm723`.
Use the GPU-specific Torch/Triton stack qualified with the chosen artifact.
For the historical 0.3.3 ROCm profile this was Torch 2.12.0, Triton 3.7.1 and
ROCm 7.2 on one RX 7900 XTX. Other public vLLM versions are rejected. CUDA
results qualify only their recorded checkpoint/runtime combinations.

The rebuilt AGPL `0.3.4.dev0` candidate wheels have
[scoped RTX 5080 qualification](validation/aimee-5080-20261103.md) with Aimee
v1.0.2, vLLM 0.30.0, Torch 2.13.0/CUDA 13.0 and Triton 3.7.1. They remain
unpublished validation artifacts. Signing, signed upgrade/rollback and the
remaining publication gates still apply; other rebuilt profiles need qualification. Archived 0.3.3 candidates are historical
payloads, not freshly certified AGPL releases. The signed model bundles carried
by earlier Aimee application releases retain their original metadata and their
own instructions. See [public release gates](public-release.md) and
[model-specific evidence](../distribution/vllm/MODEL_PLUGINS.md).

## Install the selected model package

Prepare a separate Python 3.12 environment with the matching supported vLLM/GPU
runtime. Obtain a verified release bundle containing the selected model wheel,
its exact shared-runtime version and the pinned GGUF loader when applicable.
Verify the publisher's signature and SHA-256 manifest before installing:

```sh
python -m pip install --no-index --no-deps /path/to/verified-bundle/*.whl
python -m pip check
```

This offline command assumes all other dependencies are already installed.
Source builders use [development](development.md). Do not infer a public package
index release from a package name, candidate wheel or source version.

| Model | Package / command | Recorded GGUF profile |
|---|---|---|
| Gemma4 E2B | `aimee-gemma4-e2b` | UD-Q4_K_XL |
| Gemma4 E4B | `aimee-gemma4-e4b` | UD-Q4_K_XL |
| Gemma4 12B | `aimee-gemma4-12b` | UD-Q4_K_XL |
| Gemma4 26B A4B | `aimee-gemma4-26b` | Q3_K_M |
| Qwen 3.8 27B | `aimee-qwen3-8-27b` | Q4_K_M, text-only |

One serving instance selects one adapter. Every model package pins the same
shared-runtime version for its release. Model and native-bank checkpoints,
precision and position protocols must match. An architecture's dimensions alone
do not make a different checkpoint compatible.

## Enroll and connect

Create an invitation in Aimee Settings → Clients, then use Aimee's standard
thin-client enrollment flow. An existing enrolled profile can be reused.
Use the selected model's console command:

```sh
aimee remote status
aimee-gemma4-12b --root /absolute/path/to/instance connect-aimee \
  --aimee-home /absolute/path/to/enrolled-profile
```

The profile contains `remote.conf`, `tls/client.crt`, `tls/client.key`, and the
server pin `remote-ca.pem` when enrollment supplies it. Keep credential files
owner-only. Do not copy them into source, releases or evidence. The plugin stores
only the profile path and checks the live credential on subsequent reads.
Explicit `--aimee-home` avoids ambiguity; otherwise the client uses `AIMEE_HOME`,
`AIMEE_PROFILE`, or the normal user profile directory. The instance root defaults
to `~/.local/share/aimee/<adapter>`.

## Serving configuration

Create a private `serving.json`. This example is a template: replace the model
paths, GGUF profile and full lowercase SHA-256 with the exact qualified local
checkpoint values. Compute the checksum with `sha256sum /models/model.gguf`.
The managed launcher fills recipient, adapter library, catalogue and socket
bindings; operators do not supply another user's recipient or source grant.

```json
{
  "model": "/models/gemma4-12b",
  "gguf_weights": "/models/gemma4-12b/model.gguf",
  "gguf_weights_sha256": "REPLACE_WITH_64_LOWERCASE_HEX_DIGITS",
  "gguf_weight_profile": "UD-Q4_K_XL",
  "gguf_matrix_backend": "triton",
  "host_memory_budget": 8589934592,
  "device_memory_budget": 536870912,
  "disk_budget": 17179869184,
  "native_system_context": "",
  "serve": {
    "host": "127.0.0.1",
    "port": 8000,
    "tensor_parallel_size": 1,
    "max_model_len": 2048,
    "max_num_seqs": 4,
    "max_num_batched_tokens": 256,
    "gpu_memory_utilization": 0.75,
    "enable_prefix_caching": false,
    "async_scheduling": false,
    "enable_model_compilation": false,
    "enable_piecewise_graphs": false,
    "v2_model_runner": false
  }
}
```

`model` must contain the matching `config.json` and tokenizer. GGUF weights are
local absolute paths. Keep the original checkpoint intact; native preparation
writes only instance-owned state. Qwen Q4 additionally requires
`enable_hybrid_native: true`, an immutable lowercase hexadecimal `model_revision`
(at least 40 characters), `gguf_weight_profile: "Q4_K_M"`, the text-only
`qwen3_5_text` / `Qwen3_5ForCausalLM` configuration and its qualified checkpoint.
Its tested SHA-256 is
`31629f53165ab6a7dad8c9847dcfd1fdf55829dac1e6e748f4a68581b0033d34`.
The matching recurrent state requires at least the recorded 256 MiB native
device budget for the short recall fixture; 128 MiB is insufficient. Larger
working sets can require more. A vision configuration requires its projector
and is outside this text-only profile.

| Setting | Meaning |
|---|---|
| `host_memory_budget` | Native-bank host-memory admission budget; managed default 8 GiB |
| `device_memory_budget` | Native-bank device admission budget; managed default 512 MiB |
| `disk_budget` | Prepared-cache cap; default 16 GiB; must accommodate the host reservation |
| `native_system_context` | Startup system context captured with the native bank; Qwen hybrid requests must match it |
| `gpu_memory_utilization` | vLLM model/KV allocation fraction, separate from native-bank budgets |

`num_gpu_blocks_override`, when explicitly supplied, counts runtime cache blocks,
not tokens. It is architecture-specific. In the current CUDA Qwen FP8 run, 512
hybrid blocks requested a 24.5 GiB allocation on a 16 GiB GPU; let vLLM size that
profile automatically. Attention-only Gemma has different block geometry. Do not
copy an override between architectures or historical runtime profiles.
The tested CUDA Gemma 26B GGUF profile uses no CPU offload: enabling it hit an
upstream uninitialized-parameter error during loading. Use its qualified GPU
memory allocation rather than assuming an offload budget will make it fit.
The follow-up selective UVA attempt requested 8 GiB CPU offload with a roughly
10 GiB GPU reservation. It reported only 0.02 GiB offloaded, reached 12.15 GiB
GPU use and ran out of memory alongside another workload. That RAM/10 GiB
profile is unsupported for this GGUF checkpoint. `gpu_memory_utilization` is
an engine reservation target, not a hard process-memory cap. The qualified
26B profile reserves 13.69 GiB and needs that space free at startup.

The enrolled path qualifies a single GPU, eager synchronous V1 serving, no
prefix caching, no model compilation, no speculative decoding and no multimodal
input. These restrictions are checked; setting a flag does not qualify a new
mode. Direct prepared-bank research serving has different controls and does not
establish enrollment authorization.

## Start and call the service

Supply a nonempty `VLLM_API_KEY` through the environment or a private service
environment file. Then run:

```sh
aimee-gemma4-12b --root /absolute/path/to/instance serve --config ./serving.json
```

The managed service binds loopback. Use a normal authenticated OpenAI-compatible
request; do not put memory text, publication IDs or source credentials into it:

```sh
curl --fail-with-body http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer $VLLM_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"/models/gemma4-12b","messages":[{"role":"user","content":"What is my project codename?"}],"max_tokens":64}'
```

Use the model name advertised by the running vLLM server if an alias is configured.
`GET /health` reports 503 while startup admission is withdrawn. An authenticated
canary request performs the first authorized source selection and preparation;
do not require health 200 before sending it. After successful activation, health
returns 200. The private control socket reports `paused` when the loaded model
is ready for its first selection; see [the validation harness](../scripts/validation/serving-release.py).
A cold or changed authorized source pauses
admission while the resident model prepares its bank. A warm reuse still checks
Aimee authority. Empty selection uses ordinary model behavior. An unavailable or
denied source refuses selection; it does not silently serve an old authorized view.

For Qwen's complete hybrid prefix, supply the configured nonempty
`native_system_context` as the first system message on every request. The runtime
checks it and removes that already captured turn before model execution. Gemma's
attention-only path accepts ordinary chat messages and does not impose that
hybrid system-turn check; do not infer the same request contract from shared
command names.

## Operations and troubleshooting

Stop the foreground service with its supervisor's normal termination signal.
For a managed system service, retain its unit, instance root and private
environment file under the operator's ownership. The repository's `.253`
deployment unit is a historical site configuration, not a portable installer.
Never expose private control/selection Unix sockets as an HTTP API.

For an upgrade, stop the instance, retain the old environment, configuration and
instance root, install the newly verified matching wheel set into a new
environment, reconnect and require readiness plus an authorized canary query.
For rollback restore that complete prior set. Bank identities bind model,
precision and source revisions; do not transplant a bank across profiles.
Remove a retired instance's prepared cache only after its process has stopped.

| Symptom | Check |
|---|---|
| Connection fails | Profile path, owner-only modes, endpoint, server pin, client enrollment/revocation and Aimee v1.0.2 readiness |
| HTTP 401 | The inference request needs the serving instance's `VLLM_API_KEY` |
| HTTP 503 / selection unavailable | Aimee authority/outage, profile identity changes, current source validity and model-preparation readiness |
| Bank/checkpoint mismatch | Tokenizer/config, GGUF checksum/profile, runtime versions and positive-prefix protocol |
| Admission/budget failure | Native host/device reservations and prepared-cache disk cap; model/KV memory is a separate budget |
| Unsupported vLLM version | Install the exact qualified 0.30.0 public version/vendor build |
| Source Go build references retired APIs | Use the pinned research dependency; current enrolled serving needs no Go build |

For security reports use [SECURITY.md](../SECURITY.md). Include versions, a
synthetic reproduction and redacted diagnostics. Never publish enrolled keys,
bearers, real personal memory or model weights with an issue.
