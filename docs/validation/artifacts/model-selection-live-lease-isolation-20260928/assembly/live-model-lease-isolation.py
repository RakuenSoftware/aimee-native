"""Live model-scoped lease checks; reports never include credentials or leases."""
import http.client,json,pathlib,socket,ssl,urllib.parse,time
root=pathlib.Path('/opt/aimee-large-release-validation')
output=root/'model-selection-live-lease-isolation';output.mkdir(mode=0o700,exist_ok=False)
config=json.loads(pathlib.Path('/opt/aimee-client/native-signed-6-validation/config.json').read_text())
url=urllib.parse.urlsplit(config['endpoint']);assert url.scheme=='https'
token=pathlib.Path(config['token_file']).read_text().strip()
context=ssl.create_default_context(cafile=config['ca_file']);context.load_cert_chain(config['client_identity'])
models=['google-gemma-4-12b-native-negative-v1']+[json.loads((root/'packages'/n/'2/runtime/profile.json').read_text())['native_model'] for n in ['gemma26','qwen27']]
report={'status':'running','scope':__doc__,'results':[]}
def save():(output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def request(method,path,model,body=None):
    target=(url.hostname,url.port or 443)
    if config.get('connect_address'):
        host,port=config['connect_address'].rsplit(':',1);target=(host.strip('[]'),int(port))
    connection=http.client.HTTPSConnection(url.hostname,url.port or 443,context=context,timeout=120)
    try:
        connection.sock=context.wrap_socket(socket.create_connection(target,timeout=15),server_hostname=url.hostname)
        path=url.path.rstrip('/')+path
        if model is not None:path+='?'+urllib.parse.urlencode({'model':model})
        connection.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        response=connection.getresponse();data=response.read(131073)
        return response.status,data
    finally:connection.close()
def check(label,actual,expected):
    report['results'].append({'case':label,'status':actual,'expected':expected,'passed':actual==expected});save()
    assert actual==expected,label
save()
try:
    for i,model in enumerate(models):
        status,raw=request('POST','/v1/native/select',model,{'query':'What are the native release verification vault code, project, and drink?'})
        check(str(i)+':select',status,200);offer=json.loads(raw)
        assert offer['model']==model and offer['recipient']=='native-preview' and len(offer['records'])==3
        lease=offer['lease'];assert len(lease)==64 and all(c in '0123456789abcdef' for c in lease)
        base='/v1/native/leases/'+lease+'/'
        check(str(i)+':own-approve',request('POST',base+'approve',model,{})[0],200)
        check(str(i)+':own-index',request('GET',base+'index.json',model)[0],200)
        for j,other in enumerate(models):
            if i==j:continue
            for name,method in [('approve','POST'),('index.json','GET'),('compact.pack','GET')]:
                check(str(i)+'->'+str(j)+':'+name,request(method,base+name,other,{} if method=='POST' else None)[0],403)
        check(str(i)+':omitted-selector',request('POST',base+'approve',None,{})[0],200 if i==0 else 403)
    report['status']='passed'
except BaseException as error:report.update(status='failed',error=type(error).__name__);raise
finally:save()
print(json.dumps({'status':report['status'],'cases':len(report['results'])}))
