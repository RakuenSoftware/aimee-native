# Gemma 4 native memory and live knowledge updates

2026-09-22. Focused cross-family demonstration using Google Gemma 4 12B
Instruct, revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`.

## Result

The same loaded, frozen Gemma process produced:

| Memory state | Answer |
| --- | --- |
| Disabled | `unknown` |
| Initial general-reference record | `cobalt` |
| Record revised | `amber` |
| Record revised again | `violet` |
| Disabled again | `unknown` |

All five checks passed. Every request used the same 33 conversation token IDs.
Zero memory tokens entered that conversation, and its ordinary cache length
matched only the conversation and generated tokens. Three distinct publication
views supplied the three native answers. Parameter version counters remained
unchanged, all parameters were frozen, and no optimizer or training step ran.

The single general record was `article-general/aurora-access`; its content was
“The access code for Aurora Observatory is VALUE.” The question was fixed
before the run. Aimee's real Go image compiler, signed research publication and
published reader selected that record. Publication used the current generation
as the expected predecessor. The model identity could read the published image
but not the private source or fixture signing keys.

Two updates became published in 0.021242 and 0.021949 seconds. Time from the
start of each publication to the returned correct answer was 0.336333 and
0.341737 seconds, respectively. These are single-record, local research-image
measurements, not updates to the archived 249,105-record public base or an
end-to-end production Aimee deployment benchmark.

## Implementation and environment

This reuses the existing Python native-memory connection, separate frozen-model
encoding pass, key/value cache wrapper, state lifecycle and Aimee image reader.
Gemma-specific changes identify its attention blocks and encode records with
its expected sequence boundaries. That independent encoder input does not
enter the conversation. Memory positions precede the unchanged conversation;
all 48 Gemma attention layers consume the separate bank. The model's ordinary
sliding/causal conversation mask remains in place, with separate visibility for
external memory. The tested facts and questions are short.

The original `QwenAimeeAdapter` name remains for API compatibility. Gemma's
current connection supports the prefill read path, eager attention and unshared
K/V layers. It does not claim support for every Gemma configuration or modality.
No modification to the trained model weights is required.

Dedicated Debian 13 LXC 101 on the authorised host; two Radeon RX 7900 XTX GPUs,
96 GiB RAM, 16 CPU cores. BF16 model weights, Transformers 5.17.0, native Torch
2.14.0/ROCm 7.2. Inter-device transfers use the existing host-staging approach.
The exact package list, device placement, checkpoint configuration, model hashes
and tested source are in `gemma-native-provenance/` under the raw artifact root.
The final source renames an internal helper and clarifies its module docstring;
the exact inference-tested version is also preserved there.

All 18 existing Qwen adapter structural checks pass with the extension.

## Evidence and reproduction

Raw root: [artifacts/gemma-native-2026-09-22](artifacts/gemma-native-2026-09-22/).
`gemma-native-r5/results.jsonl` is the completed demonstration;
`summary.json` and `manifest.json` contain recomputed outcomes and file hashes.
Model weights, private source images and signing keys are excluded.

```sh
python3 benchmarks/gemma_native/verify.py docs/validation/artifacts/gemma-native-2026-09-22
PYTHONPATH=integrations/qwen_aimee python -m unittest -v test_adapter.AdapterTests
```

For an actual GPU rerun, use `benchmarks/gemma_native/run.py FRESH_OUTPUT_DIR`
in the configured lab. It creates the disposable research publication and starts
one restricted model worker. `PLAN.md` records the fixed question and values.
The source dependency remains Aimee `ad3585ac5381e3f0569dd8661b41fbe82cd6501d`;
the underlying Qwen implementation is based on `f1afb8f542b9aeda8ae6e60e2ddcca1df13a958c`.

## Integration attempts

Earlier attempts are retained separately, never included as successful checks.
r1 stopped on a tokenizer return-type mismatch before answers. r2 connected
only global-attention blocks and then stopped because the publication driver
omitted its expected predecessor. r3 connected Gemma's local and global layers;
r4 also staged device transfers and compared the first prediction against an
explicit-prefix numerical reference. Both showed that unframed encoder text
produced unsuitable Gemma states. r5 used Gemma's canonical encoder boundaries
and passed the unchanged fact/update sequence. The reference in r4/r5 is a
numerical integration diagnostic, not a native-memory claim or model input in
the scored requests. The completed r5 worker exited without the teardown fault
seen in an earlier attempt.
