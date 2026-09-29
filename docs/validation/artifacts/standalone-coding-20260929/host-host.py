"""Designated .253 host operator for the installed-wheel coding experiment."""
import base64
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path('/var/lib/aimee-large-release-validation')
REMOTE = Path('/opt/aimee-large-release-validation')
NAME = 'standalone-coding-20260929'
OUT = ROOT / NAME
ENV = 'aimee-plugin-coding-test'
LAB_IMAGE = '4599ea638415'
RUNROOT = Path('/opt/swe-native') / NAME
WHEEL_SHA = '935ad0fd307883bba31338686cc57df63e5f2f4afacff34a8b2c9fcd80cf85b3'


def ct(number, code):
    return subprocess.check_output(['pct', 'exec', str(number), '--', 'python3', '-c', code], text=True)


def write_ct(number, path, data):
    ct(number, f"from pathlib import Path\nimport base64\np=Path({str(path)!r});p.parent.mkdir(parents=True,exist_ok=True);assert not p.exists();p.write_bytes(base64.b64decode({base64.b64encode(data).decode()!r}))")


def main():
    state = {'status': 'preflight', 'scope': 'Installed release wheel; controlled complete source-memory selection; fresh official SWE-bench grading', 'wheel_sha256': WHEEL_SHA}
    def save():
        state['updated'] = time.time()
        stage = OUT / 'status.next'; stage.write_text(json.dumps(state, indent=2) + '\n'); stage.replace(OUT / 'status.json')
    save()
    made = False
    try:
        with (ROOT / 'gpu-validation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for number in (101, 110):
                names = subprocess.check_output(['pct', 'exec', str(number), '--', 'podman', 'ps', '--format', '{{.Names}}'], text=True).split()
                assert all(n == 'aimee-native-release-registry' for n in names), 'GPU environment occupied'
            inputs = ROOT / 'regression/frozen-inputs.json'
            rows = json.loads(inputs.read_text())
            prep = json.loads((ROOT / 'regression/prepared-r2/preparation-status.json').read_text())
            records = prep['profiles']['gemma26']['records']; assert len(records) == len(rows) == 6
            fixture = ROOT / 'regression/prepared-r2/gemma26'
            for record in records:
                folder = fixture / record['publication']
                assert hashlib.sha256((folder / 'compact.pack').read_bytes()).hexdigest() == record['payload_sha256']
                assert hashlib.sha256((folder / 'index.json').read_bytes()).hexdigest() == record['index_sha256']
                index = json.loads((folder / 'index.json').read_text())
                assert len(index['records'][record['publication']]['tokens']) == record['encoded_memory_tokens']
            runner = ROOT / 'regression/run.py'
            manifest = {'profile': 'gemma26-standalone-0.1.1', 'wheel_sha256': WHEEL_SHA,
                        'input_sha256': hashlib.sha256(inputs.read_bytes()).hexdigest(),
                        'runner_sha256': hashlib.sha256(runner.read_bytes()).hexdigest(),
                        'publications': {r['instance_id']: r for r in records}}
            for filename, data in [('manifest.json', json.dumps(manifest, indent=2).encode()),
                                    ('frozen-inputs.json', inputs.read_bytes()), ('run.py', runner.read_bytes()),
                                    ('campaign.py', (OUT / 'campaign.py').read_bytes())]:
                write_ct(113, RUNROOT / filename, data)
            (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
            ct(113, f"from pathlib import Path\nimport json\nrows=json.loads(Path({str(RUNROOT / 'frozen-inputs.json')!r}).read_text());graded={{t['instance_id'] for t in json.loads(Path('/opt/swe-native/selected-grader-only.json').read_text())}};assert all(x['task']['instance_id'] in graded for x in rows)")
            for row in rows:
                image = 'docker.io/swebench/sweb.eval.x86_64.' + row['task']['instance_id'].replace('__', '_1776_').lower() + ':latest'
                subprocess.run(['pct', 'exec', '113', '--', 'docker', 'image', 'inspect', image], stdout=subprocess.DEVNULL, check=True)
            client = ROOT / 'clients/signed-lifecycle-r3/gemma26'
            active = json.loads((client / 'active.json').read_text())
            release = REMOTE / 'clients/signed-lifecycle-r3/gemma26/releases' / active['current']
            old = ROOT / 'plugin-standalone-20260929'
            wheel = next((old / 'release-final').glob('*.whl'))
            assert hashlib.sha256(wheel.read_bytes()).hexdigest() == WHEEL_SHA
            cmd = ['podman', 'run', '-d', '--name', ENV, '--network', 'host', '--ipc', 'host',
                   '--device', '/dev/kfd', '--device', '/dev/dri/renderD128', '--device', '/dev/dri/renderD129',
                   '--memory', '36g', '--memory-swap', '36g', '-v', str(REMOTE) + ':' + str(REMOTE),
                   '-v', str(release) + ':/release:ro', '-v', str(REMOTE / 'regression/prepared-r2/gemma26') + ':/fixture:ro',
                   '--entrypoint', '/bin/sleep', LAB_IMAGE, 'infinity']
            (OUT / 'environment-command.json').write_text(json.dumps(cmd, indent=2) + '\n')
            subprocess.run(['pct', 'exec', '101', '--', *cmd], check=True, stdout=(OUT / 'environment-id.txt').open('w')); made = True
            state['status'] = 'installing_published_wheel'; save()
            with (OUT / 'install.log').open('w') as log:
                subprocess.run(['pct', 'exec', '101', '--', 'podman', 'exec', ENV, 'python3', '-m', 'pip', 'install',
                                '--cert', str(REMOTE / 'plugin-standalone-20260929/pip-ca.pem'),
                                str(REMOTE / 'plugin-standalone-20260929/release-final' / wheel.name) + '[gguf]'],
                               stdout=log, stderr=subprocess.STDOUT, check=True)
            # Resolve the library from the installed wheel, never a host build tree.
            library = ct(101, f"import subprocess\nprint(subprocess.check_output(['podman','exec',{ENV!r},'python3','-c','import aimee_vllm;from pathlib import Path;print(Path(aimee_vllm.__file__).parent/\"native/libaimee_native.so\")'],text=True).strip())").strip()
            config = {'model': '/release/models', 'catalog': '/fixture/catalog.json',
                      'recipient': 'larger-coding-public-fixture', 'library': library,
                      'host_memory_budget': 2147483648, 'device_memory_budget': 536870912,
                      'disk_backed': True, 'lossless_transport': True, 'pipeline_transport': True,
                      'gguf_weights': '/release/models/model.gguf', 'gguf_matrix_backend': 'triton',
                      'serve': {'host': '127.0.0.1', 'port': 8170, 'tensor_parallel_size': 2,
                                'max_model_len': 8192, 'max_num_seqs': 2, 'max_num_batched_tokens': 256,
                                'gpu_memory_utilization': .85}}
            (OUT / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
            start = "import os;from pathlib import Path;import aimee_vllm;os.environ['AIMEE_KERNEL_BANK']=str(Path(aimee_vllm.__file__).parent/'native/kernels');from aimee_vllm.cli import main;main()"
            subprocess.run(['pct', 'exec', '101', '--', 'podman', 'exec', '-d',
                            '-e', 'NCCL_P2P_DISABLE=1', '-e', 'VLLM_HOST_IP=127.0.0.1', ENV,
                            'bash', '-c', 'exec python3 -c "$1" --config "$2" > "$3" 2>&1', 'start', start,
                            str(REMOTE / NAME / 'config.json'), str(REMOTE / NAME / 'server.log')], check=True)
            state['status'] = 'starting_model'; save()
            deadline = time.monotonic() + 1200
            while time.monotonic() < deadline:
                ready = ct(101, "import urllib.request\ntry:\n print(urllib.request.urlopen('http://127.0.0.1:8170/health',timeout=2).status==200)\nexcept Exception:print(False)").strip()
                if ready == 'True': break
                time.sleep(5)
            else: raise TimeoutError('installed-wheel model startup')
            state['status'] = 'running_24_attempts'; save()
            env = ['env', 'SWE_RUN_ROOT=' + str(RUNROOT), 'SWE_CONTEXT_TOKENS=8192', 'SWE_OUTPUT_TOKENS=1536',
                   'SWE_STEPS=60', 'SWE_SECONDS=900', 'SWE_GRADE_TIMEOUT=300',
                   'SWE_GRADE_TIMEOUT_OVERRIDES=' + json.dumps({'psf__requests-2193': 3600}),
                   'SWE_ADMISSION_WAIT_SECONDS=960', 'SWE_GENERATION_TIMEOUT_SECONDS=900',
                   'SWE_MODEL_LABEL=gemma26-standalone-011']
            with (OUT / 'runner.log').open('w') as log:
                result = subprocess.run(['pct', 'exec', '113', '--', *env, '/opt/swe-venv/bin/python', str(RUNROOT / 'campaign.py')], stdout=log, stderr=subprocess.STDOUT)
            report = json.loads(ct(113, f"from pathlib import Path;print(Path({str(RUNROOT / 'status.json')!r}).read_text())"))
            (OUT / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
            assert result.returncode == 0 and report['status'] == 'complete', 'coding campaign incomplete: inspect raw report'
            state.update(status='complete', arms=report['arms'], pairs=report['pairs'])
    except BaseException as error:
        state.update(status='failed', error=repr(error)); raise
    finally:
        if made:
            subprocess.run(['pct', 'exec', '101', '--', 'podman', 'stop', '-t', '30', ENV], stdout=subprocess.DEVNULL)
        save()


if __name__ == '__main__':
    main()
