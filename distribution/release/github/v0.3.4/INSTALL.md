# Install Aimee Native 0.3.4

Five dedicated model plugins with a shared native runtime. Requires an enrolled
Aimee v1.0.2 profile and separately supplied model weights. Source is AGPL-3.0-only.

## Qualified runtime

Linux x86-64, CPython 3.12, glibc 2.41+, NVIDIA RTX 5080, driver 615.71.09,
Torch 2.13.0+cu130, vLLM 0.30.0, Triton 3.7.1, Transformers 5.22.1 and GGUF 0.19.0.
The tested model profiles and memory budgets are documented at:
https://github.com/RakuenSoftware/aimee-native/blob/v0.3.4/docs/usage.md

Gemma 26B Q3_K_M needs its qualified approximately 14 GiB GPU profile. The
approximately 10 GiB GPU plus RAM offload attempt is unsupported. These artifacts
do not qualify ROCm, concurrent requests, streaming, prefix caching or compilation.

## Download and verify

Use a trusted copy of this repository's verifier and 2026 Ed25519 public key.
For example, retrieve them from the immutable release tag over GitHub HTTPS:

```sh
curl -fLO https://raw.githubusercontent.com/RakuenSoftware/aimee-native/v0.3.4/distribution/release/release-bundle.py
curl -fLO https://raw.githubusercontent.com/RakuenSoftware/aimee-native/v0.3.4/distribution/release/public-keys/2026-ed25519.pub
openssl pkey -pubin -in 2026-ed25519.pub -outform DER | sha256sum
```

Check the fingerprint matches this independently pinned value before trusting it:

```text
eba95c96cf22f1f2cc76606f851376dad401380fd3bdd54ecfb79d640c2f0eb5
```

Do not trust a public key solely because it is included in a downloaded bundle.
The following downloads require no GitHub login. The manifest signature is checked
before any listed assets are downloaded; then every size and SHA-256 is verified.
Use a new output directory:

```sh
python3 release-bundle.py download --bundle ./aimee-native-0.3.4 \
  --public-key ./2026-ed25519.pub --expected-version 0.3.4
```

The bundle includes all seven wheels, the source ZIP, licenses/notices and verifier.
The complete source ZIP uses fixed, uncompressed headers for reproducibility.
Its source revision is in the signed manifest. Extract with `unzip` to preserve
Unix executable permissions and symlinks. Build instructions are in `docs/development.md`.

## Install

Prepare an independent compatible runtime first:

```sh
python3.12 -m venv ./venv
./venv/bin/python -m pip install 'vllm==0.30.0' 'torch==2.13.0' \
  'transformers==5.22.1' 'triton==3.7.1' 'gguf==0.19.0'
python3 release-bundle.py install --bundle ./aimee-native-0.3.4 \
  --public-key ./2026-ed25519.pub --expected-version 0.3.4 \
  --python ./venv/bin/python
```

This installs all five model plugins, the matching shared runtime and the pinned
GGUF loader offline, then runs `pip check`. Model weights and the external GPU
runtime are not bundled. Use `torch.version.cuda` to check CUDA 13.0 and ensure
Torch can access the intended GPU before serving.

Next, enroll the standard Aimee thin client normally, point the selected plugin
at that profile, and configure its model files. Follow the complete operation guide:
https://github.com/RakuenSoftware/aimee-native/blob/v0.3.4/docs/usage.md

Commands: `aimee-gemma4-12b`, `aimee-gemma4-26b`, `aimee-qwen3-8-27b`,
`aimee-gemma4-e2b`, `aimee-gemma4-e4b`.

Stop serving before replacement. Keep the previous verified bundle for rollback;
run the same installer with that bundle's exact expected version, then restart.
The replacement is not atomic. If pip fails, stop serving and reinstall a complete
verified bundle after correcting the runtime problem.
