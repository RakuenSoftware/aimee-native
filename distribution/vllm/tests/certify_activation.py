"""Run the existing cold/warm activation probe in the exact release image.

Run only after the study server has stopped. This measures rank-zero transfer
and tensor wrapping with byte equality checks, not model answer latency. A
passing report means measurements and fidelity checks completed; it does not
assert that a microsecond cold-activation target was met.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--root', default='/opt/aimee-memory-lab')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root, output = pathlib.Path(args.root), pathlib.Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    probe = pathlib.Path(__file__).with_name('activation_timing.py').resolve()
    image = json.loads(subprocess.check_output(['podman', 'image', 'inspect', args.image]))[0]['Id']
    report = {'status': 'running', 'image': image, 'probe_sha256': hashlib.sha256(probe.read_bytes()).hexdigest(),
              'scope': __doc__, 'cases': {}}
    try:
        for label, fixture, publication in [('three', 'vllm-native-fixture-r1', 'alpha'), ('wide', 'wide-native-r2', 'wide')]:
            catalog = root / fixture / 'catalog.json'
            bank = pathlib.Path(json.loads(catalog.read_text())['publications'][publication]['root'])
            result = output / (label + '.json')
            command = ['podman', 'run', '--rm', '--name', 'aimee-activation-certification', '--network', 'none',
                       '--device', '/dev/kfd', '--device', '/dev/dri/renderD128', '--device', '/dev/dri/renderD129',
                       '--memory', '8g', '--memory-swap', '8g', '--entrypoint', 'python3']
            for path, mode in [(catalog.parent, 'ro'), (bank, 'ro'), (probe, 'ro'), (output, 'rw')]:
                command += ['-v', f'{path}:{path}:{mode}']
            command += [image, str(probe), '--catalog', str(catalog), '--publication', publication,
                        '--output', str(result), '--packed', '--native-profile', '--repetitions', '100', '--cold-repetitions', '20']
            with (output / (label + '.log')).open('w') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            data = json.loads(result.read_text())
            if data['status'] != 'passed' or data.get('exact_segments_verified', 0) <= 0:
                raise ValueError('activation or tensor byte equality failed: ' + label)
            if any(data['summary'][name]['n'] != count for name, count in
                   [('os_page_cache_cold', 20), ('os_page_cache_warm', 100), ('already_device_resident', 100)]):
                raise ValueError('incomplete activation sample: ' + label)
            report['cases'][label] = {'summary': data['summary'], 'result_sha256': hashlib.sha256(result.read_bytes()).hexdigest(),
                                     'exact_segments_verified': data['exact_segments_verified'], 'source_bytes': data['source_bytes']}
    except BaseException as error:
        report.update(status='failed', error=repr(error))
        raise
    else:
        report['status'] = 'passed'
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
