import subprocess,json,pathlib,importlib.metadata as md
root=pathlib.Path('/opt/aimee-memory-lab/security-review')
images=['localhost/aimee-native:gemma-preview-r12','localhost/aimee-native:gemma-preview-r13']
dbs=[]
for image in images:
 wire=subprocess.check_output(['podman','run','--rm','--entrypoint','dpkg-query',image,'-W','-f=${binary:Package}\t${Version}\n'],text=True)
 dbs.append(dict(line.split('\t') for line in wire.splitlines()))
changes={name:{'before':dbs[0].get(name),'after':version} for name,version in dbs[1].items() if version!=dbs[0].get(name)}
(root/'os-updates-r13.json').write_text(json.dumps(changes,indent=2)+'\n')
(root/'os-packages.lock').write_text('\n'.join(f'{name}={row["after"]}' for name,row in sorted(changes.items()))+'\n')
code='''import importlib.metadata as m,json,pathlib
x=m.distribution("flash-attn"); files=[str(f) for f in x.files]; suspects=[f for f in files if f.endswith(("checkpoint.py","eval.py"))];loads=[]
for f in files:
 if f.endswith(".py"):
  p=x.locate_file(f)
  if p.is_file():
   for i,line in enumerate(p.read_text(errors="replace").splitlines(),1):
    if "torch.load(" in line:loads.append({"path":f,"line":i,"code":line.strip()})
print(json.dumps({"version":x.version,"installed_files":len(files),"checkpoint_eval_modules":suspects,"torch_load_calls":loads},indent=2))
'''
raw=subprocess.check_output(['podman','run','--rm','--entrypoint','python3',images[-1],'-c',code],text=True)
(root/'flash-attn-installed-review.json').write_text(raw)
print(json.dumps({'os_upgrades':len(changes),'flash':json.loads(raw)}))
