# Approved model selection for one Aimee account

The installed signed runtime selects its native model identity automatically.
An operator can approve Gemma 12B, Gemma 26B and Qwen 27B under the same account
without rebinding that account each time the user switches installations.

The existing `preparer` remains the default for legacy bootstrap requests.
An optional `models` map on each authority binding holds additional complete
Preparer objects, keyed by their exact `profile.model` identity. Each must use
the default recipient. The server rejects unknown models, duplicate selectors,
other query parameters and recipient changes. A model selector grants no access:
the authenticated principal, current release policy, template and lease still
control delivery. A binding change invalidates previously scoped leases.

The Rust launcher reads the installed signed runtime profile before bootstrap.
It includes the model selector on bootstrap, selection, artifact downloads and
fresh approval, including reuse of existing local artifacts. The minimal Aimee
C bridge forwards the query after authentication; model routing and publication
implementation remain in aimee-qwen. No inference engine fork is involved.

## Validation

- Rust: 18 unit tests and the signed container lifecycle fixture pass.
- Go nativepublication package passes, including approved alternate selection,
  cross-model capability rejection, recipient restrictions and withdrawal.
- Seven C bridge / Go daemon tests pass, including query forwarding and malformed
  request rejection. This compiles the actual bridge header with warnings as errors.
- The TLS launcher test passes with a private CA and named endpoint. It exercises
  selection, both artifact downloads and approval for a model identity containing
  slash and plus characters, then repeats with local artifact reuse. Every request
  carries the exact model identity; hostname and CA rejection checks remain intact.

- A separate real TLS bootstrap test passes for the selected model, legacy default,
  mismatch rejection, denied selection and invalid identity lengths. Its first
  fixture certificate was incorrectly marked as a CA and TLS rejected it; the
  corrected end-entity certificate passes without disabling verification. Both
  runs are retained.
- The actual Aimee `server_http.c` caller compiles through the normal Make target
  with `-Wall -Wextra -Werror`; this is stronger than the isolated header check.

Evidence: [test logs](artifacts/model-selection-20260928/). These are control-plane
and transport fixtures, not GPU model-quality results. Full Aimee server compilation passes in the isolated release image;
deployed multi-model validation remains pending. These changes are not deployed
into the running larger-model lifecycle or coding campaigns, which retain their
pinned launcher and single-model canary bindings. After those campaigns finish,
validate approved model switching through the actual frontend before release.

## Live validation handoff

`distribution/tests/live_bootstrap_authority.py` now accepts repeated `--model`
arguments. Against one enrolled account, supply each approved native identity:

```sh
python3 distribution/tests/live_bootstrap_authority.py \
  --config /private/client/config.json --recipient '<recipient>' \
  --model '<12B-native-identity>' --model '<26B-native-identity>' \
  --model '<27B-native-identity>' --output /private/model-bootstrap-report.json
```

It retains the enrolled, invalid/missing bearer and missing client-certificate
checks, verifies each returned model/recipient, and requires denial of unknown
models, duplicate selectors and recipient overrides. The helper only reads
bootstrap state; it does not alter bindings, prepare memory or start inference.
The extension is syntax-checked, but live multi-model execution is pending the
new frontend and approved binding deployment after the pinned campaigns finish.

## Full frontend build completed

The local GCC 16 default mode rejects pre-existing mutable uses of `strchr` on
const-qualified CLI pointers. Explicit C17 proceeds past that code but the local
host lacks `libpq-fe.h`. Neither failure is in the changed native bridge. Logs
are preserved in [model-selection-build-20260928](artifacts/model-selection-build-20260928/).

An isolated Docker build of Aimee commit `816740e90` completed successfully on CT100 under
`/opt/aimee-model-selection-build-20260928`, using the existing pinned release
base and dependency recipe, two build jobs, and a 3 GiB memory limit. Its image
tag is `aimee-native-core:model-selection-816740e90`. No deployment or service
restart is part of this build; the image is built, while deployed runtime switching remains pending.

Completed image: `sha256:a97d2436f4a264acb96eb328bcf44931cd69ecd0720eabafa3b2ea049c4032f0`.
The full build log, recipe and terminal result are preserved with the local
prerequisite failures. The running frontend has not been replaced.

## Deployment candidate corrected to preserve the memory owner

