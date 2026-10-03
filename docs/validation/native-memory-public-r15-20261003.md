# Native-memory public candidate r15 — 2026-10-03

The exact staged wheel SHA-256 is
`b4b9d7fe7249bf304cadabbfea0bde53bcdd84d8f7186e3a9aa74180f9380736`
(3,526,478 bytes). The manifest SHA-256 is
`7ef5cf010d96df6eaccef91609fecd188143a43733520166552e9fc1a2fa6376`.
The signed stage is
`/opt/aimee-native-release/public-staging/native-memory-v0.2.3-r15` on CT101.
Four asset signatures, all hashes, and wheel integrity verified. It has not
been published.

The r14 launcher was inadvertently linked to GLIBC 2.39 on the newer build
host. The r15 launcher was built in a manylinux 2.34 container with the same
source, compiler toolchain, release URL, and public key. Its highest required
GLIBC symbol is 2.34, and its `--help` command ran in that container. The
wheel audit now checks every ELF member's GLIBC floor: r15 passes and r14 is
rejected. Only the launcher and wheel `RECORD` differ between r14 and r15.

The installed r15 wheel passed the TLS fixture, including a wrong-pin refusal,
and connected using a genuinely enrolled thin client to a fresh
`aimee:testing` server. It fetched the real native primitive and `pip check`
found no broken dependencies. The account had no write-tier grant, so the
response contained zero records. A deliberately invalid bearer returned HTTP
401 with the exact r15 launcher.

The exact r15 wheel passed the RTX 5080 / Gemma4 12B Q8 GGUF release-path
test: two selected records, both facts answered from one native bank, 34 prompt
tokens, and HTTP 503 after revocation. The r14 wheel passed the equivalent
two-record tests with Qwen3.8 27B Q8 and Gemma4 26B Q8 on two RX 7900 XTXs.
An exact r15 Qwen rerun could not start because an unrelated GPU experiment
left less than the requested free VRAM; it did not reach inference. Those two
exact-artifact reruns remain open. Public Aimee v0.4.6 also predates the native
primitive, so an application release containing merged PR #3001 is required
before public plugin delivery.
