# Controlled native-memory preview

The current preview includes Gemma4 12B, Gemma4 26B A4B and Qwen3.8 27B. Use the
[three-model guide](three-model-preview.md) for supported hardware, package sizes,
results and limitations, and the [release recommendation](../../docs/validation/three-model-release-recommendation-20260928.md)
for exact tested identities.

Obtain the signed model-aware launcher, pinned release trust and enrolled Aimee
account from the operator. The tested client uses Linux x86-64, Podman and two
RX 7900 XTXs with the pinned ROCm/vLLM runtime.

```sh
aimee-native install gemma4-12b-q8-native
aimee-native connect https://YOUR-AIMEE-ENDPOINT
aimee-native run
```

Choose `gemma4-26b-q8-native` or `qwen3.8-27b-q8-native` in the install command
for the larger models. Use a separate installation root for each model.
`connect` reads the scoped bearer token from standard input. Where enrollment
requires them, use `--ca-file` and `--client-identity` for the operator-issued
private CA and mTLS identity. Keep credentials out of command arguments and
shared reports. The private compiler is not installed on the client.

The launcher manages authenticated memory delivery and the model runtime; vLLM
is not forked. Serve the text API on loopback behind the application's
permissions. Stop the launcher before installing a signed update or running
`aimee-native rollback`. Rollback preserves the release-sequence high-water mark
and does not restore withdrawn memory permissions.

The current controlled channels are 12B sequence 6 and both larger sequence 2.
The [old sequence-5 beta record](sequence5-beta-20260926.md) is historical.
Public redistribution fulfillment is separate and remains under review.
