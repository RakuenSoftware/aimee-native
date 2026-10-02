"""Host coordinator: run frozen coding comparisons after each model passes its initial installed probe."""
import argparse
import base64
import fcntl
import json
from pathlib import Path
import subprocess
import time

ROOT = Path('/var/lib/aimee-large-release-validation')
REMOTE = Path('/opt/aimee-large-release-validation')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--profiles', nargs='+', choices=['gemma26', 'qwen27'], required=True)
parser.add_argument('--run-name', required=True)
parser.add_argument('--previous-pid', type=int, required=True)
args = parser.parse_args()
assert Path(args.run_name).name == args.run_name
OUT = ROOT / args.run_name
IMAGE = 'sha256:56e44a78b4ddbb228d5728311a709ee8118acc51f685b9f0e428a809b5ad2935'


def ct(number, code):
    return subprocess.check_output(['pct', 'exec', str(number), '--', 'python3', '-c', code], text=True)


def write_ct(number, path, data):
    ct(number, f"from pathlib import Path\nimport base64\np=Path({str(path)!r});p.parent.mkdir(parents=True,exist_ok=True);data=base64.b64decode({base64.b64encode(data).decode()!r});assert not p.exists() or p.read_bytes()==data; p.write_bytes(data) if not p.exists() else None")


def wait_host_report(path, pidfile, terminal):
    while True:
        report = json.loads(path.read_text()) if path.exists() else {}
        if report.get('status') in terminal:
            return report
        pid = int(pidfile.read_text())
        process = Path('/proc') / str(pid) / 'stat'
        if not process.exists() or process.read_text().split()[2] == 'Z':
            raise RuntimeError('prerequisite exited without completion: ' + str(path))
        time.sleep(15)


