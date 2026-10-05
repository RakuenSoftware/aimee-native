"""Prepare public attention-only memory with the quantized GPU consumer itself."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time


def sha256(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            checksum.update(block)
    return checksum.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("config", "output"):
        parser.add_argument("--" + name, required=True)
    options = parser.parse_args()
    path = Path(options.config)
    config = json.loads(path.read_text())
    if config.get("offline_prefix_capture") is not True:
        raise ValueError("offline capture configuration required")
    if sha256(config["gguf_weights"]) != config["gguf_weights_sha256"]:
        raise RuntimeError("quantized checkpoint checksum mismatch")
    output = Path(options.output)
    output.mkdir(mode=0o700)
    os.environ.update(
        AIMEE_VLLM_CONFIG=str(path.resolve()), AIMEE_GGUF_ENABLE="1",
        VLLM_PLUGINS=config.get("plugin", "aimee_native"), VLLM_USE_V2_MODEL_RUNNER="0",
        VLLM_USE_FLASHINFER_SAMPLER="0", VLLM_GGUF_USE_CUDA="0",
    )
    from transformers import AutoTokenizer
    from vllm import LLM, SamplingParams
    tokenizer = AutoTokenizer.from_pretrained(config["model"], local_files_only=True)
    facts = ["The workshop vault entry number is 68731.",
             "The workshop project codename is Kestrel.",
             "The workshop preferred meeting drink is rooibos."]
    text = tokenizer.apply_chat_template(
        [{"role": "system", "content": "Authoritative memory:\n" + "\n".join(facts)}],
        tokenize=False, add_generation_prompt=False, enable_thinking=False,
    )
    tokens = tokenizer.encode(text, add_special_tokens=False)
    serve = config["serve"]
    started = time.perf_counter()
    llm = LLM(
        model=config["model"], dtype="bfloat16", quantization="gguf",
        load_format="aimee_gguf_unified",
        model_loader_extra_config={"gguf_weights": config["gguf_weights"]},
        enforce_eager=True, enable_prefix_caching=False, async_scheduling=False,
        worker_cls=config.get("python_module", "aimee_vllm") + ".worker.AimeeWorker", attention_config={"backend": "CUSTOM"},
        limit_mm_per_prompt={"image": 0, "audio": 0, "video": 0},
        max_model_len=serve["max_model_len"], max_num_seqs=1,
        max_num_batched_tokens=serve["max_num_batched_tokens"],
        gpu_memory_utilization=serve["gpu_memory_utilization"],
        cpu_offload_gb=serve.get("cpu_offload_gb", 0),
        num_gpu_blocks_override=serve.get("num_gpu_blocks_override"),
    )
    model_load_seconds = time.perf_counter() - started
    started = time.perf_counter()
    llm.llm_engine.collective_rpc("aimee_attention_capture_begin", args=(tokens, text, str(output / "workshop")))
    llm.generate([{"prompt_token_ids": tokens}], SamplingParams(temperature=0, max_tokens=1), use_tqdm=False)
    results = llm.llm_engine.collective_rpc("aimee_capture_finish")
    if len(results) != 1:
        raise RuntimeError("incomplete capture rank coverage")
    elapsed = time.perf_counter() - started
    metrics = llm.llm_engine.collective_rpc("aimee_cache_stats")
    if sha256(config["gguf_weights"]) != config["gguf_weights_sha256"]:
        raise RuntimeError("quantized checkpoint changed during preparation")
    catalog = {
        "recipient": config["recipient"],
        "model_config_sha256": sha256(Path(config["model"]) / "config.json"),
        "publications": {"workshop": results[0]},
    }
    (output / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")
    index = json.loads((output / "workshop/index.json").read_text())
    preparation = {
        "scope": __doc__, "native_profile": config["adapter"] + ": " + config["gguf_weight_profile"] + " engine-encoder/consumer native-prefix",
        "facts": facts, "tokens": tokens, "layers": len(index["schema"]["segments"]) // 2,
        "dictionary_bytes": index["dictionary_bytes"], "model_load_seconds": model_load_seconds,
        "encoding_and_publication_seconds": elapsed, "metrics": metrics,
        "gguf_weights_sha256": config["gguf_weights_sha256"],
        "model_config_sha256": catalog["model_config_sha256"],
    }
    (output / "preparation.json").write_text(json.dumps(preparation, indent=2) + "\n")


if __name__ == "__main__":
    main()
