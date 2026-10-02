"""Capture installed Python/OS package inventory for a pinned runtime image.
Run inside the final image. This inventory is not a vulnerability clearance.
"""
import hashlib,importlib.metadata,json,platform,subprocess,sys
packages=[]
for d in importlib.metadata.distributions():
 m=d.metadata
 license_files=[]
 for f in d.files or []:
  if any(word in str(f).lower().split('/')[-1] for word in ('license','copying','notice')):
   path=d.locate_file(f)
   if path.is_file() and path.stat().st_size<1024*1024:
    license_files.append({'path':str(f),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
 packages.append({'name':m.get('Name'),'version':d.version,'license_expression':m.get('License-Expression'),'license':m.get('License'),'declared_license_files':m.get_all('License-File',[]),'license_files':license_files,'installer':d.read_text('INSTALLER')})
try:
 rows=subprocess.check_output(['dpkg-query','-W','-f=${Package}\t${Version}\t${Architecture}\n'],text=True).splitlines()
 os_packages=[dict(zip(('name','version','architecture'),r.split('\t'))) for r in rows]
except (FileNotFoundError,subprocess.CalledProcessError):os_packages=[]
json.dump({'schema':1,'python':sys.version,'platform':platform.platform(),'python_packages':sorted(packages,key=lambda p:(p['name'] or '').lower()),'os_packages':os_packages,'limitations':'Inventory and license metadata only. Transitive license obligations and vulnerabilities require review.'},sys.stdout,indent=2);print()
