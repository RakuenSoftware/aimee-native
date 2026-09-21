# Layered KB research fixtures

These scripts are test orchestration, not adapter/runtime dependencies or
production authorization tooling. Rust serves Qwen and the gateway; Aimee's Go
reader verifies the exact signed snapshot. No adapter training is performed.

`prepare_live.py` creates a fresh root-private research source, includes the
25-record real seed, adds a separately labeled synthetic general canary, copies
only two previously approved synthetic Aimee records, and signs a fresh fixture
grant. It builds 27 explicit read contracts using the existing Aimee compiler.
The canary deliberately shares ID 5 with the personal drink record. The model
gets the fresh minimal authorized image, not the source directory or keys.

`probe_live.py` verifies all 25 starter reads, then submits full-Qwen requests.
It revokes its fixture grant at the end and exits unsuccessfully unless all
checks pass. **The mixed-generation checks currently fail** with the broad
upstream connection. See the [validation report](../../docs/validation/layered-kb.md).
Do not change expected outcomes to turn these failures green.

The paths are explicit research-host paths under `/opt/aimee-qwen-rust` and the
previous approved research fixture, not generic deployment defaults. The host
needs an already-built native Rust release, current Go reader, model checkpoint,
and separate protected gateway. Research subject/grant values are not production
authorization decisions.

`isolated/` records the additional failed isolation attempt inside CT 103. It
creates only the disposable `aimee-layered-kb-20260920` Compose project. Fresh
startup failed its database bootstrap, so schema and migration ledger were
copied from the prior **disposable scale-test DB**, with test-database runtime
grants restored. Only the two approved synthetic memory rows were loaded.
The existing production database was not copied or mutated. Exact-entity reads
worked, but attention-generated query strings returned no facts. This replica
was not proven equivalent to the original Aimee retrieval environment.

The isolated scripts assume their exact named disposable environment and are
retained as an audit/reproduction record, not an unattended deployment recipe.
Do not run against production. All temporary Qwen/gateway and disposable Aimee
services were stopped after the run; signing keys and database passwords remain
outside this repository in root-private research directories.
