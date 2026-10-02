from pathlib import Path
import hashlib,json,os,shutil,subprocess,time
root=Path('/root/model-selection-rollout-r2-20260928');binding=Path('/etc/aimee-native/bindings.json');binary=Path('/opt/aimee-native/bin/aimee-native-delivery');overlay=Path('/opt/aimee/compose.native-preview.json')
candidate_binary=binary.with_name(binary.name+'.model-selection');candidate_binding=binding.with_name('bindings.three-models.candidate.json')
image='aimee-native-core:model-selection-816740e90-r3';image_id='sha256:34b9aecbd4b21d868c50080a13ce5ae4e4f41b67e489e9e71678e6b6edec0243'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert digest(binding)=='b9441137dedcc2ecc0f362317e6d0d4201c7ae84b41f7a6b20b5c46040312a83'
assert digest(candidate_binding)=='4bda33b9f6ded080077dd83a070ae6404609da61452c93212ff7cb0778048205'
assert digest(candidate_binary)=='14649f9e09dbe0eed44f8b02752f681334e7c1cae44d3b326a428bf1e971c43c'
assert subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).strip()==image_id
assert Path('/opt/aimee/compose.override.yaml').resolve()==overlay
old_image=json.loads(subprocess.check_output(['docker','inspect','aimee-aimee-server-1']))[0]['Image']
inode=Path('/run/aimee-native').stat().st_ino
for p in [binding,binary,overlay]:shutil.copy2(p,root/p.name)
report={'status':'deploying','started':time.time(),'previous_image':old_image,'candidate_image':image_id,'previous_binary_sha256':digest(binary),'candidate_binary_sha256':digest(candidate_binary)}
def save():(root/'status.json').write_text(json.dumps(report,indent=2)+'\n')
def replace(target,data):
 meta=target.stat();stage=target.with_name(target.name+'.rollout-next');assert not stage.exists();stage.write_bytes(data);stage.chmod(meta.st_mode & 0o777);os.chown(stage,meta.st_uid,meta.st_gid);stage.replace(target)
def compose():subprocess.run(['docker','compose','-f','/opt/aimee/compose.yaml','-f',str(overlay),'up','-d','--no-deps','aimee-server'],cwd='/opt/aimee',check=True,timeout=120)
def healthy(expected):
 deadline=time.monotonic()+660
 while time.monotonic()<deadline:
  v=json.loads(subprocess.check_output(['docker','inspect','aimee-aimee-server-1']))[0]
  if v['Image']!=expected:raise RuntimeError('unexpected frontend image')
  if v['State'].get('Health',{}).get('Status')=='healthy':return
  if v['State']['Status'] not in ('running','created'):raise RuntimeError('frontend exited')
  time.sleep(3)
 raise TimeoutError('frontend readiness')
save()
try:
 replace(binary,candidate_binary.read_bytes());replace(binding,candidate_binding.read_bytes())
 value=json.loads(overlay.read_text());value['services']['aimee-server']['image']=image;value['services']['aimee-server']['pull_policy']='never';replace(overlay,(json.dumps(value,indent=2)+'\n').encode())
 subprocess.run(['systemctl','restart','aimee-native-delivery.service'],check=True,timeout=60)
 assert Path('/run/aimee-native').stat().st_ino==inode
 compose();healthy(image_id)
 assert subprocess.check_output(['systemctl','is-active','aimee-native-delivery.service'],text=True).strip()=='active'
 report.update(status='healthy_pending_authorization_tests',runtime_directory_preserved=True)
except BaseException as error:
 report.update(status='rolling_back',error=str(error));save()
 with (root/'failed-candidate.log').open('w') as log:subprocess.run(['docker','logs','aimee-aimee-server-1'],stdout=log,stderr=subprocess.STDOUT)
 try:
  for p in [binding,binary,overlay]:replace(p,(root/p.name).read_bytes())
  subprocess.run(['systemctl','restart','aimee-native-delivery.service'],check=True,timeout=60);compose();healthy(old_image)
  report['status']='rolled_back'
 except BaseException as rollback:report.update(status='rollback_failed',rollback_error=str(rollback))
finally:report['finished']=time.time();save()
