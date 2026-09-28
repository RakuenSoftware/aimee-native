"""Stage exact tested larger artifacts for normal-launcher lifecycle validation.

Run inside CT101 after reviewed component reports have been installed. This does
not publish channels or approve external redistribution. Keys remain local.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import shutil

ROOT = Path('/opt/aimee-large-release-validation')
INPUT = ROOT / 'normal-staging-20260928'


def main():
    spec = importlib.util.spec_from_file_location('release_package', ROOT / 'assembly/package.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = {'status': 'building', 'scope': __doc__, 'packages': []}
    def save():
        (INPUT / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    save()
    try:
        for profile in ('gemma26', 'qwen27'):
            plan = json.loads((INPUT / profile / 'plan.json').read_text())
            original = json.loads((ROOT / 'packages' / profile / '2/manifest.json').read_text())
            expected = {a['path']: a for a in original['artifacts']}
            for sequence in (1, 2):
                report.update(current_profile=profile, current_sequence=sequence)
                save()
                size = sum(a['bytes'] for a in original['artifacts'])
                assert shutil.disk_usage(ROOT).free > size + 8 * 1024**3, 'insufficient staging space'
                plan['manifest'].update(sequence=sequence, version=f'0.1.0-private-preview.{sequence}')
                target = ROOT / 'normal-packages-20260928' / profile / str(sequence)
                manifest = module.package(plan, target, '/opt/aimee-native-release/private/release.key')
                assert manifest['artifacts'] == original['artifacts']
                # Only immutable, already signed validation weights are linked.
                # The assembler just independently hashed the copied bytes.
                for a in manifest['artifacts']:
                    if not a['path'].endswith('.gguf'):
                        continue
                    source = Path(plan['files'][a['path']])
                    assert expected[a['path']] == a and source.stat().st_size == a['bytes']
                    output = target / a['path']
                    link = output.with_suffix('.verified-link')
                    os.link(source, link)
                    link.replace(output)
                for path in [target] + list(target.rglob('*')):
                    path.chmod(0o755 if path.is_dir() or path.name == 'aimee-vllm' else 0o644)
                report['packages'].append({'profile': profile, 'sequence': sequence,
                    'model': manifest['model'], 'root': str(target),
                    'manifest_sha256': hashlib.sha256((target / 'manifest.json').read_bytes()).hexdigest(),
                    'artifact_set_sha256': module.artifact_set_digest(manifest['artifacts'])})
                save()
        report['status'] = 'staged'
    except BaseException as error:
        report.update(status='failed', error=repr(error))
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
