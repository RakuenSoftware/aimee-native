# Contributing to Aimee Native

Start with [README.md](README.md), [AGENTS.md](AGENTS.md) and
[public release preparation](docs/public-release.md). Source contributions are
licensed under AGPL-3.0-only. Keep third-party notices and dataset provenance.

Use the build and test commands in the README and
[Rust runtime guide](docs/rust-runtime.md). CPU CI exercises the Rust runtime,
launcher and Python packaging contracts without model weights. Go tests require
the separate Aimee source dependency. GPU and enrolled-service checks require
the matching documented environment; report skipped checks explicitly.

Keep authoritative storage and policy in Aimee. Research fixture approvals do
not establish production authorization. Never contribute credentials, private
keys, production memory or model weights.

Preserve archived evidence, source hashes and historical runtime paths. Explain
corrections in a new report. Include the relevant tests and supported hardware
scope with a pull request; avoid treating earlier GPU results as certification
of changed binaries.
