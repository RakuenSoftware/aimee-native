"""Offline Gemma attention capture from quantized weights, without a CPU model."""
import hashlib
from importlib import metadata
import json
from pathlib import Path

import torch

from .capture_session import CaptureSession, raw_tensor



class AttentionPrefixCapture(CaptureSession):
    """Exclusive attention-only capture; it does not provide hybrid recurrent state."""

    def __init__(self, config, runner, tokens, text, destination):
        if config.get("offline_prefix_capture") is not True:
            raise RuntimeError("prefix capture requires an offline worker")
        if not config.get("gguf_weights") or config.get("enable_hybrid_native"):
            raise RuntimeError("attention capture requires an attention-only GGUF model")
        if config.get("serve", {}).get("tensor_parallel_size", 1) != 1:
            raise RuntimeError("attention capture requires one GPU")
        if not tokens or len(tokens) > config["serve"]["max_model_len"]:
            raise ValueError("prefix token budget exceeded")
        root = Path(config["model"])
        c = json.loads((root / "config.json").read_bytes())
        from tokenizers import Tokenizer
        tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
        if tokenizer.encode(text, add_special_tokens=False).ids != list(tokens):
            raise ValueError("capture token/text identity mismatch")
        digest = config.get("gguf_weights_sha256", "")
        if len(digest) != 64 or any(x not in "0123456789abcdef" for x in digest):
            raise ValueError("capture requires the quantized checkpoint checksum")
        from .model_adapter import ModelAdapter
        self.adapter = ModelAdapter(config)
        if self.adapter.description["recurrent"]:
            raise RuntimeError("Gemma capture requires its dedicated Gemma adapter")
        self.config, self.runner = config, runner
        self.architecture = c.get("text_config", c)
        self.tokens, self.context = list(tokens), text
        self.destination = Path(destination)
        if self.destination.exists():
            raise ValueError("capture destination must be new")
        self.attention, self.recurrent, self.hooks = {}, {}, []
        self.request = None
        self.profile = {
            "schema": 1, "scope": "stock-model attention prefix",
            "adapter": self.adapter.description["adapter"],
            "positioning": self.adapter.description["positioning"],
            "producer": "vllm-gguf", "weights_sha256": digest,
            "weight_profile": config["gguf_weight_profile"], "kv_dtype": "bf16",
            "versions": {name: metadata.version(name) for name in ("vllm", "torch", "triton")},
            "device_capability": list(torch.cuda.get_device_capability()),
            "model_config_sha256": hashlib.sha256((root / "config.json").read_bytes()).hexdigest(),
            "tokenizer_sha256": hashlib.sha256((root / "tokenizer.json").read_bytes()).hexdigest(),
        }


    def finish(self):
        expected = set(range(self.architecture["num_hidden_layers"]))
        if set(self.attention) != expected:
            raise RuntimeError("incomplete captured attention layer coverage")
        data, segments = bytearray(), []
        for layer in sorted(expected):
            for value, chunks in enumerate(self.attention[layer]):
                tensor = torch.cat(chunks)
                if tensor.ndim != 3 or tensor.shape[0] != len(self.tokens):
                    raise RuntimeError("captured attention geometry mismatch")
                tensor = tensor.transpose(0, 1).contiguous()
                data.extend(raw_tensor(tensor))
                segments.append({"layer": layer, "value": bool(value), "heads": tensor.shape[0],
                                 "positions": len(self.tokens), "width": tensor.shape[2]})
        # Python supplies observed bytes only. The model's Rust adapter owns
        # geometry validation, identity, memory format and immutable publication.
        import tempfile
        with tempfile.NamedTemporaryFile() as payload:
            payload.write(data)
            payload.flush()
            return self.adapter.call("publish", positions=len(self.tokens),
                                     tokens=self.tokens, segments=segments,
                                     payload=payload.name, destination=str(self.destination),
                                     profile=self.profile)
