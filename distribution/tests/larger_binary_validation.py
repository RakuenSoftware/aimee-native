"""Gemma 26B real packaged CLI validation after isolated Qwen GPU work finishes.

Synthetic memory fixture; not live authority, population accuracy or learning.
No private Python/kernel source is mounted into the serving container.
"""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

LAB = Path('/opt/aimee-memory-lab')
ROOT = LAB / 'gemma26-binary-validation-20260928-r2'
NAME = 'aimee-gemma26-binary-validation-20260928-r2'
BASE = 'http://127.0.0.1:8175'
VALUES = ['28461', 'juniper', 'hibiscus']
MEMORY = ('Authoritative memory:\nThe release verification vault code is 28461.\n'
          'The release verification project is Juniper.\nThe release verification drink is hibiscus tea.')


def request(path, body=None, stream=False):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    started = time.perf_counter(); first = None
    with urllib.request.urlopen(req, timeout=240) as response:
        if not stream:
            result = json.load(response)
            if path != '/v1/chat/completions':
                return result
            answer = result['choices'][0]['message']['content']; usage = result['usage']
        else:
            answer = ''; usage = None
            for line in response:
                if not line.startswith(b'data: '):
                    continue
                data = line[6:].strip()
                if data == b'[DONE]':
                    break
                result = json.loads(data)
                if result.get('usage'):
                    usage = result['usage']
                for choice in result.get('choices', []):
                    text = choice.get('delta', {}).get('content') or ''
                    if text and first is None:
                        first = time.perf_counter() - started
                    answer += text
    return {'answer': answer, 'usage': usage, 'seconds': time.perf_counter() - started,
            'ttft_seconds': first}


def main():
    ROOT.mkdir(exist_ok=False)
    report = {'status': 'waiting', 'scope': __doc__, 'rows': []}
    def save():
        (ROOT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    save()
    # Observe the specific predecessor; never restart because observation expires.
    while True:
        state = json.loads(subprocess.check_output(['podman', 'inspect',
            'aimee-qwen27-negative-smoke-20260928'], stderr=subprocess.DEVNULL))[0]['State']
        if not state['Running']:
            break
        time.sleep(10)
    build = LAB / 'larger-binary-client-20260928-r2'
    while not (build / 'build.json').exists():
        if (build / 'build-error.json').exists():
            raise RuntimeError((build / 'build-error.json').read_text())
        time.sleep(5)
    image = json.loads((build / 'build.json').read_text())['image']
    report['image'] = image
    fixture = LAB / 'larger-native-smoke-20260928/gemma26-fixture'
    config = json.loads((fixture / 'config.json').read_text())
    config.update(gguf_weights='/weights/gemma4-26b-q8.gguf', gguf_matrix_backend='triton',
        serve={'port': 8175, 'host': '127.0.0.1', 'tensor_parallel_size': 2, 'max_model_len': 4096,
               'max_num_seqs': 4, 'max_num_batched_tokens': 256, 'gpu_memory_utilization': .85})
    (ROOT / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
    cmd = ['podman', 'run', '-d', '--name', NAME, '--network', 'host', '--ipc', 'host',
        '--device', '/dev/kfd', '--device', '/dev/dri/renderD128', '--device', '/dev/dri/renderD129',
        '--memory', '36g', '--memory-swap', '36g', '-v', str(ROOT) + ':/evidence:ro',
        '-v', str(fixture) + ':/fixture:ro', '-v', str(LAB / 'gemma4-moe') + ':/model:ro',
        '-v', str(LAB / 'gemma26-release-20260928') + ':/weights:ro',
        image, '--config', '/evidence/config.json']
    (ROOT / 'command.json').write_text(json.dumps(cmd, indent=2) + '\n')
    subprocess.run(cmd, check=True, capture_output=True)
    try:
        report['status'] = 'starting'; save()
        deadline = time.monotonic() + 1200
        while True:
            state = json.loads(subprocess.check_output(['podman', 'inspect', NAME], stderr=subprocess.DEVNULL))[0]['State']
            if not state['Running']:
                raise RuntimeError('packaged server exited')
            try:
                model = request('/v1/models')['data'][0]['id']; break
            except (urllib.error.URLError, TimeoutError):
                if time.monotonic() > deadline:
                    raise TimeoutError('server readiness deadline')
                time.sleep(5)
        report['status'] = 'running'; save()
        def run(condition, turns=0, filler=0, stream=False):
            messages = []
            if condition == 'text':
                messages.append({'role': 'system', 'content': MEMORY})
            for _ in range(turns):
                messages.extend([{'role': 'user', 'content': 'We are planning a meeting.'},
                                 {'role': 'assistant', 'content': 'Understood.'}])
            messages.append({'role': 'user', 'content': 'meeting agenda. ' * filler +
                '\nGive the release verification vault code, project, and drink. Be concise.'})
            body = {'model': model, 'messages': messages, 'temperature': 0, 'max_tokens': 96,
                    'chat_template_kwargs': {'enable_thinking': False}}
            if condition == 'native':
                body['vllm_xargs'] = {'aimee_publication': 'three'}
            if stream:
                body.update(stream=True, stream_options={'include_usage': True})
            row = request('/v1/chat/completions', body, stream)
            row.update(condition=condition, turns=turns, filler=filler, stream=stream,
                       correct=all(v in row['answer'].lower() for v in VALUES))
            return row
        for turns in (0, 4, 16, 48):
            for condition in ('control', 'native', 'text'):
                report['rows'].append(run(condition, turns=turns)); save()
        for filler in (500, 1000):
            for condition in ('native', 'text'):
                report['rows'].append(run(condition, filler=filler)); save()
        for i in range(8):
            for condition in ('native', 'text'):
                report['rows'].append(run(condition, stream=True)); save()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for row in pool.map(lambda _: run('native'), range(32)):
                row['concurrent'] = True
                report['rows'].append(row); save()
        checked = [r for r in report['rows'] if r['condition'] != 'control']
        report.update(status='passed' if all(r['correct'] for r in checked) else 'quality_failed',
                      checked=len(checked), correct=sum(r['correct'] for r in checked))
        save()
    except BaseException as error:
        report.update(status='failed', error=repr(error)); save(); raise
    finally:
        subprocess.run(['podman', 'stop', '-t', '20', NAME], capture_output=True)
        with (ROOT / 'server.log').open('w') as log:
            subprocess.run(['podman', 'logs', NAME], stdout=log, stderr=subprocess.STDOUT)


if __name__ == '__main__':
    main()
