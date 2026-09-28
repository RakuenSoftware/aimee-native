# Larger release gate review

This is the release disposition for the exact Gemma 26B and Qwen 27B
sequence-2 artifact sets retained in the unsigned normal-package plans.
It is not a set of synthetic passing reports for the package assembler.

## Decision

The user clarified on 2026-09-28 that microsecond application is an
aspirational target, not a release blocker. Measured cold/warm latency therefore
does not prevent release staging; retain the measurements and their scope in
release notes. Earlier records treating that target as a hard requirement are
superseded by this clarification, without changing their experimental results.

The first normal Gemma 26B manifest is signed and independently verified.
Its normal fresh-install, update, rollback and restore canaries passed (2/2 each).
Qwen normal lifecycle remains unfinished. Qwen sequence 1 is signed;
sequence 2 is being staged. Existing laboratory lifecycle
results establish the component path, not those pending distribution checks.

The remaining review work is identified below. Broader population-level coding
improvement is a claim limitation, not an additional release requirement.
Neither reproducible builds nor invulnerability to reverse engineering is
being introduced as a new requirement.

| Existing assembler gate | Evidence and disposition |
|---|---|
| `native_accuracy` | Both packaged runtimes passed their recorded native recall cases; both completed six-task control/text/native comparisons. Qwen retains 5/5 control successes and gains one in both rounds. Gemma retains 2/2 control successes; each native round passes 4/6, with different additional successes. Supports measured scope; not universal improvement. |
| `quantized_model` | Exact Q8 artifacts loaded and executed the packaged tests and coding comparisons. Artifact hashes, full checkpoint identity, actual sizes and runtime image are recorded. This component requirement is evidenced. |
| `all_selected_records` | Complete-source token audits for all six procedural banks per model and three-fact installed canaries passed. Do not reduce a procedure to a summary or infer delivery solely from final-answer accuracy. The archived audit is the component evidence. |
| `long_conversation` | Separate packaged model reports include conversation, long-prompt, streaming and concurrent requests. These use the fixed synthetic facts; they establish integration behavior within those tested settings. |
| `tenant_session_isolation` | Model-aware authority completed 30 paced lease-isolation checks with model/policy binding. Runtime authorization results and their scopes remain in the model-selection record. Do not relabel the unpaced service failure as a passed check. |
| `revision_withdrawal` | Recorded preparation lifecycle rejects expired/withdrawn/disconnected authority and recovers reuse. Installed signed update/rollback/restore passed. These are separate pieces of evidence; preparation-cache rejection alone does not prove immediate GPU revocation. |
| `cold_warm_latency` | **Measurement requirement complete; microseconds are aspirational, not a release blocker.** All twelve banks passed tensor fidelity. Cold medians are 3.73–14.80 ms for Gemma and 1.62–4.40 ms for Qwen. Disclose these limits; resident lookup is a different measurement. Further optimization is not a prerequisite for release staging. |
| `reusable_preparation` | Both models passed fresh preparation, repeat reuse and lifecycle checks. Fresh preparation remains seconds; reuse is separate from request-time application. This component behavior is evidenced. |
| `clean_install` | Larger laboratory fresh/update/rollback/restore passed, including updated model-aware installed consumption. Normal-feature launcher build and 12B recovery passed. **Normal Gemma fresh installation, signed update, rollback and restore each passed 2/2 runtime queries (8/8 total). Qwen normal lifecycle remains pending.** |
| `binary_disclosure_audit` | Client source exclusion, exported-symbol/debug/private-marker inspection and exact library hashes passed their recorded checks. Private wheel retained-source comparison matches 16 files. This is evidence of source exclusion, not secrecy against disassembly. |
| `authenticated_delivery` | Live model-aware bootstrap, artifact fetching, scoped leases and installed consumption passed. Channel promotion remains unperformed. This component path is evidenced. |
| `license_dependency_audit` | Completed dependency-delta reconciliation: 278 Python metadata/license-file records, 591 OS records, both Rust lockfiles and six common notices per model are unchanged. Model-specific notices are separately recorded. This preserves the earlier controlled-infrastructure disposition and known limits. **The external-distribution corresponding-source/notice fulfillment bundle remains unfinished.** |

## Provenance correction

