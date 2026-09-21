"""Research weight-only int8 base model; differentiable with respect to inputs.

Per-output-row symmetric quantization, float32 scales, BF16/FP16 dequantization
for ordinary F.linear. No custom kernel, optimizer or trainable base weights.
Block checkpointing bounds live dequantized weights during training.
This is NOT the GGUF Q8_0 codec and must have its own text baseline.
"""
import torch
from torch import nn
from torch.nn import functional as F


class FrozenInt8Linear(nn.Module):
    def __init__(self, source):
        super().__init__()
        if source.weight.requires_grad:
            raise ValueError("freeze the base model before quantization")
        self.in_features, self.out_features = source.in_features, source.out_features
        qweight = torch.empty_like(source.weight, dtype=torch.int8)
        scale = torch.empty((self.out_features, 1), device=source.weight.device, dtype=torch.float32)
        with torch.no_grad():
            for start in range(0, self.out_features, 512):
                weight = source.weight[start:start+512].float()
                s = weight.abs().amax(dim=1, keepdim=True).clamp_min(1e-12) / 127
                qweight[start:start+512] = (weight / s).round().clamp(-127, 127).to(torch.int8)
                scale[start:start+512] = s
        self.register_buffer("qweight", qweight)
        self.register_buffer("scale", scale)
        self.register_buffer("bias", source.bias.detach().clone() if source.bias is not None else None)

    def forward(self, hidden):
        weight = self.qweight.to(hidden.dtype) * self.scale.to(hidden.dtype)
        return F.linear(hidden, weight, self.bias)


def quantize_frozen_linears(module):
    count = 0
    for name, child in list(module.named_children()):
        if isinstance(child, nn.Linear):
            setattr(module, name, FrozenInt8Linear(child))
            count += 1
        else:
            count += quantize_frozen_linears(child)
    return count
