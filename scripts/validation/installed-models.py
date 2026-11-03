#!/usr/bin/env python3
"""CPU checks for five co-installed model wheels and their real Rust ABIs."""
import argparse
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from types import SimpleNamespace

MODELS = ('gemma4-12b', 'gemma4-26b', 'qwen3-8-27b', 'gemma4-e2b', 'gemma4-e4b')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    configs = root / 'distribution/vllm/tests/model_configs'
    report = {'scope': 'Installed CPU ABI/configuration checks; no GPU/model execution', 'checks': []}

    def check(name, condition):
        report['checks'].append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise RuntimeError(name)

    try:
        check('one matching shared runtime', importlib.metadata.version('aimee-native-runtime') == args.expected_version)
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            for model in MODELS:
                package = 'aimee_' + model.replace('-', '_')
                distribution = importlib.metadata.distribution(package)
                check(model + ' installed version', distribution.version == args.expected_version)
                license_name = distribution.metadata.get('License-Expression') or distribution.metadata.get('License')
                check(model + ' AGPL metadata', license_name == 'AGPL-3.0-only')
                license_file = next(p for p in distribution.files if str(p).endswith('/licenses/LICENSE'))
                check(model + ' exact license bytes', distribution.locate_file(license_file).read_bytes() == (root / 'LICENSE').read_bytes())
                module = importlib.import_module(package + '.model_adapter')
                home = temporary / model
                home.mkdir()
                (home / 'config.json').write_bytes((configs / (model + '.json')).read_bytes())
                adapter = module.ModelAdapter({'adapter': model, 'model': str(home)})
                check(model + ' real Rust binding', adapter.description['adapter'] == model)
                for other in MODELS:
                    (home / 'config.json').write_bytes((configs / (other + '.json')).read_bytes())
                    if other == model:
                        continue
                    try:
                        module.ModelAdapter({'adapter': model, 'model': str(home)})
                    except RuntimeError:
                        rejected = True
                    else:
                        rejected = False
                    check(model + ' refuses ' + other + ' geometry', rejected)
                import torch
                original = torch.tensor([0, 1, 20, 0])
                metadata = SimpleNamespace(aimee_ids=['native', 'text'], query_start_loc=torch.tensor([0, 2, 3]))
                requests = {'native': SimpleNamespace(store=SimpleNamespace(metadata={'positions': 82})),
                            'text': SimpleNamespace(store=None)}
                _, positioned = adapter.positioned_arguments((), {'positions': original}, requests, metadata)
                check(model + ' CPU positions and padding', positioned['positions'].tolist() == [82, 83, 20, 0]
                      and original.tolist() == [0, 1, 20, 0])
                command = Path(os.sys.executable).parent / package.replace('_', '-')
                help_result = subprocess.run([str(command), '--help'], capture_output=True, timeout=30)
                check(model + ' installed console entry point', help_result.returncode == 0)
        report['passed'] = True
    except Exception as error:
        report['passed'] = False
        report['error'] = type(error).__name__ + ': ' + str(error)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{sum(row['passed'] for row in report['checks'])}/{len(report['checks'])} installed CPU checks passed")
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
