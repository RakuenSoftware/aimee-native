"""Post-hoc procedure fidelity diagnostic; isolated from completed task studies."""
import argparse
import copy
import hashlib
import json
import pathlib
import re
import subprocess
import time
import urllib.request


def command_from_response(text):
    commands = re.findall(r'```(?:bash|mswea_bash_command)\s*\n(.*?)\n```', text, re.S)
    return commands[0] if len(commands) == 1 else None


def replay(fixture, command):
    image = 'docker.io/swebench/sweb.eval.x86_64.psf_1776_requests-2193:latest'
    container = subprocess.check_output(['docker', 'run', '-d', '--rm', '--network', 'none',
        '--memory', '3g', '--cpus', '2', '--entrypoint', 'sleep', image, '300'], text=True).strip()
    def execute(command):
        p = subprocess.run(['docker', 'exec', '-w', '/testbed', container, 'bash', '-c', 'source /root/.bashrc && ' + command],
                           capture_output=True, text=True, timeout=60)
        return {'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
    try:
        reset = execute('git reset --hard ' + fixture['task']['base_commit'])
        if reset['returncode']:
            raise RuntimeError('clean-base reset failed')
        setup = [execute(c) for c in fixture['setup_commands']]
        # The original reproduction intentionally failed before the fix.
        if [p['returncode'] for p in setup] != [0, 1] or 'Caught ProtocolError (Fail)' not in setup[1]['stdout']:
            raise RuntimeError('preserved pre-edit setup differs')
        observation = execute(command)
        diff = execute('git diff --no-ext-diff --binary HEAD')
        if diff['returncode']:
            raise RuntimeError('could not inspect resulting patch')
        return {'setup': setup, 'observation': observation, 'patch': diff['stdout'],
                'exact_source_patch': diff['stdout'] == fixture['source_patch'],
                'patch_sha256': hashlib.sha256(diff['stdout'].encode()).hexdigest()}
    finally:
        subprocess.run(['docker', 'rm', '-f', container], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--fixture', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--ssh-config', required=True)
    a = p.parse_args()
    target = pathlib.Path(a.output)
    if target.exists():
        raise ValueError('preserve existing diagnostic output')
    raw = pathlib.Path(a.fixture).read_bytes()
    fixture = json.loads(raw)
    if hashlib.sha256(fixture['source_patch'].encode()).hexdigest() != fixture['source_patch_sha256']:
        raise ValueError('source patch identity mismatch')
    def api(path, body=None):
        request = urllib.request.Request('http://127.0.0.1:8170' + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.load(response)
    model = api('/v1/models')['data'][0]['id']
    report = {'status': 'running', 'started': time.time(), 'fixture_sha256': hashlib.sha256(raw).hexdigest(),
        'scope': 'Post-hoc frozen pre-edit prompt; single-response source-patch fidelity, not official task accuracy. Two reversed-order deterministic repeats are not independent replications.',
        'max_tokens': 1536, 'seed': 20260926, 'encoding_revision': 'native-swe-v3-fp32-full',
        'representation_labels': fixture.get('representation_labels', {'original':'unified-diff','compact':'escaped-lines'}),
        'historical_publication': fixture['original_publication'], 'publications': {}, 'rows': []}
    def save():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + '\n')
    save()
    try:
        for variant in ('original', 'compact'):
            pub = json.loads(subprocess.check_output(['ssh', '-F', a.ssh_config, 'native-gpu'],
                input=json.dumps({'op': 'publish', 'facts': [fixture[variant + '_fact']],
                    'retain': [x['publication'] for x in report['publications'].values()]}).encode(), timeout=1320))
            if pub['records'] != 1:
                raise ValueError('incomplete procedure publication')
            expected = fixture.get('expected_publications', {}).get(variant)
            if expected is not None and pub['publication'] != expected:
                raise ValueError('publication does not match declared full-pass representation')
            if expected is None and variant == 'original' and pub['publication'] == fixture['original_publication']:
                raise ValueError('diagnostic requires fresh full-pass encoding, not historical partial-reuse cache')
            report['publications'][variant] = pub
            save()
        modes = fixture.get('mode_order', ['native-original', 'native-compact', 'text-original', 'text-compact', 'control'])
        if len(modes)!=len(set(modes)) or not set(modes)<={'native-original','native-compact','text-original','text-compact','control'}:
            raise ValueError('invalid declared diagnostic conditions')
        for repetition, order in enumerate((modes, list(reversed(modes))), 1):
            for mode in order:
                messages = copy.deepcopy(fixture['messages'])
                body = {'model': model, 'messages': messages, 'temperature': 0, 'seed': 20260926,
                        'max_tokens': 1536, 'chat_template_kwargs': {'enable_thinking': False}}
                if mode.startswith('native-'):
                    body['vllm_xargs'] = {'aimee_publication': report['publications'][mode.split('-')[1]]['publication']}
                elif mode.startswith('text-'):
                    messages[0]['content'] += '\n\nAuthoritative memory:\n' + fixture[mode.split('-')[1] + '_fact']
                count = api('/tokenize', {'model': model, 'messages': messages,
                                        'chat_template_kwargs': {'enable_thinking': False}})['count']
                if count > 6376:
                    raise ValueError('fixed prompt exceeds study input budget; no truncation allowed')
                start = time.monotonic()
                response = api('/v1/chat/completions', body)
                choice = response['choices'][0]
                text = choice['message']['content'] or ''
                command = command_from_response(text)
                row = {'mode': mode, 'repetition': repetition, 'request': body, 'response': response,
                       'generation_seconds': time.monotonic() - start, 'input_tokens': count,
                       'single_command': command is not None}
                report['rows'].append(row)
                save()
                if command is not None:
                    row['replay'] = replay(fixture, command)
                save()
        report['status'] = 'complete'
    except BaseException as error:
        report.update(status='failed', error=repr(error))
        raise
    finally:
        report['updated'] = time.time()
        save()


if __name__ == '__main__':
    main()
