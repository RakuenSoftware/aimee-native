#!/usr/bin/env python3
"""Exercise signed clean install, upgrade, rollback and restoration in one venv.

The compatible GPU runtime must already be installed. Every step verifies the
signature, version and complete asset inventory before pip can modify the venv.
Separate installed-models.py processes exercise all five real Rust bindings.
"""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('python', 'baseline', 'release', 'public-key', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--baseline-version', required=True)
    p.add_argument('--release-version', required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    report = {'passed': False, 'steps': []}
    try:
        for name, bundle, version in (
            ('clean-install', a.baseline, a.baseline_version),
            ('upgrade', a.release, a.release_version),
            ('rollback', a.baseline, a.baseline_version),
            ('restore', a.release, a.release_version),
        ):
            with (a.output / (name + '.log')).open('w') as log:
                subprocess.run([str(a.python), str(root / 'distribution/release/release-bundle.py'),
                    'install', '--bundle', str(bundle), '--public-key', str(a.public_key),
                    '--expected-version', version, '--python', str(a.python)],
                    stdout=log, stderr=subprocess.STDOUT, check=True)
                result = a.output / (name + '.json')
                subprocess.run([str(a.python), str(root / 'scripts/validation/installed-models.py'),
                    '--expected-version', version, '--output', str(result)],
                    stdout=log, stderr=subprocess.STDOUT, check=True)
            checks = json.loads(result.read_text())
            report['steps'].append({'name': name, 'version': version, 'passed': checks['passed'],
                                    'checks': len(checks['checks'])})
            print(name + ': passed', flush=True)
        report['passed'] = True
    finally:
        (a.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
