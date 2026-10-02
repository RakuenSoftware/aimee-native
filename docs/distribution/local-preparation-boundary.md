# Native preparation boundary for self-hosted Aimee

The self-hosted Aimee server does not download or load model weights. The
inference host enrolls with the normal Aimee thinclient, then requests a
model-neutral, versioned personal-memory primitive from
`POST /v1/native/primitive`. The request and response use the existing Aimee
memory-read capability and enrolled mTLS identity. Empty selections are valid;
missing source versions, duplicate records and malformed responses fail closed.

The inference host owns model-specific encoding and its local cache. A cache
entry must bind the entire ordered record/revision set and model/runtime
identity. Before activation and on reuse, it must request the current primitive
again and compare the complete selection. The host must withdraw a bank if
Aimee is unavailable or the selection changed. The model's weights remain on
the inference host throughout.

The older `/v1/native/bootstrap`, `/v1/native/select` and lease-artifact flow
still represent the preview's server-prepared path. The Rust launcher now has
`fetch-primitive` for enrolled-host diagnostics and the typed primitive client;
the serving broker has **not yet** been switched to local preparation. Do not
ship the existing preview wheel as the self-hosted release until local
preparation, activation, withdrawal and real-model tests pass.
