# Shared native-memory runtime 0.3.2 candidates

Three model-specific vLLM plugins depend on one `aimee-native-runtime==0.3.2`
wheel. Common selection, process supervision, admission, preparation, scheduling,
state and framework glue are shared. Each model plugin has its own dedicated
Rust adapter and checked binding.

Platform: Linux x86-64, CPython 3.12, glibc 2.39+, vLLM 0.30.0. The validated
consumer environment uses Torch 2.13.0, CUDA 13.0, Triton 3.7.1 and an RTX 5080.
The wheel tag does not certify execution on other platforms or vLLM revisions.

Install from this directory, selecting one model:

```sh
python -m pip install --find-links . "aimee-gemma4-12b[gguf]==0.3.2"
# alternatives: aimee-gemma4-26b[gguf]==0.3.2 or aimee-qwen3-8-27b==0.3.2
```

Enroll through the normal Aimee client, then use the selected model command:

```sh
aimee-gemma4-12b connect-aimee --aimee-home /absolute/path/to/enrolled-profile
# Supply VLLM_API_KEY in the environment or a private service environment file.
aimee-gemma4-12b serve --config serving.json
```

`audit.json` records wheel and dedicated-library hashes and verifies RECORD,
namespace isolation, adapter exports and common runtime pins. `finalization.json`
records unchanged executable bytes after adding GGUF metadata and third-party
notices. `elf-compatibility.json` records the actual ELF dependencies.

The [validation report](../../../../docs/validation/native-memory-shared-runtime-20261004.md)
records execution scope, core source-export prerequisite, retained failures and
release gates. The current artifacts pass 21 enrolled lifecycle checks per model,
87 bridge tests without skips, Qwen 324/324 recall cases, operational checks,
co-installation/uninstall checks, actual deployment, rollback and restoration.
The earlier 0.3.0 evidence is preserved in its original candidate directory.
