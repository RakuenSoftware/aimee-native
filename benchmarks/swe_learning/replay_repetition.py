"""Matched replay of one preserved response; run only after both studies end."""
import argparse
import copy
import hashlib
import json
import pathlib
import re
import subprocess
import time
import urllib.request


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--fixture', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--root', default='/opt/swe-native')
    a = p.parse_args()
    root = pathlib.Path(a.root)
    for study in ('source-learning-20260927', 'broader-source-learning-20260928'):
        if json.loads((root/study/'status.json').read_text())['status'] != 'complete':
            raise RuntimeError('study must finish before diagnostic publication: ' + study)
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
        with urllib.request.urlopen(req, timeout=180) as response:
            return json.load(response)
    model = api('/v1/models')['data'][0]['id']
    source = fixture['source']
    fact = source['complete_fact']
    pub = json.loads(subprocess.check_output(
        ['ssh', '-F', str(root/'source-learning-20260927/ssh.conf'), 'native-gpu'],
        input=json.dumps({'op': 'publish', 'facts': [fact], 'retain': []}).encode(), timeout=660))
    if pub['publication'] != source['publication'] or pub['records'] != 1:
        raise ValueError('replay must use the original publication identity')
    report = dict(status='running', scope='Post-hoc replay of one known problematic prompt. No task-grade or population claim; isolated replay may differ from concurrent scheduling.',
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
