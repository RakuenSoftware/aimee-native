"""Build a signed lab-only release from actual binaries; never forge gate evidence."""
import argparse,json,pathlib,subprocess,sys
p=argparse.ArgumentParser();p.add_argument('--lab-root',default='/opt/aimee-memory-lab');p.add_argument('--release-root',default='/opt/aimee-release-lab');p.add_argument('--sequence',type=int,required=True);p.add_argument('--profile');p.add_argument('--output',required=True);a=p.parse_args()
lab=pathlib.Path(a.lab_root);release=pathlib.Path(a.release_root);build=lab/'vllm-native-build'
digest=(release/'image-digest.txt').read_text().strip();assert digest.startswith('sha256:')
descriptor=release/f'image-{a.sequence}.json';descriptor.write_text(json.dumps({'image':'192.168.0.126:5443/aimee-native@'+digest,'model_config':'models/config.json'}))
shim=release/'aimee-vllm';shim.write_text('#!/bin/sh\nexec aimee-vllm "$@"\n')
files={'bin/aimee-vllm':str(shim),'lib/libaimee_native.so':str(build/'target/release/libaimee_qwen.so'),'runtime/image.json':str(descriptor),'models/model.gguf':str(lab/'gemma4-aimee-q8.gguf')}
if a.profile:files['runtime/profile.json']=a.profile
for path in (lab/'gemma4').iterdir():
 if path.is_file() and path.suffix in ('.json','.jinja','.model') and not path.name.endswith('.safetensors.index.json'):files['models/'+path.name]=str(path)
for path in (build/'distribution/container/licenses').glob('*.txt'):files['licenses/'+path.name]=str(path)
manifest={'schema':1,'sequence':a.sequence,'version':f'lab-{a.sequence}','platform':'linux-x86_64','model':'lab-gemma4-q8','runtime':'vllm','runtime_commit':'ced6857afa0ea7b2e3f0846a62e1394e90f15607','abi':1,'engine':'bin/aimee-vllm','model_file':'models/model.gguf','library':'lib/libaimee_native.so'}
plan=release/f'plan-{a.sequence}.json';plan.write_text(json.dumps({'manifest':manifest,'files':files}))
subprocess.run([sys.executable,str(build/'distribution/release/package.py'),str(plan),a.output,'--signing-key',str(release/'private/release.key'),'--lab-only'],check=True)
print(json.dumps({'model':manifest['model'],'sequence':a.sequence,'image':json.loads(descriptor.read_text())['image'],'artifacts':len(files),'gates':'lab_only'}))
