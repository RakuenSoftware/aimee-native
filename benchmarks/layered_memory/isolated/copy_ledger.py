import subprocess,time
old='aimee-sparse-scale-20260920-aimee-store-db-1';new='aimee-layered-kb-20260920-aimee-store-db-1'
def sql(db,q):
 return subprocess.run(['docker','exec','-i',db,'sh','-c','PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -U postgres -d aimee_store'],input=q,text=True,capture_output=True,check=True).stdout
subprocess.run(['docker','start',old],check=True,capture_output=True)
try:
 for _ in range(20):
  try:raw=sql(old,'COPY schema_migrations TO STDOUT WITH CSV;');break
  except subprocess.CalledProcessError:time.sleep(.5)
 else:raise RuntimeError('research DB unavailable')
 sql(new,'TRUNCATE schema_migrations;\nCOPY schema_migrations FROM STDIN WITH CSV;\n'+raw+'\\.\n')
 print('Copied schema ledger matching schema-only snapshot')
finally:subprocess.run(['docker','stop',old],check=True,capture_output=True)
