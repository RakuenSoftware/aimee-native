# Portable plugin evidence

The final candidate is identified by `r2-wheel-audit.json`. `wheel-audit.json`
and `final-wheel-audit.json` identify superseded candidates; the latter precedes
the upload-completion correction. They are retained rather than overwritten.

- `installed-gpu-numerical.json`: installed-wheel decoder and attention references.
- `installed-activation*.json`: final bit-exact activation/ownership suites.
- `activation-diagnostic.json`: superseded candidate's pipelined transfer failure.
- `no-pipeline.json`, `staging-diagnostic.json`, `barrier-diagnostic.json`:
  isolation experiments; staging inspection itself introduces synchronization.
- `cross-compile-profiles.json`: compilation only, explicitly no GPU execution.
- `*-live.json`: installed client, authenticated Aimee, real model answers.
- `before-barrier-gemma26-live.json`: superseded candidate's earlier live pass;
  it does not substitute for the final candidate's tests.
- `initial-gemma26-live.json`: initial launcher/libc incompatibility.
- `native-linkage.json`, `native-libc.json`: installed native binary dependencies.
- `gguf/dependency.json`: retained upstream assets and omitted optional binary.
- `published-delivery.json`: signed download and dependency verification.
- `pip-extra-delivery.json`: pip resolution/download from the controlled origin.

Logs are losslessly gzip-compressed. The Podman process-launch failures in
`initial-r2-install.log.gz` and `remaining-live-r2.log.gz` are storage infrastructure
errors; `resume-r2.log.gz` resumes at the interrupted repeat suite. No assertions
or expected values were changed to resume testing.

These artifacts exclude tokens, connection configuration, signing keys, private
client state, weights and prepared memory payloads. Model launch configurations
contain no credentials. `SHA256SUMS` covers the retained evidence.

The initial pip verifier incorrectly required a nonempty install plan. Pip had
already downloaded the pinned extra and correctly reported that the installed
environment satisfied every requirement. The corrected verifier accepts that
result and independently downloads and hashes the dependency through pip; see
`initial-pip-extra-plan.json`, `pip-extra-plan.json` and their logs. This changed
the verification script, not the published wheel or its dependencies.
