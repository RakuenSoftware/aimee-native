"""Designated-host signed lifecycle; uses a separate validation channel."""
import argparse
import json
import pathlib
import subprocess
import time

ROOT=pathlib.Path('/root/aimee-signed-lifecycle-20260928')
ROOT.mkdir(exist_ok=True)
CLIENT='/opt/aimee-client/native-signed-6-validation'
STAGING='/opt/aimee-client/bin/aimee-native-staging-6'
NORMAL='/opt/aimee-client/bin/aimee-native-normal-6'
OUTPUT='/opt/aimee-client/signed-lifecycle-20260928'


def save(**data):
    (ROOT/'status.json').write_text(json.dumps(dict(data,updated=time.time()),indent=2)+chr(10))


def ct(number,code):
    return subprocess.check_output(['pct','exec',str(number),'--','python3','-'],input=code,text=True)


def command(args,log):
    with (ROOT/log).open('w') as output:
        subprocess.run(args,stdout=output,stderr=subprocess.STDOUT,check=True)


def active():
    return json.loads(ct(110,'import pathlib;print(pathlib.Path('+repr(CLIENT+'/active.json')+').read_text())'))


def probe(label):
    save(status='probing_'+label)
    command(['pct','exec','110','--','python3',OUTPUT+'/live_client_runtime.py',
        '--launcher',NORMAL,'--root',CLIENT,'--query','What are the native release verification vault code, project, and drink?',
        '--expect','28461','--expect','Juniper','--expect','hibiscus','--repeat','2',
        '--port','8152','--output',OUTPUT+'/'+label+'.json'],label+'.log')


def restore(before, upgraded, rolled):
    # The sequence high-water guard correctly rejects a network reinstall at
    # sequence 6. The explicit local rollback command toggles the two already
    # installed releases, including restoring the newer one.
    command(['pct','exec','110','--',NORMAL,'--root',CLIENT,'rollback'],'restore6-local.log')
    restored=active();assert restored['current']==upgraded['current'] and restored['high_water_sequence']==6
    probe('restored6')
    save(status='passed',fresh=before,updated=upgraded,rolled_back=rolled,restored=restored,
        scope='Normal-edition signed installer via separate validation URL; production-URL normal launcher used for all GPU probes. Restore uses explicit local rollback toggle; sequence high-water remains 6. Published release channel unchanged. Learning gates are separate.')


def main(resume_after_fresh5=False, resume_after_rollback=False):
    predecessor=pathlib.Path('/root/aimee-retained-success-20260928')
    save(status='waiting_for_retained_success_checks')
    while True:
        d=json.loads((predecessor/'status.json').read_text());pid=int((predecessor/'pid').read_text())
        stat=pathlib.Path('/proc',str(pid),'stat');live=stat.exists() and stat.read_text().split()[2]!='Z'
        if d['status']=='failed':raise RuntimeError('retained-success infrastructure needs intervention')
        if not live:
            if d['status']!='complete':raise RuntimeError('predecessor exited incomplete')
            break
        time.sleep(15)
    if resume_after_rollback:
        checks=[]
        for label in ['fresh5','updated6','rolled_back5']:
            checked=json.loads(ct(110,'import pathlib;print(pathlib.Path('+repr(OUTPUT+'/'+label+'.json')+').read_text())'))
            assert checked['status']=='passed' and len(checked['answers'])==2 and all(row['passed'] for row in checked['answers'])
            checks.append(checked['active'])
        before,upgraded,rolled=checks
        assert active()==rolled and rolled['current']==before['current']
        assert rolled['previous']==upgraded['current'] and rolled['high_water_sequence']==6
        restore(before,upgraded,rolled)
        return
    installation=json.loads(ct(110,'import pathlib;print(pathlib.Path('+repr(OUTPUT+'/install-state.json')+').read_text())'))
    if installation['status']!='installed_sequence5':raise RuntimeError('fresh signed install is not ready')
    before=active();assert before['high_water_sequence']==5 and before['previous'] is None
    if resume_after_fresh5:
        checked=json.loads(ct(110,'import pathlib;print(pathlib.Path('+repr(OUTPUT+'/fresh5.json')+').read_text())'))
        assert checked['status']=='passed' and checked['active']==before
        assert len(checked['answers'])==2 and all(row['passed'] for row in checked['answers'])
    else:
        probe('fresh5')
    # Only the validation URL changes; the published channel remains sequence 5.
    ct(101,r'''import pathlib,json
r=pathlib.Path('/opt/aimee-native-release/candidate6-assembly-20260928')
d=json.loads((r/'validation-channel.json').read_text());link=pathlib.Path(d['link'])
target=pathlib.Path(d['candidate_target']);manifest=json.loads((target/'manifest.json').read_text());assert manifest['sequence']==6
assert str(link.resolve()) in (d['initial_target'],d['candidate_target'])
# Packager creates its temporary output root privately. This directory contains
# only signed distribution artifacts; let the origin worker traverse it.
target.chmod(0o755)
for artifact in manifest['artifacts']:
 path=target/artifact['path'];assert path.resolve().is_relative_to(target.resolve())
 path.chmod(0o755 if artifact['executable'] else 0o644)
if str(link.resolve())!=d['candidate_target']:
 stage=link.with_name(link.name+'.next');stage.symlink_to(target,target_is_directory=True);stage.replace(link)
''')
    save(status='installing_signed_sequence6')
    command(['pct','exec','110','--',STAGING,'--root',CLIENT,'install','gemma4-12b-q8-native'],'install6.log')
    upgraded=active();assert upgraded['high_water_sequence']==6 and upgraded['previous']==before['current']
    assert upgraded['current']=='3577d8041f929ae5376160c276d8136f0ddc4a80247d33f27325f4899f1a8636'
    probe('updated6')
    command(['pct','exec','110','--',NORMAL,'--root',CLIENT,'rollback'],'rollback.log')
    rolled=active();assert rolled['current']==before['current'] and rolled['high_water_sequence']==6
    probe('rolled_back5')
    restore(before,upgraded,rolled)


if __name__=='__main__':
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group();group.add_argument('--resume-after-fresh5',action='store_true');group.add_argument('--resume-after-rollback',action='store_true');args=parser.parse_args()
    try:main(args.resume_after_fresh5,args.resume_after_rollback)
    except BaseException as error:
        save(status='failed',error=repr(error));raise
