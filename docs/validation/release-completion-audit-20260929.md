# Release preparation audit — 29 September

**Superseded distribution scope:** This audit treated the complete runtime image
as the deliverable. The user clarified that the deliverable is a vLLM plugin
plus an Aimee connection. The Broadcom item therefore does not block that
release. See [standalone packaging](../../distribution/vllm/STANDALONE.md) for
the corrected implementation; the original audit below is retained as history.


The engineering evidence supports the three-model controlled preview. The full
external-distribution objective remains unresolved at the exact Broadcom vendor
package review. This audit does not turn a passing subset into unconditional
release approval.

| Requirement | Inspected evidence | Disposition |
|---|---|---|
| Repair automatic source-backed learning | `benchmarks/swe_learning/source_experience.py` requires a successful model patch and independent exact-patch replay; preserves accepted procedures after failures. Primary acquisition and literal-source repair outcomes are archived. | Demonstrated in the benchmark harness; general turnkey production learning is not claimed. |
| Validate gains and regressions over repeated tasks | Primary 64 graded attempts; original broader 32-task paired study; targeted Requests repair; ten selected retained-success attempts; six-task, four-condition comparisons per larger model. | Complete at declared scope. Original broader regression remains in the record; larger native rounds reuse frozen procedures. |
| Deliver all three models | Signed candidate inventory and twelve recorded install/update/rollback/restore phases, two native answers per phase. | Passed. 12B fresh phase was sequence 5, then update/restore 6. Larger phases were fresh 1 and update/restore 2. |
| Preserve fork-free vLLM/private implementation boundary | Model-specific gate review, compiled client source-exclusion and retained build-source comparison evidence. | Recorded checks passed; source exclusion does not imply resistance to disassembly. |
| Publish working controlled delivery | Fresh TLS, pinned signature/hash and downloaded-launcher execution check on 29 September. | Passed for 12B sequence 6, Gemma26 sequence 2, Qwen27 sequence 2. No GPU experiments were rerun. |
| Preserve measured performance limits | Cold/warm/resident measurements and explicit user clarification in release recommendation. | Complete; microseconds remain aspirational, not a release gate. |
| Deliver third-party material | Existing source/notice download checks, exact Python supplement, 342-pair source inventory reconciliation. | Collected material delivered; exact Broadcom compiled payload terms remain unresolved. |
| Push evidence and give explicit recommendation | `feature/native-distribution`; three-model release recommendation and this audit. | Recommend controlled preview only, with the outstanding item explicit. |

The [fresh delivery check and archive verification](artifacts/release-completion-audit-20260929/)
record current recipient access and rechecked archived bytes. Archive checks
cover the files enumerated in the retained checksum lists plus all twelve
candidate phase digests; they are not a new execution of every experiment.

The vendor issue has persisted across the recent source-fulfillment turns. The
public repository and original exact binary package have been inspected, and
the independent Python collection and inventory reconciliation work is now
complete. The pending request for a matching Broadcom source archive or
package-level redistribution terms has not been answered. No source archive,
license permission, or public-distribution clearance is fabricated. Resolving
that external information is the next step; further GPU runs do not resolve it.
