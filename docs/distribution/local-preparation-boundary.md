# Native preparation boundary for self-hosted Aimee

The self-hosted Aimee server does not download or load model weights. The
inference host enrolls with the normal Aimee thin client, then requests a
model-neutral, versioned personal-memory primitive from
`POST /v1/native/primitive`. The request and response use the existing Aimee
memory-read capability and enrolled mTLS identity. Empty selections are valid;
missing source versions, duplicate records and malformed responses fail closed.
The plugin stores the thin-client profile path, not a second copy of its bearer
or private key. It reads the current enrollment for each selection, so ordinary
thin-client credential renewal and revocation take effect without plugin
reenrollment.

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
`aimee-native` implementation. The Aimee server neither receives model
weights nor produces model-specific K/V tensors. The older
`/v1/native/bootstrap`, `/v1/native/select` and lease-artifact flow remains a
preview path for existing installations.

The local encoder accepts either the model's Hugging Face safetensors or a
supported GGUF checkpoint on the inference host. A GGUF-only directory needs
the matching model configuration and tokenizer alongside its weight file;
when the directory contains one model GGUF, `serve` finds it automatically.
The GGUF path has compiled two-record banks for Gemma4 12B and Qwen3.8 27B,
and Gemma4 has answered correctly through the live vLLM consumer. An installed
0.2.3 candidate then passed the complete enrolled thin-client, local GGUF
preparation and live Gemma4 vLLM path on the RTX 5080. It answered both
selected facts with 34 prompt tokens, and a subsequent request was refused
after thin-client authority was revoked. Public asset staging and an external
clean install remain release gates. This is an inference-host packaging
concern, not a reason to move preparation to the Aimee server.
