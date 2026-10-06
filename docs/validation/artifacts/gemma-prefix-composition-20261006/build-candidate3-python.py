"""Append-only review wheel: compile changed common modules, retain other pins."""
from pathlib import Path
import hashlib,json,sys,subprocess,zipfile,csv,io,base64
root=Path('/opt/jmlr-second-review-20261005/repair-cache/gemma-composition-candidate-r1')
nas=Path('/mnt/pve/backup/aimee-experiments/root-evacuation-20261005-r1/gemma-composition-candidate-r1')
work=root/'candidate3-build';work.mkdir(exist_ok=False)
package=work/'aimee_native_runtime';package.mkdir()
sys.path.insert(0,str(root/'source/distribution/release'))
from model_plugin_layout import shared_source
for name in ('composition',):
    (package/(name+'.py')).write_text(shared_source(root/'buildtmp',name))
(work/'setup.py').write_text("from setuptools import setup,Extension\nfrom Cython.Build import cythonize\nsetup(ext_modules=cythonize([Extension('aimee_native_runtime.'+n,['aimee_native_runtime/'+n+'.py'],extra_compile_args=['-O3','-g0'],extra_link_args=['-s']) for n in ('composition',)],compiler_directives={'language_level':3,'binding':True,'annotation_typing':False}))\n")
subprocess.run([sys.executable,'setup.py','build_ext','--inplace','--parallel','2'],cwd=work,check=True)
old=nas/'candidate2-python/aimee_native_runtime-0.3.2+gemma.prefix.candidate2-cp312-cp312-linux_x86_64.whl'
assert hashlib.sha256(old.read_bytes()).hexdigest()=='3f9a315eb81279a0f1fd74f9aee0b8c8e4ac29f5f21cf43cbb4ed51fc7d1ce70'
version='0.3.2+gemma.prefix.candidate3'
new=work/('aimee_native_runtime-'+version+'-cp312-cp312-linux_x86_64.whl')
files={}
with zipfile.ZipFile(old) as z:
    for name in z.namelist():
        if name.endswith('/RECORD'):continue
        target=name.replace('candidate2.dist-info','candidate3.dist-info')
        data=z.read(name)
        if name.endswith('/METADATA'):data=data.replace(b'Version: 0.3.2+gemma.prefix.candidate2',b'Version: 0.3.2+gemma.prefix.candidate3')
        files[target]=data
for module in ('composition',):
    binary=next(package.glob(module+'.*.so'));files['aimee_native_runtime/'+binary.name]=binary.read_bytes()
record='aimee_native_runtime-'+version+'.dist-info/RECORD'
rows=[]
for name,data in sorted(files.items()):rows.append((name,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('='),str(len(data))))
rows.append((record,'',''));buffer=io.StringIO();csv.writer(buffer,lineterminator='\n').writerows(rows);files[record]=buffer.getvalue().encode()
with zipfile.ZipFile(new,'x',compression=zipfile.ZIP_DEFLATED) as z:
    for name,data in sorted(files.items()):z.writestr(name,data)
site=root/'candidate3-site';site.mkdir(exist_ok=False)
with zipfile.ZipFile(new) as z:z.extractall(site)
receipt={'status':'passed','version':version,'wheel':new.name,'sha256':hashlib.sha256(new.read_bytes()).hexdigest(),'bytes':new.stat().st_size,'source_sha256':{name:hashlib.sha256((root/'buildtmp'/name).read_bytes()).hexdigest() for name in ('composition.py','preparation.py')},'retained_binary_scope':'candidate2 preparation and other unchanged modules/client; broker v2 rebuild pending','compiler':'Cython 3.1.4; annotation_typing False','base_wheel_sha256':hashlib.sha256(old.read_bytes()).hexdigest()}
(work/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
