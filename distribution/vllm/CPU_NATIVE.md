# Bounded CPU native serving profile

This profile runs stock Gemma4 text or Qwen3 dense checkpoints through actual CPU vLLM. It is a research serving integration for the established native K/V mechanism. It does not train tools, modify model parameters or implement Aimee's semantic/resource decisions.

Use a CPU-only Torch build and the declared compatible vLLM interface. The package registers an out-of-tree CPU platform so upstream CPU attention selection honours the native backend. `VLLM_TARGET_DEVICE=cpu` must not bypass that platform; startup refuses an incorrect platform rather than quietly serving without native reads.

Example configuration:

```json
{
  "cpu_native_profile": true,
  "research_owner_fixture": true,
  "model": "/owned/read-only/stock-checkpoint",
  "model_revision": "immutable-checkpoint-revision",
  "served_model_name": "owned-research-model",
  "port": 8437,
  "control_socket": "/owned/private/cpu-control.sock",
  "host_memory_budget": 536870912,
  "max_model_len": 4096,
  "refresh_drain_timeout_seconds": 5
}
```

Launch with `python -m aimee_vllm.cpu_cli --config /owned/private/cpu-config.json`. The launcher requires CPU Torch, binds loopback, selects FP32 eager synchronous single-worker serving, and disables ordinary prefix caching. The research fixture flag explicitly does not qualify enrolled selection or source authorization. An enrolled configuration instead requires the existing owner selection socket and API authentication; its complete native-tooling chain needs separate live qualification.

The publisher uses the existing UID-checked private control socket. Withdraw first, retain the returned generation, prepare the Aimee-selected publication and opaque revision, then refresh that generation. Preparation uses a private engine request and captures immutable post-RoPE K/V. Activation requires complete worker capture and a matching fingerprint. No adapter revision sorting occurs. Aimee determines the resolved view and when to distribute it.

Initial serving is paused. **Publisher readiness is the private control socket, not successful HTTP health:** HTTP health remains503 until a publication is activated. A poisoned instance requires a supervised restart and new owner distribution. HTTP arguments cannot invoke private capture or supply a trusted bank fingerprint. Caller disconnect is not proof that the worker released all native reservations.

Metrics record native reads, bank fingerprints, native bytes, ordinary sequence lengths, pins, raw text shadow-cache bytes and model parameter version checks. CPU's packed cache cannot be treated as a row-major K/V tensor. The profile leaves upstream cache writes in place and keeps a separately accounted raw text K/V copy for the native operation. The native bank budget does not include that additional ordinary text copy, model weights or process memory. Instrumented tensor-hash RPCs affect latency and are not normal speed benchmarks.

This implementation is intentionally bounded: supported model families, CPU FP32, one worker, decoder attention, explicit memory budget and bounded preparation length. It does not claim arbitrary model-family compatibility, incremental ordinary text reuse between contributions, unlimited context, or a context multiplier. Ordinary-prefix reference controls should use exactly the same tokenizer tokens as preparation, and qualification must separately check useful task outcomes.

Owner-side intake and canonical dispatch remain Aimee responsibilities. The companion private research evidence preserves the experimental owner source and its qualification limits; this plugin does not install an alternative owner. The adapter does not resolve semantic conflicts, choose resources, authorize actions or accept generated completion claims as observed effects.
