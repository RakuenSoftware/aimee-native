# Public Aimee native-memory plugin release preparation — 1 October 2026

**Superseded release decision, 2 October 2026:** The first public release must
work with any user of the latest public Aimee installation, using an invitation
issued by that user's own Aimee instance. The signed files below are retained
as a validated controlled-preview candidate, **not approved for public upload**.
The current public Aimee release has no `/v1/native/*` routes or installed
native delivery/preparation service. The private service still requires
operator-maintained principal bindings, model profiles and release policies.
Publishing these wheels today would give an ordinary Aimee user a plugin that
cannot obtain native memory from their instance. See
[the public-install gate](public-native-aimee-enrollment-20261002.md).

The [controlled 0.2.2 preview](plugin-0.2.2-release-review-20261001.md)
is signed and staged, and its `aimee-qwen` branch is pushed. Its optional GGUF
extra points to a private download address, so those bytes are **not** the
public GitHub Release asset.

The public candidate is a separate `0.2.2` build tag `2` wheel. The
[retarget record](artifacts/public-plugin-20261001/retarget-report.json) proves
that exactly two ZIP members changed: package metadata now points to a pinned
GGUF wheel under the planned `RakuenSoftware/aimee` GitHub Release tag
`native-memory-v0.2.2`, and wheel `RECORD` was recalculated. All 601 other
members, including compiled plugin modules, the Rust launcher, the consumer
library and the two runtime-compiled GPU-operation sources, are byte-identical
to the reviewed candidate. The [public wheel audit](artifacts/public-plugin-20261001/public-wheel-audit.json)
passed; a separate scan found no private-network address in the public wheel.

| Asset | SHA-256 | Bytes |
| --- | --- | ---: |
| `aimee_vllm-0.2.2-2-cp312-cp312-linux_x86_64.whl` | `40b5df989308822357d06d9c84eed611b5e45fd861162b03695e31e0f95515fb` | 4,912,256 |
| `vllm_gguf_plugin-0.0.5+triton-py3-none-any.whl` | `616360d726fbaf88c96ebbe9ec4a62fc69ba86cba591f1a8b609199ad5339246` | 230,630 |

The public-wheel [RTX 5080 probe](artifacts/public-plugin-20261001/gemma12-5080-public-build2-probe.json)
passed four native-memory questions and five empty-memory controls on Gemma
4 12B. Its installed distribution's `direct_url.json` identified the public
wheel hash above. The first public-wheel ROCm attempt reached vLLM startup
while both XTXs were occupied by another workload and served no requests. Its
[probe record](artifacts/public-plugin-20261001/gemma12-amd-public-build2-probe-infrastructure-failure.json)
and [VRAM error excerpt](artifacts/public-plugin-20261001/amd-busy-startup-excerpt.txt)
are retained. When GPU memory became available, the exact public build's
[fresh AMD probe](artifacts/public-plugin-20261001/gemma12-amd-public-build2-probe-r2.json)
passed four native-memory answers and five empty-memory controls on Gemma 4
12B. The installed-wheel CUDA probe also passed. The signed manifest predates
this supplemental AMD result and conservatively lists only the CUDA execution
of the public build; its signed bytes are unchanged.

The public asset set has now been signed in a non-web stage. Independent
verification passed for all four asset signatures and hashes. The
[staging record](artifacts/public-plugin-20261001/staging.json),
[manifest](artifacts/public-plugin-20261001/staged-manifest.json),
[SHA256SUMS](artifacts/public-plugin-20261001/staged-SHA256SUMS), and
[verification result](artifacts/public-plugin-20261001/independent-stage-verification.json)
identify the exact files. The signed stage has been copied to
`/home/virant/dev/aimee-native-public-release-prep/assets/` for release upload.
**No GitHub Release has been created or published.**

The staged public asset set is the plugin wheel, pinned GGUF loader wheel,
`manifest.json`, `SHA256SUMS`, and an Ed25519 signature for each. The private
encoder, model weights, vLLM runtime and container image are not included.
[Release notes](../../distribution/release/public-native-memory-v0.2.2-notes.md)
state the hardware/model evidence and enrolled-account requirement.

The public `aimee` repo's existing `v0.4.x` tags release its CLI and server
images. The separate `native-memory-v0.2.2` tag keeps this plugin asset release
out of that application release series. The tag is available, and publication
does not require changing `aimee`'s source or pushing its `main` branch. After
upload, a clean external download must verify every published asset hash and
signature and `pip install` the GGUF extra from the public URL before the
release can be called delivered.

The upload should first create a **draft, prerelease** under that separate tag,
pointing to a reviewed public `aimee` commit. Upload only the eight signed
assets from the staged directory: the two wheels, `manifest.json`,
`SHA256SUMS`, and each file's `.sig`. Do not upload `staging.json`, private
model files, Aimee credentials, or the private 0.2.2 build-tag-1 wheel. The
[release notes](../../distribution/release/public-native-memory-v0.2.2-notes.md)
are ready for the draft body. Verify the draft's asset names, byte counts and
SHA-256 values, then publish it. Immediately download each public URL and
verify the signatures and hashes; finally use a clean supported environment
to install the wheel with `[gguf]` so the new GitHub dependency URL is exercised.
The `aimee-qwen` implementation stays private; the public `aimee` repo receives
only the GitHub Release tag, notes, and compiled assets.

GitHub CLI's supported release flow accepts a draft, a pinned target commit,
notes from a file and asset paths in one command. Use `--latest=false` so this
plugin preview does not replace the main Aimee application release as “Latest”.
The public `main` ref was `7899ec340a9812bbd28ad9d8478abe2ef5e3f00c`
at this review; recheck it and the tag before creation. The staged upload
directory is `/home/virant/dev/aimee-native-public-release-prep/assets/`.

```sh
gh release create native-memory-v0.2.2 \
  --repo RakuenSoftware/aimee \
  --target 7899ec340a9812bbd28ad9d8478abe2ef5e3f00c \
  --title 'Aimee native memory v0.2.2 (preview)' \
  --notes-file /home/virant/dev/aimee-qwen-live/distribution/release/public-native-memory-v0.2.2-notes.md \
  --draft --prerelease --latest=false \
  /home/virant/dev/aimee-native-public-release-prep/assets/*.whl \
  /home/virant/dev/aimee-native-public-release-prep/assets/*.whl.sig \
  /home/virant/dev/aimee-native-public-release-prep/assets/manifest.json \
  /home/virant/dev/aimee-native-public-release-prep/assets/manifest.json.sig \
  /home/virant/dev/aimee-native-public-release-prep/assets/SHA256SUMS \
  /home/virant/dev/aimee-native-public-release-prep/assets/SHA256SUMS.sig
```

After reviewing the draft asset list, publish with
`gh release edit native-memory-v0.2.2 --repo RakuenSoftware/aimee --draft=false`.
The public download and `[gguf]` install check must then pass.

This workspace can push Git refs over SSH but currently has no authenticated
GitHub Releases API client (`gh` is absent and no release API token is
configured). That prevents creating the draft or uploading assets from here
until release-write access is supplied. It does not affect the signed artifact
stage or the GPU results.
