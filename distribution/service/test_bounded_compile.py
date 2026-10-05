"""Real architecture/cache parity for the larger-model compiler export path."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import torch
from safetensors.torch import save_file
from tokenizers import Tokenizer, models, pre_tokenizers
from transformers import Gemma4TextConfig, Gemma4TextModel, Qwen3_5TextConfig, Qwen3_5TextModel, PreTrainedTokenizerFast
from bounded_compile import BoundedTextCompiler, ensure_qwen_cpu_solver


class ExportParity(unittest.TestCase):
    def test_every_selected_record_and_attention_layer_reaches_export(self):
        common = dict(vocab_size=64, hidden_size=32, intermediate_size=48,
                      num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2, head_dim=8)
        cases = [
            ('gemma4', Gemma4TextModel, Gemma4TextConfig(**common, global_head_dim=8,
                sliding_window=32, layer_types=['sliding_attention','full_attention'],
                hidden_size_per_layer_input=0, vocab_size_per_layer_input=64,
                enable_moe_block=True, num_experts=4, top_k_experts=2, moe_intermediate_size=16)),
            ('qwen3_5', Qwen3_5TextModel, Qwen3_5TextConfig(**common,
                layer_types=['linear_attention','full_attention'], linear_key_head_dim=8,
                linear_value_head_dim=8, linear_num_key_heads=2, linear_num_value_heads=4,
                rope_parameters={'rope_type':'default','rope_theta':10000.0,'partial_rotary_factor':1.0,
                                 'mrope_section':[1,1,2],'mrope_interleaved':True})),
        ]
        torch.set_num_threads(2)
        policies = [(family, cls, config, policy) for family, cls, config in cases
                    for policy in (['negative'] if family == 'gemma4' else ['nonnegative', 'negative'])]
        for family, cls, config, policy in policies:
            with self.subTest(family=family, policy=policy), tempfile.TemporaryDirectory() as directory:
                if family == 'qwen3_5':
                    ensure_qwen_cpu_solver()
                torch.manual_seed(20260928)
                config._attn_implementation = 'eager'
                reference = cls(config).eval()
                for number, layer in enumerate(reference.layers):
                    if hasattr(layer, 'layer_scalar'):
                        layer.layer_scalar.fill_(0.375 + number * 0.25)
                state = {n: p.bfloat16() if p.is_floating_point() else p for n,p in reference.state_dict().items()}
                reference.load_state_dict(state)
                root = Path(directory)
                saved = {'model.language_model.'+n:p.contiguous() for n,p in state.items()}
                save_file(saved, root/'model.safetensors')
                (root/'model.safetensors.index.json').write_text(json.dumps({'weight_map':{n:'model.safetensors' for n in saved}}))
                tokenizer = Tokenizer(models.WordLevel({'[UNK]':0,'Authoritative':1,'memory':2,'alpha':3,'beta':4,'gamma':5},unk_token='[UNK]'))
                tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
                tokenizer = PreTrainedTokenizerFast(tokenizer_object=tokenizer,unk_token='[UNK]')
                tokenizer.chat_template = "{{ messages[0]['content'] }}"
                if family == 'qwen3_5':
                    tokenizer.chat_template = "{{ raise_exception('Qwen memory must use the raw independent text path') }}"
                compiler = BoundedTextCompiler.__new__(BoundedTextCompiler)
                compiler.model_path = directory
                compiler.gguf_weights = None
                compiler.max_memory_tokens = 32
                compiler.compute_dtype = torch.float32
                compiler.memory_positions = policy
                compiler.tokenizer = tokenizer
                compiler.config = SimpleNamespace(model_type=family,get_text_config=lambda:config)
                compiler.model = compiler.weights = None
                compiler.last_metrics = {}
                request={'response':{'facts':[{'content':word} for word in ['alpha','beta','gamma']]},
                         'identity':{'records':[{'id':i} for i in range(3)]}}
                try:
                    tokens,banks=compiler.encode(request)
                    self.assertTrue({3,4,5}.issubset(tokens))
                    expected_layers={0,1} if family=='gemma4' else {1}
                    self.assertEqual(set(banks),expected_layers)
                    n=len(tokens);positions=torch.arange(-n,0) if policy=='negative' else torch.arange(n)
                    with torch.inference_mode():
                        wanted=reference(input_ids=torch.tensor([tokens]),attention_mask=torch.ones((1,n),dtype=torch.long),
                                         position_ids=positions.unsqueeze(0),use_cache=True)
                    for i,(keys,values) in banks.items():
                        self.assertEqual(keys.shape[-2],n)
                        self.assertTrue(torch.equal(keys,wanted.past_key_values.layers[i].keys.bfloat16()))
                        self.assertTrue(torch.equal(values,wanted.past_key_values.layers[i].values.bfloat16()))
                    self.assertTrue(all(p.device.type=='meta' for p in compiler.model.parameters()))
                    self.assertEqual(compiler.last_metrics['evaluated_tokens'],n)
                    self.assertEqual(compiler.last_metrics['memory_positions'],policy)
                    broken={'response':request['response'],'identity':{'records':[{'id':0}]}}
                    with self.assertRaisesRegex(ValueError,'incomplete selected'):
                        compiler.encode(broken)
                finally:
                    compiler.close()


if __name__ == '__main__':
    unittest.main()
