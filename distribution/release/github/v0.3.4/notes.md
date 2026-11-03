First AGPL-3.0-only Aimee Native release: five co-installable model plugins and
one shared Rust/Cython runtime, qualified against Aimee v1.0.2.

**[Installation instructions](https://github.com/RakuenSoftware/aimee-native/blob/v0.3.4/distribution/release/github/v0.3.4/INSTALL.md)**

The release includes seven wheels, an Ed25519-signed manifest, matching source,
licenses/notices and a downloader/verifier/installer. No GitHub login is needed
to download the public assets. Model weights and the vLLM/Torch/CUDA runtime
are supplied separately.

Qualified: Linux x86-64, CPython 3.12, glibc 2.41+, CUDA 13.0, RTX 5080,
vLLM 0.30.0, Torch 2.13.0+cu130, Triton 3.7.1, Transformers 5.22.1, GGUF 0.19.0.
Models: Gemma4 12B Q4_K_M, Gemma4 26B Q3_K_M, Qwen 3.8 27B FP8,
Gemma4 E2B/E4B UD-Q4_K_XL. Exact checkpoints and budgets are in the
[validation report](https://github.com/RakuenSoftware/aimee-native/blob/v0.3.4/docs/validation/public-release-20261103.md).

Validation passed 65 installed GPU lifecycle checks, 204 signed installation /
upgrade / rollback / restoration checks, a further real-model GPU rollback,
and all release CI checks. The native wheel payloads are unchanged from that
qualification. The complete source ZIP is pinned to the exact validated source
revision; later CPU research additions on the repository's default branch are
outside this release's certification.

Gemma 26B requires its qualified approximately 14 GiB GPU profile; the
approximately 10 GiB plus RAM offload profile is unsupported. This release does
not qualify streaming, concurrent requests, ROCm, prefix caching or compilation.

2026 Ed25519 public-key fingerprint (SHA-256 of DER):
`eba95c96cf22f1f2cc76606f851376dad401380fd3bdd54ecfb79d640c2f0eb5`.
