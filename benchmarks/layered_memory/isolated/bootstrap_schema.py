import subprocess
from pathlib import Path
# Schema only, from the existing disposable scale-test DB. No production data.
name='aimee-sparse-scale-20260920-aimee-store-db-1'
subprocess.run(['docker','start',name],check=True,capture_output=True)
p=subprocess.run(['docker','exec',name,'sh','-c','PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h 127.0.0.1 -U postgres -d aimee_store --schema-only --no-privileges'],text=True,capture_output=True,check=True)
r=subprocess.run(['docker','exec','-i','aimee-layered-kb-20260920-aimee-store-db-1','sh','-c','PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U postgres -d aimee_store'],input=p.stdout,text=True,capture_output=True)
Path('/opt/aimee-layered-kb-20260920/schema-bootstrap.log').write_text(r.stdout+r.stderr)
print('schema import exit',r.returncode)
subprocess.run(['docker','stop',name],check=True,capture_output=True)
