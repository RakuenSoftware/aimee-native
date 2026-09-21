"""Research-only protocol check of the actual Aimee module SQL path."""
import json,http.client,socket,subprocess
from pathlib import Path
path='/run/aimee-restricted-upstream.sock'
class Unix(http.client.HTTPConnection):
 def connect(self):self.sock=socket.socket(socket.AF_UNIX);self.sock.settimeout(30);self.sock.connect(path)
query='Authoritative unit-b03646cbf4 Answer user Give default unit-b03646cbf4 unit-121330aded with assistant think think'
rows=[]
for label,ids,q in [('both',[5,6],query),('drink',[5],query),('city',[6],query),('empty',[],query),('missing',[5,6],'nonexistent-sentinel-zkqj')]:
 c=Unix('localhost');body={'keywords':[q],'limit':2,'restriction':{'version':1,'namespace':'aimee-published','authorization':'a'*64,'ids':ids}}
 c.request('POST','/v1/memory/search',json.dumps(body),{'Content-Type':'application/json'});r=c.getresponse();payload=json.load(r);c.close()
 rows.append({'case':label,'status':r.status,'ids':[f['id'] for f in payload.get('facts',[])],'error':payload.get('error')})
print(json.dumps(rows,indent=2))
assert [r['ids'] for r in rows]==[[5,6],[5],[6],[],[]] or [r['ids'] for r in rows]==[[6,5],[5],[6],[],[]]
assert all(r['status']==200 for r in rows)
