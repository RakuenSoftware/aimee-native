"""Snapshot primary-source reference data. Offline build tooling, never serving."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import datetime,hashlib,json,urllib.request,urllib.parse
ROOT=Path(__file__).resolve().parent
SOURCES={
 'iana-services.csv':'https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.csv',
 'nist-constants.txt':'https://physics.nist.gov/cuu/Constants/Table/allascii.txt',
 'nasa-planets.csv':'https://exoplanetarchive.ipac.caltech.edu/TAP/sync?'+urllib.parse.urlencode({'query':'select pl_name,hostname,discoverymethod,disc_year,disc_facility,pl_orbper,pl_rade,sy_dist from pscomppars order by pl_name','format':'csv'}),
 'worldbank-countries.json':'https://api.worldbank.org/v2/country?format=json&per_page=400',
}
def fetch(item):
 name,url=item
 request=urllib.request.Request(url,headers={'User-Agent':'Aimee-KB-Research/0.1 (public reference snapshot)'})
 with urllib.request.urlopen(request,timeout=90) as r:data=r.read(32<<20);ctype=r.headers.get('Content-Type')
 path=ROOT/'sources'/name;path.write_bytes(data)
 return name,dict(url=url,retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),content_type=ctype)
if __name__=='__main__':
 rows={}
 with ThreadPoolExecutor(max_workers=4) as pool:
  for name,meta in pool.map(fetch,SOURCES.items()):rows[name]=meta;print(name,meta['bytes'],flush=True)
 (ROOT/'sources/manifest.json').write_text(json.dumps(rows,indent=2)+'\n')
