# Three-model private preview — release candidate

The 12B and Gemma 26B candidates have completed their recorded normal signed
lifecycle checks. Qwen 27B is undergoing normal signed lifecycle validation. This
is the intended user workflow, not a claim that pending checks have passed or
that public distribution is open.

## Installation

The operator supplies the launcher and an enrolled Aimee account. Choose one
model per installation directory:

| Model | Installer identifier | Packaged weights |
|---|---|---|
| Gemma4 12B | `gemma4-12b-q8-native` | Q8_0 GGUF |
| Gemma4 26B A4B | `gemma4-26b-q8-native` | Q8_0 GGUF, 29,135,275,488 bytes |
| Qwen3.8 27B | `qwen3.8-27b-q8-native` | Q8_0 GGUF, 29,047,084,448 bytes; projector sidecar 1,842,940,064 bytes |

For example, once the larger candidate is approved:

```sh
aimee-native install gemma4-26b-q8-native
aimee-native connect https://YOUR-AIMEE-ENDPOINT
aimee-native run
```

`connect` reads the scoped account token from standard input. For private
certificates, use the enrollment options in the [preview guide](README.md).
Configuration, tokenizer, compiled memory consumer and pinned runtime install
together. Users do not install the private compiler, assemble memory banks,
patch vLLM or build a runtime fork.

Validated hardware is Linux x86-64 with two Radeon RX 7900 XTX GPUs and the
pinned ROCm/vLLM runtime. Larger signed profiles use a 4,096-position text
conversation and tensor parallelism across both GPUs. Other hardware/runtime
versions need their own validation. Allow space for the model, runtime image,
memory cache and both installed versions during updates; weight size alone is
not total installation size.

The launcher serves the API on loopback and manages the broker, model container
and authorized native working set. Account permissions determine memory scope.
Native memory adds no memory-text tokens to the prompt but consumes host/device
resources.

## Updates and support

Stop the running launcher before changing versions. Repeat `install` for a
signed update. `aimee-native rollback` restores the previous runtime without
lowering the release-sequence high-water mark or reinstating withdrawn memory
permission. Start `run` again and verify the application's expected memory.

Use `aimee-native doctor` for installation information. Report the release ID,
image digest and sanitized error information; exclude account credentials and
private memory from shared support logs.

## Evidence and limits

The larger runtimes completed native/text integration checks, model-aware
delivery, full-source procedural memory audits and laboratory signed lifecycle
checks. Gemma normal-channel validation passed all four phases (8/8 canaries);
Qwen normal-channel validation remains pending. Exact evidence and candidate
identities are in the [release plan](../../docs/model-release-plan-20260928.md).

The selected six-task Qwen comparison passed 5/6 without memory, 4/6 with matched
text, and 6/6 in each native reuse round. Gemma passed 2/6, 4/6 and 4/6
respectively. Both retained successful no-memory tasks. Gemma's native rounds
passed different additional tasks: equal totals do not imply individual success
persisted. These runs reuse accepted complete-source procedures; they do not
measure fresh learning between rounds or establish general coding improvement.
The separate acquisition studies and their failures remain in the research record.

Cold application medians across six banks per model were 3.73–14.80 ms for Gemma
and 1.62–4.40 ms for Qwen. This measures the tested tensor application path,
excluding server preparation, authorization and generation. Resident lookup is
a separate operation. Microsecond cold application is an optimization target,
not a release requirement. Unprepared working sets can incur server preparation
time; cached reuse avoids repeating that work.

The client excludes the private compiler/encoding implementation. Recipients
can still inspect binaries and usable tensors. Controlled preview and external
redistribution are distinct; source/notice fulfillment is tracked in the
[gate review](../../docs/validation/larger-release-gate-review-20260928.md).
