"""Host coordinator: normal signed larger installation using model-aware authority.

Dedicated enrolled client roots; no authority mutation. The normal channels are
local controlled infrastructure. Each phase probes the installed runtime.
"""
from pathlib import Path
import fcntl
import hashlib
import json
import os
import subprocess
import time

ROOT = Path('/var/lib/aimee-large-release-validation')
REMOTE = Path('/opt/aimee-large-release-validation')
RUN = 'normal-lifecycle-20260928'
OUT = ROOT / RUN
LAUNCHER = str(REMOTE / 'model-selection-normal-launcher/aimee-native')


def ct(number, code):
    return subprocess.check_output(['pct', 'exec', str(number), '--', 'python3', '-c', code], text=True).strip()


def command(number, args, log):
    with log.open('x') as stream:
        subprocess.run(['pct', 'exec', str(number), '--'] + args,
                       stdout=stream, stderr=subprocess.STDOUT, check=True)


def main():
    OUT.mkdir(exist_ok=False); os.chown(OUT, 100000, 100000)
    report = {'status': 'waiting_for_packages', 'scope': __doc__, 'phases': []}
    def save():
        (OUT / 'status.json').write_text(json.dumps(report, indent=2) + '\n')
    save()
    while True:
        build = json.loads((ROOT / 'normal-staging-20260928/build.json').read_text())
        if build['status'] == 'staged':
            break
        assert build['status'] != 'failed', build
        alive = ct(101, "from pathlib import Path; r=Path('/opt/aimee-large-release-validation/normal-staging-20260928'); p=Path('/proc')/(r/'build.pid').read_text()/'stat'; print(p.exists() and p.read_text().split()[2]!='Z')")
        assert alive == 'True', 'builder exited before staging completed'
        time.sleep(10)
    with (ROOT / 'gpu-validation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        binding = ct(100, "from pathlib import Path;import hashlib;print(hashlib.sha256(Path('/etc/aimee-native/bindings.json').read_bytes()).hexdigest())")
        for number in (101, 110):
            names = subprocess.check_output(['pct','exec',str(number),'--','podman','ps','--format','{{.Names}}'],text=True).split()
            assert all(n == 'aimee-native-release-registry' for n in names), names
        subprocess.run(['pct','exec','101','--','systemctl','stop','aimee-native-compiler.service'],check=True)
        try:
            for profile in ('gemma26', 'qwen27'):
                work = OUT / profile; work.mkdir(); os.chown(work,100000,100000)
                client = REMOTE / 'clients' / RUN / profile
                ct(110, f"""from pathlib import Path
import json
root=Path({str(client)!r});root.mkdir(parents=True,exist_ok=False);root.chmod(0o700)
config=json.loads(Path('/opt/aimee-client/native-signed-6-validation/config.json').read_text());config['memory_root']=str(root/'memory')
(root/'memory').mkdir(mode=0o700);(root/'config.json').write_text(json.dumps(config));(root/'config.json').chmod(0o600)
""")
                model = json.loads((ROOT/'normal-packages-20260928'/profile/'1/manifest.json').read_text())['model']
                def active():
                    return json.loads((ROOT/'clients'/RUN/profile/'active.json').read_text())
                def install(sequence):
                    report.update(status=f'installing_{profile}_{sequence}'); save()
                    target = REMOTE/'normal-packages-20260928'/profile/str(sequence)
                    ct(101, f"""from pathlib import Path
root=Path('/opt/aimee-native-release/www/linux-x86_64');link=root/{model!r};stage=link.with_name(link.name+'.normal-next')
assert not stage.exists()
if link.exists():assert link.is_symlink() and 'normal-packages-20260928' in str(link.resolve()),'unrelated channel'
stage.symlink_to({str(target)!r},target_is_directory=True);stage.replace(link)
""")
                    command(110,[LAUNCHER,'--root',str(client),'install',model],work/f'install{sequence}.log')
                    # Preserve room for the next real HTTP install. Verify both
                    # immutable copies against the signed digest before linking.
                    result=ct(110,f"""from pathlib import Path
import hashlib,json,os
root=Path({str(client)!r});state=json.loads((root/'active.json').read_text());release=root/'releases'/state['current'];package=Path({str(target)!r})
a=json.loads((release/'manifest.json').read_text());b=json.loads((package/'manifest.json').read_text());assert a==b
linked=[]
for item in a['artifacts']:
 if not item['path'].endswith('.gguf'):continue
 dst=release/item['path'];src=package/item['path']
 for file in (dst,src):
  with file.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==item['sha256']
 link=dst.with_suffix('.verified-link');os.link(src,link);link.replace(dst);linked.append(item['path'])
print(json.dumps({{'linked':linked,'active':state}}))
""")
                    (work/f'install{sequence}-state.json').write_text(result+'\n')
                def probe(phase):
                    report.update(status=f'probing_{profile}_{phase}'); save()
                    command(110,['python3',str(REMOTE/'assembly/live_client_runtime_locked_impl.py'),
                        '--launcher',LAUNCHER,'--root',str(client),'--query',
                        'What are the native release verification vault code, project, and drink?',
                        '--expect','28461','--expect','Juniper','--expect','hibiscus',
                        '--repeat','2','--startup-timeout','1200','--port','8177',
                        '--output',str(REMOTE/RUN/profile/(phase+'.json'))],work/(phase+'-operator.log'))
                    result=json.loads((work/(phase+'.json')).read_text());assert result['status']=='passed'
                    report['phases'].append({'profile':profile,'phase':phase,'active':active(),'queries':len(result['answers'])});save()
                install(1); first=active();assert first['high_water_sequence']==1 and first['previous'] is None
                probe('fresh1')
                install(2); second=active();assert second['high_water_sequence']==2 and second['previous']==first['current']
                probe('updated2')
                command(110,[LAUNCHER,'--root',str(client),'rollback'],work/'rollback.log')
                assert active()['current']==first['current'] and active()['high_water_sequence']==2
                probe('rollback1')
                command(110,[LAUNCHER,'--root',str(client),'rollback'],work/'restore.log')
                assert active()['current']==second['current'] and active()['high_water_sequence']==2
                probe('restored2')
            report['status']='passed'
        except BaseException as error:
            report.update(status='failed',error=repr(error));raise
        finally:
            unchanged=ct(100,"from pathlib import Path;import hashlib;print(hashlib.sha256(Path('/etc/aimee-native/bindings.json').read_bytes()).hexdigest())")==binding
            report['binding_unchanged']=unchanged
            subprocess.run(['pct','exec','101','--','systemctl','start','aimee-native-compiler.service'],check=True)
            report['compiler_restored']=True;save()
            assert unchanged, 'authority changed during lifecycle validation'


if __name__ == '__main__':
    main()
