import pathlib,subprocess,json,time,traceback
root=pathlib.Path('/opt/aimee-memory-lab');work=root/'vllm-stream-validation-20260926';image='localhost/aimee-native:gemma-stream-r2'
status={'status':'running','started':time.time(),'image':image,'completed':[]}
def save():(work/'status.json').write_text(json.dumps(status,indent=2)+'\n')
def run(name,cmd):
 status['current']=name;save()
 with (work/(name+'.log')).open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
 status['completed'].append(name);save()
try:
 run('serving',['python3',str(work/'wide_image_certification.py'),'--image',image,'--output',str(work/'serving'),'--rounds','3','--stream'])
 for pub,folder in [('alpha','vllm-native-fixture-r1'),('wide','wide-native-r2')]:
  catalog=root/folder/'catalog.json';data=json.loads(catalog.read_text());bank=pathlib.Path(data['publications'][pub]['root'])
  cmd=['podman','run','--rm','--name','aimee-activation-validation','--ipc','host','--device','/dev/kfd','--device','/dev/dri/renderD128','--device','/dev/dri/renderD129','--entrypoint','python3']
  for path,mode in [(work,'rw'),(catalog.parent,'ro'),(bank,'ro')]:cmd+=['-v',str(path)+':'+str(path)+':'+mode]
  cmd += [image,str(work/'activation_timing.py'),'--catalog',str(catalog),'--publication',pub,'--output',str(work/(pub+'-activation.json')),'--packed','--cold-repetitions','20','--repetitions','100','--native-profile']
  run(pub+'-activation',cmd)
 status['status']='passed'
except BaseException as e:status.update(status='failed',error=str(e));traceback.print_exc()
finally:status['finished']=time.time();save()
