"""Run an installed private preview against operator-created Aimee canaries.

Credentials must already have been enrolled with `connect`. Saves only the
requested canary answers, token counts, active release and container limits.
"""
import argparse
import json
import pathlib
import subprocess
import time
import urllib.request

p = argparse.ArgumentParser()
p.add_argument('--launcher', required=True)
p.add_argument('--root', required=True)
p.add_argument('--query', required=True)
p.add_argument('--expect', action='append', required=True)
p.add_argument('--output', required=True)
p.add_argument('--port', type=int, default=8152)
p.add_argument('--repeat', type=int, default=2)
a = p.parse_args()
root = pathlib.Path(a.root)
output = pathlib.Path(a.output)
report = {'status': 'incomplete', 'answers': [], 'active': json.loads((root / 'active.json').read_text())}
log = output.with_suffix('.log').open('w')
child = subprocess.Popen([a.launcher, '--root', str(root), 'run', '--port', str(a.port)], stdout=log, stderr=subprocess.STDOUT)
base = f'http://127.0.0.1:{a.port}'
try:
    for _ in range(420):
        if child.poll() is not None:
            raise RuntimeError('installed runtime exited before ready')
        try:
            with urllib.request.urlopen(base + '/v1/models', timeout=2) as response:
                model = json.load(response)['data'][0]['id']
            break
        except Exception:
            time.sleep(1)
    else:
        raise TimeoutError('installed runtime startup')
    ids = subprocess.check_output(['podman', 'ps', '-q'], text=True, stderr=subprocess.DEVNULL).split()
    containers = json.loads(subprocess.check_output(['podman', 'inspect'] + ids, stderr=subprocess.DEVNULL)) if ids else []
    report['containers'] = [{'image': v['ImageName'], 'memory_limit': v['HostConfig']['Memory'],
                             'memory_swap': v['HostConfig']['MemorySwap'],
                             'security_options': v['HostConfig'].get('SecurityOpt'),
                             'privileged': v['HostConfig']['Privileged']} for v in containers]
    for _ in range(a.repeat):
        body = {'model': model, 'messages': [{'role': 'user', 'content': a.query}],
                'temperature': 0, 'max_tokens': 100, 'chat_template_kwargs': {'enable_thinking': False}}
        request = urllib.request.Request(base + '/v1/chat/completions', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)
        answer = result['choices'][0]['message']['content']
        passed = all(word.lower() in answer.lower() for word in a.expect)
        report['answers'].append({'passed': passed, 'answer': answer, 'usage': result.get('usage'),
                                  'elapsed_ms': round((time.perf_counter() - started) * 1000, 3)})
        if not passed:
            raise RuntimeError('installed runtime missed a required canary')
    report['status'] = 'passed'
finally:
    child.terminate()
    try:
        child.wait(timeout=45)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()
    log.close()
    output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
