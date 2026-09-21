import sys,os,json,subprocess,hashlib
sys.path.insert(0,'/opt/aimee-qwen-adapter/src')
from gateway_client import UnixHTTP
root='/opt/aimee-qwen-adapter/local-first-image'
rows=[]
for label,path,mode in [('manifest_write',root+'/CURRENT','w'),('image_create',root+'/model-forged-object','w'),('credential_read','/opt/aimee-qwen-adapter/private/remote.conf','r')]:
 try:
  fd=os.open(path, os.O_RDONLY if mode == "r" else os.O_WRONLY | (os.O_CREAT if label == "image_create" else 0));os.close(fd)
  rows.append({'case':label,'denied':False})
 except PermissionError:rows.append({'case':label,'denied':True})
for path,payload in [('/v1/memory/store',{'content':'model-forged fact'}),('/publish',{'generation':999}),('/search',{'query':'unit-b03646cbf4','limit':2,'write':True})]:
 c=UnixHTTP('/run/aimee-native-read/search.sock',timeout=30);c.request('POST',path,json.dumps(payload),{'Content-Type':'application/json'});r=c.getresponse();r.read();rows.append({'case':'gateway '+path,'status':r.status,'denied':r.status in [400,403,404]});c.close()
view=json.load(open(root+'/CURRENT'))['view']
r=subprocess.run(['/opt/aimee-qwen-adapter/aimee-memory-image-v2','publish','--root',root,'--view',view,'--expected',view],capture_output=True,text=True)
rows.append({'case':'CLI publication','denied':r.returncode!=0,'error':r.stderr.strip()})
c=UnixHTTP('/run/aimee-native-read/search.sock',timeout=30);c.request('POST','/search',json.dumps({'query':'unit-b03646cbf4','limit':2}),{'Content-Type':'application/json'});r=c.getresponse();body=json.loads(r.read());rows.append({'case':'authorized read','status':r.status,'allowed':r.status==200,'ids':[f['id'] for f in body.get('facts',[])]});c.close()
print(json.dumps({'uid':os.getuid(),'checks':rows,'all_pass':all(x.get('denied',x.get('allowed',False)) for x in rows)},indent=2))
