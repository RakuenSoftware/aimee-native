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

Evidence: [test logs](artifacts/model-selection-20260928/). These are control-plane
and transport fixtures, not GPU model-quality results. Full Aimee server compilation
and deployed multi-model validation remain pending. These changes are not deployed
into the running larger-model lifecycle or coding campaigns, which retain their
pinned launcher and single-model canary bindings. After those campaigns finish,
validate approved model switching through the actual frontend before release.
