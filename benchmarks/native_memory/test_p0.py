"""Structural tests on the real HF Qwen implementation at tiny random scale.

Passing these tests does NOT demonstrate pretrained 27B memory consumption.
"""
import importlib.util
import json
import os
from pathlib import Path
import unittest

import torch
from transformers import Qwen3_5TextConfig, Qwen3_5ForCausalLM

from engram import EngramLayer, OracleValues, FrozenQwenEngram
from corpus import build
from placement import place
from frozen_int8 import FrozenInt8Linear, quantize_frozen_linears
from run_p0 import candidate_ids, swapped_ids, value_match


def tiny_qwen():
    torch.manual_seed(4817)
    config = Qwen3_5TextConfig(
        vocab_size=128, hidden_size=64, intermediate_size=96,
        num_hidden_layers=4, num_attention_heads=4, num_key_value_heads=2,
        head_dim=16, linear_key_head_dim=16, linear_value_head_dim=16,
        linear_num_key_heads=2, linear_num_value_heads=4,
        layer_types=["linear_attention", "linear_attention", "full_attention", "full_attention"],
        rope_parameters={"rope_type": "default", "rope_theta": 10000.0,
                         "partial_rotary_factor": 1.0, "mrope_section": [2, 3, 3]},
        pad_token_id=0, bos_token_id=1, eos_token_id=2)
    config._attn_implementation = "eager"
    return Qwen3_5ForCausalLM(config).eval()


