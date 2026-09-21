# Repository split and branch publication — 2026-09-21

The image compiler, reader, publisher, read bridge, source projection, and their
tests now belong to `aimee-qwen`. This supersedes earlier ownership statements
in archived reports. Historical experiment files and the older dependency
archive have not been rewritten.

## What moved

The [move manifest](../repository-split-2026-09-21.json) lists 45 source/test/doc
files and their hashes after import/path updates:

- `memory/sparse/`: local image layout, compilation, lookup, deltas, immutable
  publication, recipient filtering, delivery and tests.
- `cmd/aimee-memory-image`, `cmd/aimee-memory-publish`,
  `cmd/aimee-memory-read`, `cmd/aimee-memory-bus-probe`.
- `aimeeexport/`: conversion of authoritative source rows into sparse records.
- `scripts/install-memory-probe-grants.sh`: isolated research fixture installer.

The existing Rust adapter, Qwen integration, public KB, benchmarks and research
history already live here. The source and local reader remain read-only from
model processes. Authorization still happens before delivery.

## What remains in Aimee

Required sibling commit: `ad3585ac5381e3f0569dd8661b41fbe82cd6501d` on `agent/live-semantic-context-s0`.
Machine-readable pin: [aimee-source.json](../../dependencies/aimee-source.json).
The top-level `go.mod` uses `../aimee/server-go` to build against this checkout.

Aimee owns authoritative storage and scope rules, memory retrieval/mutation and
lifecycle semantics, release decisions, restricted source reads, event-bus
integration, and its C-to-Go migration. It exports raw scoped source rows and a
small shared read-restriction contract. Neither API authorizes a model release;
the publisher must apply Aimee's release decision before distributing content.
Aimee does not import the Qwen/image implementation.

That commit contains **123 files, +12,903 / −5,886 lines**. Most of this is the
pre-existing authoritative memory migration, not the repository split. These
changes cannot become Qwen-owned without moving Aimee's storage and policy
implementation into the adapter repository. The untracked `webchat/webchat`
ELF build artifact is excluded.

## Validation

Passed for the relocated implementation:

- Qwen `go test -race ./...`: sparse image, publisher, read ingress, image CLI,
  source projection and seed packages.
- Aimee `go test -race ./modules/memory/... ./modules/execution-policy
  ./cmd/aimee-module`: source export, restriction contract and existing core tests.
- All four moved Go command binaries build.
- Rust `cargo test --locked --no-default-features`: **8 passed**.
- Rust release transport build and Clippy with warnings denied pass.
- Authorization integration against the newly built Go reader and Rust gateway:
  **30 passed, zero skipped**.
- Aimee module source-ownership check passes; memory-boundary checker unit tests
  (8) and curator-absence unit tests (6) pass. Publication-plan checks pass.
- `git diff --check` passes in both repositories.

The split preserves the restriction JSON contract and source-row projection
semantics. New raw-export tests cover placement isolation, parameterized selected
IDs, empty selection, and rejection before storage access. A full GPU/model run
was not repeated for the repository move; no new model-accuracy or latency claim
is made.

## Remaining Aimee migration failures

The Aimee branch is a checkpoint of an **unfinished C-to-Go migration**, not a
validated production build. These are existing core migration issues, outside
the image relocation:

- Memory C boundary and descriptor validation reject 31 retired C memory policy
  files still physically present after their descriptor entries were removed.
- Module bus boundary finds old cross-module includes in those retired files.
- DB2 link-closure validation finds three obsolete support files still present;
  the link-closure checker test suite also fails against that tree.
- The selected C test build still pulls legacy memory objects and fails on
  undeclared `db2_memory_link_query_many` and
  `memory_record_lane_outcome_metrics`. Those C tests did not execute.

The migration needs a coordinated source retirement and C test/build dependency
cleanup before merge. No boundary was relaxed to hide these failures. The split
corrects the stale CMake `memory_legacy_bus.c` reference to the existing domain
and scope transport files, and registers the release-policy Go files, but does
not attempt a broad migration completion.

Logs are in [the artifact directory](artifacts/repository-split-2026-09-21/).
No production deployment, private memory export, model training, or GPU serving
restart was performed. Credential scan matches in Aimee were limited to local
validation database fixtures already declared by its provisioning scripts;
there were no matches in the moved Qwen sources.
