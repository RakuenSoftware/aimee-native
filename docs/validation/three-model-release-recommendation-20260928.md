# Three-model release recommendation

**Current release:** [Standalone plugin 0.1.1](standalone-plugin-20260929.md) is
packaged, live-tested, and delivered. The container campaign and its previous
whole-image distribution qualifications below are historical. Broadcom is not
a dependency of the distributed plugin.


## Historical container campaign recommendation

**Recommend the tested three-model controlled private preview. Do not describe
it as a generally validated autonomous coding learner or as completed public
redistribution fulfillment.** The native-memory regressions investigated in
this campaign are repaired at the recorded scope, all normal lifecycle
campaigns passed, and the tested launcher and packages are now served on the
existing controlled TLS origin.

## Released candidate identities

| Model | Sequence | Manifest SHA-256 |
|---|---:|---|
| Gemma4 12B Q8 | 6 | `3577d8041f929ae5376160c276d8136f0ddc4a80247d33f27325f4899f1a8636` |
| Gemma4 26B A4B Q8 | 2 | `1041c84fe25d84b5700b5cdf53de6eb78b38021d10689e49583cc3425f876cae` |
| Qwen3.8 27B Q8 | 2 | `90e75bcfb3e58bce208e8568d6ea335e89fdf8ecb02a4e055384d164367196bc` |

The model-aware normal launcher is
`a7ebbb5d0f9493f205ca355fab640f56e31cc686219aa038ac348de4ac4727e6`.
The [promotion and recipient checks](artifacts/controlled-promotion-20260928/)
verify the served launcher and all three model manifests through authenticated
TLS and the existing pinned signing identity. The downloaded launcher executed
its command interface successfully. This is the existing private origin, not a
new public hosting service.

## What the evidence establishes

- [Normal lifecycle inventory](artifacts/candidate-evidence-review-20260928/report.json):
  all four phases are recorded for each model, with two correct native answers
  per phase. The larger campaigns each passed 8/8. The 12B campaign begins with
  sequence 5 and updates/restores sequence 6; its fresh5 result is not relabeled
  as a fresh6 result. Separate model-aware 12B consumption/recovery also passed.
- [Larger coordinator completion](artifacts/larger-normal-lifecycle-20260928/lifecycle-summary.json):
  authority bindings remained unchanged and the 12B compiler service was
  restored. Its active service state was checked before promotion.
- Exact Q8 model profiles, complete-source delivery, native/text integration,
  conversation, streaming/concurrency, preparation reuse and authority behavior
  have their model-specific evidence in the [gate review](larger-release-gate-review-20260928.md).
  vLLM remains fork-free; private preparation code remains outside the client.
- [Primary acquisition study](artifacts/source-learning-20260927/final-primary-report.json):
  64 graded attempts across 16 tasks, with control 1/16 and each of three native
  rounds 2/16. The one gained task persists across all rounds and the sole
  control success is retained. Acquisition uses model-produced source experience
  and replay validation; repeated rounds are not independent tasks.
- [Literal-source regression repair](artifacts/requests-literal-task-20260928/final-status.json)
  recovers the Requests case. The subsequent [selected retention check](artifacts/retained-success-validation-20260928/status.json)
  passed 10/10 native attempts across five historically successful tasks.

## Larger-model task results

These are six selected tasks with frozen accepted source procedures reused
across two native rounds. They establish procedural reuse at that scope, not
fresh acquisition between rounds or a population-wide improvement estimate.

| Model | No memory | Matched text | Native round 1 | Native round 2 |
|---|---:|---:|---:|---:|
| [Gemma 26B](artifacts/larger-gemma26-complete-tasks-20260928/summary.json) | 2/6 | 4/6 | 4/6 | 4/6 |
| [Qwen 27B](artifacts/larger-qwen27-complete-tasks-20260928/summary.json) | 5/6 | 4/6 | 6/6 | 6/6 |

Both retain every no-memory success in these comparisons. Gemma's additional
successes differ by round: Requests passes only round 1 and Flask only round 2.
The original broader 12B study remains 5/32 control versus 4/32 native; the later
repair and retention checks do not rewrite that result or constitute a rerun
of the whole population. Model-weight reasoning improvement is not claimed.

## Operating limits and remaining work

The supported client profile is Linux x86-64, two RX 7900 XTXs, and the pinned
ROCm/vLLM runtime. Use the [three-model preview guide](../../distribution/beta/three-model-preview.md)
for installation and updates. Users receive compiled consumers and model
artifacts; they do not patch vLLM or install the private compiler.

Cold application medians remain 3.73–14.80 ms for the measured Gemma banks and
1.62–4.40 ms for Qwen. The user explicitly accepted microseconds as an
aspirational target, not a release blocker. Fresh server preparation, runtime
startup/JIT, request generation and resident lookup are separate operations.
Native memory avoids memory-text prompt tokens while still using host/device
resources.

Automatic source acquisition is demonstrated in the benchmark harness. A
turnkey general-purpose production learning workflow and broad task-quality
guarantee are not delivered by these experiments. This release provides the
validated native-memory integration and measured reuse capability.

Collected notices, the available exact OS sources, ROCgdb sources and notice
supplements are available through the controlled origin and passed full TLS
size/hash checks. [External distribution fulfillment](distribution-fulfillment-20260928.md)
now accounts for all 342 OS source/version pairs. The exact Broadcom compiled
payload/source review remains open. That is an explicitly unmet
external-distribution item, not hidden runtime failures or a reason to revive
the aspirational latency threshold. No public redistribution approval is claimed.

The [29 September requirement audit](release-completion-audit-20260929.md)
rechecks the delivered identities and retained phase evidence, and records the
remaining vendor information dependency.
