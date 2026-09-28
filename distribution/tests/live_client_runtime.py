"""Run an installed private preview against operator-created Aimee canaries.

Credentials must already have been enrolled with `connect`. Saves only the
requested canary answers, token counts, active release and container limits.
"""
import argparse
import fcntl
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
p.add_argument('--startup-timeout', type=int, default=420)
p.add_argument('--gpu-lock', help='Shared lab lock to serialize GPU ownership across validation jobs')
p.add_argument('--interrupt-and-recover', action='store_true')
a = p.parse_args()
gpu_lock = None
if a.gpu_lock:
    gpu_lock = open(a.gpu_lock, 'a')
    fcntl.flock(gpu_lock, fcntl.LOCK_EX)
root = pathlib.Path(a.root)
output = pathlib.Path(a.output)
report = {'status': 'incomplete', 'answers': [], 'active': json.loads((root / 'active.json').read_text())}
log = output.with_suffix('.log').open('w')
child = subprocess.Popen([a.launcher, '--root', str(root), 'run', '--port', str(a.port)], stdout=log, stderr=subprocess.STDOUT)
base = f'http://127.0.0.1:{a.port}'
try:
    deadline = time.monotonic() + a.startup_timeout
    while time.monotonic() < deadline:
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
    if a.interrupt_and_recover:
        def owned_containers():
            ids=subprocess.check_output(['podman','ps','-q'],text=True,stderr=subprocess.DEVNULL).split()
            items=json.loads(subprocess.check_output(['podman','inspect']+ids,stderr=subprocess.DEVNULL)) if ids else []
            return {item['Id'] for item in items if any(mount['Source']==str((root/'runtime.json').resolve()) for mount in item.get('Mounts',[]))}
        before=owned_containers()
        if len(before)!=1:raise RuntimeError('expected one owned model container before interruption')
        body={'model':model,'messages':[{'role':'user','content':a.query}], 'temperature':0,
              'max_tokens':512,'min_tokens':512,'ignore_eos':True,'stream':True,
              'chat_template_kwargs':{'enable_thinking':False}}
        req=urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        seen=False
        with urllib.request.urlopen(req,timeout=180) as response:
            for line in response:
                if not line.startswith(b'data: '):continue
                chunk=line[6:].strip()
                if chunk==b'[DONE]':break
                value=json.loads(chunk)
                if any(choice.get('delta',{}).get('content') and choice.get('finish_reason') is None for choice in value.get('choices',[])):
                    seen=True;break
        if not seen:raise RuntimeError('stream finished before interruption could be exercised')
        started=time.monotonic();recovery={'status':'pending','old_containers':sorted(before)}
        report['interrupted_request_recovery']=recovery
        output.write_text(json.dumps(report,indent=2)+'\n')
        deadline=time.monotonic()+600
        while time.monotonic()<deadline:
            if child.poll() is not None:raise RuntimeError('launcher exited instead of recovering interrupted native request')
            current=owned_containers()
            if current and not before.intersection(current):
                try:
                    # Recovery clears grants and starts paused. Engine discovery
                    # is ready before admission; the next ordinary query must
                    # obtain fresh Aimee authorization to reopen admission.
                    with urllib.request.urlopen(base+'/v1/models',timeout=2) as ready:
                        data=json.load(ready)
                        if ready.status==200 and any(item['id']==model for item in data['data']):break
                except Exception:pass
            time.sleep(2)
        else:raise TimeoutError('owned model did not restart and become ready')
        body={'model':model,'messages':[{'role':'user','content':a.query}], 'temperature':0,'max_tokens':100,
              'chat_template_kwargs':{'enable_thinking':False}}
        req=urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=180) as response:result=json.load(response)
        answer=result['choices'][0]['message']['content']
        if not all(word.lower() in answer.lower() for word in a.expect):raise RuntimeError('recovered runtime missed required memory')
        with urllib.request.urlopen(base+'/health',timeout=2) as ready:
            if ready.status!=200:raise RuntimeError('fresh authorized recall did not restore healthy admission')
        recovery.update(status='passed',new_containers=sorted(current),seconds=time.monotonic()-started,answer=answer,usage=result.get('usage'))
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
