# Aimee native memory for vLLM — first public binary preview

This release provides a compiled vLLM plugin and Aimee connection client. It
lets a supported model consume Aimee-approved memory through native attention
without placing the memory text in the conversation. An enrolled Aimee account
and an authorized memory publication are required; this release does not grant
access to anyone's memory or include an encoder, model weights, or vLLM itself.

The preview targets **Linux x86-64, Python 3.12, glibc 2.34+, and vLLM 0.30.x**
on a CUDA or HIP runtime that supports BF16. The exact compiled runtime was
tested with Qwen3.8 27B and Gemma 4 12B/26B on two RX 7900 XTXs, and Gemma 4
12B on an RTX 5080. Qwen's tested hybrid profile uses vLLM's V1 runner;
Gemma's tested profiles use V2. Other model/GPU combinations need their own
validation.

Download the plugin wheel and verify its SHA-256 against `SHA256SUMS` and the
signed `manifest.json`. The release also includes the small, pinned GGUF loader
wheel used by the tested GGUF profiles. With a supported vLLM environment
already installed:

```sh
python -m pip install './aimee_vllm-0.2.2-2-cp312-cp312-linux_x86_64.whl[gguf]'
aimee-native connect https://your-aimee-endpoint < /path/to/scoped-token
aimee-native serve --config ./aimee.json
```

`connect` reads the scoped account token from standard input. Your Aimee
operator supplies the endpoint, enrollment material, native model identity,
and an approved publication. If your model is not GGUF, omit `[gguf]` from the
install command. The `serve` config names your local model files and the
matching native model identity:

```json
{
  "model": "/models/my-model",
  "native_model": "<Aimee native model identity>",
  "serve": {"tensor_parallel_size": 2, "port": 8080}
}
```

For the tested Qwen3.8 27B hybrid profile, add `"v2_model_runner": false`
inside `serve`.

This is a controlled preview rather than general model certification. The
measured option tests were small canary runs, not throughput guarantees. A
publication update waits for active streams to drain; the tested long-stream
case delayed the first new-revision answer by about 66 seconds. The private
encoder and preparation implementation remain on Aimee's service.
