"""Private preparation boundary protocol test, not a live authority decision."""
import argparse,json,pathlib,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('--binary',required=True);p.add_argument('--fixture',required=True);a=p.parse_args()
fixture=pathlib.Path(a.fixture);metadata=json.loads((fixture/'config.json').read_text());catalog=json.loads((fixture/'catalog.json').read_text());alpha=catalog['publications']['alpha']
with tempfile.TemporaryDirectory() as tmp:
 root=pathlib.Path(tmp)
 reader=root/'reader';reader.write_text('''#!/usr/bin/env python3
import sys,json,pathlib
root=pathlib.Path(__file__).parent
for line in sys.stdin:
 req=json.loads(line)
 if (root/'denied').exists():out={'error':'synthetic authority denial'}
 elif req['op']=='pin':out={'view':'view1','publication':'approved1'}
 elif req['op']=='recall':out={'view':'view1','outcome':'hit','response':{'facts':[{'id':str(i),'content':'synthetic fact '+str(i)} for i in range(3)]}}
 elif req['op']=='resolve_response':out={'view':'view1','refs':[{'namespace':'test','id':str(i),'revision':'r1'} for i in range(3)]}
 else:out={'error':'unsupported'}
 print(json.dumps(out),flush=True)
''');reader.chmod(0o700)
 compiler=root/'compiler.py';compiler.write_text('''import argparse,json,pathlib,shutil,sys
p=argparse.ArgumentParser();p.add_argument('--source');p.add_argument('--output');p.add_argument('--identity');p.add_argument('--key');a=p.parse_args()
root=pathlib.Path(__file__).parent
request=json.load(sys.stdin)
assert len(request['response']['facts'])==len(request['identity']['records'])==3
with (root/'calls').open('a') as f:f.write('compiled\\n')
shutil.copytree(a.source,a.output)
p=pathlib.Path(a.output)/'index.json';index=json.loads(p.read_text());record=next(iter(index['records'].values()));index['records']={a.key:record};index['model']=a.identity;p.write_text(json.dumps(index))
if (root/'revoke-during-compile').exists():(root/'denied').touch()
''')
 config={'image_reader':str(reader),'memory_image':str(root/'image'),'query':'three facts','limit':3,'authority':'fixture','recipient':'synthetic','model_revision':alpha['model'],'runtime_profile':'gemma-bf16-tp2','encoding_revision':'fixture-v1','position_policy':'negative','cache_root':str(root/'cache'),'compiler':['python3',str(compiler),'--source',alpha['root']],'host_memory_budget':metadata['host_memory_budget']}
 path=root/'config';path.write_text(json.dumps(config))
 def run():return subprocess.run([a.binary,str(path)],capture_output=True,text=True)
 first=run();assert first.returncode==0,first.stderr;assert not json.loads(first.stdout)['reused']
 second=run();assert second.returncode==0;assert json.loads(second.stdout)['reused'];assert (root/'calls').read_text().count('compiled')==1
 (root/'denied').touch();denied=run();assert denied.returncode!=0 and not denied.stdout
 (root/'denied').unlink();(root/'revoke-during-compile').touch();config['encoding_revision']='fixture-v2';path.write_text(json.dumps(config))
 revoked=run();assert revoked.returncode!=0 and not revoked.stdout
 print(json.dumps({'all_selected_records':3,'initial_preparation':'passed','cached_reapproval':'passed','denied_cache_reuse':'passed','revoked_during_preparation':'passed','authority':'explicit protocol fixture; not live Aimee'}))
