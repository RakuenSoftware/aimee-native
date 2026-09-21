# General KB starter v0

This is a small, reviewed source corpus for the layered native-memory prototype:
25 public factual records (12 SI prefixes, six binary prefixes, seven SI base
units). It is the beginning of a general corpus, not a claim of broad knowledge
coverage. No personal, organizational, or synthetic canary data belongs here.

Each canonical record has a stable namespaced ID, content revision, structured
semantic fields, provenance URL, review date, lifecycle and scope. Latent values
are not authoritative. The same source can later produce projections for other
models. The current Qwen implementation produces frozen-model K/V on demand.

Sources checked 2026-09-20, summarized independently:

- [NIST metric prefixes](https://www.nist.gov/pml/owm/metric-si-prefixes)
- [NIST binary prefixes](https://physics.nist.gov/cuu/Units/binary.html)
- [NIST SI units](https://www.nist.gov/pml/owm/metric-si/si-units)

`queries.json` contains one explicit read example per record. These are inputs
for publication/evaluation; they are **not** a semantic query classifier or an
adapter-owned retrieval policy. Additional query forms require an Aimee read
decision or authoritative fallback.

Build the control-plane source image from the repository root:

```sh
go build -o .local/bin/aimee-kb-seed ./cmd/aimee-kb-seed
.local/bin/aimee-kb-seed --root .local/general-v0-source
```

The builder delegates to Aimee's existing sparse-image compiler. It validates
public-layer constraints and requires structured semantics and provenance. It
does not sign authorization, publish CURRENT, install an image into a model,
or grant access by labeling a record global. An output manifest digest is a
source artifact only.

Aimee's publisher selects that general digest as the upstream of an optional KB
layer or a server layer, applies its own explicit corrections/suppressions and
read contracts, and compiles a **fresh authorization-specific image** using
`aimee-memory-image compile-authorized`. Only that restricted image is delivered
to the model. Do not mount this source store inside the model's environment.

The Qwen repository holds this initial experimental corpus and preparation
entrypoint. The compiler, image format and governance stay in Aimee core; a
production corpus/publishing pipeline can move to its dedicated owner without
changing the model interface. Production authorization issuance is still pending.

Synthetic proof controls and live research orchestration are separate under
`benchmarks/layered_memory`. They must never be bundled into this general corpus.
