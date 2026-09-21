#!/usr/bin/env python3
"""Verify real cross-device autograd/cached decode before loading 27B weights."""
import json
import argparse
import sys
import torch

from engram import FrozenQwenEngram, OracleValues
from placement import place
from test_p0 import tiny_qwen
from frozen_int8 import quantize_frozen_linears


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--int8", action="store_true")
    args = parser.parse_args()
    torch.set_num_threads(8)
    if not torch.cuda.is_available() or torch.cuda.device_count() < 2:
        raise RuntimeError("two PyTorch-visible GPUs required")
    model = tiny_qwen().to(dtype=torch.bfloat16)
    model.requires_grad_(False)
    if args.int8:
        quantize_frozen_linears(model)
    hooks = place(model, dict(embedding="cpu", layers=["cuda:0", "cuda:0", "cuda:1", "cuda:1"],
                             head="cuda:1", stage_peer_transfers_via_cpu=True))
    tokens = torch.tensor([[1, 7, 11, 15]])
    with torch.no_grad():
        baseline = model(tokens, use_cache=False).logits
    print("stage: baseline", file=sys.stderr, flush=True)
    adapter = FrozenQwenEngram(model, 32, 16)
    table = OracleValues([4817, 4818], 32).to(device="cuda:0", dtype=torch.bfloat16)
    with torch.no_grad(), adapter.using(table.prepare(adapter.layer, [4817, 4818], set(table.row), table.scope, 1)):
        assert torch.equal(baseline, model(tokens, use_cache=False).logits)
    print("stage: zero parity", file=sys.stderr, flush=True)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.train()
    optimizer = torch.optim.Adam(list(adapter.layer.parameters()) + list(table.parameters()), lr=.01)
    records = []
    for step in range(3):
        optimizer.zero_grad()
        with adapter.using(table.prepare(adapter.layer, [4817, 4818], set(table.row), table.scope, 1)):
            loss = model(tokens, labels=tokens, use_cache=False).loss
            loss.backward()
        assert all(p.grad is None for p in model.parameters())
        assert torch.isfinite(loss)
        gradient = float(table.values.grad.float().norm())
        if step > 0:
            assert gradient > 0
        records.append(dict(step=step, loss=float(loss.detach()), value_gradient_norm=gradient))
        optimizer.step()
        print(f"stage: optimizer {step}", file=sys.stderr, flush=True)
    model.eval()
    with torch.no_grad(), adapter.using(table.prepare(adapter.layer, [4817, 4818], set(table.row), table.scope, 1)):
        output = model.generate(tokens, attention_mask=torch.ones_like(tokens), max_new_tokens=3,
                                do_sample=False, use_cache=True, pad_token_id=0)
    assert output.shape[1] > tokens.shape[1]
    print("stage: generation", file=sys.stderr, flush=True)
    print(json.dumps(dict(status="pass", int8=args.int8, peer_transfers="via_cpu", torch=str(torch.__version__), hip=torch.version.hip,
                         devices=[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
                         training=records, generated=output.tolist(),
                         scope="tiny random Qwen mechanics, not 27B recall"), indent=2))
    adapter.close()
    for handle in hooks:
        handle.remove()


if __name__ == "__main__":
    main()
