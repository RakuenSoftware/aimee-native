"""Read-only operator audit on the designated Proxmox host; no model calls."""
import argparse,hashlib,json,pathlib,subprocess,time

parser=argparse.ArgumentParser();parser.add_argument("--study",choices=["source-learning-20260927","broader-source-learning-20260928"],default="source-learning-20260927");args=parser.parse_args()

def read_ct(number,source):
 return json.loads(subprocess.check_output(['pct','exec',str(number),'--','python3','-'],input=source,text=True))

study_script='''import json,pathlib,time
r=pathlib.Path('/opt/swe-native/STUDY_NAME');rows=[]
def read_json(p):
 for attempt in range(10):
  try:return json.loads(p.read_text())
  except json.JSONDecodeError:
   if attempt==9:raise
   time.sleep(.05)
arms=STUDY_ARMS
for task in json.loads((r/'tasks.json').read_text()):
 for i,arm in enumerate(arms):
  p=r/'results'/arm/task['instance_id'];t=p/'trajectory.json'
  if not t.exists():continue
  d=read_json(t);row={'instance_id':task['instance_id'],'arm':arm,'text_memory':d.get('text_memory'),'native_publication':d.get('native_publication'),'calls':[c['publication'] for c in d.get('native_calls',[])],'finished':d['messages'][-1]['role']=='exit'}
  if i:
   row['source']=read_json(r/'results'/arms[i-1]/task['instance_id']/'next-publication.json')
  rows.append(row)
print(json.dumps(rows))
'''
arms=['source-control','source-learn-1'] if args.study.startswith('broader-') else ['source-control','source-learn-1','source-learn-2','source-learn-3']
study=read_ct(113,study_script.replace('STUDY_NAME',args.study).replace('STUDY_ARMS',repr(arms)))
keys=sorted({r['source']['publication'] for r in study if 'source' in r})
source="import json,pathlib\nr=pathlib.Path('/opt/aimee-memory-lab/swe-learning-20260926/banks');data={}\n"
source+="for key in "+repr(keys)+":\n data[key]={'experience':json.loads((r/key/'experience.json').read_text()),'index':json.loads((r/key/'index.json').read_text()),'payload_bytes':(r/key/'compact.pack').stat().st_size}\nprint(json.dumps(data))\n"
banks=read_ct(101,source)
report={'study':args.study,'status':'running','observed_at':time.time(),'scope':'Complete-record source provenance and request routing audit for observed calls, including in-progress attempts. Does not independently prove tensor semantics or model accuracy.','attempts':[],'publications':{}}
try:
 for row in study:
  assert row['text_memory'] is None,(row['instance_id'],row['arm'],'text memory supplied')
  expected=None
  if 'source' in row:
   pub=row['source'];expected=pub['publication'];fact=pub['complete_fact'];bank=banks[expected];experience=bank['experience'];identity=experience['identity']
   assert pub['records']==1 and experience['facts']==[fact]
   assert hashlib.sha256(fact.encode()).hexdigest()==pub['fact_sha256']
   assert [record['revision'] for record in identity['records']]==[pub['fact_sha256']]
   assert hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()==expected
   assert identity['encoding_revision']=='native-swe-v2-fp32'
   assert bank['payload_bytes']==pub['payload_bytes']
   report['publications'][expected]={'records':1,'fact_sha256':pub['fact_sha256'],'encoding_revision':identity['encoding_revision'],'payload_bytes':bank['payload_bytes'],'source_exact':True}
  assert row['native_publication']==expected,(row['instance_id'],row['arm'],'trajectory publication')
  assert all(p==expected for p in row['calls']),(row['instance_id'],row['arm'],'request publication')
  report['attempts'].append({'instance_id':row['instance_id'],'arm':row['arm'],'publication':expected,'calls_checked':len(row['calls']),'finished':row['finished'],'routing_exact':True})
 report['status']='passed'
except BaseException as error:
 report.update(status='failed',error=repr(error));raise
finally:
 root=pathlib.Path('/root/aimee-release-cert-20260927');target=root/(args.study+'-delivery-audit-'+str(int(report['observed_at']))+'.json');target.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'report':str(target),'attempts':len(report['attempts']),'publications':len(report['publications']),'calls':sum(r['calls_checked'] for r in report['attempts'])}))