The first successful frontend build used the original release base, which lacks
the subsequently deployed restricted-search memory-module fix. It is **not the
deployment candidate**. Before deployment, the final stage was changed to use
the exact currently deployed bridge.2 image, preserving that module.

BuildKit interpreted a raw `FROM sha256:…` image ID as a registry tag and rejected
the second build. The third build used a dedicated local tag bound to the same
image ID and passed. Both logs and recipes are retained.

The corrected candidate is `aimee-native-core:model-selection-816740e90-r3`,
image `sha256:34b9aecbd4b21d868c50080a13ce5ae4e4f41b67e489e9e71678e6b6edec0243`.
Running SHA-256 checks inside the old and new images with networking disabled
confirmed identical memory-module bytes and different frontend bytes. This
closes the packaging regression before deployment; it does not substitute for
live authorization checks. No running frontend or GPU campaign was changed.

## Separate model-aware launcher candidate

The model-aware lab launcher is now built and snapshotted separately at
`/opt/aimee-large-release-validation/model-selection-launcher/aimee-native-lab`,
SHA-256 `f9402df450278e9798642d99f6e177ac7eb42751cdc36b654eb8763492cd2cb3`.
Its lab-feature unit, signed lifecycle and TLS bootstrap tests pass; its source
and trust-root hashes are preserved in [build evidence](artifacts/model-selection-launcher-20260928/).
The running larger-model campaigns continue using their earlier assembly
snapshot. This candidate is for the subsequent deployed model-switching check
and remains lab-only, with no production-channel promotion.

`build_larger_launcher.py` now accepts separate source, build, evidence and binary
snapshot paths. Exclusive log/binary creation prevents overwriting a prior
candidate; defaults retain the existing larger-model build recipe.

## Private delivery-service candidate

A separate `CGO_ENABLED=0`, trimmed and stripped Go delivery-service binary is
staged at `/opt/aimee-large-release-validation/model-selection-service/aimee-native-delivery`,
SHA-256 `14649f9e09dbe0eed44f8b02752f681334e7c1cae44d3b326a428bf1e971c43c`.
Before building, every non-test nativepublication source and the command entry
point was checked against the local committed source hash. Module and execution
policy source hashes, Go build information and the build command are retained
in [service evidence](artifacts/model-selection-service-20260928/).
All seven actual C bridge / authorization fixtures pass against this exact
candidate binary. It is not yet deployed; the active service remains unchanged.

## Three-model binding staged without changing the active account

The private candidate is `/etc/aimee-native/bindings.three-models.candidate.json`
on CT100. It keeps the original 12B default and adds the two larger signed native
identities under the same recipient, using their existing private preparation
templates. Model configuration digests were checked against sequence-2 signed
package contents. The active binding's bytes were verified unchanged.

Before applying it, require the lifecycle coordinator to finish and restore the
original binding SHA-256
`b9441137dedcc2ecc0f362317e6d0d4201c7ae84b41f7a6b20b5c46040312a83`.
The candidate SHA-256 is
`4bda33b9f6ded080077dd83a070ae6404609da61452c93212ff7cb0778048205`.
Only its noncredential manifest is archived; the binding itself stays private on
the authority host. Frontend/service rollout and live enrolled-account checks
remain prerequisites to claiming deployed model switching.


The exact tested delivery binary is also staged on the authority host at
`/opt/aimee-native/bin/aimee-native-delivery.model-selection`, root-owned and
executable. Its SHA-256 matches the build above. The active binary was verified
unchanged and the current service remains active; no restart or account-binding
change was made. [Staging receipt](artifacts/model-selection-service-20260928/authority-host-staging.json).


## Authority rollout hit the entrypoint startup deadline

After the larger signed lifecycle stopped and restored its original account
binding, the staged frontend, delivery binary and three-model binding were
applied with private rollback copies. The candidate exited before readiness;
automatic rollback restored the original files and image, but that frontend
also exited before readiness. Its entrypoint reported the server still running
without its HTTP socket after the default 120 seconds. This is not a successful
rollout or rollback-readiness result.

The original frontend is being restored with the supported
`AIMEE_WFE_SOCKET_WAIT_TENTHS=6000` startup allowance. Audit verification remains
enabled. The host simultaneously showed substantial I/O pressure. That is
consistent with slow startup but does not independently prove the full cause.
The candidate remains unvalidated until the original service recovers and a
subsequent deployment passes live authorization checks.
[Failed rollout record](artifacts/release-io-startup-failures-20260928/).


