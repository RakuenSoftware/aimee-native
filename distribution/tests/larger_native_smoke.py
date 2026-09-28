"""Private larger-model native-memory smoke using previously prepared banks.

Synthetic selected records only. This validates the actual model/backend and
Rust publication path, not live Aimee authorization or automatic learning.
The private source package is used only to build new GPU kernel profiles.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time


def prepare(a):
    import sys
    import torch
    sys.path.insert(0, a.publisher)
    from publisher import publish
    root = Path(a.output)
    root.mkdir(exist_ok=False)
    saved = torch.load(Path(a.prepared) / 'native-state.pt', weights_only=True)
    report = json.loads((Path(a.prepared) / 'result.json').read_text())
    assert report['selected_records'] == 3 and len(saved['tokens']) == report['tokens']
    identity = a.profile + '-full-fp32-synthetic-three-records-v1'
    publish(root / 'memory', identity, 'three', saved['tokens'], saved['banks'])
    catalog = {'model_config_sha256': hashlib.sha256((Path(a.model) / 'config.json').read_bytes()).hexdigest(),
               'recipient': 'larger-model-synthetic-validation',
               'publications': {'three': {'root': '/fixture/memory', 'model': identity, 'key': 'three'}}}
    (root / 'catalog.json').write_text(json.dumps(catalog, indent=2) + '\n')
    config = {'model': '/model', 'catalog': '/fixture/catalog.json',
              'recipient': catalog['recipient'], 'library': a.library,
              'host_memory_budget': 1024**3, 'device_memory_budget': 256*1024**2,
              'disk_backed': True, 'lossless_transport': True, 'pipeline_transport': True}
    (root / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    (root / 'preparation.json').write_text(json.dumps(report, indent=2) + '\n')


def run(a):
    from vllm import LLM, SamplingParams
    output = Path(a.output)
    assert not output.exists(), 'preserve prior results'
    config = json.loads(Path('/fixture/config.json').read_text())
    weights = '/weights/qwen27-q8.gguf' if a.profile == 'qwen27' else '/weights/gemma4-26b-q8.gguf'
    extra = {'gguf_weights': weights}
    if a.profile == 'qwen27':
        extra['mm_proj'] = '/weights/qwen27-mmproj-f32.gguf'
    model = LLM(model=config['model'], tokenizer=config['model'],
                quantization='gguf', load_format='aimee_gguf_unified',
                model_loader_extra_config=extra, tensor_parallel_size=2,
                dtype='bfloat16', enforce_eager=True, enable_prefix_caching=False,
                max_model_len=4096, max_num_seqs=2, max_num_batched_tokens=256,
                gpu_memory_utilization=.85, disable_custom_all_reduce=True,
                worker_cls='aimee_vllm.worker.AimeeWorker',
                attention_config={'backend': 'CUSTOM'}, async_scheduling=False,
                limit_mm_per_prompt={'image': 0, 'audio': 0, 'video': 0})
    tokenizer = model.get_tokenizer()
    memory = ('Authoritative memory:\nThe release verification vault code is 28461.\n'
              'The release verification project is Juniper.\n'
              'The release verification drink is hibiscus tea.')
    cases = [
        ('What is the release verification vault code? Return only the code.', ['28461']),
        ('What is the release verification project? Return only the name.', ['juniper']),
        ('What is the release verification drink? Return only the drink.', ['hibiscus']),
        ('Give the release verification vault code, project, and drink. Be concise.', ['28461', 'juniper', 'hibiscus']),
        ('Compute 17 + 25. Return only the integer.', ['42']),
    ]
    report = {'scope': 'Synthetic three-record native/text/no-memory smoke; no live authorization or learning certification',
              'profile': a.profile, 'rows': [], 'status': 'running'}
    for question, expected in cases:
        for condition in ('control', 'native', 'text'):
            messages = [{'role': 'user', 'content': question}]
            if condition == 'text':
                messages.insert(0, {'role': 'system', 'content': memory})
            prompt = tokenizer.apply_chat_template(messages, tokenize=False,
                add_generation_prompt=True, enable_thinking=False)
            params = SamplingParams(temperature=0, max_tokens=96, seed=20260928,
                extra_args={'aimee_publication': 'three'} if condition == 'native' else {})
            started = time.perf_counter()
            result = model.generate([prompt], params, use_tqdm=False)[0]
            answer = result.outputs[0].text
            report['rows'].append({'question': question, 'condition': condition,
                'expected': expected, 'answer': answer,
                'contains_all': all(word in answer.lower() for word in expected),
                'prompt_tokens': len(result.prompt_token_ids),
                'output_tokens': len(result.outputs[0].token_ids),
                'seconds': time.perf_counter() - started})
            output.write_text(json.dumps(report, indent=2) + '\n')
    report['cache_stats'] = model.collective_rpc('aimee_cache_stats')
    for condition in ('control', 'native', 'text'):
        report[condition + '_passed'] = sum(r['contains_all'] for r in report['rows'] if r['condition'] == condition)
    report['native_prompt_unchanged'] = all(report['rows'][i]['prompt_tokens'] == report['rows'][i+1]['prompt_tokens'] for i in range(0, len(report['rows']), 3))
    report['status'] = 'complete'
    output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['prepare', 'run'])
    p.add_argument('--profile', choices=['gemma26', 'qwen27'], required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--prepared')
    p.add_argument('--publisher')
    p.add_argument('--model')
    p.add_argument('--library')
    a = p.parse_args()
    if a.mode == 'prepare':
        if not all((a.prepared, a.publisher, a.model, a.library)):
            p.error('prepare requires prepared, publisher, model and library paths')
        prepare(a)
    else:
        run(a)
