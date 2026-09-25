# Distribution recovery and installer lifecycle — 2026-09-25

Follow-up to `vllm-release-20260925.md`. This work stays in the private integration
repository and does not patch or fork vLLM.

## Recovery defects addressed

- A failed preparation was treated like successful activation when a later feed
  event reported the same view. It now retries after failure; pending work and
  successful activation still suppress redundant preparation.
- Continuous feed events could starve the idle-only health check. Health checks
  now have their own deadline while retaining a single pending stream read.
- A refresh can outlive cancellation of the client awaiting its control response.
  Withdrawals now advance a generation; supervised refresh carries that generation,
  and superseded activation is rejected before changing admission or workers.
- Forced server termination can leave its control socket behind. The supervisor
  removes only the socket it observed on its owned server, after the process exits,
  and only if the inode still matches. A replacement endpoint is not deleted.

These changes do not introduce file verification or control traffic into attention.

## Process and signed-installer evidence

Six supervisor tests pass, including real subprocesses and Unix socket I/O:
first preparation fails, unchanged publication retries successfully, catalog is
installed, feed EOF stops the server, and the owned socket is removed. Authority
and compilation in that process test are explicitly synthetic.

Five control tests pass, including stale-generation rejection followed by valid
activation without poisoning the current generation.

The Rust launcher suite passes its existing eight unit tests plus a new integration
test. The integration test signs two fixture releases with an ephemeral test key,
installs and upgrades them, invokes the real CLI, rolls back, and rejects a corrupt
signature without changing the active release. It captures the Podman invocation
and verifies image selection, model paths, token exclusion and the absence of an
installation-root mount. The container executable is a fixture: this is **not**
clean-machine GPU/container installation certification or a production trust root.

The first Rust integration build failed type inference for a fixture map; an
explicit map type fixed it. Both build records are retained. The standalone
preparation probe was renamed so unittest discovery does not execute its CLI parser.

## Deployment work still outstanding

The authenticated publication interfaces are reused, but a live Aimee deployment,
remote native-artifact delivery and automatic trusted request selection are still
needed. Signing/origin provisioning, a signed clean-machine container install,
broader quantization parity and isolated performance certification remain open.
Do not equate these process/fixture tests with production authorization.

## Real GPU HTTP recovery

The compiled r9 client passed `http_recovery_probe.py` on Gemma BF16, TP2, both
7900 XTXs and the existing synthetic three-record publications:

1. Startup remained paused and returned HTTP 503 before activation.
2. A superseded generation could not activate memory. The current generation
   activated only after both workers agreed.
3. Native recall returned the expected private code.
4. A long streaming response was closed after generated content arrived. Admission
   moved to `restart_required`; subsequent generation received HTTP 503.
5. The server was stopped and restarted. It again remained closed; an old generation
   was rejected. Fresh activation succeeded and native recall returned the same code.

This probe performs the restart explicitly. Automatic supervisor recovery is
covered by the process/unit tests above; a live authenticated feed plus automatic
GPU restart is still a combined integration gate. No production credentials were
used. The run is a lifecycle test, not a throughput benchmark.

The private image was rebuilt as `localhost/aimee-native:gemma-preview-r6`, image
configuration ID `06b802798f4450a69c0171f78fa12b50eccf26e05e059dbfbd655668aba6ac36`.
Its compiled control module passes all five control tests. The GPU test used the
same compiled r9 wheel in the lab runtime; it did not certify a new clean host.
