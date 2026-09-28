"""Inspect raw generated tokens after the failed Gemma baseline; no memory."""
import json
import pathlib
import subprocess
import time
from larger_model_baseline import NAME, ROOT, request


def main():
    output = ROOT / 'raw-token-diagnostic.json'
    assert not output.exists(), 'preserve prior diagnostic output'
    state = json.loads(subprocess.check_output(['podman', 'inspect', NAME], stderr=subprocess.DEVNULL))[0]['State']
    assert not state['Running'], 'another operator owns the runtime'
    subprocess.run(['podman', 'start', NAME], check=True)
    try:
        deadline = time.monotonic() + 1200
        while True:
            state = json.loads(subprocess.check_output(['podman', 'inspect', NAME], stderr=subprocess.DEVNULL))[0]['State']
            if not state['Running']:
                raise RuntimeError('runtime exited during diagnostic startup')
            try:
                model = request('/v1/models', timeout=3)['data'][0]['id']
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise TimeoutError('diagnostic readiness')
                time.sleep(5)
        rows = []
        for path, prompt in [('/v1/chat/completions', {'messages': [{'role': 'user', 'content': 'Compute 17 + 25. Return only the integer.'}],
                                                       'chat_template_kwargs': {'enable_thinking': False}}),
                             ('/v1/completions', {'prompt': 'The capital of France is'})]:
            data = dict(model=model, max_tokens=16, temperature=0, seed=20260928,
                        skip_special_tokens=False, return_token_ids=True, **prompt)
            rows.append({'path': path, 'request': data, 'response': request(path, data)})
            output.write_text(json.dumps(rows, indent=2) + '\n')
    finally:
        with (ROOT / 'raw-token-server.log').open('w') as log:
            subprocess.run(['podman', 'logs', NAME], stdout=log, stderr=subprocess.STDOUT)
        subprocess.run(['podman', 'stop', '--time', '60', NAME], check=True)


if __name__ == '__main__':
    main()
