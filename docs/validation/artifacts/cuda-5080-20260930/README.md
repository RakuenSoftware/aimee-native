# RTX 5080 evidence

- `environment.json`: final package versions, GPU/driver, upstream sampler setting
  and byte identity of all installed plugin files against release 0.2.0.
- `numerical.json`: executed CUDA decoder and independent attention references.
- `activation.json`, `activation-repeat.json`: two complete 108-activation suites.
  Two-rank layouts execute sequentially on one GPU; this is not NVIDIA TP=2 inference.
- `gemma12-live.json`: final installed-plugin/Aimee integration result.
- `gemma12-live-config.json`, `model-files.json`: serving settings and weight/config
  hashes. Model weights and prepared memory payloads are not archived.
- `initial-gemma12-live.json`: copied client-certificate path was invalid on host.
- `proc-path-gemma12-live.json`: model path canonicalization crossed namespaces.
- `missing-gguf-gemma12-live.json`: initial test setup bypassed dependency resolution.
- `flashinfer-gemma12-live.json`: optional upstream sampler required undiscovered nvcc.
- `delivery/`: signed follow-up attestation and verified-download result. The
  release-time manifest is retained unchanged as `release-manifest.json`.
- `cleanup.json`: GPU had no remaining compute processes after the test.

Logs are losslessly gzip-compressed. `initial-environment.json` predates normal
GGUF dependency resolution; `environment.json` records the successful setup.
No plugin binary, kernel source or upstream source was changed between these
setup attempts. The successful run selected vLLM's existing PyTorch sampler
through `VLLM_USE_FLASHINFER_SAMPLER=0`.

Only an explicit artifact allowlist was collected. Private client configuration,
mutual-TLS keys, bearer tokens and model weights remain outside the repository.
`SHA256SUMS` covers the retained evidence.
