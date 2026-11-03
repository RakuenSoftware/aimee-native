# Aimee research dependency snapshot

> Current application compatibility is recorded in [aimee-release.json](aimee-release.json).
> The historical Go source pin is prepared into an ignored dependency directory
> with [the development instructions](../docs/development.md). The maintained
> enrolled runtime consumes HTTPS source releases and needs no core source checkout.


This archive records the implementation **before** the repository split on
2026-09-21. The maintained image, publisher, read-ingress and source projection
code now lives in `aimee-native`. Authoritative memory and policy remain in Aimee.
Build current code using the top-level README and the sibling revision in the
[split report](../docs/validation/repository-split.md).

The archive and its manifest remain unchanged to preserve source hashes and
reproduce earlier research. The manifest records the Aimee base commit and the
then-uncommitted source closure; the base commit alone did not contain those
changes.

The bundle contains the 11 local Go packages required to build the memory image,
publisher, and read-ingress executables, plus Go dependency manifests and tests.
Third-party Go dependencies remain pinned by `go.mod`/`go.sum`; model weights,
credentials, databases, grants, and private memory are not part of this bundle.

To build the archived image reader without depending on a dirty sibling checkout:

```sh
mkdir -p .local/aimee-dependency .local/bin
tar -xzf dependencies/aimee-memory-source-2026-09-21.tar.gz -C .local/aimee-dependency
go -C .local/aimee-dependency/server-go build \
  -o "$PWD/.local/bin/aimee-memory-image" ./cmd/aimee-memory-image
go -C .local/aimee-dependency/server-go build \
  -o "$PWD/.local/bin/aimee-memory-publish" ./cmd/aimee-memory-publish
```

Do not substitute this archive for the current sibling dependency: the current
code requires the new raw-row export and read-contract APIs, absent from this
historical snapshot. Historical source archives under
`docs/validation/artifacts/` also remain unchanged.
