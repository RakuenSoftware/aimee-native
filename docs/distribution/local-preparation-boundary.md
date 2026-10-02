# Native preparation boundary for self-hosted Aimee

The self-hosted Aimee server does not download or load model weights. The
inference host enrolls with the normal Aimee thinclient, then requests a
model-neutral, versioned personal-memory primitive from
`POST /v1/native/primitive`. The request and response use the existing Aimee
memory-read capability and enrolled mTLS identity. Empty selections are valid;
missing source versions, duplicate records and malformed responses fail closed.

The inference host owns model-specific encoding and its local cache. A cache
entry must bind the entire ordered record/revision set and model/runtime
identity. On startup the launcher fingerprints the local checkpoint, tokenizer
and optional serving GGUF; this one-time disk read is outside the request path.
Before activation and on reuse, it must request the current primitive
again and compare the complete selection. The host must withdraw a bank if
Aimee is unavailable or the selection changed. The model's weights remain on
the inference host throughout.

The `serve` path now fetches the primitive, prepares a complete selected bank
on the inference host, and rechecks the primitive before activation and on
subsequent requests. The local cache and portable Rust bank writer live in the
private `aimee-qwen` implementation. The Aimee server neither receives model
weights nor produces model-specific K/V tensors. The older
`/v1/native/bootstrap`, `/v1/native/select` and lease-artifact flow remains a
preview path for existing installations.

The local encoder currently needs the model's Hugging Face safetensors on the
inference host. vLLM may serve GGUF weights, but a GGUF-only directory is not
yet a certified source for initial local encoding. This is an inference-host
packaging limit, not a reason to move preparation to the Aimee server. A public
self-hosted wheel still needs an installed-wheel enrollment, withdrawal and
real-model check before release.
