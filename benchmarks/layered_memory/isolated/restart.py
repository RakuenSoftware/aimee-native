import subprocess
sql='GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO aimee_store_runtime; GRANT USAGE,SELECT,UPDATE ON ALL SEQUENCES IN SCHEMA public TO aimee_store_runtime;'
p=subprocess.run(['docker','exec','-i','aimee-layered-kb-20260920-aimee-store-db-1','sh','-c','PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U postgres -d aimee_store'],input=sql,text=True,capture_output=True,check=True)
print(p.stdout)
subprocess.run(['docker','start','aimee-layered-kb-20260920-aimee-server-1'],check=True)
