# Self-hosted native plugin v0.2.3: 3 October follow-up

This follows the [2 October release review](public-native-v0.2.3-release-review.md),
which is preserved as a historical snapshot. The public stage was replaced
after live Qwen testing found a real native-answer regression. No GitHub Release
has been published.

The signed r12 wheel is
`aimee_vllm-0.2.3-1-cp312-cp312-linux_x86_64.whl`, SHA-256
`d165b32d6a5eb885e233999d3c73ee0224d79852642c97909c3dc22f1bf2ddab`
(3,448,481 bytes). Its CT101 stage is
`/opt/aimee-native-release/public-staging/native-memory-v0.2.3-r12`.
The staged manifest SHA-256 is
`a2996cf325abf1308af22fe2f4e93006458a4d4aba84ea3fc746f8bde82205bb`.
The wheel integrity and binary-disclosure audit passed. The public Aimee
`verify_assets.py` checked all staged sizes, hashes, and four Ed25519
signatures against the committed metadata in PR #3002.

| Exact-wheel live check | Outcome | Prompt tokens | Native bank | Revoked request |
| --- | --- | ---: | ---: | --- |
| Gemma4 12B Q8, RTX 5080, two selected records | Both facts answered | 34 | 1 | HTTP 503 |
| Qwen3.8 27B Q8, two RX 7900 XTXs, two selected records | Both facts answered | 29 | 1 | HTTP 503 |

Each check used an enrolled thin-client profile and an mTLS Aimee primitive
server, locally prepared the selected records from a GGUF-only model directory,
published the bank, and sent a fact-free user question to vLLM. The Qwen
answer was: “The release verification project codename is Halcyon and the
notebook color is blue.” The corresponding Gemma answer stated the project
codename and blue-notebook preference. The prompts did not contain the facts.
These are release-path smokes, not estimates of broad recall accuracy.

The earlier r9 and r11 Qwen live runs prepared and published a native bank but
failed to recover both facts. A direct vLLM Q8 control without Aimee correctly
answered the facts when given as text; an Aimee-backend control with no native
bank also answered the text-supplied facts. The failure was isolated to local
bank preparation. A full-checkpoint versus GGUF comparison used the same 25
tokens and negative positions but found native K/V cosine similarities of
roughly 0.18–0.69. Direct Qwen weight comparison found GGUF effective
zero-centered RMSNorm scales exactly 1.0 above the original checkpoint values.
The local GGUF encoder had applied those scales to a Transformers model that
adds 1.0 internally. The r12 fix reverses the GGUF conversion for those
norms, leaving gated-delta SSM norms unchanged. All 209 mapped Qwen norm
tensors then matched the checkpoint; eight focused tests passed. The corrected
r12 live Qwen run passed on its first prompt.

Gemma4 26B exact-wheel validation and a three-record, four-question Qwen
check remain pending while another GPU campaign occupies the XTXs. An initial
Gemma 26B fixture used symlinks that the launcher rejected; hardlinks fixed
that setup issue. A later attempt omitted the model's separate chat template;
the fixture now includes it. A subsequent restart failed vLLM's free-VRAM
check before native preparation because the concurrent GPU campaign had
started. None of those attempts establishes a Gemma 26B model result for r12.

The public release remains a signed, unpublished candidate. A clean download
and `[gguf]` install from the final GitHub Release URL cannot be performed
until assets are published. The offered Aimee server version must include the
native primitive route from public PR #3001.
