"""Explicit binary-only container context; never point a Docker build at the repo."""
import argparse,hashlib,json,pathlib,shutil,zipfile,email,re
p=argparse.ArgumentParser();p.add_argument('--wheel',required=True);p.add_argument('--library',required=True);p.add_argument('--kernels',required=True);p.add_argument('--gguf-wheel');p.add_argument('--runtime-wheels',required=True);p.add_argument('--output',required=True);a=p.parse_args()
wheel=pathlib.Path(a.wheel);bank=pathlib.Path(a.kernels);out=pathlib.Path(a.output)
with zipfile.ZipFile(wheel) as w:
 for name in w.namelist():
  if name.endswith(('.py','.pyc','.c','.pyx')) and name!='aimee_vllm/__init__.py':raise ValueError('private source in wheel')
manifest=json.loads((bank/'manifest.json').read_text())
files={'manifest.json'}
for kernel in manifest['kernels']:
 for name in kernel['files']:
  if pathlib.Path(name).name!=name or not name.endswith(('.json','.hsaco')):raise ValueError('unapproved kernel artifact')
  files.add(name)
if not manifest['kernels']:raise ValueError('empty kernel bank')
lock=pathlib.Path(__file__).with_name('runtime-requirements.lock')
os_lock=pathlib.Path(__file__).with_name('os-packages.lock')
if not os_lock.read_text().splitlines() or any(not re.fullmatch(r'[a-z0-9][a-z0-9+.-]*(?::[a-z0-9]+)?=[A-Za-z0-9.+:~_-]+',line) for line in os_lock.read_text().splitlines()):raise ValueError('invalid OS dependency lock')
expected={}
for line in lock.read_text().splitlines():
 if not line.strip() or line.startswith('#'):continue
 match=re.fullmatch(r'([A-Za-z0-9_.-]+)==([^ ]+) --hash=sha256:([a-f0-9]{64})',line)
 if not match:raise ValueError('invalid runtime dependency lock')
 key=(match[1].lower().replace('_','-'),match[2])
 if key in expected:raise ValueError('duplicate runtime dependency')
 expected[key]=match[3]
resolved={}
for dependency in pathlib.Path(a.runtime_wheels).iterdir():
 if dependency.is_symlink() or not dependency.is_file() or dependency.suffix!='.whl':raise ValueError('unexpected runtime dependency file')
 with zipfile.ZipFile(dependency) as z:
  names=[n for n in z.namelist() if n.count('/')==1 and n.endswith('.dist-info/METADATA')]
  if len(names)!=1:raise ValueError('missing wheel metadata')
  metadata=email.message_from_bytes(z.read(names[0]))
 key=(metadata['Name'].lower().replace('_','-'),metadata['Version'])
 if key not in expected or key in resolved or hashlib.sha256(dependency.read_bytes()).hexdigest()!=expected[key]:raise ValueError('runtime dependency does not match lock')
 resolved[key]=dependency
if set(resolved)!=set(expected):raise ValueError('incomplete runtime dependencies')
out.mkdir(parents=True,exist_ok=False);(out/'kernels').mkdir()
(out/'runtime-wheels').mkdir()
for dependency in resolved.values():shutil.copyfile(dependency,out/'runtime-wheels'/dependency.name)
shutil.copyfile(lock,out/'runtime-requirements.lock')
shutil.copyfile(os_lock,out/'os-packages.lock')
shutil.copyfile(wheel,out/'client.whl');(out/'wheel-name.txt').write_text(wheel.name)
shutil.copyfile(a.library,out/'libaimee_native.so')
for name in files:shutil.copyfile(bank/name,out/'kernels'/name)
shutil.copyfile(pathlib.Path(__file__).with_name('Dockerfile'),out/'Dockerfile')
shutil.copytree(pathlib.Path(__file__).with_name('licenses'),out/'licenses')
if a.gguf_wheel:
 dependency=pathlib.Path(a.gguf_wheel)
 if dependency.name!='vllm_gguf_plugin-0.0.5-cp310-abi3-linux_x86_64.whl':raise ValueError('uncertified GGUF dependency name')
 shutil.copyfile(dependency,out/dependency.name)
 with (out/'Dockerfile').open('a') as docker:
  docker.write('\nCOPY '+dependency.name+' /opt/aimee/'+dependency.name+'\nRUN python3 -m pip install --no-deps /opt/aimee/'+dependency.name+' gguf==0.19.0 && rm /opt/aimee/'+dependency.name+'\n')
report={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in out.rglob('*') if f.is_file()}
(out/'artifacts.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'files':len(report),'private_source_included':False,'artifact_digests':report}))
