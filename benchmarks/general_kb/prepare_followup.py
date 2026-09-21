"""Isolated expanded-KB publication. Approvals here are explicitly research fixtures."""
import datetime,json,os,subprocess,time
from pathlib import Path
b=Path('/opt/aimee-qwen-rust');r=b/'kb-followup-20260920';r.mkdir(mode=0o750);os.chown(r,0,989)
(r/'private').mkdir(mode=0o700);(r/'traces').mkdir(mode=0o700);os.chown(r/'traces',997,989)
now=datetime.datetime.now(datetime.timezone.utc)
def issue(plan,stem):
 p=r/'private'/stem;p.mkdir(mode=0o700)
 plan['authorization']['valid_until']=(now+datetime.timedelta(hours=8)).isoformat()
 (p/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,separators=(',',':')))
 subprocess.run([str(b/'aimee-issue-fixture'),'--input',str(p/'plan.json'),'--key',str(p/'key'),'--public-key',str(p/'public'),'--output',str(p/'grant')],check=True,stdout=subprocess.DEVNULL)
 return p
base=b/'kb-scale-20260920/249105'
plan=json.loads((base/'private/plan.json').read_text());plan['authorization']['reference_cues']=json.loads((b/'general-v2-cues.json').read_text())
p=issue(plan,'local');del plan
start=time.perf_counter()
result=subprocess.check_output([str(b/'aimee-memory-image'),'sync-published','--root',str(base/'private/source'),'--output-root',str(r/'image'),'--authorization',str(p/'grant'),'--authority-key',str(p/'public'),'--subject','scale','--policy-epoch','test','--reader-gid','989'],text=True)
print('publication',result.strip(),'seconds',time.perf_counter()-start,flush=True)
old=b/'general-kb-live';plan=json.loads((old/'private/plan.json').read_text());p=issue(plan,'remote')
subprocess.run([str(b/'aimee-memory-image'),'compile-authorized','--root',str(old/'private/source'),'--output-root',str(p/'image'),'--authorization',str(p/'grant'),'--authority-key',str(p/'public'),'--subject','general-kb-research','--policy-epoch','research-1'],check=True)
script=(b/'start-published-kb.sh').read_text().replace('published-kb-live',r.name)
lines=script.splitlines()
for i,line in enumerate(lines):
 if '--unit=aimee-rust-gateway' in line:
  line=line.replace('$live/image','$live/private/remote/image').replace('$live/authorization.json','$live/private/remote/grant').replace('$live/issuer-public.hex','$live/private/remote/public')
 if '--unit=aimee-rust-qwen' in line:
  line=line.replace('--read-authority research-aimee-103','--read-authority test').replace('--property=User=aimee-auth-native','--property=WorkingDirectory="$live" --property=User=aimee-auth-native')
 lines[i]=line
(b/'start-followup.sh').write_text('\n'.join(lines)+'\n')
