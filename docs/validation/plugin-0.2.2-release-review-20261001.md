# Aimee vLLM plugin 0.2.2 release review — 1 October 2026

**Disposition: approve the signed candidate for the controlled private preview.**
This is approval of the candidate and its declared scope, not a record of
publication or a general hardware/model certification. The existing 0.2.1
download remains in place until 0.2.2 is deliberately published.

## Reviewed release identity

- Staged wheel: `aimee_vllm-0.2.2-1-cp312-cp312-linux_x86_64.whl`,
  4,814,570 bytes, SHA-256
  `ff069f26ff20316e91576e3f901275b41e74599b5c2b73b5f307eb297fa9d46e`.
- Staged manifest SHA-256:
  `0fcab09a03a536b896b3176a532911b2c486de370c793629de70bc218703909d`.
- Both staged files have verified Ed25519 signatures under the pinned release
  public key. The wheel-member/RECORD audit passed; the wheel excludes model
  weights, credentials, the private encoder source, and a bundled vLLM/runtime
  image. Generic runtime-compiled GPU operations are included.
- The optional GGUF dependency was fetched through the controlled TLS origin
  during review and matched the hash pinned in the wheel metadata. The
  publication script's read-only preflight repeated the signature, hash and
  dependency checks and passed. A copied stage with a modified manifest was
  rejected by that preflight.

## Execution evidence

The exact wheel passed native and empty-memory installed-wheel probes and
four-client matrices on two RX 7900 XTXs for Gemma 4 12B, Gemma 4 26B, and
Qwen3.8 27B. All 72 scored requests across six option configurations passed.
The corrected live-publication test changed the catalogue digest while an old
stream was active; the first replacement request succeeded and 30/30 follow-up
answers were correct. On an RTX 5080, the exact wheel passed four native and
five empty-memory Gemma 12B requests. The
[candidate validation report](plugin-polish-20261001.md) links to the raw
results and retains the initial Gemma 26B GPU-reset startup failure.

## Supported preview boundary

The wheel targets Linux x86-64, CPython 3.12, glibc 2.34+, and an already
installed vLLM 0.30.x CUDA or HIP environment with a supported BF16 GPU.
The measured Qwen hybrid profile uses the V1 runner because vLLM 0.30's hybrid
V2 path does not expose the request slots required by this plugin. Gemma 12B
and 26B were measured with V2. The execution record covers gfx1100 for all
three models and sm120 for Gemma 12B; it does not certify every supported
runtime GPU or every model on CUDA.

This remains a controlled preview for enrolled recipients with Aimee-approved
publications. The plugin is not a general authorization engine. Broader
organization-policy grant issuance and arbitrary model/profile certification
are outside this release. Native and empty canary prompts are not a matched
native-versus-text performance benchmark. A long active stream delayed the
tested publication replacement by approximately 66 seconds; activation is
ordered, and no simultaneous old/new execution is claimed. The earlier
Gemma 26B startup encountered a host GPU reset, then passed after reset.

## Publication and rollback

The reviewed [publication command](../../distribution/release/publish-staged-plugin.py)
defaults to a read-only preflight. Its `--publish` mode copies the signed files
to a new immutable `0.2.2` directory on the controlled origin, then downloads
and compares their bytes and signatures over TLS. It must be run in CT101 with
the staged directory at
`/opt/aimee-large-release-validation/plugin-polish-20261001/release-stage-lease-r1`.
The [preflight result](artifacts/plugin-polish-20261001/release-publication-preflight.json)
passed; **`--publish` has not been run**. The publication command does not
change the 0.2.1 directory. Rollback for recipients is to keep or reinstall
the existing signed 0.2.1 wheel and its matching hosted-service revision; if
0.2.2 delivery needs withdrawal, remove its versioned origin directory from
serving after affected recipients have been notified. Already downloaded
artifacts cannot be remotely retracted.
