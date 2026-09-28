"""Live canary preparation for larger profiles, without changing account bindings.

Run on CT100. Reuses current Aimee grants, gateway and pinned SSH transport.
Copies the existing preparation template into isolated model-specific caches.
"""
import json
import os
from pathlib import Path
import pwd
import subprocess
import time

ROOT = Path('/var/lib/aimee-native/larger-live-preparation-20260928')
PROFILES = [
    ('gemma26', 'ed0c1eb3633de771906e9ba004a44cc5635bcc06ee2062077c3d2e88a50707d3'),
    ('qwen27', '191e0af232104ed8b65258cf3fb2b842e288008baca7633c11b82a1ac7203aab'),
]


def main():
    original = Path('/etc/aimee-native/preparation.json')
    owner = original.stat(); user = pwd.getpwuid(owner.st_uid).pw_name
    ROOT.mkdir(mode=0o700, exist_ok=False); os.chown(ROOT, owner.st_uid, owner.st_gid)
    report = {'status': 'running', 'scope': __doc__, 'profiles': []}
    def save():
        (ROOT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    save()
    try:
        for profile, digest in PROFILES:
            root = ROOT / profile; root.mkdir(mode=0o700); os.chown(root, owner.st_uid, owner.st_gid)
            config = json.loads(original.read_text())
            config.update(model_revision=profile + '-full-fp32-negative-v1-' + digest,
                runtime_profile='vllm-0.30.0-rocm723-' + profile + '-tp2-bf16-q8',
                encoding_revision='bounded-fp32-negative-v1', position_policy='negative',
                cache_root=str(root / 'prepared'),
                query='What are the native release verification vault code, project, and drink?')
            path = root / 'preparation.json'; path.write_text(json.dumps(config, indent=2)); path.chmod(0o600)
            os.chown(path, owner.st_uid, owner.st_gid)
            rows = []
            for attempt in range(2):
                started = time.monotonic()
                result = subprocess.run(['runuser', '-u', user, '--', '/opt/aimee-native/bin/native-prepare', str(path)],
                                        capture_output=True, text=True, timeout=650)
                (root / f'attempt-{attempt}.stderr').write_text(result.stderr)
                if result.returncode:
                    raise RuntimeError(f'{profile} live preparation attempt {attempt} failed')
                data = json.loads(result.stdout)
                assert data['records'], 'empty approved working set'
                rows.append({'reused': data['reused'], 'records': data['records'], 'key': data['key'],
                             'seconds': time.monotonic() - started})
                (root / f'attempt-{attempt}.json').write_text(json.dumps(rows[-1], indent=2) + '\n')
            assert not rows[0]['reused'] and rows[1]['reused'], 'fresh/reuse contract failed'
            assert rows[0]['key'] == rows[1]['key'] and rows[0]['records'] == rows[1]['records']
            report['profiles'].append({'profile': profile, 'status': 'passed',
                'model_revision': config['model_revision'], 'selected_records': len(rows[0]['records']),
                'fresh_seconds': rows[0]['seconds'], 'reuse_seconds': rows[1]['seconds'],
                'unchanged_key_and_records': True})
            save()
        report['status'] = 'passed'; save()
    except BaseException as error:
        report.update(status='failed', error=repr(error)); save(); raise


if __name__ == '__main__':
    main()
