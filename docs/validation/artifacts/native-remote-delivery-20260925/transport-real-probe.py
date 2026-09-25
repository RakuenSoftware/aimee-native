import pathlib,json,subprocess,os,ssl,urllib.request,time,secrets
lab=pathlib.Path('/opt/aimee-memory-lab');private=pathlib.Path('/opt/aimee-release-lab/private');work=lab/'native-transport-r3';work.mkdir(mode=0o700,exist_ok=True)
result=json.loads((lab/'real-reader-preparation-r3.json').read_text())
# Reports preserve the actual prepared bytes and all selected records.
prepared=result.get('reuse',result.get('first',{})).get('result')
assert prepared and len(prepared['records'])==3
(work/'prepared.json').write_text(json.dumps(prepared)); token=secrets.token_hex(32);(work/'token').write_text(token);os.chmod(work/'token',0o600)
def run(args):subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
run(['openssl','req','-new','-newkey','rsa:2048','-nodes','-subj','/CN=native-transport-client','-keyout',str(work/'client.key'),'-out',str(work/'client.csr')])
(work/'client.ext').write_text('extendedKeyUsage=clientAuth\nkeyUsage=digitalSignature\n')
run(['openssl','x509','-req','-in',str(work/'client.csr'),'-CA',str(private/'tls.crt'),'-CAkey',str(private/'tls.key'),'-CAcreateserial','-days','2','-extfile',str(work/'client.ext'),'-out',str(work/'client.crt')])
(work/'identity.pem').write_bytes((work/'client.crt').read_bytes()+(work/'client.key').read_bytes());os.chmod(work/'identity.pem',0o600)
launcher=lab/'vllm-native-build/distribution/launcher/target/debug/aimee-native'
c=json.loads((lab/'preparation-check-r1/config.json').read_text());c['compiler']=json.loads((lab/'real-reader-preparation-config.json').read_text())['compiler'];c['cache_root']=str(lab/'preparation-check-r1/cache');(work/'preparation.json').write_text(json.dumps(c))
os.environ['AIMEE_NATIVE_LIBRARY']=str(lab/'aimee-qwen/target/release/libaimee_qwen.so')
log=(work/'server.log').open('w');server=subprocess.Popen([str(lab/'native-delivery-fixture-real'),'--preparation-template',str(work/'preparation.json'),'--native-prepare',str(lab/'vllm-native-build/target/release/native-prepare'),'--prepared',str(work/'prepared.json'),'--model-config',str(lab/'gemma4/config.json'),'--token-file',str(work/'token'),'--cert',str(private/'server.crt'),'--key',str(private/'server.key'),'--client-ca',str(private/'tls.crt'),'--listen','192.168.0.126:8446','--deny',str(work/'denied'),'--deny-approve',str(work/'deny-approve')],stdout=log,stderr=log)
report={'authority':'isolated synthetic mTLS/bearer fixture with actual scoped reader, Rust private preparer and approval-only checks; not production enrollment','checks':{}}
try:
 time.sleep(.5)
 args=[str(launcher),'--root',str(work/'client')]
 def invoke(tail,input=None):
  start=time.perf_counter();r=subprocess.run(args+tail,input=input,capture_output=True,text=True);return r, time.perf_counter()-start
 conn=['connect','https://192.168.0.126:8446','--ca-file',str(private/'tls.crt'),'--client-identity',str(work/'identity.pem')]
 r,t=invoke(conn,token+'\n');assert r.returncode==0,r.stderr;report['checks']['authenticated_connect']={'passed':True,'seconds':t}
 fetch=['fetch-memory','alpha vault alpha project alpha drink','--recipient',prepared['recipient'],'--model',prepared['model']]
 for name in ['cold_download','cached_reapproval']:
  r,t=invoke(fetch);assert r.returncode==0,r.stderr;v=json.loads(r.stdout);assert v['records']==3;report['checks'][name]={'passed':True,'seconds':t,'records':v['records']}
 (work/'deny-approve').touch();r,t=invoke(fetch);assert r.returncode!=0;report['checks']['denied_final_approval']={'passed':True};(work/'deny-approve').unlink()
 (work/'denied').touch();r,t=invoke(fetch);assert r.returncode!=0;report['checks']['denied_cached_delivery']={'passed':True};(work/'denied').unlink()
 r,t=invoke(conn,'incorrect-fixture-credential\n');assert r.returncode!=0;report['checks']['wrong_credential']={'passed':True}
 r,t=invoke(fetch);assert r.returncode==0;report['checks']['failed_connect_preserved_previous_identity']={'passed':True}
 bad=fetch.copy();bad[bad.index('--recipient')+1]='another-recipient';r,t=invoke(bad);assert r.returncode!=0;report['checks']['recipient_mismatch']={'passed':True}
 server.terminate();server.wait(timeout=10);r,t=invoke(fetch);assert r.returncode!=0;report['checks']['offline_cached_bytes_not_authority']={'passed':True}
 report['status']='passed'
finally:
 if server.poll() is None:server.terminate();server.wait(timeout=10)
 log.close();(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
