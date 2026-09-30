"""Paired no-memory/text controls with an explicitly empty native catalogue.

Uses an existing installed runtime configuration but never loads its publications
or selection socket. Research control only, not an Aimee authorization test.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--runtime', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--gpu-lock', required=True)
p.add_argument('--repeat', type=int, default=24)
a = p.parse_args()
r = a.output.parent
report = {'status': 'waiting_for_gpu', 'answers': [], 'scope': __doc__}
def save(): a.output.write_text(json.dumps(report, indent=2) + '\n')
save()
with open(a.gpu_lock, 'a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    assert not subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader'], text=True).strip(), 'GPU occupied'
    source = json.loads(a.runtime.read_text())
    keys = ['model', 'library', 'recipient', 'host_memory_budget', 'device_memory_budget', 'gguf_weights', 'gguf_matrix_backend', 'serve']
    config = {k: source[k] for k in keys if k in source}
    config['catalog'] = str(r / 'empty-catalog.json')
    catalog = {'recipient': config['recipient'], 'model_config_sha256': hashlib.sha256((Path(config['model'])/'config.json').read_bytes()).hexdigest(), 'publications': {}}
    Path(config['catalog']).write_text(json.dumps(catalog))
    config_path = r / 'control-config.json'
    config_path.write_text(json.dumps(config))
    report.update(status='starting', native_publications=0, selection_enabled=False)
    save()
    base = 'http://127.0.0.1:' + str(config['serve']['port'])
    with a.output.with_suffix('.log').open('w') as log:
        child = subprocess.Popen(['python', '-c', 'from aimee_vllm.cli import main; main()', '--config', str(config_path)], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + 1200
            while time.monotonic() < deadline:
                if child.poll() is not None: raise RuntimeError('control server exited')
                try:
                    with urllib.request.urlopen(base + '/v1/models', timeout=2) as response: model = json.load(response)['data'][0]['id']
                    break
                except Exception: time.sleep(1)
            else: raise TimeoutError('control startup')
            report['status'] = 'running'; save()
            query = 'What are the native release verification vault code, project, and drink?'
            for iteration in range(a.repeat):
                for arm in ('no-memory', 'text'):
                    messages = [{'role': 'user', 'content': query}]
                    if arm == 'text':
                        messages[0]['content'] = 'Native release verification: vault code 28461; project Juniper; drink Hibiscus tea.\n\n' + query
                    body = {'model': model, 'messages': messages, 'temperature': 0, 'max_tokens': 100, 'chat_template_kwargs': {'enable_thinking': False}}
                    req = urllib.request.Request(base + '/v1/chat/completions', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
                    start = time.perf_counter()
                    with urllib.request.urlopen(req, timeout=240) as response: result = json.load(response)
                    answer = result['choices'][0]['message']['content']
                    report['answers'].append({'iteration': iteration, 'arm': arm, 'answer': answer, 'all_facts_correct': all(w in answer.lower() for w in ['28461', 'juniper', 'hibiscus']), 'usage': result.get('usage'), 'elapsed_ms': round((time.perf_counter()-start)*1000, 3)})
                    save()
            report['status'] = 'completed'
        except Exception as e:
            report.update(status='failed', error=str(e)); raise
        finally:
            child.terminate()
            try: child.wait(timeout=50)
            except subprocess.TimeoutExpired:
                import signal
                os.killpg(child.pid, signal.SIGKILL); child.wait(); report['cleanup_forced'] = True
            save()
