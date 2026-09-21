# Live incremental KB checks

These scripts run on the research host `192.168.1.253`, against only the disposable
`aimee-layered-kb-20260920` Docker project in LXC103. They are not production setup
commands. They intentionally make synthetic Aimee memory mutations.

`prepare_live.py ROOT` creates a fresh private source configuration, a SELECT-only
PostgreSQL role, synthetic records via the existing Aimee HTTP API, an exact-ID
release policy, and publisher/consumer transient services. ROOT must be a new
folder under `/opt/aimee-qwen-rust`. It needs the existing approved 249,105-record
public base and built Aimee executables. Stop only prior research services with
the same names before another run. Never export `ROOT/private` as evidence.

The full-model probe requires the Rust runtime on port18793, record encoding
enabled, traces under ROOT/traces, and the new recipient image at ROOT/image.
Start the model **after** the consumer has committed CURRENT. The gateway must
use that same published image plus a real authenticated restricted Aimee ingress
for `stream-live`. An absent gateway is a transport failure, not an answer-quality
result. Aimee's bus principal permits only one bridge attachment at a time; reuse
its granted executable and identity, never weaken the grant to admit a probe.
The recorded `start-model.sh` and command JSON in the artifact set show exact
successful research service arguments.

```sh
python3 -u probe_live.py ROOT --output live-results-r2.jsonl
python3 -u check_live_safety.py ROOT
```

The mutation probe covers initial cold/warm composition, an actual same-key update,
deletion, supersession, explicit release of the replacement identity, and narrowed
release. It records raw responses, exact prompt IDs, cache retention/encoding
counts, selected canonical references, transferred bytes and publication time.
It checks physical removal of old/unapproved synthetic bytes. Results files are
never overwritten. A failed attempt must remain archived.

The safety probe checks model filesystem permissions, consumer disconnect/resume,
and withdrawal during an active Qwen generation. It deliberately leaves the
release inactive and the recipient image withdrawn. Do not reactivate automatically
without reviewing the experiment's explicit policy.

See `docs/validation/incremental-publication.md` for measured results and limits.

## Optimized publication measurements

Use the current Go publisher and image-reader builds, without changing Rust's
native-memory transport:

```sh
python3 prepare_live.py ROOT \
  --publisher aimee-memory-publish-optimized \
  --image-reader aimee-memory-image-optimized
python3 measure_publication.py ROOT --rounds 6
python3 probe_live.py ROOT
python3 check_live_safety.py ROOT
```

`measure_publication.py` temporarily updates only the approved synthetic drink and
restores its original content in the last round. Run it before the native mutation
probe. It measures from the real Aimee API mutation through visible publication,
records the API duration separately, and joins receiver metrics by generation.
The preparation driver now saves publisher/consumer command JSON for reconnect.
Model/gateway setup still follows the existing constraints above.

The publisher's `--history-keep` (default 64) and `--compact-interval` (default 1m)
control background private resume-history compaction. For a bounded research
compaction test, use two checkpoints and 1s. Do not run independent compaction
concurrently with a writer; the publication service serializes its worker with
compilation. A pruned resume cursor intentionally falls back to a full snapshot.

Measured results and remaining limits: [publication latency](../../docs/validation/publication-latency.md).
