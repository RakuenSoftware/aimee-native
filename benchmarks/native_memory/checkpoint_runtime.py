"""Load a frozen research checkpoint through its exact original implementation."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import torch


def inspect_checkpoint(source, train):
    source, train = Path(source), Path(train)
    sys.path.insert(0, str(source.resolve()))
    ref = importlib.import_module("run_p0")
    if Path(ref.__file__).resolve().parent != source.resolve():
        raise ValueError("different implementation already imported; use a fresh process")
    saved = torch.load(train / "adapter.pt", map_location="cpu", weights_only=True)
    identity = saved["identity"]
    for name, expected in identity["implementation_sha256"].items():
        if ref.digest(source / name) != expected:
            raise ValueError(f"original implementation mismatch: {name}")
    if str(torch.__version__) != identity["torch"] or ref.transformers.__version__ != identity["transformers"]:
        raise ValueError("library mismatch")
    recorded = json.loads((train / "arguments.json").read_text())
    fixtures = Path(recorded["fixtures"])
    if json.loads((fixtures / "sha256.json").read_text()) != identity["fixtures"]:
        raise ValueError("fixture manifest mismatch")
    config = ref.AutoConfig.from_pretrained(identity["model"], trust_remote_code=False)
    tokenizer = ref.AutoTokenizer.from_pretrained(identity["model"], trust_remote_code=False)
    for field, value in [("config_sha256", config.to_json_string()),
                         ("tokenizer_sha256", tokenizer.backend_tokenizer.to_str()),
                         ("chat_template_sha256", str(tokenizer.chat_template))]:
        if hashlib.sha256(value.encode()).hexdigest() != identity[field]:
            raise ValueError(f"{field} mismatch")
    metadata = ref.read_fixture(fixtures, "memories.json")
    compatibility = dict(identity=identity, checkpoint_sha256=ref.digest(train / "adapter.pt"))
    return SimpleNamespace(ref=ref, saved=saved, identity=identity, config=config, tokenizer=tokenizer,
                           fixtures=fixtures, metadata=metadata, compatibility=compatibility, recorded=recorded)


def load_model(runtime):
    r, i = runtime, runtime.identity
    for name, expected in i["local_weight_sha256"].items():
        if r.ref.digest(Path(i["model"]) / name) != expected:
            raise ValueError(f"base weight mismatch: {name}")
    cls = {"qwen3_5": r.ref.Qwen3_5ForConditionalGeneration,
           "qwen3_5_text": r.ref.Qwen3_5ForCausalLM}[r.config.model_type]
    r.model = cls.from_pretrained(i["model"], dtype=getattr(torch, i["dtype"]),
                                attn_implementation="eager", trust_remote_code=False).eval().requires_grad_(False)
    if i["base_quantization"] == "int8_per_row_v1":
        r.ref.quantize_frozen_linears(r.model)
    elif i["base_quantization"] != "none":
        raise ValueError("unsupported base quantization")
    r.hooks = r.ref.place(r.model, i["placement"]) if i["placement"] else []
    r.input_device = i["placement"]["embedding"] if i["placement"] else r.recorded["device"]
    if not i["placement"]:
        r.model.to(r.input_device)
    r.adapter = r.ref.FrozenQwenEngram(r.model, i["value_width"], i["attention_width"], i["after_block"])
    dtype = i.get("adapter_dtype", "base")
    r.adapter.layer.to(dtype=getattr(torch, i["dtype"] if dtype == "base" else dtype))
    r.adapter.layer.load_state_dict(r.saved["layer"])
    return r