def main():
    OUT.mkdir(exist_ok=False)
    state = {'status': 'waiting_for_signed_lifecycle', 'scope': __doc__, 'profiles': {}}
    def save():
        state['updated'] = time.time()
        p = OUT / 'status.next'; p.write_text(json.dumps(state, indent=2) + '\n'); p.replace(OUT / 'status.json')
    save()
    try:
        previous = Path('/proc') / str(args.previous_pid) / 'stat'
        while previous.exists() and previous.read_text().split()[2] != 'Z':
            time.sleep(10)
        prior = json.loads((ROOT / 'regression-runs-r4/status.json').read_text())
        assert prior['status'] == 'failed', 'resume requires terminal original failure'
        state['status'] = 'waiting_for_preparation'; save()
        while True:
            prep = json.loads((ROOT / 'regression/prepared-r2/preparation-status.json').read_text())
            if prep['status'] in ('prepared', 'failed'):
                break
            live = ct(101, "from pathlib import Path\nr=Path('/opt/aimee-large-release-validation/regression');p=Path('/proc')/(r/'prepare-r2.pid').read_text()/'stat';print(p.exists() and p.read_text().split()[2]!='Z')").strip()
            assert live == 'True', 'preparer exited without terminal report'
            time.sleep(15)
        assert prep['status'] == 'prepared', 'memory preparation prerequisite failed'
        inputs = ROOT / 'regression/frozen-inputs.json'
        rows = json.loads(inputs.read_text())
        for profile in args.profiles:
            assert profile == 'gemma26', 'this continuation is Gemma-only'
            state.update(status='waiting_for_initial_probe_' + profile); save()
            first_probe = ROOT / 'signed-lifecycle-r5' / profile / 'fresh1.json'
            while not first_probe.exists():
                lifecycle = json.loads((ROOT / 'signed-lifecycle-r5/status.json').read_text())
                if lifecycle['status'] == 'failed':
                    raise RuntimeError('signed lifecycle failed before initial probe for ' + profile)
                pid = int((ROOT / 'assembly/signed-lifecycle-r5.pid').read_text())
                process = Path('/proc') / str(pid) / 'stat'
                assert process.exists() and process.read_text().split()[2] != 'Z', 'lifecycle coordinator exited before initial probe'
                time.sleep(5)
            assert json.loads(first_probe.read_text())['status'] == 'passed', 'initial installed probe failed'
            state.update(status='waiting_for_gpu_' + profile); save()
            with (ROOT / 'gpu-validation.lock').open('a') as gpu_lock:
                fcntl.flock(gpu_lock, fcntl.LOCK_EX)
                for number in (101, 110):
                    names = subprocess.check_output(['pct', 'exec', str(number), '--', 'podman', 'ps', '--format', '{{.Names}}'], text=True).split()
                    assert all(n == 'aimee-native-release-registry' for n in names), 'test GPUs already owned'
                work = OUT / profile; work.mkdir()
                runroot = Path('/opt/swe-native/larger-regression-resume-r6-20260928') / profile
                records = prep['profiles'][profile]['records']; assert len(records) == 6
                manifest = {'profile': profile, 'input_sha256': __import__('hashlib').sha256(inputs.read_bytes()).hexdigest(),
                            'publications': {r['instance_id']: r for r in records}}
                for filename, data in [('manifest.json', json.dumps(manifest).encode()), ('frozen-inputs.json', inputs.read_bytes()),
                        ('run.py', (ROOT / 'regression/run.py').read_bytes()),
                        ('larger_regression.py', (ROOT / 'regression/larger_regression.py').read_bytes())]:
                    write_ct(113, runroot / filename, data)
                # Validate frozen IDs against the private grader before allocating GPUs.
                ct(113, f"from pathlib import Path\nimport json\nr=Path({str(runroot)!r});rows=json.loads((r/'frozen-inputs.json').read_text());graded={{t['instance_id'] for t in json.loads(Path('/opt/swe-native/selected-grader-only.json').read_text())}};assert all(x['task']['instance_id'] in graded for x in rows)")
                for row in rows:
                    iid = row['task']['instance_id']
                    image = 'docker.io/swebench/sweb.eval.x86_64.' + iid.replace('__', '_1776_').lower() + ':latest'
                    inspect = subprocess.run(['pct', 'exec', '113', '--', 'docker', 'image', 'inspect', image],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if inspect.returncode:
                        with (work / (iid + '-pull.log')).open('w') as log:
                            subprocess.run(['pct', 'exec', '113', '--', 'docker', 'pull', image],
                                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
                client = ROOT / 'clients/signed-lifecycle-r3' / profile
                active = json.loads((client / 'active.json').read_text())
                release = REMOTE / 'clients/signed-lifecycle-r3' / profile / 'releases' / active['current']
                config = {'model': '/release/models', 'catalog': '/fixture/catalog.json',
                    'recipient': 'larger-coding-public-fixture', 'library': '/opt/aimee/libaimee_native.so',
                    'host_memory_budget': 1073741824, 'device_memory_budget': 268435456,
                    'disk_backed': True, 'lossless_transport': True, 'pipeline_transport': True,
                    'gguf_weights': '/release/models/model.gguf', 'gguf_matrix_backend': 'triton' if profile == 'gemma26' else 'cuda',
                    'serve': {'host': '127.0.0.1', 'port': 8170, 'tensor_parallel_size': 2, 'max_model_len': 4096,
                              'max_num_seqs': 2, 'max_num_batched_tokens': 256, 'gpu_memory_utilization': .85}}
                descriptor = json.loads((client / 'releases' / active['current'] / 'runtime/image.json').read_text())
                if descriptor.get('mm_proj'):
                    config['mm_proj'] = '/release/' + descriptor['mm_proj']
                (work / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
                name = 'aimee-larger-coding-resume-r6-' + profile
                cmd = ['podman', 'run', '-d', '--name', name, '--network', 'host', '--ipc', 'host',
                    '--device', '/dev/kfd', '--device', '/dev/dri/renderD128', '--device', '/dev/dri/renderD129',
                    '--memory', '36g', '--memory-swap', '36g', '-v', str(release) + ':/release:ro',
                    '-v', str(REMOTE / 'regression/prepared-r2' / profile) + ':/fixture:ro',
                    '-v', str(REMOTE / OUT.name / profile) + ':/evidence:ro', IMAGE, '--config', '/evidence/config.json']
                (work / 'command.json').write_text(json.dumps(cmd, indent=2) + '\n')
                state.update(status='starting_' + profile); save()
                subprocess.run(['pct', 'exec', '101', '--', *cmd], check=True, stdout=(work / 'container.txt').open('w'))
                try:
                    # Bound readiness without restarting a still-compiling model.
                    deadline = time.monotonic() + 1200
                    while True:
                        healthy = ct(101, "import urllib.request\ntry:\n r=urllib.request.urlopen('http://127.0.0.1:8170/health',timeout=3);print(r.status==200)\nexcept Exception:print(False)").strip()
                        if healthy == 'True':
                            break
                        alive = subprocess.check_output(['pct', 'exec', '101', '--', 'podman', 'inspect', '-f', '{{.State.Running}}', name], text=True).strip()
                        assert alive == 'true', 'coding server exited before ready'
                        if time.monotonic() > deadline:
                            raise TimeoutError('coding server readiness')
                        time.sleep(5)
                    state.update(status='testing_' + profile); save()
                    env = ['env', 'SWE_RUN_ROOT=' + str(runroot), 'SWE_CONTEXT_TOKENS=4096', 'SWE_OUTPUT_TOKENS=1536',
                           'SWE_STEPS=40', 'SWE_SECONDS=600', 'SWE_GENERATION_TIMEOUT_SECONDS=1200', 'SWE_GRADE_TIMEOUT=300', 'SWE_GRADE_TIMEOUT_OVERRIDES=' + json.dumps({'psf__requests-2193':3600}), 'SWE_MODEL_LABEL=' + profile]
                    with (work / 'runner.log').open('w') as log:
                        subprocess.run(['pct', 'exec', '113', '--', *env, '/opt/swe-venv/bin/python', str(runroot / 'larger_regression.py')],
                                       stdout=log, stderr=subprocess.STDOUT, check=True)
                    report = json.loads(ct(113, f"from pathlib import Path\nprint(Path({str(runroot / 'status.json')!r}).read_text())"))
                    assert report['status'] == 'complete'
                    (work / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
                    state['profiles'][profile] = {'status': 'complete', 'arms': report['arms'], 'pairs': report['pairs']}; save()
                finally:
                    subprocess.run(['pct', 'exec', '101', '--', 'podman', 'stop', '-t', '30', name], stdout=subprocess.DEVNULL)
                    with (work / 'server.log').open('w') as log:
                        subprocess.run(['pct', 'exec', '101', '--', 'podman', 'logs', name], stdout=log, stderr=subprocess.STDOUT)
        state['status'] = 'complete'
    except BaseException as error:
        state.update(status='failed', error=repr(error)); raise
    finally:
        save()


if __name__ == '__main__':
    main()
