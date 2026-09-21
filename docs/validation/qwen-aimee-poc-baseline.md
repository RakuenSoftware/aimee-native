# Qwen ↔ Aimee native memory: established baseline and corrections

Subsequent design work: [local sparse memory in RAM/SSD](../proposals/pending/aimee-local-sparse-memory.md).
The user has since requested fast local consumption and incremental updates;
the historical latency deferral below describes the completed POC, not the
requirements of that next phase.

Date: 2026-09-20. Status: **core proof of concept established, including
two-memory composition without prompt preload.** This is the handoff for the
next phase and the current interpretation of the linked historical experiments.

## Question answered

The agreed feasibility question was:

> Can a Qwen latent-memory mechanism consume a memory whose authoritative
> source is Aimee, with no representation of that memory in the model's textual
> context?

For the implemented native K/V path, yes: existing Aimee returns authoritative
records, the untrained model-specific adapter converts them to Qwen states, and
frozen Qwen uses those states while generating. Recalled memory text is absent
from the main generation prompt. Individual recall and two-record composition
have both succeeded. This core feasibility question is no longer an open gate.

The precise representation matters: current Aimee records are tokenized and
encoded in a **separate frozen-Qwen forward pass** to produce external K/V
states. These are additional attention states, with real computation and memory
costs. This is not a compact learned projection or a claim that Qwen never
processes the memory text. No adapter training or main-cache replay is involved.

## What had already worked

| Implementation / experiment | Recorded result | Interpretation |
| --- | --- | --- |
| Older learned-projection composition probes | Singleton format prerequisites failed; combined output supplied only the drink. Multiple-choice probe also failed to follow its response contract. | Different adapter and representation. These did not isolate a general composition limitation. |
| Direct untrained adapter, prompt-driven lookup, limit 4 | `oolong;Lima`, and `Lima; oolong` with requested order reversed | Native consumption and composition were already demonstrated before hybrid preload was added. |
| Earlier hidden-state native read, limit 4 | `oolong;Lima`; memory disabled returned `unknown` | Native-runtime retrieval and two-record consumption also worked before hybrid preload. The query readout was noisy. |
| Attention-query bridge, limit 1, chained lookup cases | Received the first link record repeatedly; never received the second phrase record | Failed acquisition of the second fact; not a test of composing two available facts. |
| Current attention-query bridge, limit 4, preload disabled | `oolong;Lima` | The current native path composes both facts without prompt preload. |
| Same current joint prompt, hybrid / legacy prompt-only / memory disabled | `oolong;Lima` / `oolong;Lima` / `unknown` | Hybrid works, but preload is not required for this success. |

Sources: [older composition probe](native-memory-composition.md),
[choice probe](native-memory-choice.md), [direct adapter](qwen-aimee-direct.md),
[hidden-state read](qwen-aimee-native-read.md),
[attention bridge](qwen-aimee-attention.md), and [hybrid results](qwen-aimee-hybrid.md).
Each report retains its original raw results and implementation provenance.

## Corrections to the earlier analysis

The assistant incorrectly treated different experiments as a continuing
"native composition fails" result, overlooking earlier successful composition
and failing to separate retrieval availability from consumption. The user
repeatedly challenged the tests; that objection was justified.

The one-record setting constrained **each Aimee search response**, not the
total bank capacity. Multiple calls could still accumulate multiple records.
In the attention-chain failures they did not: the second required record never
arrived. Those failures cannot establish that Qwen cannot combine two supplied
memories. A failed answer is insufficient to locate a failure in composition.

The current four-record native-only control succeeds. Consequently:

- Do not claim preload fixed composition; native-only also succeeds.
- Do not claim all historical failures were caused by the one-record limit.
  Older learned-adapter probes supplied both projections. Earlier runtime-token
  decode tests sometimes received the second fact late but did not use it.
- Do not claim a controlled proof that increasing the limit alone caused the
  improvement. The older chain tasks and current drink/city task differ, and
  there was no matched limit-1 versus limit-4 ablation for this joint question.
- Do not reopen core native-memory feasibility based on those historical
  failures. The present implementation has positive direct evidence.

The user required a single successful Aimee-native consumption example to
establish feasibility, not parity across a large benchmark. We have exceeded
that threshold, including successful composition. Broad reliability and serving
refinements are separate next-phase questions, not retroactive POC gates.

## Current implementation and evidence

Prompt-driven preload and attention-driven native recall use the same
request-local bank and the same Aimee client. Preload runs once; native requests
continue during prefill and decode. Returned records are retained by ID, repeated
IDs refresh their values, and unchanged banks reuse their encoding. Aimee owns
record selection; the adapter adds no domain-specific memory logic.

Current defaults are `recall_mode: attention`, `preload_memory: true`,
`decode_recall: true`, and four results per lookup. `preload_memory: false`
selects native-only; `aimee_memory: false` disables both. Traces distinguish
`prompt_preload` from `qwen_attention_query` and retain exact returned records
and bank IDs. Native requests here mean Qwen's actual projected attention
queries translated to Aimee's text API, not an emitted tool command or a trained
deliberate-search policy.

The joint hybrid, native-only, legacy prompt-only, and disabled controls had
identical 74-token main prompts. Relevant records were IDs 5 (oolong) and 6
(Lima). Neither answer value appeared in those prompts. Eighteen structural
tests passed. [Verification and traces](artifacts/qwen-aimee-hybrid-2026-09-20/verification.json)
record the checks; [runtime hashes](artifacts/qwen-aimee-hybrid-2026-09-20/runtime.json)
identify the tested source. The latest deployment used
`aimee-qwen-hybrid.service` on `.253`, loopback port 18792, with a one-hour
experimental lifetime; this note is not a guarantee that it is still running.

## Constraints to carry into next steps

- No adapter training. Aimee owns memory learning, relevance, governance, and
  authority; the per-model adapter handles translation and native delivery.
- Keep integration inside the model runtime, below prompt/chat construction.
  No memory tools, chat-template protocol, or recalled text in the main prompt.
- Keep prompt-driven preload and native recall available as complementary paths.
- Use existing Aimee directly for the POC. Slow synchronous access is acceptable.
  Engram images, optimized serving, and latency targets are deferred.
- Do not require a two-step lookup to accept ordinary recall or composition.
- Preserve failures and controls, but identify the implementation, query,
  retrieval limit, returned IDs, bank contents, and arrival step before assigning
  failure to retrieval, transport, conversion, or model consumption. Only judge
  composition when all required memories were available for the tested answer
  and the probe itself is valid.

The next phase should build on this working baseline. Broader factual coverage,
efficient representations, and active-request update/revocation semantics are
not established by these narrow checks. The user has requested notes before
choosing next steps; no additional experiment or architecture change is selected
or started by this handoff.
