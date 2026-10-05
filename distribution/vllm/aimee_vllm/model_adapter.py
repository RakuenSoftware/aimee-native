"""ABI bridge only. Each Rust entry point belongs to one model adapter."""
import ctypes
import json
from pathlib import Path


class ModelAdapter:
    def __init__(self, config, library=None):
        from ._model import BOUND_ADAPTER
        config = dict(config)
        if BOUND_ADAPTER is not None:
            config.setdefault("adapter", BOUND_ADAPTER)
        if BOUND_ADAPTER is not None and config.get("adapter") != BOUND_ADAPTER:
            raise RuntimeError("this plugin belongs to a different model")
        # This is an entry-point registry, not an architecture implementation.
        symbol = {
            "gemma4-12b": "aimee_gemma4_12b_adapter",
            "gemma4-26b": "aimee_gemma4_26b_adapter",
            "qwen3-8-27b": "aimee_qwen3_8_27b_adapter",
        }.get(config.get("adapter"))
        if symbol is None:
            raise RuntimeError("select the model's dedicated Rust adapter")
        self.serving = config
        self.library = library or ctypes.CDLL(config["library"])
        self.config = json.loads((Path(config["model"]) / "config.json").read_bytes())
        self.entry = getattr(self.library, symbol)
        self.entry.argtypes, self.entry.restype = [ctypes.c_char_p], ctypes.c_void_p
        self.free = self.library.aimee_model_adapter_result_free
        self.free.argtypes, self.free.restype = [ctypes.c_void_p], None
        self.description = self.call("describe")

    def call(self, op, **fields):
        pointer = self.entry(json.dumps({"op": op, "config": self.config, **fields}).encode())
        if not pointer:
            raise RuntimeError("dedicated model adapter rejected the request")
        try:
            return json.loads(ctypes.string_at(pointer))
        finally:
            self.free(pointer)

    def positioned_arguments(self, args, kwargs, requests, metadata):
        """Copy runtime tensors across the ABI; Rust owns position mapping."""
        import torch
        ids = getattr(metadata, "aimee_ids", None)
        if ids is None:
            return args, kwargs
        starts = metadata.query_start_loc.tolist()
        positions = kwargs.get("positions", args[1] if len(args) > 1 else None)
        if (positions is None or positions.dim() not in (1, 2)
                or len(starts) != len(ids) + 1 or starts[0] != 0):
            raise RuntimeError("model adapter request mapping is unavailable")
        ranges = []
        for i, rid in enumerate(ids):
            pin = requests.get(rid)
            if pin is None:
                raise RuntimeError("model adapter request is not pinned")
            ranges.append([starts[i], starts[i + 1],
                           0 if pin.store is None else pin.store.metadata["positions"]])
        # Runner padding is not a live request and receives zero prefix offset.
        if starts[-1] < positions.shape[-1]:
            ranges.append([starts[-1], positions.shape[-1], 0])
        rows = positions.unsqueeze(0) if positions.dim() == 1 else positions
        result = self.call("positions", positions=rows.tolist(), ranges=ranges)
        shifted = torch.tensor(result, dtype=positions.dtype, device=positions.device)
        if positions.dim() == 1:
            shifted = shifted[0]
        if "positions" in kwargs:
            return args, {**kwargs, "positions": shifted}
        return (args[0], shifted, *args[2:]), kwargs

    def admit_store(self, store):
        self.call("segments", positions=store.metadata["positions"],
                  segments=store.metadata["segments"])
        if self.description["recurrent"]:
            if store.hybrid is None:
                raise RuntimeError("Qwen adapter requires its complete hybrid prefix")
            recurrent=store.hybrid.spec["recurrent"]
            self.call("recurrent_layout", layouts=recurrent["layouts"], bytes=recurrent["bytes"])
        else:
            if store.hybrid is not None:
                raise RuntimeError("Gemma adapter does not accept recurrent state")
            profile = json.loads((Path(store.spec["root"]) / "profile.json").read_bytes())
            from importlib import metadata
            self.call("memory_profile", profile=profile, model_root=self.serving["model"],
                      weights_sha256=self.serving.get("gguf_weights_sha256"),
                      weight_profile=self.serving.get("gguf_weight_profile"),
                      versions={name:metadata.version(name) for name in ("vllm","torch","triton")})
