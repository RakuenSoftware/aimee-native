"""Frozen, matched multi-turn test of native attachment versus contextual memory.

All artifacts go to the explicit run directory on the NAS. Pilot and main are
separate. No implicit prompt cache, CPU offload, or mutable past-history state.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import time

from scoped_cache import ScopedCache, tensor_digest

SYSTEM = ('Answer the current question with the shortest exact answer and no explanation. '
          'Use only memory supplied for the current request. Request-only memory '
          'from earlier turns is expired. For access-code questions without current '
          'memory answer unknown. For local questions use the value stated in '
          'the question.')
COLORS = ['red', 'blue', 'green', 'black', 'white', 'orange', 'purple', 'yellow']
ARMS = ['persistent-text', 'removed-text', 'native-at-injection']


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def fixtures(pilot):
    rng = random.Random('learning-expansion-20261011-pilot' if pilot else 'learning-expansion-20261011-main')
    histories = [0, 4096] if pilot else [0, 1024, 4096]
    sizes = [100, 2000] if pilot else [100, 250, 500, 1000, 2000]
    episodes = []
    for history in histories:
        for size in sizes:
            for sample in range(1 if pilot else 2):
                eid = len(episodes)
                values = [str(x) for x in rng.sample(range(100000, 1000000), 6)]
                records = [{'record_id': f'Terminal{eid}_{r//3}', 'revision': r%3+1,
                            'content': f'The access code for terminal Terminal{eid}_{r//3} is {value}.',
                            'expected': value} for r,value in enumerate(values)]
                turns=[]
                for r,record in enumerate(records):
                    a,b=rng.randrange(10,50),rng.randrange(10,50)
                    question=f'What is the access code for terminal {record["record_id"]}? Reply with only the code or unknown.'
                    turns.extend([
                        {'kind':'injection','record':r,'question':question,'expected':record['expected']},
                        {'kind':'unrelated','record':None,'question':f'Compute {a} + {b}. Reply with only the integer.','expected':str(a+b)},
                        {'kind':'withdrawal','record':None,'question':question,'expected':'unknown','forbidden':values[:r+1]},
                        {'kind':'injection','phase':'reselect','record':r,'question':question,'expected':record['expected']}])
                episodes.append({'id':eid,'history_target':history,'record_target_tokens':size,
                                 'value_position':'start' if sample==0 else 'end','records':records,'turns':turns})
    reps=1 if pilot else 3
    return {'seed':'learning-expansion-20261011','pilot':pilot,'arms':ARMS,'process_repetitions':reps,
            'episodes':episodes,'requests':sum(len(e['turns']) for e in episodes)*len(ARMS)*reps,
            'system':SYSTEM,'max_answer_tokens':32,'dtype':'BF16',
            'history_definition':'Additional public-history padding tokens; exact system/chat prefix is counted separately.',
            'record_definition':'Exact serialized user-memory block length including chat framing; no BOS token. Padding is neutral synthetic filler; this is record-size pressure, not dense-paragraph generalization.',
            'scope':'24 turns; six revisioned records, two uses each; identical expiry instructions and private-output replacement; both scoped arms preserve unaffected history.',
            'primary':'Selected accuracy, withdrawal old-code intrusion, arithmetic distraction, cumulative public tokens, prefill categories, latency including cleanup and preparation.',
            'secondary':'Causal attention context-steps are analytic key-query counts under stock full attention, not measured FLOPs; cache residence integrates stage-endpoint byte samples, not allocator-exact byte-time.',
            'criteria':'Report all quality and cost outcomes; full CUDA residency, source/checkpoint hashes, identical native/removed public history, unchanged earlier tensors. Greedy process repeats are not independent tasks; no predetermined 92 percent saving.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path); parser.add_argument('--model', required=True)
    parser.add_argument('--pilot', action='store_true'); parser.add_argument('--repeat', type=int, default=0)
    args = parser.parse_args(); root = args.root
    assert str(root).startswith('/mnt/pve/backup/aimee-experiments/'), 'Experiment artifacts must be on NAS'
    root.mkdir(parents=True, exist_ok=True)
    fixture = fixtures(args.pilot)
    if (root/'fixture.json').exists():
        assert json.loads((root/'fixture.json').read_text()) == fixture
    else:
        write(root/'fixture.json', fixture)
        write(root/'source-manifest.json', {p.name: digest(p) for p in Path(__file__).parent.glob('*.py')})
    for name, sha in json.loads((root/'source-manifest.json').read_text()).items():
        assert digest(Path(__file__).with_name(name)) == sha
    lock = open('/opt/jmlr-second-review-20261005/gpu-exclusive.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip()
    import torch
    import transformers
    from transformers import AutoTokenizer, AutoModelForCausalLM
    torch.set_num_threads(4); torch.manual_seed(20261011)
    model_path = Path(args.model)
    model_files = {p.name: digest(p) for p in model_path.iterdir() if p.is_file() and p.suffix in {'.json', '.safetensors'}}
    with torch.inference_mode():
        tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
        model = AutoModelForCausalLM.from_pretrained(args.model, local_files_only=True, dtype=torch.bfloat16,
                                                    attn_implementation='sdpa').to('cuda').eval()
        engine = ScopedCache(model)
        def msg(role, text, generation=False):
            result = tokenizer.apply_chat_template([{'role': role, 'content': text}], tokenize=True,
                                                  add_generation_prompt=generation, enable_thinking=False,
                                                  return_dict=False)
            return result if isinstance(result, list) else result['input_ids']
        def timed(fn):
            torch.cuda.synchronize(); start = time.perf_counter(); value = fn(); torch.cuda.synchronize()
            return value, time.perf_counter()-start
        warm = msg('system', SYSTEM)+msg('user', 'Local question: a red label is red. What color is it?', True)
        for _ in range(3):
            a = engine.answer(warm, None, tokenizer); del a
        engine.counters = {'prefill_tokens': 0, 'decode_tokens': 0, 'attention_context_steps': 0}
        metadata = {'model': 'Qwen/Qwen3-0.6B', 'model_files': model_files, 'torch': torch.__version__,
                    'transformers': transformers.__version__, 'dtype': 'BF16', 'attention': 'stock SDPA',
                    'gpu': torch.cuda.get_device_name(), 'repeat': args.repeat, 'pid': os.getpid(),
                    'bytes_per_KV_token': 2*model.config.num_hidden_layers*model.config.num_key_value_heads*model.config.head_dim*2,
                    'layer_count': model.config.num_hidden_layers,
                    'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'all_parameter_devices': sorted(set(str(p.device) for p in model.parameters()))}
        write(root/f'metadata-{args.repeat}.json', metadata)
        order = list(fixture['episodes']); random.Random(20261011+args.repeat).shuffle(order)
        arms = ARMS[args.repeat:]+ARMS[:args.repeat]
        with (root/f'rows-{args.repeat}.jsonl').open('x') as stream, (root/f'preparation-{args.repeat}.jsonl').open('x') as prep:
            for episode in order:
                bank_ids=[]
                frame=tokenizer.encode('<|im_start|>user\n',add_special_tokens=False)
                tail=tokenizer.encode('<|im_end|>\n',add_special_tokens=False)
                pad=tokenizer.encode(' note',add_special_tokens=False)
                assert len(pad)==1
                for record in episode['records']:
                    core=tokenizer.encode('Request-only memory: '+record['content']+'\n',add_special_tokens=False)
                    n=episode['record_target_tokens']-len(frame)-len(tail)-len(core)
                    assert n>=0
                    body=core+pad*n if episode['value_position']=='start' else pad*n+core
                    ids=frame+body+tail
                    assert len(ids)==episode['record_target_tokens'] and 151643 not in ids
                    bank_ids.append(ids)
                banks = []
                episode_bank_preparation_seconds = 0.0
                for rid, ids in enumerate(bank_ids):
                    bank, seconds = timed(lambda: engine.prefill(ids))
                    banks.append(bank)
                    episode_bank_preparation_seconds += seconds
                    prep.write(json.dumps({'episode': episode['id'], 'record': rid, 'tokens': ids,
                                           'seconds': seconds, 'attention_context_steps': len(model.model.layers)*len(ids)*(len(ids)+1)//2, 'bytes': sum(t.numel()*t.element_size() for pair in engine.pairs(bank) for t in pair),
                                           'state_sha256': tensor_digest(engine.pairs(bank))})+'\n'); prep.flush()
                system = msg('system', SYSTEM)
                filler = tokenizer.encode('Public archive note: the maintenance log lists ordinary scheduling details. '*1024,
                                          add_special_tokens=False)
                hids = system+tokenizer.encode('<|im_start|>user\n', add_special_tokens=False)
                end = tokenizer.encode('<|im_end|>\n', add_special_tokens=False)+msg('assistant', 'Archive noted.')
                history = hids+filler[:episode['history_target']]+end
                initial, bootstrap_seconds = timed(lambda: engine.prefill(history))
                initial_hash = tensor_digest(engine.pairs(initial))
                for arm in arms:
                    public_ids = list(history); current = engine.wrap(engine.pairs(initial))
                    for ti, turn in enumerate(episode['turns']):
                        checkpoint = current
                        before_length = checkpoint.get_seq_length()
                        before_ptrs = [t.data_ptr() for pair in engine.pairs(checkpoint) for t in pair]
                        before_counters = dict(engine.counters)
                        query_ids = msg('user', turn['question'], True)
                        record = turn['record']
                        turn_start_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        torch.cuda.synchronize(); turn_start = time.perf_counter()
                        attachment = memory_prefill = 0.0
                        cache_bytes_before = sum(t.numel()*t.element_size() for pair in engine.pairs(checkpoint) for t in pair)
                        native_ids = []
                        if record is not None and arm == 'native-at-injection':
                            selected, attachment = timed(lambda: engine.attach(checkpoint, banks[record]))
                            native_ids = bank_ids[record]
                        elif record is not None:
                            selected, memory_prefill = timed(lambda: engine.prefill(bank_ids[record], checkpoint))
                        else:
                            selected = engine.wrap(engine.pairs(checkpoint))
                        memory_counters = dict(engine.counters)
                        selected_prefix_tokens = selected.get_seq_length()
                        assert selected_prefix_tokens+len(query_ids)+fixture['max_answer_tokens'] <= model.config.max_position_embeddings, 'Window limit would be exceeded'
                        answer = engine.answer(query_ids, selected, tokenizer)
                        query_cache = answer.pop('query_cache')
                        after_answer_counters = dict(engine.counters)
                        cache_bytes_answer = sum(t.numel()*t.element_size() for pair in engine.pairs(query_cache) for t in pair)
                        torch.cuda.synchronize(); inference_total = time.perf_counter()-turn_start
                        # answer() grows selected in place. Its decode cache is no
                        # longer needed once the answer and counters are captured.
                        del selected
                        commit_ids = msg('user', 'The private operation has finished. Please acknowledge completion.')+msg('assistant', 'Acknowledged.')
                        if arm == 'persistent-text':
                            # Preserve the injected record, but replace the private
                            # exchange with the same public notice used by scoped arms.
                            retained = before_length+(len(bank_ids[record]) if record is not None else 0)
                            pairs = [(k[..., :retained, :], v[..., :retained, :]) for k, v in engine.pairs(query_cache)]
                            public_base = engine.wrap(pairs)
                            del query_cache
                            current, cleanup = timed(lambda: engine.prefill(commit_ids, public_base))
                            del pairs, public_base
                            if record is not None: public_ids.extend(bank_ids[record])
                        else:
                            del query_cache
                            current, cleanup = timed(lambda: engine.prefill(commit_ids, checkpoint))
                        public_ids.extend(commit_ids)
                        torch.cuda.synchronize(); total = time.perf_counter()-turn_start
                        assert checkpoint.get_seq_length() == before_length
                        assert before_ptrs == [t.data_ptr() for pair in engine.pairs(checkpoint) for t in pair]
                        assert current.get_seq_length() == len(public_ids)
                        assert all(t.device.type == 'cuda' for pair in engine.pairs(current) for t in pair)
                        if arm != 'persistent-text':
                            assert all(r['content'] not in tokenizer.decode(public_ids) for r in episode['records'])
                        row = dict(answer, turn_start_utc=turn_start_utc, turn_end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                   bootstrap_seconds=bootstrap_seconds, bootstrap_tokens=len(history),
                                   episode_bank_preparation_seconds=episode_bank_preparation_seconds,
                                   repeat=args.repeat, episode=episode['id'], history_target=episode['history_target'],
                                   arm=arm, turn=ti, record_target_tokens=episode['record_target_tokens'], value_position=episode['value_position'], kind=turn['kind'], expected=turn['expected'], forbidden=turn.get('forbidden', []),
                                   phase=turn.get('phase', 'first-use' if record is not None else None),
                                   prior_history_tokens=before_length, public_history_tokens=len(public_ids),
                                   task_token_ids=query_ids, native_bank_tokens=len(native_ids),
                                   memory_text_prefill_seconds=memory_prefill, attachment_seconds=attachment,
                                   request_first_seconds=attachment+memory_prefill+answer['inference_first_seconds'],
                                   request_end_seconds=inference_total, cleanup_seconds=cleanup, turn_total_seconds=total,
                                   prefill_tokens=engine.counters['prefill_tokens']-before_counters['prefill_tokens'],
                                   decode_tokens=engine.counters['decode_tokens']-before_counters['decode_tokens'],
                                   history_reprefill_tokens=0, history_checkpoint_unchanged=True,
                                   selected_prefix_tokens=selected_prefix_tokens,
                                   prefill_memory_tokens=memory_counters['prefill_tokens']-before_counters['prefill_tokens'],
                                   prefill_task_tokens=after_answer_counters['prefill_tokens']-memory_counters['prefill_tokens'],
                                   prefill_cleanup_tokens=engine.counters['prefill_tokens']-after_answer_counters['prefill_tokens'],
                                   attention_context_steps=engine.counters['attention_context_steps']-before_counters['attention_context_steps'],
                                   attention_memory=memory_counters['attention_context_steps']-before_counters['attention_context_steps'],
                                   attention_task_and_decode=after_answer_counters['attention_context_steps']-memory_counters['attention_context_steps'],
                                   attention_cleanup=engine.counters['attention_context_steps']-after_answer_counters['attention_context_steps'],
                                   cache_bytes_before=cache_bytes_before, cache_bytes_after_answer=cache_bytes_answer,
                                   cache_bytes_after_cleanup=sum(t.numel()*t.element_size() for pair in engine.pairs(current) for t in pair),
                                   cache_byte_seconds_stage_proxy=(cache_bytes_before+cache_bytes_answer)*0.5*inference_total +
                                       (cache_bytes_before+sum(t.numel()*t.element_size() for pair in engine.pairs(current) for t in pair))*0.5*cleanup,
                                   window_limit_tokens=model.config.max_position_embeddings,
                                   window_headroom_tokens=model.config.max_position_embeddings-current.get_seq_length(),
                                   public_transcript_sha256=hashlib.sha256(json.dumps(public_ids).encode()).hexdigest(),
                                   cuda_allocated_bytes=torch.cuda.memory_allocated(), cuda_reserved_bytes=torch.cuda.memory_reserved(),
                                   physical_devices=sorted(set(str(t.device) for pair in engine.pairs(current) for t in pair)))
                        stream.write(json.dumps(row)+'\n'); stream.flush(); os.fsync(stream.fileno())
                        del checkpoint
                    assert tensor_digest(engine.pairs(initial)) == initial_hash
                    del current
                del initial, banks
                torch.cuda.empty_cache()
                print(json.dumps({'repeat': args.repeat, 'episode': episode['id'], 'completed': True}), flush=True)
        assert model_files == {p.name: digest(p) for p in model_path.iterdir() if p.is_file() and p.suffix in {'.json', '.safetensors'}}
        write(root/f'completion-{args.repeat}.json', {'passed': True, 'requests': sum(len(e['turns']) for e in order)*len(ARMS),
              'all_GPU': True, 'model_files_unchanged': True})


if __name__ == '__main__':
    main()
