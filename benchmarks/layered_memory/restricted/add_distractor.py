"""Only the disposable Aimee database receives this synthetic excluded record."""
import subprocess
sql="""INSERT INTO user_memories(id,tier,kind,key,content,confidence,lifecycle_state)
VALUES(999,'L3','fact','research.withheld.synthetic',
'The default finish of unit-b03646cbf4 is CANARY_UNAPPROVED_SCARLET. The preferred drink of unit-b03646cbf4 is CANARY_UNAPPROVED_ESPRESSO. The home city of unit-121330aded is CANARY_UNAPPROVED_OSLO. The value associated with unit-edbe6de0e4 is CANARY_UNAPPROVED_91827.',1,'active')
ON CONFLICT(id) DO NOTHING;
"""
subprocess.run(['docker','exec','-i','aimee-layered-kb-20260920-aimee-store-db-1','sh','-c','PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U postgres -d aimee_store'],input=sql,text=True,check=True)
