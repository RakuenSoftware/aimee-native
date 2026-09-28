"""Measure all frozen larger-model procedure banks; never load model weights.

Run in CT101. The shared GPU lock serializes this with serving campaigns.
Results cover rank-zero application, not inference or live authority latency.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', required=True)
    p.add_argument('--probe', required=True)
    p.add_argument('--image', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    root, probe, output = Path(a.root), Path(a.probe), Path(a.output)
    output.mkdir(exist_ok=False)
    report = {'status': 'waiting_for_gpu', 'scope': __doc__, 'cases': []}
    def save():
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    save()
    try:
        with (root / 'gpu-validation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            active = json.loads(subprocess.check_output(['podman', 'ps', '--format', 'json']))
            if any(c.get('Names') != ['aimee-native-release-registry'] for c in active):
                raise RuntimeError('unexpected active container; refusing competing GPU use')
            image = json.loads(subprocess.check_output(['podman', 'image', 'inspect', a.image]))[0]['Id']
            report.update(status='running', image=image, probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest())
            save()
            for model in ('gemma26', 'qwen27'):
                fixture = root / 'regression/prepared-r2' / model
                catalog = fixture / 'catalog.json'
                publications = json.loads(catalog.read_text())['publications']
                for publication, spec in sorted(publications.items()):
                    if spec['root'] != '/fixture/' + publication:
                        raise ValueError('unexpected fixture root')
                    result = output / (model + '-' + publication + '.json')
                    command = ['podman', 'run', '--rm', '--name', 'aimee-larger-activation', '--network', 'none',
                               '--device', '/dev/kfd', '--device', '/dev/dri/renderD128', '--device', '/dev/dri/renderD129',
                               '--memory', '8g', '--memory-swap', '8g', '--entrypoint', 'python3',
                               '-v', f'{fixture}:/fixture:ro', '-v', f'{probe}:/probe.py:ro',
                               '-v', f'{output}:/output:rw', image, '/probe.py',
                               '--catalog', '/fixture/catalog.json', '--publication', publication,
                               '--output', '/output/' + result.name, '--packed', '--native-profile',
                               '--repetitions', '100', '--cold-repetitions', '20']
                    with result.with_suffix('.log').open('w') as log:
                        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
                    data = json.loads(result.read_text())
                    if data['status'] != 'passed' or data.get('exact_segments_verified', 0) <= 0:
                        raise ValueError('activation fidelity failed')
                    for name, count in [('os_page_cache_cold', 20), ('os_page_cache_warm', 100), ('already_device_resident', 100)]:
                        if data['summary'][name]['n'] != count:
                            raise ValueError('incomplete samples')
                    report['cases'].append({'model': model, 'publication': publication,
                                            'catalog_sha256': hashlib.sha256(catalog.read_bytes()).hexdigest(),
                                            'result_sha256': hashlib.sha256(result.read_bytes()).hexdigest(),
                                            'summary': data['summary'], 'source_bytes': data['source_bytes'],
                                            'exact_segments_verified': data['exact_segments_verified']})
                    save()
            report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=repr(error))
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
