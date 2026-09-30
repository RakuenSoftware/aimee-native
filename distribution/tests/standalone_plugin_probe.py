"""Exercise an installed plugin against live Aimee in an existing vLLM environment.

Run inside the test environment; no container management or model installation.
Uses an already enrolled private client root. Never archives credentials.
"""
import argparse
import importlib.metadata
import json
from pathlib import Path
import subprocess
import time
import urllib.request

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--root', type=Path, required=True)
p.add_argument('--config', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--interrupt-and-recover', action='store_true')
p.add_argument('--repeat', type=int, default=2)
p.add_argument('--interleave-controls', action='store_true', help='Interleave unrelated tasks; these do not disable automatic memory selection')
p.add_argument('--startup-timeout', type=int, default=1200)
a = p.parse_args()
settings = json.loads(a.config.read_text())
port = settings.get('serve', {}).get('port', 8000)
base = f'http://127.0.0.1:{port}'
report = {'status': 'running', 'answers': [], 'scope': __doc__,
          'environment': {n: importlib.metadata.version(n) for n in ['aimee-vllm', 'vllm', 'torch', 'triton']}}
def save(): a.output.write_text(json.dumps(report, indent=2) + '\n')
save()
# Repeat authenticated connect through the installed entry point, not a copied serving config.
c = json.loads((a.root / 'config.json').read_text())
args = ['aimee-native', '--root', str(a.root), 'connect', c['endpoint']]
for key, flag in [('ca_file', '--ca-file'), ('client_identity', '--client-identity'), ('connect_address', '--connect-address')]:
    if c.get(key): args += [flag, c[key]]
connected = subprocess.run(args, input=Path(c['token_file']).read_bytes(), capture_output=True)
if connected.returncode:
    report['status'] = 'connection_failed'; save()
    raise RuntimeError('installed client connect failed: ' + connected.stderr.decode())
report['authenticated_connect'] = True; save()
log = a.output.with_suffix('.log').open('w')
child = subprocess.Popen(['aimee-native', '--root', str(a.root), 'serve', '--config', str(a.config)], stdout=log, stderr=subprocess.STDOUT)
try:
    deadline = time.monotonic() + a.startup_timeout
    while time.monotonic() < deadline:
        if child.poll() is not None: raise RuntimeError('plugin serving process exited before ready')
        try:
            with urllib.request.urlopen(base + '/v1/models', timeout=2) as response:
                model = json.load(response)['data'][0]['id']
            break
        except Exception: time.sleep(1)
    else: raise TimeoutError('plugin startup timed out')
    report['model_ready'] = True; save()
    query = 'What are the native release verification vault code, project, and drink?'
    for iteration in range(a.repeat):
        body = {'model': model, 'messages': [{'role': 'user', 'content': query}],
                'temperature': 0, 'max_tokens': 100, 'chat_template_kwargs': {'enable_thinking': False}}
        req = urllib.request.Request(base + '/v1/chat/completions', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        start = time.perf_counter()
        with urllib.request.urlopen(req, timeout=240) as response: result = json.load(response)
        answer = result['choices'][0]['message']['content']
        passed = all(word in answer.lower() for word in ['28461', 'juniper', 'hibiscus'])
        report['answers'].append({'passed': passed, 'answer': answer, 'usage': result.get('usage'), 'elapsed_ms': round((time.perf_counter()-start)*1000, 3)})
        save()
        if not passed: raise RuntimeError('missing native canary fact')
        if a.interleave_controls:
            value = 17 + iteration
            control = dict(body, messages=[{'role': 'user', 'content': f'Calculate {value} + 24. Reply with only the integer.'}])
            req = urllib.request.Request(base + '/v1/chat/completions', data=json.dumps(control).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=240) as response: result = json.load(response)
            answer = result['choices'][0]['message']['content']
            passed = answer.strip() == str(value + 24)
            report.setdefault('interleaved_tasks', []).append({'iteration': iteration, 'expected': str(value + 24), 'answer': answer, 'passed': passed, 'usage': result.get('usage')})
            save()
            if not passed: raise RuntimeError('unrelated arithmetic task failed between native recalls')
    if a.interrupt_and_recover:
        def model_child():
            children = Path(f'/proc/{child.pid}/task/{child.pid}/children').read_text().split()
            matches = []
            for pid in children:
                try:
                    if b'aimee_vllm.cli' in Path(f'/proc/{pid}/cmdline').read_bytes(): matches.append(int(pid))
                except FileNotFoundError: pass
            return matches[0] if len(matches) == 1 else None
        before = model_child()
        if before is None: raise RuntimeError('cannot identify owned standalone model process')
        streaming = dict(body, stream=True, max_tokens=512, min_tokens=512, ignore_eos=True)
        req = urllib.request.Request(base + '/v1/chat/completions', data=json.dumps(streaming).encode(), headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req, timeout=240) as response:
            for line in response:
                if not line.startswith(b'data: ') or line[6:].strip() == b'[DONE]': continue
                event = json.loads(line[6:])
                if any(c.get('delta', {}).get('content') for c in event.get('choices', [])): break
            else: raise RuntimeError('no streamed content before interruption')
        started = time.monotonic()
        deadline = started + a.startup_timeout
        after = None
        while time.monotonic() < deadline:
            if child.poll() is not None: raise RuntimeError('supervisor exited during recovery')
            current = model_child()
            if current is not None and current != before:
                try:
                    with urllib.request.urlopen(base + '/v1/models', timeout=2) as response: json.load(response)
                    after = current; break
                except Exception: pass
            time.sleep(1)
        if after is None: raise TimeoutError('standalone model process did not restart')
        req = urllib.request.Request(base + '/v1/chat/completions', data=json.dumps(body).encode(), headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req, timeout=240) as response: recovered = json.load(response)
        answer = recovered['choices'][0]['message']['content']
        passed = all(word in answer.lower() for word in ['28461', 'juniper', 'hibiscus'])
        report['recovery'] = {'passed': passed, 'previous_model_pid': before, 'restarted_model_pid': after,
                              'seconds': round(time.monotonic()-started, 3), 'answer': answer, 'usage': recovered.get('usage')}
        save()
        if not passed: raise RuntimeError('native canary failed after standalone restart')
    serving = json.loads((a.root / 'runtime.json').read_text())
    if '/aimee_vllm/native/' not in serving['library']: raise RuntimeError('consumer library not from installed wheel')
    report['consumer_from_wheel'] = True
    report['status'] = 'passed'
except Exception as e:
    report['status'] = 'failed'; report['error'] = str(e); raise
finally:
    child.terminate()
    try: child.wait(timeout=50)
    except subprocess.TimeoutExpired:
        child.kill(); child.wait(); report['cleanup_forced'] = True
    log.close(); save()
