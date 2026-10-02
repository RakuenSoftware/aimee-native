"""Matched replay of one preserved response; run only after both studies finish inference."""
import argparse
import copy
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.request


def require_inference_complete(root):
    primary = json.loads((root/'source-learning-20260927/status.json').read_text())
    if primary['status'] != 'complete':
        raise RuntimeError('primary study must finish before diagnostic publication')
    broader = root/'broader-source-learning-20260928'
    state = json.loads((broader/'status.json').read_text())
    if state['status'] == 'failed':
        raise RuntimeError('broader study failed before diagnostic publication')
    # Use the same audited 63-graded-plus-final-submission boundary as the
    # operator queue. The final CPU grade is still mandatory for release.
    handoff = json.loads(subprocess.check_output(
        [sys.executable, str(root/'swe_gpu_handoff.py'), str(broader)], text=True))
    if not handoff['gpu_ready']:
        raise RuntimeError('broader inference must finish before diagnostic publication')
    return handoff


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--fixture', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--root', default='/opt/swe-native')
    a = p.parse_args()
    root = pathlib.Path(a.root)
    handoff = require_inference_complete(root)
    target = pathlib.Path(a.output)
    if target.exists():
        raise ValueError('preserve prior diagnostic; output already exists')
    fixture = json.loads(pathlib.Path(a.fixture).read_text())
    messages = fixture['request']['messages']
    digest = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()
    if digest != fixture['observed_call']['prompt_sha256']:
        raise ValueError('fixture prompt identity mismatch')
    base = 'http://127.0.0.1:8170'
    def api(path, body=None):
        req = urllib.request.Request(base+path, data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=600) as response:
            return json.load(response)
    model = api('/v1/models')['data'][0]['id']
    source = fixture['source']
    fact = source['complete_fact']
    pub = json.loads(subprocess.check_output(
        ['ssh', '-F', str(root/'source-learning-20260927/ssh.conf'), 'native-gpu'],
        input=json.dumps({'op': 'publish', 'facts': [fact], 'retain': []}).encode(), timeout=1320))
    if pub['publication'] != source['publication'] or pub['records'] != 1:
        raise ValueError('replay must use the original publication identity')
    report = dict(status='running', scope='Post-hoc replay of one known problematic prompt. No task-grade or population claim; isolated replay may differ from concurrent scheduling.',
                  inference_handoff=handoff, generation_timeout_seconds=600,
                  fixture_sha256=hashlib.sha256(pathlib.Path(a.fixture).read_bytes()).hexdigest(),
                  publication=pub['publication'], rows=[])
    def save():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2)+'\n')
    save()
    try:
        for repetition, modes in enumerate([('control', 'native', 'text'), ('text', 'native', 'control')], 1):
            for mode in modes:
                body = copy.deepcopy(fixture['request'])
                body['model'] = model
                if mode == 'native':
                    body['vllm_xargs'] = {'aimee_publication': pub['publication']}
                elif mode == 'text':
                    body['messages'][0]['content'] += '\n\nAuthoritative memory:\n' + fact
                start = time.monotonic()
                response = api('/v1/chat/completions', body)
                choice = response['choices'][0]
                text = choice['message']['content'] or ''
                report['rows'].append(dict(mode=mode, repetition=repetition, seconds=time.monotonic()-start,
                    answer=text, finish_reason=choice['finish_reason'], usage=response['usage'],
                    thought_count=text.count('thought'),
                    response_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    prompt_sha256=hashlib.sha256(json.dumps(body['messages'], sort_keys=True).encode()).hexdigest(),
                    fenced_command_count=len(re.findall(r'```(?:bash|mswea_bash_command)\s*\n(.*?)\n```', text, re.S)),
                    matches_original_response=text == fixture['response']))
                save()
        report['status'] = 'complete'
    except BaseException as error:
        report.update(status='failed', error=repr(error))
        raise
    finally:
        save()
    print(json.dumps({'status': report['status'], 'rows': len(report['rows'])}))


if __name__ == '__main__':
    main()
