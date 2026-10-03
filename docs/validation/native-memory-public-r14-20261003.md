# Native-memory public candidate r14 — 2026-10-03

**Superseded:** the launcher requires GLIBC 2.39 despite the documented 2.34
floor. The r15 rebuild and audit close this portability defect. Do not publish
the r14 wheel.

The exact candidate wheel is `aimee_vllm-0.2.3-1-cp312-cp312-linux_x86_64.whl`,
SHA-256 `d023b8f420efd21c93fc3b7e0431023a254b2ade2d52490520ef91c0eff004ea`
(3,526,231 bytes). Compared with r13, only the hardened Rust launcher and the
wheel's `RECORD` changed. The launcher honors an enrolled Aimee server's
explicit TLS pin when its certificate does not name the LAN IP. Built-in TLS
roots remain disabled for that pinned path. The test with a different pin
refused the connection.

The compiled-wheel integrity and binary-disclosure audit passed. `pip check`
reported no broken requirements after installing the exact wheel. The release
fixture exercised an enrolled thin-client profile, local GGUF preparation,
native vLLM consumption of **two selected records**, and a revoked next
request:

| Model | Device | Answer | Prompt tokens | Revoked request |
| --- | --- | --- | ---: | --- |
| Gemma4 12B Q8 | RTX 5080 | Both facts | 34 | HTTP 503 |
| Qwen3.8 27B Q8 | 2 × RX 7900 XTX | Both facts | 29 | HTTP 503 |
| Gemma4 26B Q8 | 2 × RX 7900 XTX | Both facts | 34 | HTTP 503 |

All three runs used the installed r14 wheel and one native bank. The fixture
served the records over mTLS using the standard thin-client profile. The
first Gemma 26B attempt could not start because a separate GPU job had left
only 8.56 GiB and 5.06 GiB free; it was retried after that job finished and
passed. This was resource contention, not an inference failure.

For server integration, a fresh `ghcr.io/rakuensoftware/aimee:testing` server
was deployed in isolated CT110. Its normal CLI enrolled a thin client. The
installed r14 wheel connected with that profile using both explicit
`--aimee-home` and standard `AIMEE_HOME`, and fetched the actual
`/v1/native/primitive` response. An invalid bearer returned HTTP 401. The
fresh account had no write-tier grant and therefore no memory records: this
test establishes real enrollment, TLS, route, and authorization behavior;
selected-record answers are established by the release fixture above.

The exact signed stage is
`/opt/aimee-native-release/public-staging/native-memory-v0.2.3-r14` on CT101.
Its manifest SHA-256 is
`73d1abe28125a29b14026b34f9a2d6cbcff984baedd1536c4a98ca66d6db5cdb`.
The wheel, GGUF dependency, manifest, and SHA256SUMS have four verified
Ed25519 signatures. The stage is not published. Public Aimee v0.4.6 predates
the native primitive; the application server must be released with that route
before the plugin can be offered to users on the latest Aimee.