class P0Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)

    def test_oracle_and_counterfactual_banks_and_value_scoring(self):
        fixture = build(100)
        memories = {m["memory_id"]: m for m in fixture["memories"]}
        for example in fixture["heldout"]:
            ids = candidate_ids(example, list(memories), 16, "oracle")
            self.assertEqual(set(ids), set(example["memory_ids"]))
            swapped, target = swapped_ids(example, ids, memories)
            self.assertFalse(set(swapped) & set(ids))
            self.assertEqual(len(swapped), len(ids))
            self.assertFalse(value_match(target, example["answer"]))
        self.assertTrue(value_match("Oslo;Kestrel", "Oslo; Kestrel"))
        self.assertFalse(value_match("Kestrel;Oslo", "Oslo; Kestrel"))
        self.assertFalse(value_match("Oslo;Kestrel;extra", "Oslo; Kestrel"))

    def test_fp32_interface_preserves_bf16_boundary_and_gradients(self):
        base = tiny_qwen().to(torch.bfloat16)
        tokens = torch.tensor([[1, 7, 11, 15]])
        with torch.no_grad():
            reference = base(tokens, use_cache=False).logits
        adapter = FrozenQwenEngram(base, 32, 16)
        adapter.layer.float()
        table = OracleValues([4817], 32)
        with adapter.using(table.prepare(adapter.layer, [4817], {4817}, table.scope, 1)):
            with torch.no_grad():
                self.assertTrue(torch.equal(reference, base(tokens, use_cache=False).logits))
        with torch.no_grad():
            adapter.layer.output.weight.normal_(std=0.01)
        with adapter.using(table.prepare(adapter.layer, [4817], {4817}, table.scope, 1)):
            base(tokens, labels=tokens, use_cache=False).loss.backward()
        self.assertGreater(float(table.values.grad.norm()), 0)
        self.assertEqual(table.values.grad.dtype, torch.float32)
        self.assertTrue(all(p.grad is None for p in base.parameters()))
        adapter.close()

    def test_zero_init_and_disabled_exact_logits(self):
        base = tiny_qwen()
        tokens = torch.tensor([[1, 7, 11, 15]])
        with torch.no_grad():
            reference = base(tokens, use_cache=False).logits
            adapter = FrozenQwenEngram(base, 32, 16)
            bank = adapter.layer.prepare([4817], torch.randn(1, 32), 1)
            with adapter.using(bank):
                self.assertTrue(torch.equal(reference, base(tokens, use_cache=False).logits))
            adapter.layer.output.weight.normal_(std=0.1)
            with adapter.using(None):
                self.assertTrue(torch.equal(reference, base(tokens, use_cache=False).logits))
            with adapter.using(bank):
                self.assertFalse(torch.equal(reference, base(tokens, use_cache=False).logits))
            adapter.close()
            self.assertTrue(torch.equal(reference, base(tokens, use_cache=False).logits))

    def test_gradient_opens_channel_and_base_stays_frozen(self):
        base = tiny_qwen()
        adapter = FrozenQwenEngram(base, 32, 16)
        table = OracleValues([4817, 4818], 32)
        tokens = torch.tensor([[1, 7, 11, 15, 19]])
        labels = tokens.clone()
        labels[:, :3] = -100
        optimizer = torch.optim.Adam(list(adapter.layer.parameters()) + list(table.parameters()), lr=0.01)
        losses = []
        for step in range(12):
            optimizer.zero_grad()
            bank = table.prepare(adapter.layer, [4817, 4818], set(table.row), table.scope, 1)
            with adapter.using(bank):
                loss = base(tokens, labels=labels, use_cache=False).loss
                loss.backward()
            losses.append(float(loss.detach()))
            self.assertTrue(all(p.grad is None for p in base.parameters()))
            if step == 0:
                self.assertGreater(float(adapter.layer.output.weight.grad.norm()), 0)
                self.assertEqual(float(table.values.grad.norm()), 0)
            if step == 1:
                self.assertGreater(float(table.values.grad.norm()), 0)
                self.assertGreater(float(adapter.layer.key.weight.grad.norm()), 0)
            optimizer.step()
        self.assertLess(losses[-1], losses[0])
        adapter.close()

    def test_cached_decode_uses_resident_bank_only(self):
        base = tiny_qwen()
        adapter = FrozenQwenEngram(base, 32, 16)
        table = OracleValues([4817, 4818], 32)
        with torch.no_grad():
            adapter.layer.output.weight.normal_(std=0.1)
            bank = table.prepare(adapter.layer, [4817, 4818], set(table.row), table.scope, 1)
            # Make all further table reads fail. Prefill and decode need only bank.
            table.row.clear()
            table.values.fill_(float("nan"))
            prefix = torch.tensor([[1, 7, 11]])
            next_token = torch.tensor([[15]])
            with adapter.using(bank):
                prefix_out = base(prefix, use_cache=True)
                cached = base(next_token, past_key_values=prefix_out.past_key_values, use_cache=True).logits[:, -1]
                full = base(torch.cat([prefix, next_token], dim=1), use_cache=False).logits[:, -1]
            torch.testing.assert_close(cached, full, atol=2e-5, rtol=2e-5)
        adapter.close()

    def test_validity_scope_generation_and_bank_pinning(self):
        layer = EngramLayer(64, 32, 16)
        table = OracleValues([4817, 4818], 32)
        with torch.no_grad():
            old = table.prepare(layer, [4817], {4817}, table.scope, 1)
            new = table.prepare(layer, [4817, 4818], {4818}, table.scope, 1)
            self.assertEqual(old.ids, (4817,))
            self.assertEqual(new.ids, (4818,))
            snapshot = old.values.clone()
            table.values.zero_()
            self.assertTrue(torch.equal(old.values, snapshot))
        for scope, generation in [("wrong-tenant", 1), (table.scope, 2)]:
            with self.assertRaises(ValueError):
                table.prepare(layer, [4817], {4817}, scope, generation)
        with self.assertRaises(KeyError):
            table.prepare(layer, [9999], {9999}, table.scope, 1)
        with self.assertRaises(ValueError):
            table.prepare(layer, [4817, 4818], set(table.row), table.scope, 1, k=1)

    def test_empty_bank_and_existing_poison_fixture(self):
        aimee = Path(os.environ.get("AIMEE_SOURCE", Path(__file__).resolve().parents[3] / "aimee"))
        path = aimee / "benchmarks" / "memory" / "poison_gate.py"
        spec = importlib.util.spec_from_file_location("existing_poison_gate", path)
        policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
        fixture = json.loads(path.with_name("poison_fixtures.json").read_text())
        rows = fixture["scenarios"][1]["rows"]
        # Reuse the existing fixture's adjudication. No new governance rules.
        ids = {row["id"]: i for i, row in enumerate(rows)}
        active = {ids[row["id"]] for row in rows if not policy.row_is_suppressed(row, fixture["n_min"])}
        table = OracleValues(list(ids.values()), 32)
        layer = EngramLayer(64, 32, 16)
        bank = table.prepare(layer, list(ids.values()), active, table.scope, 1)
        self.assertEqual(set(bank.ids), {ids["fact_refresh"], ids["fact_snapshot"]})
        empty = table.prepare(layer, [ids["poison_refresh"]], active, table.scope, 1)
        hidden = torch.randn(1, 3, 64)
        self.assertIs(layer(hidden, empty), hidden)
        self.assertTrue(torch.isfinite(layer(hidden, empty)).all())

    def test_corpus_is_frozen_and_queries_do_not_contain_answers(self):
        a, b = build(), build()
        self.assertEqual(a, b)
        self.assertEqual(len(a["memories"]), 1000)
        training_queries = {q["query"] for q in a["train"]}
        self.assertFalse(training_queries & {q["query"] for q in a["heldout"]})
        for example in a["train"] + a["heldout"]:
            for answer in example["answer"].split("; "):
                self.assertNotIn(answer.lower(), example["query"].lower())

    def test_static_placement_preserves_forward_and_backward(self):
        base = tiny_qwen()
        tokens = torch.tensor([[1, 7, 11, 15]])
        with torch.no_grad():
            original = base(tokens, use_cache=False).logits
        hooks = place(base, dict(embedding="cpu", layers=["cpu"] * 4, head="cpu"))
        with torch.no_grad():
            self.assertTrue(torch.equal(original, base(tokens, use_cache=False).logits))
        adapter = FrozenQwenEngram(base, 32, 16)
        bank = adapter.layer.prepare([4817], torch.randn(1, 32), 1)
        with adapter.using(bank):
            base(tokens, labels=tokens, use_cache=False).loss.backward()
        self.assertGreater(float(adapter.layer.output.weight.grad.norm()), 0)
        adapter.close()
        for hook in hooks:
            hook.remove()

    def test_checkpointed_frozen_blocks_reach_memory_values(self):
        base = tiny_qwen()
        adapter = FrozenQwenEngram(base, 32, 16)
        base.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        base.train()
        with torch.no_grad():
            adapter.layer.output.weight.normal_(std=0.01)
        table = OracleValues([4817, 4818], 32)
        tokens = torch.tensor([[1, 7, 11, 15]])
        with adapter.using(table.prepare(adapter.layer, [4817, 4818], set(table.row), table.scope, 1)):
            base(tokens, labels=tokens, use_cache=False).loss.backward()
        self.assertGreater(float(table.values.grad.norm()), 0)
        self.assertTrue(all(p.grad is None for p in base.parameters()))
        adapter.close()

    def test_frozen_int8_input_gradient_and_qwen_checkpoint(self):
        source = torch.nn.Linear(32, 64).requires_grad_(False)
        quantized = FrozenInt8Linear(source)
        hidden = torch.randn(2, 32, requires_grad=True)
        output = quantized(hidden)
        output.sum().backward()
        reference = quantized.qweight.float() * quantized.scale
        torch.testing.assert_close(hidden.grad, reference.sum(dim=0).expand_as(hidden))
        self.assertEqual(list(quantized.parameters()), [])
        base = tiny_qwen().requires_grad_(False)
        self.assertGreater(quantize_frozen_linears(base), 0)
        adapter = FrozenQwenEngram(base, 32, 16)
        base.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        base.train()
        tokens = torch.tensor([[1, 7, 11, 15]])
        with adapter.using(adapter.layer.prepare([4817], torch.randn(1, 32), 1)):
            loss = base(tokens, labels=tokens, use_cache=False).loss
            loss.backward()
        self.assertGreater(float(adapter.layer.output.weight.grad.norm()), 0)
        self.assertTrue(all(p.grad is None for p in base.parameters()))
        adapter.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
