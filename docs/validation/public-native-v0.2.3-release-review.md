# Self-hosted native plugin release review — 2 October 2026

This is the 2 October snapshot. The [3 October follow-up](public-native-v0.2.3-followup-20261003.md)
records the later Qwen regression, encoder correction, and signed r12 candidate.

The `native-memory-v0.2.3` GitHub Release assets are signed and staged, **not
published**. The public Aimee server primitive is on the separate
`feature/native-delivery-current` branch, PR #3001, and must be included in
the Aimee version offered to users. A public GitHub Release remains distinct
from that server change.

| Asset | SHA-256 | Bytes |
| --- | --- | ---: |
| `aimee_vllm-0.2.3-1-cp312-cp312-linux_x86_64.whl` | `d2fc60d17c5280b461103f9adb93ecbe12a39470eeda497cc8348e5b8b566f3d` | 4,936,139 |
| `vllm_gguf_plugin-0.0.5+triton-py3-none-any.whl` | `616360d726fbaf88c96ebbe9ec4a62fc69ba86cba591f1a8b609199ad5339246` | 230,630 |

The stage is `/opt/aimee-native-release/public-staging/native-memory-v0.2.3`
inside CT101 on `192.168.1.253`. It contains those two wheels,
`manifest.json`, `SHA256SUMS`, an Ed25519 signature for each of the four
assets, and a local `staging.json` receipt. The staging script verified all
signatures, the wheel audit hash, the pinned GitHub dependency URL and GGUF
wheel hash, the absence of private-network URLs and model weights in the
plugin wheel, and the installed-wheel live result. The signed manifest SHA-256
is `b89ca74f7c3dc3032c8b7b3d9769df38e8c007909c3cb85b6511e02f92889e32`.

The exact wheel was installed in the RTX 5080 vLLM environment. Its normal
`connect-aimee` and `serve` path used a disposable enrolled thin client and
mTLS source primitive, prepared two records locally from Gemma4 12B Q8 GGUF,
and answered both selected facts with 34 prompt tokens. A subsequent request
after authorization revocation returned HTTP 503. `pip check` found no broken
requirements. The wheel declares Accelerate and GGUF reader dependencies;
private encoder modules are compiled, and the Rust launcher is compatible
with glibc 2.34.

Qwen3.8 27B Q8 GGUF-only preparation also produced a two-record bank, with
21 memory positions and 1,376,256 tensor bytes. A live Qwen GGUF consumer
run remains unverified in this release candidate because its 28 GB checkpoint
does not fit the 16 GB 5080 and the two RX 7900 XTX GPUs were occupied.
The prior native Qwen vLLM consumer result remains separate evidence.

Remaining public delivery gates are a current Aimee server containing the
primitive route, the actual GitHub Release upload, and a clean external
download/signature/dependency-install check from that published URL. The
`[gguf]` dependency points to the planned release asset URL, so that final
online install cannot pass until the asset exists. There is no second plugin
enrollment or model download by the Aimee server.
