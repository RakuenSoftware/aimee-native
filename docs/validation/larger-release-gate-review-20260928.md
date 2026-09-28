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

Normal larger-model manifests have not yet been signed or installed through
the normal channel. Existing laboratory lifecycle results establish the
component path, not that unexecuted final distribution step.

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
| `clean_install` | Larger laboratory fresh/update/rollback/restore passed, including updated model-aware installed consumption. Normal-feature launcher build and 12B recovery passed. **Exact normal-format larger installation is still unexecuted.** |
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
