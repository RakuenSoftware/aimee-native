"""Private CPU reference logits from original weights with bounded residency.

Uses the original Transformers model and Accelerate offload hooks. This is an
inference diagnostic, not a native-memory experiment or serving implementation.
"""
import argparse
import json
import pathlib
import sys
import time

import torch
from accelerate import cpu_offload, init_empty_weights
from transformers import AutoConfig, AutoTokenizer, Gemma4ForCausalLM, Qwen3_5ForCausalLM

p = argparse.ArgumentParser()
p.add_argument('--model', required=True)
p.add_argument('--source', required=True)
p.add_argument('--output', required=True)
p.add_argument('--threads', type=int, default=8)
a = p.parse_args()
sys.path.insert(0, a.source)
from checkpoint_weights import CheckpointWeights

output = pathlib.Path(a.output)
assert not output.exists(), 'preserve prior diagnostic'
torch.set_num_threads(a.threads)
started = time.monotonic()
config = AutoConfig.from_pretrained(a.model, local_files_only=True)
text = config.get_text_config()
text._attn_implementation = 'eager'
classes = {'gemma4': Gemma4ForCausalLM, 'qwen3_5': Qwen3_5ForCausalLM}
cls = classes[config.model_type]
with init_empty_weights():
    model = cls(text).eval()
index = json.loads((pathlib.Path(a.model) / 'model.safetensors.index.json').read_text())['weight_map']
aliases = {}
for name in model.state_dict():
    if name in index:
        continue
    if name == 'lm_head.weight' and text.tie_word_embeddings:
        canonical = 'model.language_model.embed_tokens.weight'
    else:
        assert name.startswith('model.'), name
        canonical = 'model.language_model.' + name[len('model.'):]
    assert canonical in index, (name, canonical)
    aliases[name] = canonical
tokenizer = AutoTokenizer.from_pretrained(a.model, local_files_only=True)
prompt = tokenizer.apply_chat_template([{'role': 'user', 'content': 'Compute 17 + 25. Return only the integer.'}],
    tokenize=False, add_generation_prompt=True, enable_thinking=False)
ids = tokenizer.encode(prompt, add_special_tokens=False)
assert 0 < len(ids) <= 128
with CheckpointWeights(a.model, aliases=aliases) as weights:
    cpu_offload(model, execution_device=torch.device('cpu'), state_dict=weights,
                preload_module_classes=['Qwen3_5GatedDeltaNet'] if config.model_type == 'qwen3_5' else [])
    with torch.inference_mode():
        result = model(input_ids=torch.tensor([ids]), attention_mask=torch.ones((1, len(ids)), dtype=torch.long),
                       use_cache=False, logits_to_keep=1)
    logits = result.logits[0, -1].float()
    finite = bool(torch.isfinite(logits).all())
    assert finite, 'nonfinite original-checkpoint logits'
    values, indices = logits.topk(10)
    report = {'status': 'complete', 'scope': 'Original checkpoint FP32 CPU next-token reference; no memory',
        'model_type': config.model_type, 'input_token_ids': ids, 'finite': finite,
        'top_tokens': [{'id': int(i), 'token': tokenizer.decode([int(i)], skip_special_tokens=False), 'logit': float(v)}
                       for i, v in zip(indices, values)],
        'weight_reads': weights.reads, 'expanded_bytes_total': weights.expanded_bytes,
        'all_parameters_released': all(p.device.type == 'meta' for p in model.parameters()),
        'seconds': time.monotonic() - started}
output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
