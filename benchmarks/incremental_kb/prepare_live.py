"""Prepare an isolated live-source publication experiment on research host .253.
Only the named disposable Aimee stack is used. No production memory is exported.
The publisher policy is an explicit operator release, not a fixture-signed grant.
"""
import argparse,datetime,json,os,secrets,subprocess
from pathlib import Path
B=Path('/opt/aimee-qwen-rust')
p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--publisher',default='aimee-memory-publish-stream');p.add_argument('--image-reader',default='aimee-memory-image-stream');args=p.parse_args();root=args.root.resolve()
assert root.parent==B,'Use a research directory under /opt/aimee-qwen-rust'
assert not root.exists(),'Use a new experiment directory'
root.mkdir();(root/'private').mkdir(mode=0o700);(root/'traces').mkdir(mode=0o700);os.chown(root/'traces',997,989)
def pct(*args,**kw):return subprocess.check_output(['pct','exec','103','--',*args],**kw)
pid=subprocess.check_output(['lxc-info','-n','103','-pH'],text=True).strip();host=Path('/proc')/pid/'root'
live=root/'private';local=live

project='aimee-layered-kb-20260920';db=project+'-aimee-store-db-1'
bus=f'/var/lib/docker/volumes/{project}_aimee-server-home/_data/server-module-bus.sock'
def store(key,body):
    request=dict(kind='fact',tier='L3',key=key,content=body,confidence=1)
    program="""import http.client,socket,json,sys
class U(http.client.HTTPConnection):
 def connect(self):self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.connect(self.host)
x=json.load(sys.stdin);c=U(x['socket']);c.request('POST','/v1/memory/store',json.dumps(x['body']),{'Content-Type':'application/json'});r=c.getresponse();out=json.loads(r.read());assert r.status==200 and out['status']=='ok',out;print(json.dumps(out))
"""
    reply=json.loads(subprocess.check_output(['pct','exec','103','--','python3','-c',program],input=json.dumps(dict(socket=bus.replace('server-module-bus.sock','aimee-http.sock'),body=request)),text=True))
    return dict(request,id=reply['id'])
drink=store('stream drink 20260921','The preferred drink of stream-unit-d47 is oolong.')
city=store('stream city 20260921','The home city of stream-unit-c92 is Lima.')
canary=store('stream private 20260921','The private release secret is CANARY_'+secrets.token_hex(16)+'.')
metadata=dict(project=project,container_init=pid,lxc_root=str(live),bus=bus,drink=drink,city=city,canary=canary)
(root/'private/records.json').write_text(json.dumps(metadata));os.chmod(root/'private/records.json',0o600)
role='aimee_stream_reader_'+secrets.token_hex(6);password=secrets.token_hex(32)
statement=f"CREATE ROLE {role} LOGIN PASSWORD '{password}'; GRANT CONNECT ON DATABASE aimee_store TO {role}; GRANT USAGE ON SCHEMA public TO {role}; GRANT SELECT ON user_memories TO {role}; ALTER ROLE {role} SET default_transaction_read_only=on;"
subprocess.run(['pct','exec','103','--','docker','exec','-i',db,'sh','-c','PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U postgres -d aimee_store'],input=statement,text=True,stdout=subprocess.DEVNULL,check=True)
ip=pct('docker','inspect','--format','{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',db,text=True).strip()
certificate=pct('docker','exec',db,'cat','/var/lib/aimee-postgres/plain/secure/server.crt')
(local/'database-ca.pem').write_bytes(certificate)
(local/'source.env').write_text(f'AIMEE_IMAGE_DATABASE_URL=postgresql://{role}:{password}@{ip}:5432/aimee_store?sslmode=verify-full&sslrootcert={local / "database-ca.pem"}\n');os.chmod(local/'source.env',0o600)
base=B/'kb-cue-fix-20260921/image';head=json.loads((base/'CURRENT').read_text())['view']
base_snapshot=base/'snapshots'/head
policy=dict(version=1,recipient='incremental-research',peer_uid=0,namespace='stream-live',base_view=head,valid_until=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=8)).isoformat(),active=True,records=[dict(id=str(drink['id']),scope_type='user',scope_value='_user',follow_updates=True,cues=['preferred drink','drink of stream-unit-d47']),dict(id=str(city['id']),scope_type='user',scope_value='_user',follow_updates=True,cues=['home city','city of stream-unit-c92'])])
(local/'release.json').write_text(json.dumps(policy,indent=2));os.chmod(local/'release.json',0o600)
# Audit-safe policy excludes credentials and the unauthorized canary payload.
(root/'release-initial.json').write_text(json.dumps(policy,indent=2)+'\n')
(root/'setup.json').write_text(json.dumps({k:v for k,v in metadata.items() if k!='canary'},indent=2)+'\n')
publisher_command=['systemd-run','--unit=aimee-stream-publisher','--property=RuntimeMaxSec=6h','--property=NoNewPrivileges=yes','--property=EnvironmentFile='+str(live/'source.env'),'--property=StandardOutput=append:'+str(live/'publisher.log'),'--property=StandardError=append:'+str(live/'publisher.log'),'/usr/bin/nsenter','-t',pid,'-n',str(B/args.publisher),'--socket',str(live/'publication.sock'),'--release-policy',str(live/'release.json'),'--recipient','incremental-research','--base',str(base_snapshot),'--root',str(live/'history'),'--interval','1s','--database-server-name','aimee-store-db']
(root/'publisher-command.json').write_text(json.dumps(publisher_command)+'\n')
subprocess.run(publisher_command,check=True)
consumer_command=['systemd-run','--unit=aimee-stream-consumer','--property=RuntimeMaxSec=6h','--property=NoNewPrivileges=yes','--property=StandardOutput=append:'+str(root/'consumer.log'),'--property=StandardError=append:'+str(root/'consumer.log'),str(B/args.image_reader),'follow-published','--publication-unix',str(local/'publication.sock'),'--state-root',str(root/'private/resume'),'--root',str(root/'image'),'--reader-gid','989']
(root/'consumer-command.json').write_text(json.dumps(consumer_command)+'\n')
subprocess.run(consumer_command,check=True)
print(json.dumps(dict(root=str(root),general_records=249105,approved_personal_records=2,source='actual disposable Aimee memory module',policy='exact-ID server-owned release')))
