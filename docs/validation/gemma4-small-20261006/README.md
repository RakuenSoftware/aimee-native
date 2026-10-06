# Gemma4 E2B/E4B native release qualification

The 0.3.3 candidates add two dedicated Rust adapters following the existing
model-plugin pattern. They include the model-specific shared-K/V capture and
GGUF per-layer input bindings, plus the shared runtime's corrected vLLM version
check. All five model packages pin shared runtime 0.3.3.

## Qualification

The immutable 0.3.2 input wheels passed the following checks on 2026-10-06:

| Execution profile | E2B | E4B |
| --- | --- | --- |
| CPU native lifecycle with installed Rust adapter | 42/42 | 42/42 |
| Installed Rust admission checks | 45/45 | 45/45 |
| RTX 5080 vLLM Q8_0/BF16 extended lifecycle, corrected runtime | 27/27 | 27/27 |
| 7900 XTX vLLM Q8_0/BF16 extended lifecycle, corrected runtime | 27/27 | 27/27 |

The extended lifecycle uses a 240-token native bank across two 128-token prefill
chunks. It checks recall, reuse, corrections, retirement, restoration, rejected
requests, complete streaming, concurrent requests, actual source outage and
recovery, recipient mismatch and server-side revocation. The JSON files alongside
this report preserve the original results, versions and hashes.

The three larger native smokes passed 18/18 each: Gemma4 12B Q8_0 and 26B Q3_K_M
on one 7900 XTX, Qwen 27B FP8/BF16 with 18 GiB CPU offload on RTX 5080. The current
launcher/capture qualifies one GPU. The installed gfx1100 stack rejects Qwen's
required FP8 arithmetic; that native capture path has CUDA coverage only.

## 0.3.3 candidate continuity and installation

[Candidate wheels, promotion report and audit](../../../distribution/release/candidates/model-plugins-0.3.3-20261006)
record every input and output digest. Version promotion changes distribution
metadata, exact shared-runtime dependency pins and RECORD entries. Every
executable payload member and its permissions remain identical to the qualified
input. Historical inputs are not overwritten. These are unsigned candidates;
signing, release manifest inclusion and published installation remain required.

The 0.3.3 wheels were installed on .253 and passed:

- Six Rust adapter source regressions in an isolated crate on CT101.
- Five-plugin wheel audit: RECORD integrity, namespace isolation, exact runtime
  pins, one dedicated Rust symbol per model and executable shared client.
- 20 installed small-model contract checks.
- Five shared-K/V capture checks per model, including two chunks and rejection
  of incomplete or mismatched observations.
- Six projection conversion checks per model, including rejection of malformed
  quantization metadata and preservation of other packed weights.
- Six installed distribution version checks and eight compiled-runtime version
  cases. vLLM 0.30.0 and local vendor suffixes pass; other public versions fail.

The 0.3.3 installed checks and payload continuity support the prior GPU results;
the full GPU lifecycle matrix was run on the recorded 0.3.2 input wheels.

## Reproduction

Run the source release-interface regression:

```sh
python3 distribution/vllm/tests/release_compatibility.py
```

Build fresh candidates from the pinned private Rust snapshot:

```sh
python3 distribution/release/build-model-plugins.py \
  --rust-source /path/to/pinned/rust-source --output /path/to/new-build --version 0.3.3
```

The promotion script is for preserving the already qualified payloads:

```sh
python3 distribution/release/promote-model-plugins.py \
  --source /path/to/qualified-five-plugin-wheels --output /path/to/new-candidates
python3 distribution/release/audit-model-plugins.py \
  --wheels /path/to/new-candidates --output /path/to/audit.json \
  --models gemma4-12b gemma4-26b qwen3-8-27b gemma4-e2b gemma4-e4b
```

In an environment containing the candidate wheels, Torch, Transformers and the
pinned GGUF extra, run `distribution/tests/small-models/test_release_version.py`.
The other installed regression scripts use `AIMEE_VALIDATION_ROOT`: a fixture
root containing `models/gemma4-e2b`, `models/gemma4-e4b` (pinned checkpoint config
and tokenizer) and an `evidence` directory. Run `plugin_contract_checks.py`, then
`test_fresh_capture.py` and `test_projection_failures.py` with each model name.
No credentials or model weights are distributed in this PR.
