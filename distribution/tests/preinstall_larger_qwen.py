"""Overlap Qwen's CPU-only signed installation with Gemma GPU validation.

Uses the same installer and client root as the lifecycle coordinator. The
installer's update lock serializes any later overlapping install invocation.
No account binding, credential, model-serving process or release gate changes.
"""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path('/var/lib/aimee-large-release-validation')
REMOTE = Path('/opt/aimee-large-release-validation')


def main():
    out = ROOT / 'qwen-preinstall'; out.mkdir(exist_ok=False)
    report = {'status': 'running', 'scope': __doc__}
    def save():
        (out / 'status.json').write_text(json.dumps(report, indent=2) + '\n')
    save()
    try:
        package = ROOT / 'packages/qwen27/1'
        raw = (package / 'manifest.json').read_bytes(); manifest = json.loads(raw)
        model = 'lab-qwen3.8-27b-q8-native'
        assert manifest['model'] == model and manifest['sequence'] == 1 and manifest['gates'] == ['lab_only']
        assert (package / 'manifest.sig').stat().st_size == 64
        report['manifest_sha256'] = hashlib.sha256(raw).hexdigest(); save()
        code = f"from pathlib import Path\nr=Path('/opt/aimee-native-release/www/validation/larger/linux-x86_64');p=r/{model!r};assert not p.exists();p.symlink_to('/opt/aimee-large-release-validation/packages/qwen27/1',target_is_directory=True)"
        subprocess.run(['pct', 'exec', '101', '--', 'python3', '-c', code], check=True)
        client = REMOTE / 'clients/signed-lifecycle-r3/qwen27'
        code = f"from pathlib import Path\np=Path({str(client)!r});p.mkdir(mode=0o700,parents=True,exist_ok=False)"
        subprocess.run(['pct', 'exec', '110', '--', 'python3', '-c', code], check=True)
        with (out / 'install.log').open('w') as log:
            subprocess.run(['pct', 'exec', '110', '--', str(REMOTE / 'assembly/aimee-native-lab'),
                '--root', str(client), 'install', model], stdout=log, stderr=subprocess.STDOUT, check=True)
        active = json.loads((ROOT / 'clients/signed-lifecycle-r3/qwen27/active.json').read_text())
        assert active['current'] == report['manifest_sha256'] and active['high_water_sequence'] == 1 and active['previous'] is None
        report.update(status='installed', active=active)
    except BaseException as error:
        report.update(status='failed', error=repr(error)); raise
    finally:
        save()


if __name__ == '__main__':
    main()
