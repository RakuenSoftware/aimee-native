from pathlib import Path
import secrets,subprocess,json
root=Path('/opt/aimee-layered-kb-20260920');root.mkdir(mode=0o700)
(root/'compose.yaml').write_bytes(Path('/opt/aimee/compose.yaml').read_bytes())
env={'AIMEE_APPLICATION_IMAGE':'aimee:0.4.4-probe-fix-20260917','AIMEE_POSTGRES_IMAGE':'ghcr.io/rakuensoftware/aimee-postgres:0.4.4','AIMEE_EMBEDDER_IMAGE':'ghcr.io/rakuensoftware/aimee-embedder-a25m:0.4.4','AIMEE_API_PORT':'127.0.0.1:18744','AIMEE_WEB_PORT':'127.0.0.1:18444','AIMEE_MODULE_ROUNDTABLE':'0','AIMEE_RUNTIME_WEB_ENABLED':'0'}
for k in ['AIMEE_STORE_ADMIN_PASSWORD','AIMEE_STORE_MIGRATOR_PASSWORD','AIMEE_STORE_RUNTIME_PASSWORD']:env[k]=secrets.token_hex(24)
p=root/'.env';p.write_text(''.join(f'{k}={v}\n' for k,v in env.items()));p.chmod(0o600)
(root/'limits.json').write_text(json.dumps({'services':{'aimee-server':{'mem_limit':'2g','cpus':2,'restart':'no'},'aimee-store-db':{'mem_limit':'2g','cpus':2,'restart':'no'},'aimee-embedder':{'mem_limit':'768m','cpus':1,'restart':'no'}}}))
cmd=['/opt/aimee/scripts/compose-local.sh','-p','aimee-layered-kb-20260920','--env-file',str(p),'-f',str(root/'compose.yaml'),'-f',str(root/'limits.json'),'up','-d','--no-build','--pull','never']
with (root/'provision.log').open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=log)
print('isolated project exit:',r.returncode)
raise SystemExit(r.returncode)
