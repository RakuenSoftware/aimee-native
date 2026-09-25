# Isolated distribution lab

These tools exercise real readers, preparation and inference with synthetic
records and ephemeral signing/authorization identities. They are not production
account services. Run only on a dedicated authorized lab. Do not use a customer
memory store, existing publication socket or production signing key.

The current probes use `/opt/aimee-memory-lab`, `.253` CT101 for private builds and
CT110 for clean installs, and a private TLS origin/registry at 192.168.0.126. The
hostnames, nested-container flags and lab signing trust are test configuration.
Only one GPU model server should run across the two containers at a time.

## Private preparation / feed

Build each fixture binary separately (the fixtures are separate Go packages):

```
go build -o aimee-selection-fixture ./distribution/tests/lab/selection-fixture
go build -o aimee-publication-stream-fixture ./distribution/tests/lab/publication-stream
```

`selection-fixture --root NEW_DIRECTORY` creates six scoped synthetic records.
Optional `--facts fixture.json` accepts 1–32 `{content, cue}` entries. Authorization
expires after one hour. Save the printed source descriptor for the private probes.
The stream fixture takes `--root APPROVED_SOURCE --socket NEW_SOCKET --denied
MARKER`; same-UID Unix authentication and the current source state are checked
on each real publication-stream iteration.

`real_preparation.py` takes `--source`, `--output`, `--encoding-revision` and
`--publisher-library`. It runs the actual reader, Rust preparer and private CPU
Gemma compiler, then checks approved reuse. The private publisher-enabled Rust
library and Torch environment are required only on this private host.
`prepare_selection_onmiss.py` configures the automatic-selection fixture from
those results. `feed_gpu_probe.py` drives the actual follower, preparation on
miss, denial, restoration and publisher disconnection with GPU answers.

`serving_matrix.py` drives an already running runtime; `matrix_server.py` owns a
fresh BF16 fixture server. `wide_working_set.py` owns a 32-record preparation and
Q8 server and scores exact five-digit answer sets. These probes record failures
and raw answers rather than silently reducing selected records or changing the
scoring rule after results are observed.

## Signed clean-client test

Provision lab keys outside the repository. Compile the launcher with
`--features lab-release`, `AIMEE_RELEASE_PUBLIC_KEY`, `AIMEE_RELEASE_URL` and
`AIMEE_LAB_CA_FILE` pointing at the **public CA**, never the signing private key.
The TLS server uses a separate CA-signed leaf certificate. Install its CA into
Podman's registry trust on the clean client. No TLS verification bypass is used.

`release_origin.py` serves a bounded operator-selected lab release directory over
TLS. `assemble_release.py --sequence N --output NEW_DIRECTORY` signs an explicit
lab-only release; its default paths describe the isolated test installation.
It needs the already built binaries, model, image digest and external signing key.
Normal production launchers reject lab-only releases.

The clean client installs with `aimee-native-lab install lab-gemma4-q8`. For the
current lifecycle test, the harness still installs synthetic approved native
banks/catalog/serving configuration explicitly. `connect` records a fixture
credential; it does **not** establish a real Aimee account session here.
`installed_lifecycle.py` validates GPU answers after an already installed upgrade
and after rollback, including retention of the release high-water sequence.

The released image contains the compiled client, Rust consumer and GPU binaries;
it does not contain these test tools, private compiler, publisher glue, authority
fixtures or private signing keys. Stop the lab release origin/registry when tests
finish. Do not promote a lab manifest to production gate evidence.
