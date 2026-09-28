import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
import numpy as np
import torch
import gguf
from safetensors import safe_open
from safetensors.torch import save_file
from stream_gemma import plan,encode_slice


class StreamingConversion(unittest.TestCase):
    def test_chunked_dense_expert_and_scalar_payloads_match_pinned_quantizer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=pathlib.Path(temporary)
            generator=torch.Generator().manual_seed(20260928)
            tensors={
                'model.language_model.embed_tokens.weight':torch.randn(129,32,generator=generator).bfloat16(),
                'model.language_model.layers.0.experts.gate_up_proj':torch.randn(3,64,32,generator=generator).bfloat16(),
                'model.language_model.layers.0.experts.down_proj':torch.randn(3,32,32,generator=generator).bfloat16(),
                'model.language_model.layers.0.layer_scalar':torch.tensor([0.7]).bfloat16(),
                'model.language_model.layers.0.router.proj.weight':torch.randn(3,32,generator=generator).bfloat16()}
            (root/'config.json').write_text(json.dumps({'model_type':'gemma4'}))
            save_file(tensors,root/'model.safetensors')
            (root/'model.safetensors.index.json').write_text(json.dumps({'weight_map':{n:'model.safetensors' for n in tensors}}))
            rows=plan(root)
            with safe_open(root/'model.safetensors',framework='pt',device='cpu') as weights:
                for row in rows:
                    original=tensors[row['source']].float().numpy()
                    reference=gguf.quants.quantize(original,gguf.GGMLQuantizationType.Q8_0) if row['q8'] else original
                    np.testing.assert_array_equal(encode_slice(weights,row,chunk_bytes=512),reference)
            out=root/'model.gguf';report=root/'report.json'
            subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('stream_gemma.py')),'--model',str(root),'--output',str(out),'--report',str(report)],check=True,capture_output=True)
            self.assertEqual(json.loads(report.read_text())['status'],'converted')
            reader=gguf.GGUFReader(str(out))
            self.assertEqual(len(reader.tensors),len(tensors))
            for tensor,row in zip(reader.tensors,rows):
                original=tensors[row['source']].float().numpy()
                reference=gguf.quants.quantize(original,gguf.GGMLQuantizationType.Q8_0) if row['q8'] else original
                np.testing.assert_array_equal(tensor.data,reference)
                self.assertEqual(tuple(reversed(tensor.shape)),tuple(original.shape))


if __name__=='__main__':unittest.main()
