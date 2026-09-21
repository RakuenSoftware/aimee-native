"""Install only in the disposable research container, never the primary Aimee."""
import subprocess
from pathlib import Path
name='aimee-layered-kb-20260920-aimee-server-1'
def run(*args,**kw):return subprocess.run(list(args),check=True,**kw)
run('docker','stop',name,stdout=subprocess.DEVNULL)
for binary in ['aimee-module-memory','aimee-memory-read']:
 Path('/tmp/'+binary).chmod(0o755)
 run('docker','cp','/tmp/'+binary,name+':/usr/local/libexec/aimee-modules/'+binary)
root=Path('/var/lib/docker/volumes/aimee-layered-kb-20260920_aimee-server-home/_data')
p=root/'modules.d/server/restricted-read-research.grant'
p.write_text('version=1\nprincipal_class=1\nprincipal_ref=200\nuid=self\nexecutable=/usr/local/libexec/aimee-modules/aimee-memory-read\npublish=\nsubscribe=\nrequest=5895\nserve=\n')
run('docker','start',name)
run('docker','exec',name,'chmod','755','/usr/local/libexec/aimee-modules/aimee-memory-read','/usr/local/libexec/aimee-modules/aimee-module-memory')
run('docker','restart',name)