The original frontend subsequently reached healthy state with zero restarts
under the 600-second allowance, and the restored account binding matched its
original hash. [Recovery receipt](artifacts/release-io-startup-failures-20260928/recovery-result.json).
A separate candidate rollout now retains that entrypoint allowance, uses a
660-second external readiness window, and captures candidate logs before any
rollback. Its live authorization outcome remains pending.


## Deployed authority and three-model bootstrap passed

The corrected rollout reached healthy state with the candidate frontend image,
tested delivery binary, and three-model account binding. The runtime directory
inode was preserved. Startup completed in approximately 205 seconds; the former
120-second entrypoint allowance was insufficient for this host.

The enrolled client passed all 10 live bootstrap checks: default selection,
each of the three explicit model identities, missing/invalid bearer denial,
missing client certificate denial, and rejection of an unapproved model,
duplicate model selector, and recipient override. The same account selected all
three approved profiles without changing recipient authority.

[Deployment and live authorization evidence](artifacts/model-selection-live-bootstrap-20260928/).
This closes live bootstrap selection, not artifact delivery, lease lifecycle,
or installed GPU consumption through the new model-aware launcher. Those checks
remain required before the deployed path is release-complete.


## All three models passed live artifact fetch and approval

The same enrolled account fetched approved memory for Gemma 12B, Gemma 26B and
Qwen 27B through the deployed model selector. Each model used a fresh client
cache followed by a repeated fetch: **6/6 passed**, each retaining all three
selected records. Publication identity and authorized view remained stable
within each pair; publications differed across model encodings while the
source authorization view was shared. The Rust delivery path performed the
artifact checks and approval rather than a fixture bypass.

The authority reused existing private preparations. These checks do not show
new 12B compilation while its resident compiler is paused; restoring that
service remains necessary after the larger-model resource window. Initial
client fetches took approximately 0.33–0.37 seconds and repeated fetches
0.18–0.20 seconds, including network selection, local storage and approval.
They are not GPU application latency measurements.

[Sanitized results and executed recipes](artifacts/model-selection-live-fetch-20260928/).
The queued installed-runtime probes still need to prove GPU consumption through
the new model-aware launcher; the broader coding comparisons are also unfinished.


The 12B follow-up is now queued on the same GPU lock after the existing larger
jobs. It restores the paused resident compiler, waits for its ready socket,
and runs the already installed signed sequence-6 runtime through the model-aware
launcher. Two normal three-fact recalls and an interrupted-stream recovery
with fresh authorization are required. The compiler is left running after this
check so default-model preparation is restored. This is queued work, not a pass.
[Executed coordinator recipe](artifacts/model-selection-12b-followup-20260928/).


## Live model-scoped lease isolation passed

The deployed enrolled-account route passed 30/30 paced lease checks across the
three approved model identities: selection, own-model approval and index fetch,
all six cross-model directions for approval/index/payload denial, and omitted
selector behavior. The default model correctly permits its legacy selector-free
approval; either larger model's lease is denied when routed to that default.
No credentials or lease tokens are included in the reports.

An initial unpaced run passed its first 13 checks, then received HTTP 503 instead
of the expected 403 on a cross-model approval. It did not grant access and was
not counted as a passing isolation check. A separate run with 0.5-second request
spacing passed all expected statuses. The original 503's cause is not established;
no authorization rule was relaxed or service configuration changed for the retry.
[Both reports and executed recipes](artifacts/model-selection-live-lease-isolation-20260928/).

## Qwen signed update passed installed native consumption

The model-aware launcher served both native canary requests correctly from
signed Qwen sequence 2. Each recalled all three synthetic facts through the
deployed authority with the account binding unchanged. The exact pinned image
was `b71da5a610b2871b2bb96ed05cf4d9de71036a78baa4d349aa9d87e1f23f5a9d`;
active manifest was `9583fee3e7cee9475ecef3c9a1463aa731f515ecb30c43da20a07b8cd92548c5`,
with high-water sequence 2. Whole-request times were 6.15 and 4.07 seconds,
including generation and first-use compilation where incurred; these are not
measurements of memory application alone. Each request used 26 prompt tokens
and generated 47 tokens. The report is preserved in
`artifacts/model-selection-installed-results-20260928/qwen27-updated2.json`.
The coordinator has advanced to rollback; rollback/restore and Gemma's updated
model-aware probe are still pending.

