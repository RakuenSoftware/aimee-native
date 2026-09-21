# Local-memory diagnostic benchmarks

These drivers preserve raw measurements. **They do not currently establish
quality-equivalent local/remote performance.** Read
[the validation report](../../docs/validation/aimee-local-sparse-memory.md)
before interpreting any timings.

- `scale_image.py`: real image build/open/read at 1K, 10K, 100K, 1M facts;
  exact, natural, alias and missing queries. Records failures, RSS, bytes, and
  individual samples. Requires an existing `aimee-memory-image` binary and
  a fresh output directory on the intended storage device.
- `update_image.py`: publish 100 changed records at each scale; verify an old
  pinned reader remains old and a new reader consumes the new generation.
  Run once after `scale_image.py`; it modifies only that benchmark image.
- `scale_aimee.py`: destructive fixture loading **only in the hardcoded
  disposable Compose project** `aimee-sparse-scale-20260920`. Uses its actual
  Aimee HTTP API over a Unix socket, excluding external network/TLS cost.
  Requires a fresh database. Optional `--indexed` compares the same queries
  before/after ordinary PostgreSQL indexes and removes only those test indexes.
  Direct COPY skips ingestion, embeddings, aliases, and KB graph behavior.
- `matched_qwen.py`: alternates configured local and remote readers in one real
  Qwen service. This controls delivery, not retrieval/governance equivalence.

The image/service scale probes have deterministic but separately drawn queries;
use identical recorded query files before claiming paired scale statistics.
Recently built files can be cached: no driver currently proves cold SSD latency.
The service probes use ten examples per family by default, insufficient for
reliable tail estimates. Do not present errors as fast successful retrieval.

An architectural comparison must first demonstrate Aimee-equivalent retrieval,
contraction/deduplication, contradictions, supersession, scope, evidence,
validity, and update behavior. Current results have no such certificate and
must remain diagnostic-only. Higher RAM/disk use is acceptable.

## Published decisions and native-state reuse

`publish_recall.py` is a separate control-plane research command. It reads real
Aimee responses and publishes exact-query, limit, scope, authority and expiry
contracts alongside canonical source records. It does not grant the model write
access. This operator-set expiry is **not an Aimee-issued freshness lease**;
production mutation/invalidation integration remains required.

`local_first_qwen.py` compares four arms in one frozen model: remote reads with
and without RAM encoding reuse, and local-first reads with and without that
reuse. It randomizes arms, retains raw responses, and excludes two warmup blocks.
The default repeated prompt measures an intentionally published working set, not
representative hit rate. `--novel` reverses the question to exercise uncovered
requests and real Aimee fallback. Check returned facts, native encoding hashes,
answers, hit/fallback counts and failures before interpreting timing differences.

The larger general image is present, but only explicitly published decisions
are locally answerable in this implementation. Image size alone does not prove
semantic coverage. Neither this benchmark nor an exact cache hit demonstrates
full local graph reasoning or Aimee-equivalent contradiction resolution.

## Authorization experiments

`authorized_live.py` uses real read-only requests to the isolated 1M-record
Aimee instance and two deliberately disjoint signed research grants. It tests
permitted local hits, permitted fallback, cross-grant denial, physical payload
exclusion, missing results, revocation, and forged request fields. Its grants
are fixture decisions, not production Aimee permission evaluation.

`issue_fixture_grant.go` signs those explicit fixture plans. Run only as the
research control plane; never expose the issuer or its private key to a model.
The script does not discover or decide who should be authorized.

Build it from the `aimee-qwen` root with
`go build -o .local/bin/aimee-issue-fixture ./benchmarks/local_memory`.
The root Go module consumes the sibling `../aimee/server-go` implementation;
the general memory-image compiler stays in Aimee.

The authorization-specific compiler writes fresh directories. Earlier raw
image benchmarks are historical diagnostics and require explicit research or
internal-backup flags with the hardened CLI. Do not reuse them to distribute
an organization-wide image to a model.
