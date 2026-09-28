"""Proxmox-host coordinator for dedicated-canary, signed larger-model checks.

Uses a separate lab-only release channel. Restores the canary binding on exit.
No account credentials or signing keys are copied into evidence.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/var/lib/aimee-large-release-validation')
REMOTE = Path('/opt/aimee-large-release-validation')
EVIDENCE = ROOT / 'signed-lifecycle-r3'


def ct(number, code):
    return subprocess.check_output(['pct', 'exec', str(number), '--', 'python3', '-c', code], text=True)


def command(number, args, log):
    with log.open('w') as output:
        subprocess.run(['pct', 'exec', str(number), '--'] + args, stdout=output, stderr=subprocess.STDOUT, check=True)


def main():
    EVIDENCE.mkdir(mode=0o700, exist_ok=False)
    os.chown(EVIDENCE, 100000, 100000)
    report = {'status': 'waiting_for_packages', 'profiles': [], 'scope': __doc__}
    def save():
        (EVIDENCE / 'status.json').write_text(json.dumps(report, indent=2) + '\n')
    save()
    def ready(profile, sequence):
        path = ROOT / 'packages' / profile / str(sequence)
        while not (path / 'manifest.json').exists():
            live = ct(101, "from pathlib import Path\nr=Path('/opt/aimee-large-release-validation/assembly');pid=(r/'package-build.pid').read_text();p=Path('/proc')/pid/'stat';print(p.exists() and p.read_text().split()[2]!='Z')").strip()
            if live != 'True':
                raise RuntimeError('package builder exited before requested package completed')
            time.sleep(10)
        manifest = json.loads((path / 'manifest.json').read_text())
        assert manifest['sequence'] == sequence and manifest['gates'] == ['lab_only']
        assert (path / 'manifest.sig').stat().st_size == 64
        return path, manifest
    ready('gemma26', 1)
    # The experimental model containers must be stopped before installer tests own GPUs.
    for number in (101, 110):
        names = subprocess.check_output(['pct', 'exec', str(number), '--', 'podman', 'ps', '--format', '{{.Names}}'], text=True)
        assert all(name == 'aimee-native-release-registry' for name in names.split()), 'another container owns test resources'
    ct(101, "from pathlib import Path\nimport shutil\nr=Path('/opt/aimee-large-release-validation/assembly');source=Path('/opt/aimee-memory-lab/vllm-native-build/distribution/launcher/target/release/aimee-native');shutil.copyfile(source,r/'aimee-native-lab');(r/'aimee-native-lab').chmod(0o755)")
    launcher = str(REMOTE / 'assembly/aimee-native-lab')
    # The backup remains private on CT100. The coordinator only sees its hash.
    original_hash = ct(100, "from pathlib import Path\nimport hashlib\np=Path('/etc/aimee-native/bindings.json');b=Path('/root/larger-bindings-backup-20260928-r3.json');assert not b.exists();b.write_bytes(p.read_bytes());b.chmod(0o600);print(hashlib.sha256(p.read_bytes()).hexdigest())").strip()
    expected_hash = original_hash
    try:
        for name in ('gemma26', 'qwen27'):
            first_package, manifest = ready(name, 1)
            defaults = json.loads((first_package / 'runtime/profile.json').read_text())
            model = manifest['model']
            profile = {'profile': name, 'model': model, 'native_model': defaults['native_model']}

            work = EVIDENCE / name; work.mkdir(mode=0o700); os.chown(work, 100000, 100000)
            client = REMOTE / 'clients' / EVIDENCE.name / name
            # Credentials stay in the existing CT110 enrolled account directory.
            ct(110, f"""from pathlib import Path
import json
root=Path({str(client)!r});root.mkdir(parents=True,exist_ok=False);root.chmod(0o700)
config=json.loads(Path('/opt/aimee-client/native-signed-6-validation/config.json').read_text())
config['memory_root']=str(root/'memory')
(root/'config.json').write_text(json.dumps(config));(root/'config.json').chmod(0o600)
""")
            config_hash = profile['native_model'].rsplit('-', 1)[1]
            expected_hash = ct(100, f"""from pathlib import Path
