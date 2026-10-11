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
    rng = random.Random('request-injection-20261011-pilot' if pilot else 'request-injection-20261011-main')
    histories = [128, 1024] if pilot else [128, 1024, 4096]
    count = 2 if pilot else 8
    episodes = []
    for history in histories:
        for sample in range(count):
            eid = len(episodes)
            colors = [str(x) for x in rng.sample(range(100000, 1000000), 3)]
            names = [f'Vexa{eid}', f'Vexa{eid}', f'Torin{eid}']
            records = [{'record_id': name, 'revision': 2 if r == 1 else 1,
                        'content': f'The access code for terminal {name} is {color}.', 'expected': color}
                       for r, (name, color) in enumerate(zip(names, colors))]
            turns = []
            for r, record in enumerate(records):
                turns.extend([
                    {'kind': 'injection', 'record': r, 'question': f'What is the access code for terminal {record["record_id"]}? Reply with only the code or unknown.',
                     'expected': record['expected']},
                    {'kind': 'unrelated', 'record': None,
                     'question': 'For this unrelated task, reply with the single word blue.', 'expected': 'blue'},
                    {'kind': 'withdrawal', 'record': None,
                     'question': f'What is the access code for terminal {record["record_id"]}? Reply with only the code or unknown.', 'expected': 'unknown',
                     'forbidden': list(colors[:r+1])},
                    {'kind': 'injection', 'phase': 'reselect', 'record': r,
                     'question': f'What is the access code for terminal {record["record_id"]}? Reply with only the code or unknown.', 'expected': record['expected']}])
            episodes.append({'id': eid, 'history_target': history, 'records': records, 'turns': turns})
    return {'seed': 'request-injection-20261011', 'pilot': pilot, 'arms': ARMS,
            'process_repetitions': 1 if pilot else 3, 'episodes': episodes,
            'requests': sum(len(e['turns']) for e in episodes)*len(ARMS)*(1 if pilot else 3),
            'system': SYSTEM,
            'max_answer_tokens': 32,
            'scope': 'Frozen attention receiver; explicit fixture selection. All arms replace private questions/answers with identical public completion notices. Persistent text retains request-only records despite identical expiry instructions. Removed text preserves the unaffected pre-injection checkpoint and reconstructs only the subsequent public notice, rather than artificially rebuilding the entire history. Native banks are prepared once and selected twice per record.',
            'primary': 'Injection accuracy; withdrawal stale intrusion; unrelated accuracy; prefill work and end-to-end turn cost including cleanup. Native preparation measured separately.',
            'success_criteria': 'Never modify earlier history tensors; no record text in native task/public tokens; physical CUDA residency; report observed quality and timing without a success-conditioned headline.'}


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
        model = AutoModelForCausalLM.from_pretrained(args.model, local_files_only=True, dtype=torch.float32,
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
        engine.counters = {'prefill_tokens': 0, 'decode_tokens': 0}
        metadata = {'model': 'Qwen/Qwen3-0.6B', 'model_files': model_files, 'torch': torch.__version__,
                    'transformers': transformers.__version__, 'dtype': 'FP32', 'attention': 'stock SDPA',
                    'gpu': torch.cuda.get_device_name(), 'repeat': args.repeat, 'pid': os.getpid(),
                    'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'all_parameter_devices': sorted(set(str(p.device) for p in model.parameters()))}
        write(root/f'metadata-{args.repeat}.json', metadata)
        order = list(fixture['episodes']); random.Random(20261011+args.repeat).shuffle(order)
        arms = ARMS[args.repeat:]+ARMS[:args.repeat]
        with (root/f'rows-{args.repeat}.jsonl').open('x') as stream, (root/f'preparation-{args.repeat}.jsonl').open('x') as prep:
            for episode in order:
                bank_ids = [msg('user', 'Request-only memory: '+r['content']) for r in episode['records']]
                banks = []
                for rid, ids in enumerate(bank_ids):
                    bank, seconds = timed(lambda: engine.prefill(ids))
                    banks.append(bank)
                    prep.write(json.dumps({'episode': episode['id'], 'record': rid, 'tokens': ids,
                                           'seconds': seconds, 'bytes': sum(t.numel()*t.element_size() for pair in engine.pairs(bank) for t in pair),
                                           'state_sha256': tensor_digest(engine.pairs(bank))})+'\n'); prep.flush()
                system = msg('system', SYSTEM)
                filler = tokenizer.encode('Public archive note: the maintenance log lists ordinary scheduling details. '*1024,
                                          add_special_tokens=False)
                hids = system+tokenizer.encode('<|im_start|>user\n', add_special_tokens=False)
                end = tokenizer.encode('<|im_end|>\n', add_special_tokens=False)+msg('assistant', 'Archive noted.')
                history = hids+filler[:max(0, episode['history_target']-len(hids)-len(end))]+end
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
                        torch.cuda.synchronize(); turn_start = time.perf_counter()
                        attachment = memory_prefill = 0.0
                        native_ids = []
                        if record is not None and arm == 'native-at-injection':
                            selected, attachment = timed(lambda: engine.attach(checkpoint, banks[record]))
                            native_ids = bank_ids[record]
                        elif record is not None:
                            selected, memory_prefill = timed(lambda: engine.prefill(bank_ids[record], checkpoint))
                        else:
                            selected = engine.wrap(engine.pairs(checkpoint))
                        answer = engine.answer(query_ids, selected, tokenizer)
                        query_cache = answer.pop('query_cache')
                        torch.cuda.synchronize(); inference_total = time.perf_counter()-turn_start
                        commit_ids = msg('user', 'The private operation has finished. Please acknowledge completion.')+msg('assistant', 'Acknowledged.')
                        if arm == 'persistent-text':
                            # Preserve the injected record, but replace the private
                            # exchange with the same public notice used by scoped arms.
                            retained = before_length+(len(bank_ids[record]) if record is not None else 0)
                            pairs = [(k[..., :retained, :], v[..., :retained, :]) for k, v in engine.pairs(query_cache)]
                            public_base = engine.wrap(pairs)
                            current, cleanup = timed(lambda: engine.prefill(commit_ids, public_base))
                            if record is not None: public_ids.extend(bank_ids[record])
                        else:
                            current, cleanup = timed(lambda: engine.prefill(commit_ids, checkpoint))
                        public_ids.extend(commit_ids)
                        torch.cuda.synchronize(); total = time.perf_counter()-turn_start
                        assert checkpoint.get_seq_length() == before_length
                        assert before_ptrs == [t.data_ptr() for pair in engine.pairs(checkpoint) for t in pair]
                        assert current.get_seq_length() == len(public_ids)
                        assert all(t.device.type == 'cuda' for pair in engine.pairs(current) for t in pair)
                        if arm != 'persistent-text':
                            assert all(r['content'] not in tokenizer.decode(public_ids) for r in episode['records'])
                        row = dict(answer, repeat=args.repeat, episode=episode['id'], history_target=episode['history_target'],
                                   arm=arm, turn=ti, kind=turn['kind'], expected=turn['expected'], forbidden=turn.get('forbidden', []),
                                   phase=turn.get('phase', 'first-use' if record is not None else None),
                                   prior_history_tokens=before_length, public_history_tokens=len(public_ids),
                                   task_token_ids=query_ids, native_bank_tokens=len(native_ids),
                                   memory_text_prefill_seconds=memory_prefill, attachment_seconds=attachment,
                                   request_first_seconds=attachment+memory_prefill+answer['inference_first_seconds'],
                                   request_end_seconds=inference_total, cleanup_seconds=cleanup, turn_total_seconds=total,
                                   prefill_tokens=engine.counters['prefill_tokens']-before_counters['prefill_tokens'],
                                   decode_tokens=engine.counters['decode_tokens']-before_counters['decode_tokens'],
                                   history_reprefill_tokens=0, history_checkpoint_unchanged=True,
                                   public_transcript_sha256=hashlib.sha256(json.dumps(public_ids).encode()).hexdigest(),
                                   cuda_allocated_bytes=torch.cuda.memory_allocated(), cuda_reserved_bytes=torch.cuda.memory_reserved(),
                                   physical_devices=sorted(set(str(t.device) for pair in engine.pairs(current) for t in pair)))
                        stream.write(json.dumps(row)+'\n'); stream.flush(); os.fsync(stream.fileno())
                        del selected, query_cache, checkpoint
                    assert tensor_digest(engine.pairs(initial)) == initial_hash
                    del current
                del initial, banks
                print(json.dumps({'repeat': args.repeat, 'episode': episode['id'], 'completed': True}), flush=True)
        assert model_files == {p.name: digest(p) for p in model_path.iterdir() if p.is_file() and p.suffix in {'.json', '.safetensors'}}
        write(root/f'completion-{args.repeat}.json', {'passed': True, 'requests': sum(len(e['turns']) for e in order)*len(ARMS),
              'all_GPU': True, 'model_files_unchanged': True})


if __name__ == '__main__':
    main()