`ced6857afa0ea7b2e3f0846a62e1394e90f15607` identifies upstream vLLM, not the
private integration. That field is not a stale private commit or an unexplained
source mismatch. The retained private wheel source matches revision
`33735a9b0bbf0795f6f7f011fa74ba66d4bc2d4f`; the comparison is post-build source
matching, not reproducible-build proof. The earlier ambiguous source-identity
concern is resolved at that stated scope.

## Evidence locations

- [Unsigned exact-artifact package reviews](artifacts/larger-normal-package-review-20260928/)
- [Gemma packaged runtime](artifacts/gemma26-binary-validation-20260928-r2/report.json) and [Qwen packaged runtime](artifacts/qwen27-binary-validation-20260928/report.json)
- [Complete-source token audits](artifacts/larger-token-audit-20260928/)
- [Live model-aware authority and installed results](model-selection-20260928.md)
- [Preparation and lifecycle results](artifacts/larger-live-preparation-20260928/)
- [All twelve activation banks](artifacts/larger-activation-complete-20260928/report.json) and [controlled path comparison](activation-path-comparison-20260928.md)
- [Native binary inspection](artifacts/larger-library-audit-20260928/report.json), [private source exclusion](artifacts/larger-binary-client-20260928-r2/source-audit.json), and [retained source comparison](artifacts/larger-build-source-comparison-20260928/report.json)
- [Notice inspection](artifacts/larger-notice-audit-20260928/report.json) and [dependency version comparison](artifacts/larger-runtime-inventory-20260928/comparison.json)

[Reproducible larger dependency-delta review](artifacts/larger-dependency-delta-review-20260928/report.json) binds both exact artifact sets to the retained baseline evidence. No normal release gate was signed by this review.

## Normal-format staging after acceptance clarification

[Component gate reports](artifacts/larger-normal-staging-20260928/) now bind
the completed component evidence to each exact artifact set for controlled
normal-format staging. They explicitly withhold final installation approval
until normal signed lifecycle checks complete. The dependency report retains
its controlled-infrastructure scope; it does not grant external redistribution
clearance. This follows the existing 12B staging procedure.

The builder reuses the tested sequence-2 component bytes unchanged. Two new
normal-format sequence numbers exercise installation, update, rollback and
restore; their runtime artifacts are identical. Each phase must pass native
canary consumption. The normal launcher, dedicated client roots and deployed
model-aware authority are used without changing account bindings or the 12B
channel. Immutable validation weight copies are deduplicated only after their
bytes have been checked against the signed artifact digest.

The [first normal Gemma signed manifest](artifacts/larger-normal-signed-20260928/)
retains artifact set `c3f0d24983929829ccf4f853552fcea93234d5df9cc4f71068a9181e09eab957`.
Its Ed25519 signature was independently verified with the retained public key.
This records staging, not a completed normal installation or release approval.

[Normal Gemma fresh-runtime evidence](artifacts/larger-normal-lifecycle-20260928/gemma26/fresh1.json)
records both correct answers, 27 prompt tokens each, and the expected pinned
image under its 36 GiB container limit. End-to-end measured response times were
90.12 s and 27.40 s in this installation campaign, which included first-request
JIT activity and concurrent staging I/O. These are not native activation timings
or a matched native/text performance comparison. No model or memory bytes were
changed for this normal-channel check.

[Normal Gemma signed-update evidence](artifacts/larger-normal-lifecycle-20260928/gemma26/updated2.json)
also passed 2/2. The sequence-2 manifest signature was independently verified,
and the installed high-water sequence advanced to 2 while retaining sequence 1
as the previous release. The subsequent rollback and restore also passed 2/2 each.

[Normal Gemma rollback evidence](artifacts/larger-normal-lifecycle-20260928/gemma26/rollback1.json)
records 2/2 correct native answers after returning to sequence 1. The anti-rollback
high-water mark correctly remains at sequence 2. The [restore check](artifacts/larger-normal-lifecycle-20260928/gemma26/restored2.json)
returned to sequence 2 and also passed 2/2. Across all four lifecycle phases
this is 8/8 repeated three-fact canaries, not eight independent tasks.

The [consolidated notice bundle](artifacts/consolidated-notices-20260928/)
retains 588 unique notice texts and references for all 277 third-party Python
packages. The private Aimee notice is delivered separately. This closes Python
notice collection, not corresponding-source fulfillment. The [OS package payload
inspection](artifacts/os-notice-relationships-20260928/) distinguishes headers,
samples and metadata from compiled binaries; absent notice filenames alone are
not treated as additional source-distribution requirements.
