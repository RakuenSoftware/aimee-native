"""New research publication, preserving yesterday's source and result artifacts.
Fixture approvals only; this does not issue production user permissions.
"""
import datetime, importlib.util, json, os, subprocess, time
from pathlib import Path
b=Path('/opt/aimee-qwen-rust'); old=b/'kb-followup-20260920'; root=b/'kb-cue-fix-20260921'
root.mkdir(mode=0o750,exist_ok=True); os.chown(root,0,989)
(root/'private').mkdir(mode=0o700,exist_ok=True)
(root/'traces').mkdir(mode=0o700,exist_ok=True);os.chown(root/'traces',997,989)
spec=importlib.util.spec_from_file_location('cues',b/'cues-v2.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
now=datetime.datetime.now(datetime.timezone.utc)
summary={}
def issue(plan,name):
    private=root/'private'/name;private.mkdir(mode=0o700,exist_ok=True)
    plan['authorization']['id']='canonical-cues-20260921-'+name
    plan['authorization']['valid_until']=(now+datetime.timedelta(hours=8)).isoformat()
    (private/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,separators=(',',':')))
    subprocess.run([str(b/'aimee-issue-fixture'),'--input',str(private/'plan.json'),'--key',str(private/'key'),
        '--public-key',str(private/'public'),'--output',str(private/'grant')],check=True,stdout=subprocess.DEVNULL)
    return private
plan=json.loads((old/'private/local/numeric-plan.json').read_text())
original_count=len(plan['authorization']['reference_cues'])
new_cues=c.compile_cues(plan['records'],'test')
plan['authorization']['reference_cues']=new_cues
(root/'cues.json').write_text(json.dumps(new_cues,ensure_ascii=False,separators=(',',':')))
private=issue(plan,'local');del plan
start=time.perf_counter()
result=subprocess.check_output([str(b/'aimee-memory-image-next'),'sync-published',
    '--root',str(b/'kb-scale-20260920/249105/private/source'),'--output-root',str(root/'image'),
    '--authorization',str(private/'grant'),'--authority-key',str(private/'public'),
    '--subject','scale','--policy-epoch','test','--reader-gid','989'],text=True)
summary.update(original_cues=original_count,new_cues=len(new_cues),publication_seconds=time.perf_counter()-start,publication=json.loads(result))
print(json.dumps(summary),flush=True)
plan=json.loads((old/'private/remote/plan.json').read_text());private=issue(plan,'remote')
subprocess.run([str(b/'aimee-memory-image-next'),'compile-authorized','--root',str(b/'general-kb-live/private/source'),
    '--output-root',str(private/'image'),'--authorization',str(private/'grant'),'--authority-key',str(private/'public'),
    '--subject','general-kb-research','--policy-epoch','research-1'],check=True,stdout=subprocess.DEVNULL)
(root/'publication.json').write_text(json.dumps(summary,indent=2)+'\n')
script=(b/'start-followup.sh').read_text().replace('kb-followup-20260920',root.name)
# Let systemd remove the research gateway socket on normal exit or its time limit.
script=script.replace('--unit=aimee-rust-gateway', '--unit=aimee-rust-gateway --property=RuntimeDirectory=aimee-rust-native --property=RuntimeDirectoryMode=0750')
(b/'start-cue-fix.sh').write_text(script)
