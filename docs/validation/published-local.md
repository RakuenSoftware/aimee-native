# Published local knowledge: authorization before delivery

Date: 2026-09-20. This supersedes the local permission-enforcement assumptions in
the earlier authorization reports. Historical artifacts are preserved.

## Boundary

Aimee decides what the recipient may receive **before writing or transferring the
recipient's store**. A local read API cannot protect information that the model
can already read directly from that store. Public knowledge and approved private
memories are both consumed as delivered data, without reauthorizing each lookup.

The implemented flow is:

```text
Aimee authorization / publication
    -> physically filtered recipient image on RAM/SSD
    -> direct local reader
    -> untrained Rust Qwen adapter
    -> native attention K/V

uncovered request -> existing authorized Aimee fallback
```

The publisher's `CompileAuthorized` still checks the release decision and writes
a fresh image containing only approved serving fields and records. No source
history, excluded records, opaque metadata, aliases or relations are copied.
The image now includes a small routing descriptor committed into the manifest.
The signed grant is retained by the publisher, not copied into the delivered
directory. Production automatic export must consume Aimee's existing identity
and permission decisions; the experiments use explicit fixture approvals.

## Implementation

The model-independent `serve-published --root IMAGE` command requires only the
delivered image. It loads indexes, validates image integrity and returns facts
with canonical namespace/ID/revision. It does not read grant files, verify grant
signatures, check subject/epoch/lease, or contact a server. Temporal validity of
knowledge and compiled routing remain ordinary data semantics.

The Rust model path defaults to this reader when no legacy grant flags are given.
A new request pins the current image without the former gateway identity call.
A local hit needs one reader exchange, including canonical identity, rather than
a second authorization/resolution exchange. Remote fallback remains separately
authorized through the existing gateway/Aimee connection. The privileged
research proxy still uses its old credential/egress configuration; successful
local reads never contact that proxy. The old guarded reader is retained for
compatibility and comparison, not used by the new model launch.

The adapter has no new learned parameters, fact-specific logic, permission
evaluator, or write operation. No Qwen memory-consumption code changed.

## Measured local performance

Same `.253` host, compiled image, 256 seeded queries and persistent JSON-lines
protocol. Each query must return exactly the expected canonical record content.
The Rust path also validates canonical references and reads all 13,261 entries.
Its configured gateway path does not exist.

| Path | Median | p95 | Correct sampled reads |
|---|---:|---:|---:|
| Previous guarded reader | 41.0827475 ms | 52.872911 ms | 256/256 |
| Published reader | 0.0445295 ms | 0.048738 ms | 256/256 |
| Rust adapter → published reader | 0.0556315 ms | 0.121474 ms | 256/256 |

All **13,261/13,261** exhaustive reads through Rust returned the right content
and canonical ID. No DB, RPC or gateway is needed for these hits. This is local
transport/lookup latency, not model generation latency or a remote-Aimee speed
comparison. Kernel file caches are warm; cold SSD/concurrent-load sweeps remain.
The previous reader repeatedly parsed and verified a 13K-record grant, so the
large improvement removes unnecessary work rather than demonstrating a novel
retrieval algorithm.

Startup was 0.629579 s for the guarded reader, 0.326891 s for the published reader,
and 0.708787 s for the Rust process including its libtorch load and child reader.
The new delivered image is **12,736,494 bytes**, containing 13,261 general objects
and two approved synthetic personal objects. Publication took 0.900254 s using
an existing canonical source. This differs from the prior build timing, which
included building the source as well as compiling the recipient image.

## Full Qwen rerun

All 34 questions were rerun using the new Rust release and the 13,261-object
published image. **32/34 passed, with all 34 answers identical to the previous
guarded run.** The same physical-constant exponent and mixed personal preference
errors remain. All three public two-record composition answers passed.

Trace audit confirms identical main-prompt token IDs, zero main-prompt memory
tokens, exact expected public record sets/content/revisions, and no excluded
personal ID. Every general fact came from the local image. The model launch
contained no local grant/key flags, and its OS identity could not read the
gateway's grant file. This was checked against the running process, not inferred
only from the intended launch script.

Median end-to-end time was **6.097359 s**, versus **6.329859 s** previously;
total time was 244.506107 s versus 249.063516 s for 34 requests. These are single
serial runs, not statistically established throughput gains. Native encoding,
decode and remaining remote fallback dominate response time. The local lookup
improvement must not be presented as a comparable model-level speedup.

## Update and withdrawal behavior

Three real Rust/Go integration tests pass with no usable grant/verifier files
and no gateway at the configured path:

- Local facts and canonical references work; direct scanning of the whole image
  finds none of the excluded record or metadata canaries.
- A publisher switches the active directory to a freshly compiled generation.
  An already-running request remains pinned; the next request sees the new value
  and uses a different generation key for native-state caching.
- Removing the active publication causes the next request to fail, and that
  failed request cannot continue reading the old view. An uncovered query
  attempts fallback rather than inventing a local result.

There is deliberately no local grant-expiry test that claims delivered bytes
become confidential again. Withdrawal is a publication/distribution operation.
The trusted publisher must remove obsolete directories and quiesce active
consumers when immediate withdrawal is required. The current reader pins a
generation for a request; it does not erase an already-active bank or recover
information a recipient has already learned. Automatic production distribution,
recipient lifecycle management and obsolete-file cleanup remain integration work.

Go sparse/CLI race tests, six Rust unit tests, Clippy, and 26 historical gateway
test executions also pass. The publisher tests reject denied publication and
verify physical exclusion even when reading files directly, bypassing lookup.

The live Qwen withdrawal check also passed: after the publisher removed `CURRENT`,
the next native request failed with HTTP 502 and no answer, without changing any
grant. Afterward the temporary model/gateway and disposable Aimee containers were
stopped, the experimental image directory was restricted to the publisher, and
fallback credentials were retired. Production Aimee services were left running.

## Evidence and reproduction

[Raw artifacts](artifacts/published-local-2026-09-20/) include matched timings,
test output, publication sizes and the full-model rerun. The
[benchmark instructions](../../benchmarks/general_kb/README.md) describe the
real-process tests and reproduction commands. The
[corpus report](general-kb.md) records the earlier full-model results and remaining
fallback relevance/consumption issues.
