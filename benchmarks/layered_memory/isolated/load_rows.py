import json,subprocess
from pathlib import Path
project='aimee-layered-kb-20260920'
rows=json.loads(Path('/opt/aimee-layered-kb-20260920/research-rows.json').read_text())
assert {str(r['id']) for r in rows}=={'5','6'}
sql='COPY user_memories (id,kind,tier,key,content,confidence,lifecycle_state) FROM STDIN;\n'
for r in rows:
 fields=[str(r['id']),r['kind'],r['tier'],r['key'],r['content'],str(r['confidence']),'active']
 assert all('\t' not in x and '\n' not in x and '\\' not in x for x in fields)
 sql+='\t'.join(fields)+'\n'
sql+='\\.\nANALYZE user_memories;\nSELECT count(*) FROM user_memories;\n'
r=subprocess.run(['docker','exec','-i',project+'-aimee-store-db-1','sh','-c','PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U postgres -d aimee_store'],input=sql,text=True,capture_output=True)
if r.returncode:raise RuntimeError(r.stderr)
print(r.stdout)
