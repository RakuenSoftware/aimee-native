# General KB experiments

The corpus lives locally on the model host. No general records are imported into
`aimee-server`. See [source data](../../knowledge/general-v1/README.md),
[initial Qwen results](../../docs/validation/general-kb.md), and
[published-reader results](../../docs/validation/published-local.md).

Build dependencies from the repository root:

```sh
go -C ../aimee/server-go build -o "$PWD/.local/bin/aimee-memory-image" ./cmd/aimee-memory-image
go build -o .local/bin/aimee-issue-fixture ./benchmarks/local_memory
cargo build --locked --no-default-features
python3 -m unittest discover -s benchmarks/general_kb -p test_published.py -v
```

`test_published.py` runs real Rust/Go processes with no gateway at the configured
path. It verifies canonical local hits without any grant files, physical absence
of excluded data, a pinned generation across a publisher update, new-request
generation adoption, withdrawal, and an uncovered query's fallback attempt.

`benchmark_published.py` compares the historical guarded reader, direct published
reader, and Rust-to-published-reader path on identical seeded queries. Its
`--root` is an existing compiled research deployment containing `image/` plus
publisher-only credentials for the legacy comparison. The published modes do
not receive those credentials. All 13,261 entries are also read through Rust.

```sh
python3 benchmarks/general_kb/benchmark_published.py \
  --root /private/research-deployment --records knowledge/general-v1/records.json \
  --reader .local/bin/aimee-memory-image --rust target/debug/aimee-qwen \
  --output /private/local-benchmark.json
```

`prepare_live.py` and `prepare_published_live.py` are explicitly research-host
publication scripts. They require existing synthetic personal fixtures and a
publisher-owned source image. They are not production installers or permission
issuers. The latter publishes into a fresh directory, leaves grants root-only,
and removes all local authorization flags from the model launch command.

`make_cases.py` creates reproducible questions, outside the knowledge image.
`probe_model.py` runs no-memory, compact oracle-text and native arms against the
actual Rust Qwen endpoint. `MODES=native` restricts a rerun; `RESULT_FILE` chooses
a fresh output. Text is a diagnostic consumption control, not a proposal to
insert the whole KB into context. The runtime, corpus, source revisions, prompt,
and greedy decoding must be held fixed when comparing readers.

`audit_model.py` audits the initial and addressing-fixed archived runs.
`summarize.py` reports raw scores and explicitly corrects the baseline's
Tórshavn/Torshavn spelling equivalence without rewriting raw evidence.

Python is experiment tooling only. Serving uses Rust, Go and native libtorch.

`delivery_probe.py` compiles the full public corpus into isolated fixture-approved
snapshots, installs them using the real publisher CLI, and reads all entries
through Rust. It measures a replacement with one synthetic update and one
retirement, checks physical removal, then withdraws the image. `--root` must be
new. Supply `--reader-user` and `--reader-gid` when running as a publisher identity
that can launch the model account. The reader needs no gateway or grant files.
The public corpus itself is never modified. See
[delivery results](../../docs/validation/local-delivery.md).
