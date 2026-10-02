import pathlib,json,hashlib
r=pathlib.Path('/opt/aimee-large-release-validation/packages')
report={'scope':'Exact signed package notice presence and byte identity. Not a new vulnerability scan or public redistribution clearance.','packages':{}}
for model in ['gemma26','qwen27']:
 p=r/model/'2';raw=(p/'manifest.json').read_bytes();m=json.loads(raw);rows=[]
 for a in m['artifacts']:
  if not a['path'].startswith('licenses/'):continue
  f=p/a['path'];b=f.read_bytes();h=hashlib.sha256(b).hexdigest()
  assert len(b)==a['bytes'] and h==a['sha256']
  rows.append({'path':a['path'],'bytes':len(b),'sha256':h})
 assert {'licenses/model-NOTICE.txt','licenses/Apache-2.0.txt','licenses/native-target-notices.txt','licenses/launcher-target-notices.txt','licenses/vllm.txt','licenses/vllm-gguf-plugin.txt'} <= {x['path'] for x in rows}
 report['packages'][model]={'manifest_sha256':hashlib.sha256(raw).hexdigest(),'model':m['model'],'runtime_commit':m['runtime_commit'],'notices':rows}
report['status']='passed'
print(json.dumps(report,indent=2))
