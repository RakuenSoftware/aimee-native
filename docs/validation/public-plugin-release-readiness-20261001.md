# Public Aimee native-memory plugin release preparation — 1 October 2026

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
wheel hash above. The first ROCm attempt reached vLLM startup while both XTXs
were occupied by another workload and served no requests. Its
[probe record](artifacts/public-plugin-20261001/gemma12-amd-public-build2-probe-infrastructure-failure.json)
and [VRAM error excerpt](artifacts/public-plugin-20261001/amd-busy-startup-excerpt.txt)
are retained. A fresh AMD probe is queued for when both cards have sufficient
free VRAM. The public signing stage is queued after that pass; neither stage
nor GitHub Release publication is yet claimed here.

The planned public asset set is the plugin wheel, pinned GGUF loader wheel,
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
