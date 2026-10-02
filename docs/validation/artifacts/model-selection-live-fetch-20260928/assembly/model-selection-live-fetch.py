from pathlib import Path
import subprocess,json,time,hashlib
r=Path('/opt/aimee-large-release-validation');out=r/'model-selection-live-fetch';out.mkdir(mode=0o700,exist_ok=False)
launcher=r/'model-selection-launcher/aimee-native-lab';assert hashlib.sha256(launcher.read_bytes()).hexdigest()=='f9402df450278e9798642d99f6e177ac7eb42751cdc36b654eb8763492cd2cb3'
state={'status':'running','scope':'Real enrolled model-specific selection, artifact fetch and approval with fresh client caches; no GPU inference.','results':[]}
def save():(out/'status.json').write_text(json.dumps(state,indent=2)+'\n')
save()
try:
 for name in ['gemma26','qwen27']:
  client=out/name;client.mkdir(mode=0o700);memory=client/'memory';memory.mkdir(mode=0o700)
  config=json.loads(Path('/opt/aimee-client/native-signed-6-validation/config.json').read_text());config['memory_root']=str(memory)
  p=client/'config.json';p.write_text(json.dumps(config));p.chmod(0o600)
  model=json.loads((r/'packages'/name/'2/runtime/profile.json').read_text())['native_model']
  prior=None
  for attempt in range(2):
   start=time.monotonic();result=subprocess.run([str(launcher),'--root',str(client),'fetch-memory','What are the native release verification vault code, project, and drink?','--recipient','native-preview','--model',model],capture_output=True,text=True,timeout=900)
   (client/('attempt-'+str(attempt)+'.stderr')).write_text(result.stderr)
   assert result.returncode==0, name+' fetch failed'
   value=json.loads(result.stdout);assert value['records']==3,'incomplete selected working set'
   if prior:assert value['publication']==prior['publication'] and value['authorized_view']==prior['authorized_view']
   state['results'].append({'model':name,'attempt':attempt,'passed':True,'records':value['records'],'publication':value['publication'],'authorized_view':value['authorized_view'],'seconds':time.monotonic()-start});prior=value;save()
 state['status']='passed'
except BaseException as e:state.update(status='failed',error=str(e));raise
finally:save()
