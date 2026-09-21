"""Deterministic held-out question forms; never feed these into KB construction."""
from pathlib import Path
import json,random
root=Path(__file__).resolve().parents[2]
records=json.loads((root/'knowledge/general-v1/records.json').read_text())['records'];by={r['id']:r for r in records};rng=random.Random(20260920)
cases=[]
def add(label,r,query,expected,kind='exact',**more):cases.append(dict(id=label,domain=r['metadata']['semantic']['domain'],query=query,expected=str(expected),scorer=kind,memory_ids=[r['id']],**more))
ports=[]
for r in records:
 if r['metadata']['semantic']['domain']!='iana':continue
 a=r['metadata']['semantic']['assignments'];tcp={x['port'] for x in a if x['protocol']=='tcp'}
 if len(tcp)==1 and 1024<next(iter(tcp))<49152:ports.append(r)
chosen=rng.sample(ports,12)
for i,r in enumerate(chosen):
 port=next(x['port'] for x in r['metadata']['semantic']['assignments'] if x['protocol']=='tcp')
 q=f'Which TCP port is registered for {r["key"]}? Reply with the port number only.' if i%2==0 else f'For {r["key"]}, give its registered TCP port as one integer.'
 add('port-'+str(i),r,q,port,'number')
planets=[r for r in records if r['metadata']['semantic']['domain']=='nasa' and int(r['metadata']['semantic']['disc_year'])>=2025 and r['metadata']['semantic']['pl_orbper']]
for i,r in enumerate(rng.sample(planets,8)):
 s=r['metadata']['semantic'];q=f'According to the NASA archive, what is the orbital period in days for {r["key"]}? Return the number only.'
 add('planet-'+str(i),r,q,s['pl_orbper'],'number')
countries=[r for r in records if r['metadata']['semantic']['domain']=='worldbank' and r['metadata']['semantic']['capitalCity']]
for i,r in enumerate(rng.sample(countries,4)):add('capital-'+str(i),r,f'What capital city does the World Bank list for {r["key"]}? Return the city name only.',r['metadata']['semantic']['capitalCity'])
constants=[r for r in records if r['metadata']['semantic']['domain']=='nist' and '...' not in r['metadata']['semantic']['value']]
for i,r in enumerate(rng.sample(constants,4)):
 add('constant-'+str(i),r,f'Give the 2022 CODATA numerical value for {r["key"]}. Return the value only, without units.',r['metadata']['semantic']['value'].replace(' ',''),'number')
for i in range(3):
 a,b=chosen[2*i:2*i+2];vals=[next(x['port'] for x in r['metadata']['semantic']['assignments'] if x['protocol']=='tcp') for r in [a,b]]
 cases.append(dict(id='compose-'+str(i),domain='composition',query=f'Give the registered TCP ports for {a["key"]} and {b["key"]}, in that order. Return two integers separated by a semicolon.',expected=';'.join(map(str,vals)),scorer='pair',memory_ids=[a['id'],b['id']]))
for i,r in enumerate(chosen[:2]):
 port=next(x['port'] for x in r['metadata']['semantic']['assignments'] if x['protocol']=='tcp')
 cases.append(dict(id='personal-'+str(i),domain='personal_composition',query=f'Give the TCP port for {r["key"]}, then the preferred drink of unit-b03646cbf4, then the home city of unit-121330aded. Separate the three values with semicolons.',expected=f'{port};oolong;Lima',scorer='pair',memory_ids=[r['id']],personal=True))
cases.append(dict(id='unknown',domain='abstention',query='What is the registered TCP port of IANA service aimee-nonexistent-zq81927? Return unknown if unavailable.',expected='unknown',scorer='exact',memory_ids=[]))
(root/'benchmarks/general_kb/cases.json').write_text(json.dumps(cases,indent=2)+'\n')
print('cases',len(cases),'source objects',len(records))
