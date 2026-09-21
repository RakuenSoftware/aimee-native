"""Structural adapter checks on tiny frozen Qwen, not a recall benchmark."""
import unittest
import re
from types import SimpleNamespace

import torch
from transformers import Qwen3_5TextConfig, Qwen3_5ForCausalLM

from aimee_client import AimeeError
from qwen_adapter import QwenAimeeAdapter
from attention_bridge import NativeAttentionRequest, addressed_query


class Tokenizer:
    all_special_ids = []

    def encode(self, text, add_special_tokens=False):
        return [3 + ord(char) % 120 for char in text]

    def decode(self, ids, skip_special_tokens=False):
        return " ".join(str(i) for i in ids)

    def convert_ids_to_tokens(self, ids):
        return [("Ġ" if n else "") + str(i) for n, i in enumerate(ids)]

    def __call__(self, text, add_special_tokens=False, return_offsets_mapping=False):
        matches = list(re.finditer(r"\d+", text))
        return {"input_ids": [int(m.group()) for m in matches],
                "offset_mapping": [(m.start(), m.end()) for m in matches]}


class Client:
    def __init__(self, facts):
        self.facts = facts
        self.calls = []

    def search(self, query, limit):
        self.calls.append((query, limit))
        return {"facts": self.facts, "windows": [], "active_context_missing": False}


