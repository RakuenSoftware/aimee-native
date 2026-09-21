# Aimee research dependency snapshot

The active generic implementation still belongs to the sibling `aimee` repository.
This is an archival dependency snapshot, not a second maintained implementation.
It preserves the exact sparse-image, publisher, read-ingress, policy, and memory
source needed by the Qwen research implementation while those Aimee changes are
still uncommitted. The manifest records the Aimee base commit, package closure,
and individual source hashes. It is not a claim that the base commit alone
contains these experimental changes.

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

The seed tool and historical fixture issuer use the repository's `go.mod`, whose
normal replacement points to `../aimee/server-go`. To use this snapshot instead,
create a local module file rather than changing that maintained dependency:

```sh
cp go.mod .local/snapshot.mod
go mod edit -modfile=.local/snapshot.mod \
  -replace="github.com/JBailes/aimee/server-go=$PWD/.local/aimee-dependency/server-go"
go test -modfile=.local/snapshot.mod ./...
```

For ongoing development, use the sibling repository. When Aimee publishes these
packages, replace the working-checkout dependency with its reviewed revision.
Historical source archives under `docs/validation/artifacts/` remain evidence of
the exact earlier experiments and have not been rewritten.
