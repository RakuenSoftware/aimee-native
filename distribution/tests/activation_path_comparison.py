"""Isolate overlay and upload scheduling costs on one frozen native bank.

Uses the unchanged compiled consumer and byte-fidelity probe. This diagnostic
is not a model-quality benchmark or a release-wide latency certification.
Run in CT101; the direct arena must reside on the same Optane filesystem as
Podman's graphroot. Never use a RAM-backed directory for the direct arm.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--arena', type=Path, required=True)
    p.add_argument('--image', required=True)
    a = p.parse_args()
    a.output.mkdir(exist_ok=False)
    a.arena.mkdir(exist_ok=False)
    probe = a.root / 'activation-validation-code/activation_timing.py'
    previous = json.loads((a.root / 'activation-validation-r1/report.json').read_text())
    case = max((c for c in previous['cases'] if c['model'] == 'gemma26'), key=lambda c: c['source_bytes'])
    fixture = a.root / 'regression/prepared-r2/gemma26'
    report = dict(status='waiting', scope=__doc__, case=case, results=[],
                  probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest())
    def save():
        (a.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    save()
    try:
        with (a.root / 'gpu-validation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            active = json.loads(subprocess.check_output(['podman', 'ps', '--format', 'json']))
            if any(c.get('Names') != ['aimee-native-release-registry'] for c in active):
                raise RuntimeError('unexpected container; refusing competing GPU use')
            report['image'] = json.loads(subprocess.check_output(['podman', 'image', 'inspect', a.image]))[0]['Id']
            report['arena_mount'] = subprocess.check_output(['findmnt', '-T', str(a.arena), '-J'], text=True)
            report['status'] = 'running'
            save()
            # Reverse order on the second pass to expose simple order drift.
            arms = [('overlay', True), ('direct', False), ('direct', True), ('overlay', False)]
            for repeat, order in enumerate((arms, list(reversed(arms)))):
                for storage, pipeline in order:
                    name = f'{repeat}-{storage}-{"pipeline" if pipeline else "bulk"}'
                    cmd = ['podman', 'run', '--rm', '--name', 'aimee-activation-path-comparison', '--network', 'none',
                           '--device', '/dev/kfd', '--device', '/dev/dri/renderD128', '--device', '/dev/dri/renderD129',
                           '--memory', '8g', '--memory-swap', '8g', '--entrypoint', 'python3',
                           '-v', f'{fixture}:/fixture:ro', '-v', f'{probe}:/probe.py:ro',
                           '-v', f'{a.output}:/output:rw']
                    if storage == 'direct':
                        cmd += ['-v', f'{a.arena}:/arena:rw', '-e', 'TMPDIR=/arena']
                    cmd += [report['image'], '/probe.py', '--catalog', '/fixture/catalog.json',
                            '--publication', case['publication'], '--output', f'/output/{name}.json',
                            '--packed', '--native-profile', '--repetitions', '100', '--cold-repetitions', '10']
                    if not pipeline:
                        cmd += ['--parallel-only']
                    with (a.output / f'{name}.log').open('x') as log:
                        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
                    result = a.output / f'{name}.json'
                    data = json.loads(result.read_text())
                    if data['status'] != 'passed' or data['exact_segments_verified'] != case['exact_segments_verified']:
                        raise RuntimeError('tensor fidelity failed')
                    if data['source_bytes'] != case['source_bytes']:
                        raise RuntimeError('source extent changed')
                    report['results'].append(dict(name=name, summary=data['summary'],
                                                  sha256=hashlib.sha256(result.read_bytes()).hexdigest()))
                    save()
            report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=repr(error))
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
