"""Offline port validation against the archived Python reference, not serving code."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import torch
from transformers import Qwen3_5TextConfig, Qwen3_5ForCausalLM

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/qwen_aimee'))
from qwen_adapter import QwenAimeeAdapter
from test_adapter import Tokenizer, Client
from frozen_int8 import quantize_frozen_linears

p = argparse.ArgumentParser()
p.add_argument('--binary', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
torch.set_num_threads(2)
summary = {}
for precision in ['fp32', 'bf16', 'int8-bf16']:
    for length in [4, 65]:
        name = f'{precision}-{length}'
        root = a.output / name
        root.mkdir(exist_ok=True)
        torch.manual_seed(4817)
        c = Qwen3_5TextConfig(
            vocab_size=128, hidden_size=64, intermediate_size=96,
            num_hidden_layers=4, num_attention_heads=4, num_key_value_heads=2,
            head_dim=16, linear_key_head_dim=16, linear_value_head_dim=16,
            linear_num_key_heads=2, linear_num_value_heads=4,
            layer_types=['linear_attention', 'linear_attention', 'full_attention', 'full_attention'],
            rope_parameters={'rope_type':'default', 'rope_theta':10000.,
                             'partial_rotary_factor':1., 'mrope_section':[2,3,3]},
            pad_token_id=0, bos_token_id=1, eos_token_id=2)
        c._attn_implementation = 'eager'
        m = Qwen3_5ForCausalLM(c).eval().requires_grad_(False)
        if precision != 'fp32':
            m = m.to(torch.bfloat16)
        m.save_pretrained(root / 'tiny')
        if precision.startswith('int8'):
            quantize_frozen_linears(m)
        tokenizer = Tokenizer()
        facts = [{'id':1, 'content':'one'}, {'id':2, 'content':'two'}]
        prompt = [1 + (i * 7) % 120 for i in range(length)]
        memory = tokenizer.encode('Authoritative memory:\none\ntwo')
        decode = [19]
        (root/'input.json').write_text(json.dumps(dict(prompt=prompt, memory=memory, decode=decode)))
        adapter = QwenAimeeAdapter(m, tokenizer, Client(facts), host_memory=True)
        with torch.inference_mode():
            baseline = m(input_ids=torch.tensor([prompt]), use_cache=True).logits
            with adapter.request('unchanged query'):
                native = m(input_ids=torch.tensor([prompt]), use_cache=True)
                step = m(input_ids=torch.tensor([decode]), past_key_values=native.past_key_values, use_cache=True)
                reference = {'baseline':baseline.float().flatten().tolist(),
                             'native':native.logits.float().flatten().tolist(),
                             'decode':step.logits.float().flatten().tolist()}
        adapter.close()
        (root/'python.json').write_text(json.dumps(reference))
        out = root/'rust.json'
        out.unlink(missing_ok=True)
        cmd = [str(a.binary.resolve()), 'probe', '--model', str(root/'tiny'),
               '--input', str(root/'input.json'), '--output', str(out)]
        if precision.startswith('int8'):
            cmd.append('--int8')
        subprocess.run(cmd, check=True)
        actual = json.loads(out.read_text())
        result = {}
        tolerance = 2e-5 if precision == 'fp32' else 0.005
        for arm, want in reference.items():
            x, y = torch.tensor(actual[arm]), torch.tensor(want)
            result[arm] = {'max_abs':(x-y).abs().max().item(),
                           'mean_abs':(x-y).abs().mean().item(),
                           'passed':torch.allclose(x,y,atol=tolerance,rtol=tolerance)}
        result['main_cache_length'] = actual['main_cache_length']
        result['passed'] = all(v['passed'] for v in result.values() if isinstance(v,dict)) and actual['main_cache_length'] == length+1
        summary[name] = result
        print(name, json.dumps(result), flush=True)
(a.output/'summary.json').write_text(json.dumps(summary, indent=2))
assert all(v['passed'] for v in summary.values()), 'Rust numerical parity failed'
