"""Real Rust ABI tests for the three dedicated adapters, without model weights."""
import ctypes
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace as NS

import torch
from aimee_vllm.model_adapter import ModelAdapter

CONFIGS = Path(__file__).parent / "model_configs"


@unittest.skipUnless(os.environ.get("AIMEE_STORE_LIBRARY"), "requires native adapter library")
class DedicatedAdapterTests(unittest.TestCase):
    def adapter(self, name, config_name=None):
        config_name = config_name or name
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / "config.json").write_bytes((CONFIGS / (config_name + ".json")).read_bytes())
        return ModelAdapter({"adapter": name, "library": os.environ["AIMEE_STORE_LIBRARY"], "model": str(root)})

    def test_cross_model_selection_fails(self):
        names = ("gemma4-12b", "gemma4-26b", "qwen3-8-27b")
        for name in names:
            self.assertEqual(self.adapter(name).description["adapter"], name)
            for other in names:
                if name != other:
                    with self.assertRaisesRegex(RuntimeError, "rejected"):
                        self.adapter(name, other)

    def test_real_rust_positions_handle_mixed_requests_and_padding(self):
        for name in ("gemma4-12b", "gemma4-26b", "qwen3-8-27b"):
            adapter = self.adapter(name)
            original = torch.tensor([0, 1, 20, 0])
            metadata = NS(aimee_ids=["native", "text"], query_start_loc=torch.tensor([0, 2, 3]))
            requests = {"native": NS(store=NS(metadata={"positions": 82})), "text": NS(store=None)}
            args, kwargs = adapter.positioned_arguments((), {"positions": original}, requests, metadata)
            self.assertEqual(kwargs["positions"].tolist(), [82, 83, 20, 0])
            self.assertEqual(original.tolist(), [0, 1, 20, 0])
            with self.assertRaisesRegex(RuntimeError, "pinned"):
                adapter.positioned_arguments((), {"positions": original}, {}, metadata)

    def test_gemma_precision_and_tokenizer_bindings_are_enforced_by_rust(self):
        import hashlib
        for name in ("gemma4-12b","gemma4-26b"):
            adapter=self.adapter(name)
            root=Path(adapter.serving["model"])
            (root/"tokenizer.json").write_bytes(b'{}')
            versions={"vllm":"0.30.0","torch":"2.13.0","triton":"3.7.1"}
            profile={"adapter":name,"positioning":"native-prefix-absolute-v1",
                     "model_config_sha256":hashlib.sha256((root/"config.json").read_bytes()).hexdigest(),
                     "tokenizer_sha256":hashlib.sha256(b'{}').hexdigest(),
                     "weights_sha256":"a"*64,"weight_profile":"Q4_K_M","versions":versions}
            fields=dict(profile=profile,model_root=str(root),weights_sha256="a"*64,
                        weight_profile="Q4_K_M",versions=versions)
            adapter.call("memory_profile",**fields)
            for key,value in (("weights_sha256","b"*64),("weight_profile","Q8_0"),
                              ("tokenizer_sha256","c"*64),("adapter","wrong"),
                              ("positioning","negative-prefix"),("versions",{})):
                altered=dict(profile);altered[key]=value
                with self.assertRaisesRegex(RuntimeError,"rejected"):
                    adapter.call("memory_profile",**dict(fields,profile=altered))

    def test_qwen_private_seed_plan_handles_preemption_and_rejects_slot_aliasing(self):
        adapter=self.adapter("qwen3-8-27b")
        rows=[[False,0,3],[True,0,1],[True,40,2]]
        self.assertTrue(adapter.call("seed_needed",requests=rows))
        self.assertEqual(adapter.call("seed_plan",requests=rows,capacity=4),[1])
        rows[1][1]=40
        self.assertFalse(adapter.call("seed_needed",requests=rows))
        self.assertEqual(adapter.call("seed_plan",requests=rows,capacity=4),[])
        for invalid in ([[True,0,1],[True,0,1]],[[True,0,-1]],[[True,0,4]]):
            with self.assertRaisesRegex(RuntimeError,"rejected"):
                adapter.call("seed_plan",requests=invalid,capacity=4)

    def test_real_gemma_publication_is_owned_by_rust_and_readable(self):
        for name, count, global_heads in (("gemma4-12b",48,1),("gemma4-26b",30,2)):
            adapter = self.adapter(name)
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                segments = [dict(layer=i,value=value,heads=global_heads if i%6==5 else 8,
                                 width=512 if i%6==5 else 256,positions=2)
                            for i in range(count) for value in (False,True)]
                payload = root / "captured.bf16"
                size = sum(s["heads"]*s["width"]*2*2 for s in segments)
                payload.write_bytes(b"\0"*size)
                result = adapter.call("publish", tokens=[2,11], positions=2, segments=segments,
                                      payload=str(payload), destination=str(root/"prepared"),
                                      profile={"weights_sha256":"a"*64})
                index = json.loads((root/"prepared/index.json").read_bytes())
                profile = json.loads((root/"prepared/profile.json").read_bytes())
                self.assertEqual(profile["adapter"], name)
                self.assertEqual(profile["positioning"], "native-prefix-absolute-v1")
                self.assertEqual(index["dictionary_bytes"], size)
                self.assertEqual(index["records"][result["key"]]["tokens"], [2,11])
                lib = adapter.library
                lib.aimee_store_open.argtypes, lib.aimee_store_open.restype = [ctypes.c_char_p], ctypes.c_void_p
                lib.aimee_store_close.argtypes = [ctypes.c_void_p]
                handle = lib.aimee_store_open(json.dumps({**result,"byte_budget":size+4096}).encode())
                self.assertTrue(handle)
                lib.aimee_store_close(handle)
                bad = [dict(s) for s in segments]; bad[0]["width"] = 512
                with self.assertRaisesRegex(RuntimeError,"rejected"):
                    adapter.call("publish",tokens=[2,11],positions=2,segments=bad,payload=str(payload),
                                 destination=str(root/"bad"),profile={})
                self.assertFalse((root/"bad").exists())