def tiny_model():
    torch.manual_seed(4817)
    config = Qwen3_5TextConfig(vocab_size=128, hidden_size=64, intermediate_size=96,
        num_hidden_layers=4, num_attention_heads=4, num_key_value_heads=2,
        head_dim=16, linear_key_head_dim=16, linear_value_head_dim=16,
        linear_num_key_heads=2, linear_num_value_heads=4,
        layer_types=["linear_attention", "linear_attention", "full_attention", "full_attention"],
        rope_parameters={"rope_type": "default", "rope_theta": 10000.0,
            "partial_rotary_factor": 1.0, "mrope_section": [2, 3, 3]},
        pad_token_id=0, bos_token_id=1, eos_token_id=2)
    config._attn_implementation = "eager"
    return Qwen3_5ForCausalLM(config).eval().requires_grad_(False)


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)

    def test_roundtrip_preserves_response_and_main_cache_without_trainable_adapter(self):
        model = tiny_model()
        original = {name: value.clone() for name, value in model.state_dict().items()}
        facts = [{"id": 19, "content": "one"}, {"id": 7, "content": "two"}]
        client = Client(facts)
        adapter = QwenAimeeAdapter(model, Tokenizer(), client, memory_limit=2)
        tokens = torch.tensor([[1, 7, 11, 15]])
        with torch.inference_mode():
            reference = model(tokens, use_cache=True).logits
            with adapter.request("unchanged question") as state:
                output = model(input_ids=tokens, use_cache=True)
                self.assertEqual(client.calls, [("unchanged question", 2)])
                self.assertIs(state["aimee_response"]["facts"], facts)
                self.assertEqual(output.past_key_values.get_seq_length(), 4)
                self.assertEqual(state["bank_layers"], [2, 3])
                self.assertEqual(state["native_reads"], 2)
                self.assertFalse(torch.equal(reference, output.logits))
                model(input_ids=torch.tensor([[17]]), past_key_values=output.past_key_values, use_cache=True)
                self.assertEqual(len(client.calls), 1)
                self.assertEqual(output.past_key_values.get_seq_length(), 5)
                self.assertEqual(state["native_reads"], 4)
            self.assertIsNone(adapter.active)
            self.assertEqual(state["banks"], {})
            self.assertTrue(torch.equal(reference, model(tokens, use_cache=True).logits))
        self.assertTrue(all(torch.equal(original[name], value) for name, value in model.state_dict().items()))
        self.assertTrue(all(not p.requires_grad for p in model.parameters()))
        self.assertFalse(isinstance(adapter, torch.nn.Module))
        adapter.close()

    def test_empty_response_has_exact_base_behavior_and_requests_do_not_leak(self):
        model = tiny_model()
        client = Client([])
        adapter = QwenAimeeAdapter(model, Tokenizer(), client)
        tokens = torch.tensor([[1, 7, 11, 15]])
        with torch.inference_mode():
            expected = model(tokens, use_cache=True).logits
            for query in ["first", "second"]:
                with adapter.request(query) as state:
                    self.assertTrue(torch.equal(expected, model(input_ids=tokens, use_cache=True).logits))
                    self.assertEqual(state["native_reads"], 0)
        self.assertEqual([call[0] for call in client.calls], ["first", "second"])
        adapter.close()

    def test_failures_propagate_and_release_request(self):
        model = tiny_model()
        class Broken:
            def search(self, query, limit):
                raise AimeeError("unavailable")
        adapter = QwenAimeeAdapter(model, Tokenizer(), Broken())
        with self.assertRaises(AimeeError), adapter.request("question"):
            model(input_ids=torch.tensor([[1, 7]]), use_cache=True)
        self.assertIsNone(adapter.active)
        adapter.close()

    def test_capacity_overflow_does_not_silently_drop_facts(self):
        model = tiny_model()
        client = Client([{"id": 1, "content": "abc"}])
        adapter = QwenAimeeAdapter(model, Tokenizer(), client, max_memory_tokens=1)
        with self.assertRaisesRegex(RuntimeError, "refusing silent truncation"), adapter.request("question"):
            model(input_ids=torch.tensor([[1, 7]]), use_cache=True)
        self.assertIsNone(adapter.active)
        adapter.close()

    def test_native_layer_calls_from_activations_once_and_reads_in_same_forward(self):
        model = tiny_model()
        client = Client([{"id": 21, "content": "native fact"}])
        adapter = QwenAimeeAdapter(model, Tokenizer(), client)
        tokens = torch.tensor([[1, 7, 11, 15]])
        with torch.inference_mode():
            reference = model(tokens, use_cache=True).logits
            with adapter.request(recall_mode="native") as state:
                output = model(input_ids=tokens, use_cache=True)
                self.assertEqual(len(client.calls), 1)
                self.assertEqual(state["request"]["query_source"], "block_hidden_states")
                self.assertEqual(state["request"]["query"], state["native_query_state"]["query"])
                self.assertEqual(state["native_query_state"]["shape"], [1, 4, 64])
                self.assertEqual(state["native_reads"], 2)
                self.assertFalse(torch.equal(reference, output.logits))
                model(input_ids=torch.tensor([[17]]), past_key_values=output.past_key_values, use_cache=True)
                self.assertEqual(len(client.calls), 1)
                self.assertEqual(output.past_key_values.get_seq_length(), 5)
            self.assertEqual(state["banks"], {})
            self.assertTrue(torch.equal(reference, model(tokens, use_cache=True).logits))
        self.assertEqual(list(adapter.native_read.parameters()), [])
        adapter.close()

    def test_native_query_changes_with_state_without_token_or_text_input(self):
        model = tiny_model()
        client = Client([])
        adapter = QwenAimeeAdapter(model, Tokenizer(), client)
        hashes = []
        for ids in [[9, 12], [25, 31]]:
            hidden = model.model.embed_tokens.weight[ids].detach().unsqueeze(0)
            with adapter.request(recall_mode="native") as state:
                self.assertIs(adapter.native_read(hidden), hidden)
                self.assertEqual(state["native_query_state"]["readout_token_ids"], ids)
                hashes.append(state["native_query_state"]["sha256"])
        self.assertEqual([c[0] for c in client.calls], ["9 12", "25 31"])
        self.assertNotEqual(hashes[0], hashes[1])
        adapter.close()

    def test_native_rejects_external_query(self):
        model = tiny_model()
        adapter = QwenAimeeAdapter(model, Tokenizer(), Client([]))
        with self.assertRaisesRegex(ValueError, "external query"), adapter.request("caller query", recall_mode="native"):
            self.fail("native read accepted prompt text as its query")
        self.assertIsNone(adapter.active)
        adapter.close()

    def test_empty_native_readout_is_not_an_api_request_or_decode_retry(self):
        model = tiny_model()
        class EmptyTokenizer(Tokenizer):
            def decode(self, ids, skip_special_tokens=False):
                return ""
        client = Client([])
        adapter = QwenAimeeAdapter(model, EmptyTokenizer(), client)
        tokens = torch.tensor([[1, 7]])
        with torch.inference_mode(), adapter.request(recall_mode="native") as state:
            output = model(input_ids=tokens, use_cache=True)
            before = dict(state["native_query_state"])
            model(input_ids=torch.tensor([[9]]), past_key_values=output.past_key_values, use_cache=True)
            self.assertEqual(client.calls, [])
            self.assertFalse(state["requested"])
            self.assertTrue(state["native_query_state"]["empty_query"])
            self.assertEqual(state["native_query_state"], before)
        adapter.close()

    def test_runtime_cues_read_new_memory_during_decode_and_keep_separate_cache(self):
        model = tiny_model()
        class SequenceClient:
            def __init__(self):
                self.calls = []
            def search(self, query, limit):
                self.calls.append(query)
                fact = {"id": 1, "content": "first"} if len(self.calls) == 1 else {"id": 2, "content": "second"}
                return {"facts": [fact], "windows": []}
        client = SequenceClient()
        adapter = QwenAimeeAdapter(model, Tokenizer(), client)
        original = {n: p.clone() for n, p in model.state_dict().items()}
        with torch.inference_mode(), adapter.request(recall_mode="native_tokens", decode_cue_boundary="every_token") as state:
            output = model(input_ids=torch.tensor([[1, 7, 11]]), use_cache=True)
            self.assertEqual(client.calls, ["1 7 11"])
            self.assertEqual(state["recall_events"][0]["bank_memory_ids"], [1])
            model(input_ids=torch.tensor([[17]]), past_key_values=output.past_key_values, use_cache=True)
            self.assertEqual(client.calls, ["1 7 11", "17"])
            self.assertEqual(state["recall_events"][1]["bank_memory_ids"], [1, 2])
            self.assertEqual(state["recall_events"][1]["phase"], "decode")
            self.assertEqual(state["recall_events"][1]["native_reads_before"], 2)
            model(input_ids=torch.tensor([[19]]), past_key_values=output.past_key_values, use_cache=True)
            self.assertEqual(client.calls[-1], "17 19")
            self.assertEqual(state["recall_events"][-1]["status"], "bank_unchanged")
            self.assertEqual(state["native_reads"], 6)
            self.assertEqual(output.past_key_values.get_seq_length(), 5)
            self.assertEqual(state["runtime_decode_ids"], [17, 19])
        self.assertEqual(state["banks"], {})
        self.assertTrue(all(torch.equal(original[n], p) for n, p in model.state_dict().items()))
        self.assertEqual(list(adapter.runtime_read.parameters()), [])
        adapter.close()

    def test_runtime_cues_prefill_only_control_makes_no_decode_calls(self):
        model = tiny_model()
        client = Client([{"id": 1, "content": "one"}])
        adapter = QwenAimeeAdapter(model, Tokenizer(), client)
        with torch.inference_mode(), adapter.request(recall_mode="native_tokens", decode_recall=False) as state:
            output = model(input_ids=torch.tensor([[1, 7, 11]]), use_cache=True)
            model(input_ids=torch.tensor([[17]]), past_key_values=output.past_key_values, use_cache=True)
            self.assertEqual(client.calls, [("1 7 11", 4)])
            self.assertEqual(state["runtime_decode_ids"], [17])
            self.assertEqual(state["native_reads"], 4)
        with self.assertRaisesRegex(ValueError, "external query"), adapter.request("override", recall_mode="native_tokens"):
            self.fail("accepted external query")
        adapter.close()

    def test_runtime_decode_failure_surfaces_and_releases_bank(self):
        model = tiny_model()
        class BrokenOnDecode:
            def __init__(self):
                self.count = 0
            def search(self, query, limit):
                self.count += 1
                if self.count > 1:
                    raise AimeeError("decode unavailable")
                return {"facts": [{"id": 1, "content": "one"}], "windows": []}
        adapter = QwenAimeeAdapter(model, Tokenizer(), BrokenOnDecode())
        with self.assertRaises(AimeeError), torch.inference_mode(), adapter.request(recall_mode="native_tokens", decode_cue_boundary="every_token") as state:
            output = model(input_ids=torch.tensor([[1, 7]]), use_cache=True)
            model(input_ids=torch.tensor([[17]]), past_key_values=output.past_key_values, use_cache=True)
        self.assertIsNone(adapter.active)
        self.assertEqual(state["banks"], {})
        self.assertEqual(state["recall_events"][-1]["phase"], "decode")
        adapter.close()

    def test_runtime_cues_wait_for_complete_words_without_entity_rules(self):
        model = tiny_model()
        class WordTokenizer(Tokenizer):
            def decode(self, ids, skip_special_tokens=False):
                return "".join({1: "question", 17: "re", 18: "cord", 19: "\n"}.get(i, "") for i in ids)
        client = Client([])
        adapter = QwenAimeeAdapter(model, WordTokenizer(), client)
        with torch.inference_mode(), adapter.request(recall_mode="native_tokens") as state:
            output = model(input_ids=torch.tensor([[1]]), use_cache=True)
            for token in [17, 18]:
                model(input_ids=torch.tensor([[token]]), past_key_values=output.past_key_values, use_cache=True)
                self.assertEqual(len(client.calls), 1)
            model(input_ids=torch.tensor([[19]]), past_key_values=output.past_key_values, use_cache=True)
            self.assertEqual(client.calls, [("question", 4), ("record", 4)])
            self.assertEqual(state["recall_events"][-1]["step"], 3)
        adapter.close()

    def test_attention_request_controls_translation_with_identical_address_metadata(self):
        keys = torch.eye(3).view(1, 1, 3, 3)
        sources = [("sequence", [9, 12, 25])]
        for query, expected in [(torch.tensor([20., 0., 0.]), "9"),
                                (torch.tensor([0., 0., 20.]), "25")]:
            req = NativeAttentionRequest(query.view(1, 1, 1, 3), keys, keys, None, 2, 1.0)
            text, spans = addressed_query(req, Tokenizer(), sources, 1, max_words=1)
            self.assertEqual(text, expected)
            self.assertEqual(len(spans), 1)

    def test_attention_translation_respects_added_special_token_metadata(self):
        tokenizer = Tokenizer()
        tokenizer.added_tokens_decoder = {9: SimpleNamespace(special=True)}
        keys = torch.eye(2).view(1, 1, 2, 2)
        request = NativeAttentionRequest(torch.tensor([20., 0.]).view(1, 1, 1, 2),
                                         keys, keys, None, 2, 1.)
        text, _ = addressed_query(request, tokenizer, [("sequence", [9, 12])], 1, max_words=1)
        self.assertEqual(text, "12")

    def test_native_attention_empty_response_is_exact_base_math(self):
        model = tiny_model()
        client = Client([])
        adapter = QwenAimeeAdapter(model, Tokenizer(), client)
        tokens = torch.tensor([[1, 7, 11, 15]])
        with torch.inference_mode():
            reference = model(tokens, use_cache=True)
            with adapter.request(recall_mode="attention") as state:
                output = model(input_ids=tokens, use_cache=True)
                self.assertTrue(torch.equal(reference.logits, output.logits))
                self.assertEqual(state["request"]["origin"], "qwen_attention_query")
                self.assertEqual(state["recall_events"][0]["native_query_shape"], [1, 4, 4, 16])
                self.assertEqual(len(client.calls), 1)
                self.assertEqual(state["native_reads"], 0)
        adapter.close()

    def test_hybrid_preload_and_native_requests_share_bank_without_replaying_main_cache(self):
        model = tiny_model()
        original = {n: p.clone() for n, p in model.state_dict().items()}
        class UpdatingClient:
            def __init__(self):
                self.calls = []
            def search(self, query, limit):
                self.calls.append(query)
                facts = ([{"id": 1, "content": "first"}] if len(self.calls) == 1 else
                         [{"id": 2, "content": "second"}] if len(self.calls) == 2 else
                         [{"id": 1, "content": "updated"}])
                return {"facts": facts, "windows": []}
        client = UpdatingClient()
        adapter = QwenAimeeAdapter(model, Tokenizer(), client)
        with torch.inference_mode(), adapter.request(recall_mode="attention", preload_query="user question") as state:
            output = model(input_ids=torch.tensor([[1, 7, 11]]), use_cache=True)
            self.assertEqual(client.calls[0], "user question")
            self.assertEqual(len(client.calls), 2)
            preload, native = state["recall_events"]
            self.assertEqual(preload["origin"], "prompt_preload")
            self.assertEqual(preload["native_reads_before"], 0)
            self.assertEqual(preload["bank_memory_ids"], [1])
            self.assertEqual(native["origin"], "qwen_attention_query")
            self.assertEqual(native["bank_memory_ids_before"], [1])
            self.assertEqual(native["bank_memory_ids"], [1, 2])
            self.assertEqual(state["native_reads"], 2)
            self.assertEqual(state["runtime_prefill_ids"], [1, 7, 11])
            model(input_ids=torch.tensor([[17]]), past_key_values=output.past_key_values, use_cache=True)
            self.assertEqual(len(client.calls), 3)
            self.assertEqual(state["recall_events"][-1]["phase"], "decode")
            self.assertEqual(state["recall_events"][-1]["bank_memory_ids"], [1, 2])
            self.assertEqual(state["resident_facts"]["1"]["content"], "updated")
            self.assertEqual(output.past_key_values.get_seq_length(), 4)
            self.assertEqual(state["runtime_decode_ids"], [17])
            self.assertEqual(state["native_reads"], 4)
        self.assertIsNone(adapter.active)
        self.assertEqual(state["banks"], {})
        self.assertTrue(all(torch.equal(original[n], p) for n, p in model.state_dict().items()))
        adapter.close()

    def test_hybrid_empty_preload_continues_native_recall_and_failure_cleans_up(self):
        model = tiny_model()
        class EmptyThenFact(Client):
            def search(self, query, limit):
                self.calls.append((query, limit))
                return {"facts": [] if len(self.calls) == 1 else [{"id": 42, "content": "one"}], "windows": []}
        client = EmptyThenFact([])
        adapter = QwenAimeeAdapter(model, Tokenizer(), client)
        with torch.inference_mode(), adapter.request(recall_mode="attention", preload_query="user question") as state:
            model(input_ids=torch.tensor([[1, 7, 11]]), use_cache=True)
            self.assertEqual(len(client.calls), 2)
            self.assertEqual(state["recall_events"][0]["status"], "empty")
            self.assertEqual(state["recall_events"][1]["bank_memory_ids"], [42])
            self.assertEqual(state["native_reads"], 2)
        class Broken:
            def search(self, query, limit):
                raise AimeeError("unavailable")
        adapter.client = Broken()
        with self.assertRaises(AimeeError), adapter.request(recall_mode="attention", preload_query="user question") as failed:
            model(input_ids=torch.tensor([[1, 7]]), use_cache=True)
        self.assertIsNone(adapter.active)
        self.assertEqual(failed["banks"], {})
        self.assertEqual(failed["recall_events"][0]["origin"], "prompt_preload")
        with self.assertRaises(ValueError), adapter.request("question", preload_query="invalid mode"):
            self.fail("preload accepted outside attention mode")
        adapter.close()

    def test_native_attention_delivers_response_to_same_request_and_decode(self):
        model = tiny_model()
        original = {n: p.clone() for n, p in model.state_dict().items()}
        client = Client([{"id": 42, "content": "one"}])
        adapter = QwenAimeeAdapter(model, Tokenizer(), client)
        tokens = torch.tensor([[1, 7, 11]])
        with torch.inference_mode():
            baseline = model(tokens, use_cache=True).logits
            with adapter.request(recall_mode="attention") as state:
                output = model(input_ids=tokens, use_cache=True)
                self.assertFalse(torch.equal(baseline, output.logits))
                self.assertEqual(state["native_reads"], 2)
                self.assertEqual(state["recall_events"][0]["attention_layer"], 2)
                model(input_ids=torch.tensor([[17]]), past_key_values=output.past_key_values, use_cache=True)
                self.assertEqual(len(client.calls), 2)
                self.assertEqual(state["recall_events"][-1]["native_query_shape"], [1, 4, 1, 16])
                self.assertEqual(output.past_key_values.get_seq_length(), 4)
                self.assertEqual(state["native_reads"], 4)
        self.assertTrue(all(torch.equal(original[n], p) for n, p in model.state_dict().items()))
        self.assertEqual(state["banks"], {})
        with self.assertRaisesRegex(ValueError, "external query"), adapter.request("invented query", recall_mode="attention"):
            self.fail("accepted externally supplied query")
        adapter.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
