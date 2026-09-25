# Private approved-publication bridge

`native-prepare` consumes an **already authorized**, recipient-scoped published
image through the existing `aimee-memory-image serve-published` reader protocol.
It does not issue permissions. Build it separately from the client:

```
cargo build --locked --release --no-default-features \
  --features preparation-service --bin native-prepare
native-prepare /private/preparation.json
```

The operator-owned JSON specifies `image_reader`, `memory_image`, `query`, `limit`
(1–32), `authority`, `recipient`, `model_revision`, `runtime_profile`,
`encoding_revision`, `position_policy`, `cache_root`, `compiler` (argv array) and
`host_memory_budget`. The compiler receives the complete approved response and
ordered record revisions on stdin, with `--output`, `--identity`, `--key` appended
to its arguments. `gemma_compile.py` is the private reference compiler, requiring
`--model` and `AIMEE_NATIVE_LIBRARY` pointing to the private publisher-enabled
Rust library. `publisher.py` is private ownership glue; no research checkout is
needed by this worker. Build the default Torch-enabled library separately from
the stripped consumer library.
No preparation worker is shipped in the client image.

Cache reuse is bound to the authorization view, recipient, full selected record
set and encoding/runtime identities. Approval is checked again before a cache
hit or newly compiled result is released. Compilation is control-plane work;
the inference attention path does not perform this check or run an encoder.

`follow_native.py --config /private/supervisor.json` owns the server and existing
Aimee feed follower. Its config contains:

- `serving_config`: native serving JSON, with `start_paused: true`, a local
  `control_socket`, catalog, recipient, model, library and budgets.
- `server`: argv for `aimee-vllm --config ...` or the matched container launcher.
- `follower`: argv for the existing authenticated publication follower. It must
  emit the existing installed/unchanged/withdrawn JSON event protocol.
- `preparations`: publication-name-to-argv mapping for `native-prepare` configs.
- `restart_limit`: optional bounded recovery count, default three.

No shell interpolation is used for these argv arrays. Feed credentials remain
with the existing authenticated follower. Configure a single approved recipient
per serving instance; this component is not a public multi-tenant gateway.

The supervisor stops new admissions before preparing an update, cancels obsolete
preparations, checks result/view/recipient binding, atomically replaces the private
catalog, and requests coordinated activation. Each withdrawal advances a
control generation; activation from an older preparation is rejected even if
its control request outlives cancellation. Every worker must acknowledge the
same digest before ingress resumes. Withdrawal stops new requests; existing
requests may finish. Feed termination stops the owned server. A poisoned server
requests full restart; restarted serving remains closed until new authorization.
Health checks also run while publication events are arriving. Failed preparation
is retried on the next unchanged-view event; only successful activation suppresses
that retry. After stopping its server, the supervisor removes the observed owned
Unix socket if the same socket is still present, so forced exits can restart.

The control socket is Unix-only, mode 0600, with same-UID peer enforcement. Keep
it in the mounted publication directory for containers. HTTP control routes are
not added. `refresh`, `withdraw`, and `status` are operator control operations.

`selection.py --config /private/selection.json` provides trusted per-request
selection through a same-UID Unix socket. Its configuration supplies `socket`,
`image_reader`, `memory_image`, `authority`, `recipient`, `catalog` and `limit`.
Set `selection_socket` in serving configuration to enable it. The caller sends
only a query; any supplied publication ID is overridden. A cached working set
must match the entire ordered authorized revision list and current view.
Optional `preparation_config`, `native_prepare` and `control_socket` enable
private preparation on misses with approval checked again before activation.
Complex/missing reads currently fail explicitly pending authoritative fallback.

This remains a **co-located private integration**. Hosted account authentication
and recipient-bound prepared-artifact delivery to remote clients still require
deployment integration. The protocol tests
use synthetic authority and are not evidence that a live production deployment
has been authenticated. Do not open an external preview on that assumption.

Run the process tests with `python3 -m unittest discover -s distribution/service`.
The standalone preparation protocol probe is `probe_prepare_boundary.py`; it
requires `--binary` and `--fixture` and is intentionally separate from discovery.
