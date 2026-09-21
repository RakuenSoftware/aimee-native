"""Deterministic factual source import. No training, serving, or grant issuance."""
from pathlib import Path
from collections import defaultdict,Counter
import csv,hashlib,json,re
ROOT=Path(__file__).resolve().parent
NS='aimee-general-v1'
def encoded(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def build():
 manifest=json.loads((ROOT/'sources/manifest.json').read_text());records=[]
 for name,meta in manifest.items():
  assert hashlib.sha256((ROOT/'sources'/name).read_bytes()).hexdigest()==meta['sha256'],name
 def add(domain,ident,key,content,semantic,source,locator):
  meta=manifest[source]
  metadata={'semantic':dict(domain=domain,**semantic),'provenance':{'source_url':meta['url'],'checked_on':meta['retrieved_at'][:10],'retrieved_at':meta['retrieved_at'],'source_sha256':meta['sha256'],'locator':locator}}
  revision=hashlib.sha256(encoded(dict(key=key,content=content,metadata=metadata))).hexdigest()
  records.append(dict(namespace=NS,id=domain+'.'+ident,revision=revision,scope={'type':'global','value':'_global'},key=key,content=content,kind='fact',tier='L3',confidence=1,lifecycle='active',metadata=metadata))
 services=defaultdict(set)
 for row in csv.DictReader((ROOT/'sources/iana-services.csv').open()):
  name=row['Service Name'].strip().lower();port=row['Port Number'];protocol=row['Transport Protocol']
  if name and port.isdigit() and protocol in ['tcp','udp','sctp','dccp']:
   services[name].add((protocol,int(port)))
 for name,assignments in sorted(services.items()):
  a=[dict(protocol=p,port=n) for p,n in sorted(assignments)]
  desc='; '.join(f'{p.upper()} port {n}' for p,n in sorted(assignments))
  add('iana',name,'IANA service '+name,f'IANA service {name} has these registered transport/port assignments: {desc}.',{'subject':name,'assignments':a},'iana-services.csv',{'service_name':name})
 for row in csv.DictReader((ROOT/'sources/nasa-planets.csv').open()):
  name=row['pl_name'];facts=[f'host star {row["hostname"]}',f'discovery year {row["disc_year"]}',f'discovery method {row["discoverymethod"]}',f'discovery facility {row["disc_facility"]}']
  if row['pl_orbper']:facts.append(f'orbital period {row["pl_orbper"]} days')
  # The composite table can contain derived parameters. Keep source values as
  # reported, without asserting that every number is a direct measurement.
  if row['pl_rade']:facts.append(f'reported planet radius {row["pl_rade"]} Earth radii')
  if row['sy_dist']:facts.append(f'reported system distance {row["sy_dist"]} parsecs')
  add('nasa',name,'planet '+name,f'For planet {name}, the NASA Exoplanet Archive composite table lists: '+ '; '.join(facts)+'.',dict(row),'nasa-planets.csv',{'pl_name':name})
 for line in (ROOT/'sources/nist-constants.txt').read_text().splitlines()[11:]:
  if not line.strip():continue
  label,value,uncertainty,unit=(line[:60].strip(),line[60:85].strip(),line[85:110].strip(),line[110:].strip())
  if not value:continue
  add('nist',re.sub('[^a-z0-9]+','-',label.lower()).strip('-'),'constant '+label,f'The 2022 CODATA value of the constant {label} is {value} {unit}. Its standard uncertainty is {uncertainty}.',dict(subject=label,value=value,unit=unit,uncertainty=uncertainty,adjustment=2022),'nist-constants.txt',{'quantity':label})
 for row in json.loads((ROOT/'sources/worldbank-countries.json').read_text())[1]:
  if row['region']['id']=='NA':continue # aggregate regions are not economies
  name=row['name'];semantic={k:row[k] for k in ['id','iso2Code','name','capitalCity','longitude','latitude']}
  semantic['region']=row['region']['value'].strip();semantic['income_level']=row['incomeLevel']['value']
  capital=f'capital city {row["capitalCity"]}; ' if row['capitalCity'] else ''
  add('worldbank',row['id'],'economy '+name,f'The World Bank country endpoint lists economy {name}: code {row["id"]}; two-letter code {row["iso2Code"]}; {capital}region {semantic["region"]}; income group {semantic["income_level"]}.',semantic,'worldbank-countries.json',{'id':row['id']})
 records.sort(key=lambda r:r['id'])
 assert len({r['id'] for r in records})==len(records)
 assert all('CANARY_' not in r['content'] and len(r['content'])<8192 for r in records)
 change=dict(namespace=NS,kind='general',generation=1,source='Official reference snapshot: IANA / NASA Exoplanet Archive / NIST CODATA 2022 / World Bank',coverage=['canonical_facts','source_provenance','named_reference_lookup'],records=records)
 data=json.dumps(change,ensure_ascii=False,indent=2)+'\n';(ROOT/'records.json').write_text(data)
 summary=dict(records=len(records),domains=dict(sorted(Counter(r['metadata']['semantic']['domain'] for r in records).items())),canonical_json_bytes=len(data.encode()),content_bytes=sum(len(r['content'].encode()) for r in records),sha256=hashlib.sha256(data.encode()).hexdigest(),read_contracts=0,synthetic_records=0)
 (ROOT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');return summary
if __name__=='__main__':print(json.dumps(build(),indent=2))
