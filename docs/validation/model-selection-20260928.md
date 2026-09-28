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
and transport fixtures, not GPU model-quality results. Full Aimee server compilation
and deployed multi-model validation remain pending. These changes are not deployed
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

## Full frontend build in progress

The local GCC 16 default mode rejects pre-existing mutable uses of `strchr` on
const-qualified CLI pointers. Explicit C17 proceeds past that code but the local
host lacks `libpq-fe.h`. Neither failure is in the changed native bridge. Logs
are preserved in [model-selection-build-20260928](artifacts/model-selection-build-20260928/).

An isolated Docker build of Aimee commit `816740e90` is now running on CT100 under
`/opt/aimee-model-selection-build-20260928`, using the existing pinned release
base and dependency recipe, two build jobs, and a 3 GiB memory limit. Its image
tag is `aimee-native-core:model-selection-816740e90`. No deployment or service
restart is part of this build; completion and runtime switching remain pending.
