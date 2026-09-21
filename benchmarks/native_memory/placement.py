"""Explicit static model placement for a frozen research model.

No inference-only weight offload hooks: backwards must retain access to each
block's weights on its own device. Transfers of activations remain in autograd.
"""
import torch


def move_tree(value, device, stage_peers=False):
    if isinstance(value, torch.Tensor):
        target = torch.device(device)
        if stage_peers and value.device.type == "cuda" and target.type == "cuda" and value.device != target:
            return value.to("cpu").to(target)
        return value.to(device)
    if isinstance(value, tuple):
        return tuple(move_tree(v, device, stage_peers) for v in value)
    if isinstance(value, list):
        return [move_tree(v, device, stage_peers) for v in value]
    if isinstance(value, dict):
        return {k: move_tree(v, device, stage_peers) for k, v in value.items()}
    # HF caches are mutable, per-layer objects. Do not migrate all layers' state
    # on each block; the corresponding block initializes/updates its own state.
    return value


def place(model, spec):
    text = model.model.language_model if hasattr(model.model, "language_model") else model.model
    if len(spec["layers"]) != len(text.layers):
        raise ValueError("placement must specify every decoder block")
    hooks = []

    def assign(module, device):
        module.to(device)

        def transfer(module, args, kwargs):
            return move_tree(args, device, spec.get("stage_peer_transfers_via_cpu", False)), move_tree(kwargs, device, spec.get("stage_peer_transfers_via_cpu", False))
        hooks.append(module.register_forward_pre_hook(transfer, with_kwargs=True))

    assign(text.embed_tokens, spec["embedding"])
    assign(text.rotary_emb, spec["embedding"])
    for block, device in zip(text.layers, spec["layers"]):
        assign(block, device)
    assign(text.norm, spec["head"])
    assign(model.lm_head, spec["head"])
    return hooks