import json,hashlib,os
p=Path('/etc/aimee-native/bindings.json');assert hashlib.sha256(p.read_bytes()).hexdigest()=={expected_hash!r}
original=Path('/root/larger-bindings-backup-20260928-r3.json');d=json.loads(original.read_text());assert len(d['bindings'])==1
b=d['bindings'][0];assert b['preparer']['profile']['recipient']=='native-preview'
b['preparer']['template']='/var/lib/aimee-native/larger-live-preparation-20260928/{name}/preparation.json'
b['preparer']['profile']['model']={profile['native_model']!r};b['preparer']['profile']['model_config_sha256']={config_hash!r}
meta=p.stat();stage=p.with_suffix('.larger.next');stage.write_text(json.dumps(d));stage.chmod(meta.st_mode & 0o777);os.chown(stage,meta.st_uid,meta.st_gid);stage.replace(p)
print(hashlib.sha256(p.read_bytes()).hexdigest())
""").strip()
            def channel(sequence):
                candidate_path, candidate_manifest = ready(name, sequence)
                assert candidate_manifest['model'] == model
                candidate = {'root': str(REMOTE / 'packages' / name / str(sequence))}
                ct(101, f"""from pathlib import Path
root=Path('/opt/aimee-native-release/www/validation/larger/linux-x86_64');root.mkdir(parents=True,exist_ok=True)
link=root/{model!r};stage=link.with_name(link.name+'.next');assert not stage.exists()
stage.symlink_to({candidate['root']!r},target_is_directory=True);stage.replace(link)
""")
            def active():
                return json.loads((ROOT / 'clients' / EVIDENCE.name / name / 'active.json').read_text())
            def probe(label):
                report.update(status='probing_' + name + '_' + label); save()
                command(110, ['python3', str(REMOTE / 'assembly/live_client_runtime.py'),
                    '--launcher', launcher, '--root', str(client), '--query',
                    'What are the native release verification vault code, project, and drink?',
                    '--expect', '28461', '--expect', 'Juniper', '--expect', 'hibiscus',
                    '--repeat', '2', '--startup-timeout', '1200', '--port', '8177',
                    '--output', str(REMOTE / EVIDENCE.name / name / (label + '.json'))], work / (label + '-operator.log'))
            channel(1)
            report.update(status='installing_' + name + '_sequence1'); save()
            command(110, [launcher, '--root', str(client), 'install', model], work / 'install1.log')
            first = active(); assert first['high_water_sequence'] == 1 and first['previous'] is None
            probe('fresh1')
            channel(2)
            report.update(status='installing_' + name + '_sequence2'); save()
            command(110, [launcher, '--root', str(client), 'install', model], work / 'install2.log')
            second = active(); assert second['high_water_sequence'] == 2 and second['previous'] == first['current']
            probe('updated2')
            command(110, [launcher, '--root', str(client), 'rollback'], work / 'rollback.log')
            assert active()['current'] == first['current'] and active()['high_water_sequence'] == 2
            probe('rollback1')
            command(110, [launcher, '--root', str(client), 'rollback'], work / 'restore.log')
            assert active()['current'] == second['current'] and active()['high_water_sequence'] == 2
            probe('restored2')
            report['profiles'].append({'profile': name, 'status': 'passed', 'queries': 8,
                                       'first': first, 'second': second}); save()
        report['status'] = 'passed'; save()
    except BaseException as error:
        report.update(status='failed', error=repr(error)); save(); raise
    finally:
        restored = ct(100, f"""from pathlib import Path
import hashlib,os
p=Path('/etc/aimee-native/bindings.json');assert hashlib.sha256(p.read_bytes()).hexdigest()=={expected_hash!r},'canary binding changed outside coordinator'
original=Path('/root/larger-bindings-backup-20260928-r3.json');meta=p.stat();stage=p.with_suffix('.larger.restore');stage.write_bytes(original.read_bytes());stage.chmod(meta.st_mode & 0o777);os.chown(stage,meta.st_uid,meta.st_gid);stage.replace(p);print(hashlib.sha256(p.read_bytes()).hexdigest())
""").strip()
        assert restored == original_hash
        report['original_binding_restored'] = True; save()


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        path = EVIDENCE / 'status.json'
        if path.exists():
            data = json.loads(path.read_text()); data.update(status='failed', error=repr(error))
            path.write_text(json.dumps(data, indent=2) + '\n')
        raise
