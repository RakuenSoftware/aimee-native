import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from aimee_vllm.gguf_loader import UnifiedGGUFLoader


class UnifiedMappingTests(unittest.TestCase):
    def mapping(self, names):
        loader = UnifiedGGUFLoader.__new__(UnifiedGGUFLoader)
        adapter = NS(map_name=lambda name: "model.layers.0.self_attn.q_proj.weight" if name == "blk.0.attn_q.weight" else None)
        files = NS(all_files=["fixture.gguf"])
        with patch.object(loader, "_prepare_model_files", return_value=files), \
             patch("aimee_vllm.gguf_loader.Gemma4GGUFAdapter", return_value=adapter), \
             patch("aimee_vllm.gguf_loader.get_gguf_tensor_names", return_value=names), \
             patch("aimee_vllm.gguf_loader._get_unquantized_modules", return_value=[]):
            return loader._prepare_adapter(NS(hf_config=NS(model_type="gemma4_unified")))

    def test_derived_rotary_tensor_is_not_loaded_as_a_weight(self):
        _, plan = self.mapping(["rope_freqs.weight", "blk.0.attn_q.weight"])
        self.assertNotIn("rope_freqs.weight", plan.name_map)

    def test_unknown_tensor_still_refuses_admission(self):
        with self.assertRaisesRegex(RuntimeError, "unmapped"):
            self.mapping(["unexpected.weight", "blk.0.attn_q.weight"])


if __name__ == "__main__":
    unittest.main()
