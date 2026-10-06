import unittest
import tempfile
import hashlib
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from aimee_vllm.gguf_loader import UnifiedGGUFLoader


class UnifiedMappingTests(unittest.TestCase):
    def test_text_only_qwen_uses_registered_text_model_without_vision_weights(self):
        loader=UnifiedGGUFLoader.__new__(UnifiedGGUFLoader)
        config=NS(hf_config=NS(model_type='qwen3_5_text',architectures=['Qwen3_5ForConditionalGeneration']))
        adapter=object();plan=NS(files=NS(mm_proj=None))
        with patch('aimee_vllm.gguf_loader.GGUFModelLoader._prepare_adapter',return_value=(adapter,plan)):
            self.assertEqual(loader._prepare_adapter(config),(adapter,plan))
            self.assertEqual(config.hf_config.architectures,['Qwen3_5ForCausalLM'])
            plan.files.mm_proj='vision.gguf'
            with self.assertRaisesRegex(RuntimeError,'text-only Qwen'):
                loader._prepare_adapter(config)

    def test_bound_checkpoint_checksum_is_verified_before_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            weights=Path(directory)/'checkpoint.gguf';weights.write_bytes(b'quantized checkpoint fixture')
            extra={'gguf_weights':str(weights),'gguf_weights_sha256':hashlib.sha256(weights.read_bytes()).hexdigest()}
            with patch('aimee_vllm.gguf_loader.GGUFModelLoader.__init__',return_value=None):
                UnifiedGGUFLoader(NS(model_loader_extra_config=extra))
                weights.write_bytes(b'different checkpoint')
                with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                    UnifiedGGUFLoader(NS(model_loader_extra_config=extra))
                for bad in ('invalid',42):
                    with self.subTest(checksum=bad),self.assertRaisesRegex(ValueError,'invalid'):
                        UnifiedGGUFLoader(NS(model_loader_extra_config=dict(extra,gguf_weights_sha256=bad)))

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
