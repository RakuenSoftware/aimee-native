"""Actual complete-hybrid serving gate on a matching BF16 checkpoint.

Uses public fixture facts and a trusted test catalogue. Native and text controls
share instructions. No production authorization or arbitrary-alias guarantee is
inferred from this isolated integration test.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time
import urllib.request
import urllib.error

from hybrid_serving_profile import PROFILE, SYSTEM


def main(a):
    # Full model loading can transiently exceed the final offloaded footprint.
    # Require a bounded cgroup so the test cannot exhaust the shared host.
    cgroup = next(line.split(':', 2)[2].strip() for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0:'))
    limit = (Path('/sys/fs/cgroup') / cgroup.lstrip('/') / 'memory.max').read_text().strip()
    if limit == 'max':
        raise RuntimeError('run this gate in a service with an explicit MemoryMax')
    root = Path(a.output)
    root.mkdir(mode=0o700)
    config = json.loads(Path(a.config).read_text())
    port = config['serve']['port']
    facts = json.loads(Path(a.facts).read_text())
    cases = [('initial', 'What is the access code for Aldren station?', '2648'),
             ('initial', 'Give the station entry number recorded for Aldren.', '2648'),
             ('next', 'What access code belongs to the station connected to Osreth relay?', '5802'),
             ('next', 'For Osreth, give the entry number at its destination.', '5802'),
             ('next', 'Which station code is reachable from Osreth outpost?', '5802')]
    if a.tasks:
        selection=json.loads(Path(a.facts).read_text())
        facts=selection['bundle_facts']
        cases=[(selection['task_bundles'][task['id']],task['query'],task['answer'])
               for task in json.loads(Path(a.tasks).read_text())['tasks']]
    # Check the longest text control before the expensive checkpoint load. It
    # also bounds the absolute positions of the equivalent native prefix.
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(a.model)
    maximum=0
    for publication,query,_ in cases:
        context=SYSTEM+'\n\nAuthoritative memory:\n'+'\n'.join(f['content'] for f in facts.get(publication,{'facts':[]})['facts'])
        messages=[{'role':'system','content':context}]
        for _ in range(78 if a.tasks else 48):
            messages += [{'role':'user','content':'We are planning a meeting.'},{'role':'assistant','content':'Understood.'}]
        messages.append({'role':'user','content':query})
        maximum=max(maximum,len(tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False))+40)
    if maximum>config['serve']['max_model_len']:
        raise RuntimeError(f'48-turn gate needs {maximum} tokens; increase max_model_len before loading')
    rows = []
    env = {**os.environ, 'OMP_NUM_THREADS': '8'}
    if a.plugin:
        env['PYTHONPATH'] = a.plugin
    else:
        env.pop('PYTHONPATH', None)
    module = config.get('python_module', 'aimee_vllm')
    command = [a.python, '-c', 'from '+module+'.cli import main; main()', '--config', a.config]
    report = {'argv': command, 'config': config, 'rows': rows, 'status': 'starting',
              'accelerator': subprocess.check_output(['nvidia-smi', '--query-gpu=name,uuid', '--format=csv,noheader'], text=True).strip(),
              'scope': __doc__, 'integration_only': a.integration_only, 'consumption_profile': PROFILE, 'system_context_sha256': hashlib.sha256(SYSTEM.encode()).hexdigest(), 'config_sha256': hashlib.sha256(Path(a.config).read_bytes()).hexdigest()}

    def save():
        (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    def request(body):
        headers = {'Content-Type': 'application/json'}
        if env.get('VLLM_API_KEY'):
            headers['Authorization'] = 'Bearer ' + env['VLLM_API_KEY']
        req = urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions',
                                     data=json.dumps(body).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=900) as response:
            return json.load(response)

    def run(case, native, turns, forced_tokens=0):
        publication, query, expected = case
        context = SYSTEM
        if not native:
            context += '\n\nAuthoritative memory:\n' + '\n'.join(f['content'] for f in facts.get(publication,{'facts':[]})['facts'])
        messages = [{'role': 'system', 'content': context}]
        for _ in range(turns):
            messages += [{'role': 'user', 'content': 'We are planning a meeting.'},
                         {'role': 'assistant', 'content': 'Understood.'}]
        messages += [{'role': 'user', 'content': query}]
        body = {'model': a.model, 'messages': messages, 'max_tokens': forced_tokens or 32, 'temperature': 0,
                'chat_template_kwargs': {'enable_thinking': False}}
        if forced_tokens:
            body['min_tokens'] = forced_tokens
        if native and publication is not None:
            body['vllm_xargs'] = {'aimee_publication': publication}
        start = time.monotonic()
        result = request(body)
        answer = result['choices'][0]['message']['content'].strip().rstrip('.')
        row = {'publication': publication, 'native': native, 'turns': turns,
                'query': query, 'answer': answer, 'expected': expected,
                'correct': answer.lower() == expected, 'usage': result.get('usage'),
                'elapsed_seconds': time.monotonic() - start}
        if forced_tokens:
            row.pop('correct'); row.pop('expected')
            row.update(forced_tokens=forced_tokens, quality_scored=False)
        return row

    def operate(op):
        with socket.socket(socket.AF_UNIX) as channel:
            channel.settimeout(180)
            channel.connect(config['control_socket'])
            channel.sendall(json.dumps({'op':op}).encode()+b'\n')
            return json.loads(channel.makefile('rb').readline())

    bootstrap_original = None
    if a.integration_only:
        catalogue_path = Path(config['catalog'])
        bootstrap_original = catalogue_path.read_bytes()
        empty = json.loads(bootstrap_original); empty['publications'] = {}
        catalogue_path.write_text(json.dumps(empty))
    save()
    with (root / 'server.log').open('xb') as log:
        proc = subprocess.Popen(command, stdout=log, stderr=log, env=env, start_new_session=True)
        try:
            deadline = time.monotonic() + 1800
            while True:
                if proc.poll() is not None:
                    raise RuntimeError('serving exited during startup')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=2):
                        break
                except Exception:
                    if time.monotonic() > deadline:
                        raise RuntimeError('serving startup timed out')
                    time.sleep(1)
            if a.integration_only:
                Path(config['catalog']).write_bytes(bootstrap_original)
                activation=operate('refresh')
                if activation.get('state')!='active' or activation.get('publications')!=len(json.loads(bootstrap_original)['publications']):
                    raise RuntimeError('initial empty catalogue could not activate hybrid publications')
                report['empty_startup_activated']=True
            else:
                if a.tasks:
                    # Diagnose on the two already observed development failures
                    # before evaluating the untouched fresh task set.
                    for case in cases:
                        if case[1] not in ('Which station code is reachable from Merisol outpost?',
                                            'Which station code is reachable from Osreth outpost?'):
                            continue
                        for turns in (16, 48):
                            for native in (True, False):
                                row = run(case, native, turns)
                                row['development_probe'] = True
                                rows.append(row); print(json.dumps(row), flush=True); save()
                                if not row['correct']:
                                    report.update(status='quality_gate_failed',correct=sum(r['correct'] for r in rows),n=len(rows))
                                    raise RuntimeError('frozen consumption instruction development probe failed')
                for turns in (0, 16, 48):
                    for case in cases:
                        for native in ((True, False) if turns==0 or not a.tasks else (True,)):
                            row = run(case, native, turns)
                            rows.append(row)
                            print(json.dumps(row), flush=True)
                            save()
                    if turns==0 and any(not row['correct'] for row in rows):
                        report.update(status='quality_gate_failed',correct=sum(row['correct'] for row in rows),n=len(rows))
                        raise RuntimeError('paired zero-turn quality gate failed; long stages not run')
            # Simultaneous native/plain requests exercise private state ownership
            # and request position mapping inside the actual upstream scheduler.
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                for row in pool.map(lambda item: run(*item), [(cases[0], True, 0), (cases[2], False, 0)]):
                    row['mixed_batch'] = True
                    rows.append(row)
            if a.tasks:
                # Hybrid prefill admission can queue two long prompts without
                # preempting. Admit unequal prompt sizes, then force 40 decode
                # tokens across a real attention-page boundary while both live.
                # Continuations are mechanical pressure probes, not QA scores.
                pressure=[]
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    for probe in pool.map(lambda item:run(*item),[(cases[0],True,32,40),(cases[2],True,78,40)]):
                        if probe['usage']['completion_tokens']!=40:
                            raise RuntimeError('forced generation did not reach the pressure boundary')
                        pressure.append(probe)
                report['pressure_probes']=pressure
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/metrics',timeout=60) as response:
                    metrics=response.read().decode()
                (root/'prometheus.txt').write_text(metrics)
                preemptions=sum(float(line.rsplit(' ',1)[1]) for line in metrics.splitlines() if line.startswith('vllm:num_preemptions_total'))
                if preemptions<1:raise RuntimeError('native recomputation test did not exercise preemption')
                report['preemptions']=preemptions
            with socket.socket(socket.AF_UNIX) as control:
                control.settimeout(60)
                control.connect(config['control_socket'])
                control.sendall(b'{"op":"metrics"}\n')
                report['metrics'] = json.loads(control.makefile('rb').readline())
            if a.tasks:
                seeds=sum(worker['hybrid_seed_events'] for worker in report['metrics']['workers'])
                minimum=48*(sum(row['native'] and row['publication'] is not None for row in rows)+len(report['pressure_probes']))
                if seeds<=minimum:raise RuntimeError('no additional native recurrent initialization observed after preemption')
                report['seed_measurement_request_count']=len(rows)+len(report['pressure_probes'])
                report['initialization_without_recomputation']=minimum
                report['observed_hybrid_seed_events']=seeds
            if a.tasks and all(row['correct'] for row in rows):
                catalogue_path=Path(config['catalog'])
                original=catalogue_path.read_bytes()
                catalogue=json.loads(original)
                publication=cases[0][0]
                body={'model':a.model,'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':cases[0][1]}],
                      'max_tokens':8,'temperature':0,'chat_template_kwargs':{'enable_thinking':False},
                      'vllm_xargs':{'aimee_publication':publication}}
                def reject(candidate,status):
                    try:request(candidate)
                    except urllib.error.HTTPError as error:
                        if error.code==status:return
                        raise
                    raise RuntimeError(f'request was not rejected with {status}')
                def publish(value):
                    temporary=catalogue_path.with_name(catalogue_path.name+f'.validation-{os.getpid()}')
                    with temporary.open('xb') as target:
                        target.write(value);target.flush();os.fsync(target.fileno())
                    os.replace(temporary,catalogue_path)
                wrong_context={**body,'messages':[{'role':'system','content':'Different instructions'},body['messages'][1]]}
                reject(wrong_context,400)
                report['context_mismatch_rejected']=True
                try:
                    if operate('withdraw').get('state')!='withdrawn':raise RuntimeError('withdrawal failed')
                    reject(body,503)
                    report['withdrawal_rejected']=True
                    spec=catalogue['publications'][publication]
                    invalid=Path(spec['root']).with_name(Path(spec['root']).name+f'.invalid-revision-{os.getpid()}');invalid.mkdir(mode=0o700)
                    prefix=json.loads((Path(spec['root'])/'hybrid.json').read_text())
                    for name in ('index.json','compact.pack',prefix['recurrent']['payload']):
                        os.link(Path(spec['root'])/name,invalid/name)
                    prefix['model_revision']='b'*40
                    raw=(json.dumps(prefix,sort_keys=True)+'\n').encode()
                    (invalid/'hybrid.json').write_bytes(raw)
                    bad=json.loads(original)
                    bad['publications'][publication]={**spec,'root':str(invalid),'hybrid_state':hashlib.sha256(raw).hexdigest()}
                    publish(json.dumps(bad).encode())
                    if 'error' not in operate('refresh'):raise RuntimeError('wrong model revision was admitted')
                    reject(body,503)
                    report['revision_mismatch_rejected']=True
                    publish(original)
                    if operate('refresh').get('state')!='active':raise RuntimeError('revision rejection recovery failed')
                    operate('withdraw')
                    empty={**catalogue,'publications':{}}
                    publish(json.dumps(empty).encode())
                    if operate('refresh').get('publications')!=0:raise RuntimeError('empty catalogue did not withdraw worker stores')
                    reject(body,400)
                    report['empty_catalogue_rejected']=True
                    publish(original)
                    if operate('refresh').get('state')!='active':raise RuntimeError('republish failed')
                    row=run(cases[0],True,0);row['republished']=True;rows.append(row)
                finally:
                    publish(original)
            report['correct'] = sum(row['correct'] for row in rows)
            report['n'] = len(rows)
            report['status'] = 'passed' if report['correct'] == report['n'] else 'quality_gate_failed'
            save()
            if report['status'] != 'passed':
                raise RuntimeError('complete hybrid serving quality gate failed')
        except BaseException as error:
            report['error'] = str(error)
            if report['status'] != 'quality_gate_failed':
                report['status'] = 'failed'
            save()
            raise
        finally:
            if bootstrap_original is not None:
                Path(config['catalog']).write_bytes(bootstrap_original)
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=45)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
    print(json.dumps({'status': report['status'], 'correct': report['correct'], 'n': report['n']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('output', 'python', 'config', 'model', 'facts'):
        parser.add_argument('--' + key, required=True)
    parser.add_argument('--plugin', help='Development import root; omit for installed release wheels')
    parser.add_argument('--integration-only', action='store_true', help='Validate current live bootstrap, pressure and control gates separately from retained quality matrices')
    parser.add_argument('--tasks',help='Frozen full suite; long conversation text controls use the paired zero-turn reference')
    main(parser.parse_args())
