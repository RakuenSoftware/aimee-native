"""Locate exact superseded Ubuntu/PPA sources; never substitute a newer version.

Returned publication records and source URLs are evidence of availability,
not downloaded source, checksum verification or redistribution approval.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import urllib.parse
import urllib.request

ARCHIVES={
 'curl':'ubuntu/+archive/primary',
 'pyjwt':'ubuntu/+archive/primary',
 'gcc-13':'~ubuntu-toolchain-r/+archive/ubuntu/test',
 'gcc-16':'~ubuntu-toolchain-r/+archive/ubuntu/test',
 'python3.12':'~deadsnakes/+archive/ubuntu/ppa',
}
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--plan',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
plan=json.loads(a.plan.read_text())
rows=[r for r in plan['packages'] if r['status']=='unresolved' and r['source'] in ARCHIVES]
def get(url):
 with urllib.request.urlopen(url,timeout=30) as response:return json.load(response)
def resolve(row):
 source,version=row['source'],row['version']
 query=urllib.parse.urlencode({'ws.op':'getPublishedSources','source_name':source,'version':version,'exact_match':'true'})
 url='https://api.launchpad.net/1.0/'+ARCHIVES[source]+'?'+query
 result=dict(source=source,version=version,query=url)
 try:
  data=get(url)
  result['publication_response']=data
  entries=[e for e in data.get('entries',[]) if e.get('source_package_name')==source and e.get('source_package_version')==version]
  result['status']='not_found'
  for entry in entries:
   reference=entry['self_link']
   assert reference.startswith('https://api.launchpad.net/1.0/')
   files=get(reference+'?ws.op=sourceFileUrls')
   if files:
    assert all(urllib.parse.urlsplit(u).scheme=='https' and urllib.parse.urlsplit(u).hostname=='launchpad.net' for u in files)
    result.update(status='publication_located',publication=reference,files=files)
    break
 except Exception as error:result.update(status='lookup_failed',error=repr(error))
 return result
with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(resolve,rows))
report=dict(scope=__doc__,results=results,located=sum(r['status']=='publication_located' for r in results))
a.output.parent.mkdir(parents=True,exist_ok=True)
with a.output.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({r['source']:r['status'] for r in results}))