## Qwen rollback passed installed native consumption

Both native canary requests passed after rollback to signed sequence 1
(`c5180309b74100e2e54d00db47b5a69bc02f7b61ada01c5f59f2016c1ad70e75`).
The high-water sequence remained 2. This verifies native consumption after
rollback through the deployed model-aware launcher; the two repeated queries
use the same three canary facts. Raw results are preserved in
`artifacts/model-selection-installed-results-20260928/qwen27-rollback1.json`.
The coordinator has advanced to restored sequence 2; that phase remains pending.

## Normal-feature model-aware launcher built

The same model-aware source now has a normal-feature optimized build at
`model-selection-normal-launcher/aimee-native`, SHA-256
`a7ebbb5d0f9493f205ca355fab640f56e31cc686219aa038ac348de4ac4727e6`.
It omits the lab-release feature, uses the existing release public key/CA and
normal HTTPS origin, and retains rejection of lab-only packages. Normal-feature
unit and signed-lifecycle/TLS-bootstrap tests passed before compilation.
Build logs and exact source/trust hashes are preserved in
`artifacts/model-selection-normal-launcher-20260928/`.

The build helper now supports an explicit normal edition, requiring an HTTPS
release URL and using two Cargo jobs. Existing lab defaults remain intact.
The waiting 12B recovery worker was replaced before GPU acquisition with the
same protocol selecting this binary. The replacement receipt records both PIDs
and the script/binary hashes. Its output is
`model-selection-12b-normal-restore-probe`; the earlier waiting-only directory
is retained unchanged. GPU recovery validation of this normal binary is pending,
and no public channel was changed. Qwen/Gemma lab packages continue with the
lab launcher during their already-active checks.

## Qwen restore passed; larger Qwen lifecycle complete

Restored signed sequence 2 answered both native canary requests correctly,
with high-water sequence 2 intact. The report is preserved in
`artifacts/model-selection-installed-results-20260928/qwen27-restored2.json`.
Together with the earlier fresh-install pair and the newly recorded update and
rollback pairs, all four Qwen signed lifecycle phases passed (8/8 repeated
canary queries). The fresh phase used the earlier launcher; update, rollback
and restore used the model-aware launcher and deployed multi-model authority.
These are the same three synthetic facts, not eight independent knowledge cases.
The installed coordinator has moved to Gemma's model-aware sequence-2 check.
No normal-channel promotion follows automatically from this lab lifecycle pass.

## Larger installed model-aware batch complete

Gemma sequence 2 passed both native canary requests through the updated
model-aware launcher. The full batch is passed: Qwen update, rollback and
restore plus Gemma sequence 2 each passed two queries. The authority binding
remained unchanged throughout. Exact results and the terminal batch report are
in `artifacts/model-selection-installed-results-20260928/`. This closes the
queued larger-model installed-consumption checks; it does not promote the
lab-only manifests or substitute for the pending normal-launcher 12B recovery
and larger-bank timing measurements.

## Normal launcher 12B recovery completed

The normal-feature model-aware launcher passed both initial 12B native canary
queries. After deliberate interruption of an active streamed native request,
it replaced its owned runtime and broker, obtained fresh authorization, and
correctly recalled all three canary facts again. The new container identity
differed from the original, and admission health returned successfully.
The previously paused resident 12B compiler was restored and remains active.
Exact report and executed coordinator are preserved in
`artifacts/model-selection-normal-recovery-20260928/`. This closes the queued
normal-binary recovery check. It does not assert broader learning reliability
or promote the larger lab-only packages to normal release channels.

## Normal larger-model package plans prepared

Unsigned normal-format plans now exist for both larger models in
`artifacts/larger-normal-package-review-20260928/`. They retain the exact tested
sequence-2 component bytes and artifact-set identities; only proposed normal
model identity, sequence and version metadata differ. Each plan includes a
review record with hashed evidence references and distinct upstream-runtime
and private-integration provenance. No artifact was signed or published by
this preparation. Gate evidence is intentionally empty, so the release
assembler rejects signing until explicit component dispositions exist.
The cold-application target and broader learning reliability remain unmet;
these cannot be turned into passing release criteria by package assembly.
