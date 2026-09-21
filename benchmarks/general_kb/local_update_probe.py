"""Local publisher-only update/forget/revocation using the full reference corpus.
The changed value is explicitly synthetic and stays outside the public artifact.
"""
from pathlib import Path
import json,subprocess,datetime,time,hashlib,tempfile
repo=Path(__file__).resolve().parents[2];root=Path(tempfile.mkdtemp(prefix='general-update-',dir=repo/'.local'));reader=repo/'.local/bin/aimee-memory-image';issuer=repo/'.local/bin/aimee-issue-fixture'
base=json.loads((repo/'knowledge/general-v1/records.json').read_text());source=root/'source';private=root/'private';private.mkdir(mode=0o700)
def cli(*args):
 x=subprocess.check_output([str(reader),*map(str,args)],text=True);return json.loads(x) if x else None
def build(name,c):
 p=private/(name+'.json');p.write_text(json.dumps(c));return cli('build','--root',source,'--input',p)['view']
head=build('base',base);cli('publish','--root',source,'--view',head)
allrows=base['records'];by={r['id']:r for r in allrows};old=by['iana.ssh'];removed=by['iana.telnet']
until=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=1)).isoformat()
def grant(head,rows,path,active=True):
 a=dict(version=1,id='local-update-research',subject='general-kb-research',policy_epoch='research-1',source_view=head,active=active,valid_until=until,grants=[],reference_lookups=[dict(namespace=base['namespace'],authority='test',mode='exact-key-v1')])
 p=private/'plan.json';p.write_text(json.dumps(dict(authorization=a,records=rows,reads=[])))
 subprocess.run([str(issuer),'--input',str(p),'--key',str(private/'key'),'--public-key',str(root/'public.hex'),'--output',str(path)],check=True,stdout=subprocess.DEVNULL)
def auth(path):return ['--authorization',path,'--authority-key',root/'public.hex','--subject','general-kb-research','--policy-epoch','research-1']
def start(image,path):return subprocess.Popen([str(reader),'serve','--root',str(image),*map(str,auth(path))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
def read(p,query):p.stdin.write(json.dumps(dict(op='recall',query=query,limit=4,authority='test'))+'\n');p.stdin.flush();return json.loads(p.stdout.readline())
first=root/'grant1.json';grant(head,allrows,first);cli('compile-authorized','--root',source,'--output-root',root/'image1',*auth(first));p=start(root/'image1',first)
initial=read(p,'Which TCP port for IANA service ssh?');assert initial['response']['facts'][0]['content']==old['content']
changed=dict(old,revision='research-override-v2',content='RESEARCH OVERRIDE ONLY: IANA service ssh uses TCP port 10443 in the test deployment.');changed['metadata']=dict(old['metadata'],research_override=True)
delta=dict(namespace=base['namespace'],kind='general',generation=2,previous=head,source='explicit research publisher mutation, not a claim about public IANA registration',coverage=base['coverage'],records=[changed],delete=[{k:removed[k] for k in ['namespace','id','revision']}])
next_head=build('synthetic-delta',delta);cli('publish','--root',source,'--view',next_head,'--expected',head)
newrows=[changed if r['id']==old['id'] else r for r in allrows if r['id']!=removed['id']]
second=root/'grant2.json';grant(next_head,newrows,second);cli('compile-authorized','--root',source,'--output-root',root/'image2',*auth(second))
# New authority decision immediately invalidates an old reader; no stale serving.
first.write_bytes(second.read_bytes());stale=read(p,'Which TCP port for IANA service ssh?');assert 'error' in stale;p.terminate();p.wait()
p=start(root/'image2',second);updated=read(p,'Which TCP port for IANA service ssh?');forgotten=read(p,'Which TCP port for IANA service telnet?')
assert updated['response']['facts'][0]['content']==changed['content'];assert forgotten['outcome']=='uncovered'
grant(next_head,newrows,second,active=False);revoked=read(p,'Which TCP port for IANA service ssh?');assert 'error' in revoked;p.terminate();p.wait()
result=dict(corpus_records=len(allrows),updated_value_seen=True,retired_key_uncovered=True,old_reader_denied=True,revoked_reader_denied=True,source_artifact_unchanged=hashlib.sha256((repo/'knowledge/general-v1/records.json').read_bytes()).hexdigest(),generation_one=head,generation_two=next_head)
(root/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
