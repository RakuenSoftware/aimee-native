# Restricted upstream research run

These are test drivers for the disposable `aimee-layered-kb-20260920` Compose
project on CT103, reached via `.253`. They never target the primary container.
The serving path is Rust -> Go restricted ingress -> live Go memory module ->
Aimee store bus -> PostgreSQL. Python only provisions and checks the experiment.

1. Build `aimee-module-memory`, `aimee-memory-read`, and `aimee-memory-image`
   from sibling `aimee/server-go`; build the Rust adapter with the documented
   ROCm/libtorch settings.
2. Copy the first two binaries to CT103 `/tmp`. Run `install.py` there. It
   installs them only inside the disposable server and admits research principal
   200. This is explicit test wiring, not production module registration.
3. Start `aimee-memory-read` inside that container as UID1000, using
   `--bus /var/lib/aimee/server-module-bus.sock
   --socket /var/lib/aimee/restricted-read.sock
   --namespace aimee-published --principal 200`.
4. Expose that socket to the privileged gateway with a short root-owned symlink
   `/run/aimee-restricted-upstream.sock` through CT103's `/proc/PID/root` view.
   Keep the model identity outside that trust boundary. The socket is mode0600.
5. Run `prepare.py` on `.253` in a fresh experiment directory. It creates a
   research-signed authorized image from the 25 public facts, one separate
   synthetic general canary and the two approved synthetic personal memories.
6. Start Rust gateway with `--upstream-unix /run/aimee-restricted-upstream.sock
   --upstream-namespace aimee-published` and the fresh image/grant binding. Start
   Qwen with the same image and a two-result memory limit. Use the isolation and
   model flags in the Rust runtime guide.
7. `probe_upstream.py` checks the live module; `probe_model.py` checks generation,
   local starter reads and revocation. The model probe revokes its grant last.
8. `add_distractor.py` runs in CT103 and adds an explicitly unapproved synthetic
   row only in the disposable DB. For a repeat, explicitly reauthorize the same
   fixture or create a fresh grant/image; preserve first-run artifacts. The
   recorded second run reauthorized the identical fixture and reused encoding
   caches, so its times are warm-cache observations.
9. `audit_traces.py` checks prompt equality, canonical identities, restriction
   receipts and absence of the excluded canary. Stop test services and revoke
   grants when finished.

The first run used only approved personal DB rows; the second additionally used
row999 with competing answers and a secret-value canary. Both passed. See
[the report](../../../docs/validation/restricted-kb.md) for exact numbers and
limitations. Scripts have deliberate research-host paths and fixture grants;
do not run them against a production authority.
