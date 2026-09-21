"""Real local-reader integration; set AIMEE_IMAGE_READER to the Go binary."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from local_image import AimeeImageClient


@unittest.skipUnless(os.environ.get("AIMEE_IMAGE_READER"), "set AIMEE_IMAGE_READER")
class LocalImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = os.environ["AIMEE_IMAGE_READER"]
        self.general = self.build("general", "general", "", [self.record("general", "base", "global")])
        self.first = self.build("user", "server", self.general, [self.record("user", "drink oolong", "user")])
        self.call("publish", "--view", self.first)

    def record(self, namespace, content, scope):
        return {"namespace": namespace, "id": "1", "revision": content, "scope": {"type": scope, "value": "_" + scope},
                "key": content, "content": content, "confidence": 1, "lifecycle": "active", "kind": "fact", "tier": "L3"}

    def call(self, command, *args):
        return subprocess.check_output([self.binary, command, "--root", str(self.root), *args])

    def build(self, namespace, kind, upstream, records, **extra):
        changes = {"namespace": namespace, "kind": kind, "generation": 1, "upstream": upstream,
                   "records": records, "source": "local-reader-test", "coverage": ["facts"], **extra}
        path = self.root / "input.json"
        path.write_text(json.dumps(changes))
        return json.loads(self.call("build", "--input", str(path)))["view"]

    def client(self, scopes=("user:_user",)):
        client = AimeeImageClient(self.binary, self.root, scopes=scopes, unsafe_research=True)
        self.addCleanup(client.close)
        return client

    def test_live_reader_is_pinned_until_next_model_request(self):
        client = self.client()
        self.assertEqual(client.begin_request(), self.first)
        result = client.search("drink", 4)
        self.assertEqual(result["facts"][0]["id"], "user:1")
        self.assertEqual(result["facts"][0]["content"], "drink oolong")
        second = self.build("user", "server", self.general, [self.record("user", "drink coffee", "user")],
                            generation=2, previous=self.first)
        self.call("publish", "--view", second, "--expected", self.first)
        self.assertEqual(client.search("drink", 4)["facts"][0]["content"], "drink oolong")
        self.assertEqual(client.begin_request(), second)
        self.assertEqual(client.search("drink", 4)["facts"][0]["content"], "drink coffee")

    def test_private_records_require_startup_scope_grant(self):
        client = self.client(scopes=())
        client.begin_request()
        self.assertEqual(client.search("drink", 4)["facts"], [])
        self.assertEqual(client.search("base", 4)["facts"][0]["id"], "general:1")

    def test_tiny_qwen_pins_and_consumes_local_records_with_ram_bank(self):
        import torch
        from test_adapter import tiny_model, Tokenizer
        from qwen_adapter import QwenAimeeAdapter

        class CueTokenizer(Tokenizer):
            # The preload is an ordinary client query. Native attention reads
            # still run with the tiny tokenizer's numeric address metadata.
            pass

        client = self.client()
        model = tiny_model()
        adapter = QwenAimeeAdapter(model, CueTokenizer(), client, host_memory=True)
        self.addCleanup(adapter.close)
        ids = torch.tensor([[1, 7, 11]])
        with torch.inference_mode():
            expected = model(input_ids=ids, use_cache=True).logits
            with adapter.request(recall_mode="attention", preload_query="drink") as state:
                output = model(input_ids=ids, use_cache=True)
                self.assertEqual(state["source_view"], self.first)
                self.assertEqual(list(state["resident_facts"]), ["user:1"])
                self.assertEqual(state["bank_residence"], "ram")
                self.assertTrue(all(k.device.type == v.device.type == "cpu" for k, v in state["banks"].values()))
                self.assertEqual(output.past_key_values.get_seq_length(), 3)
                self.assertEqual(state["native_reads"], 2)
                self.assertFalse(torch.equal(expected, output.logits))
            self.assertIsNone(adapter.active)


if __name__ == "__main__":
    unittest.main(verbosity=2)
