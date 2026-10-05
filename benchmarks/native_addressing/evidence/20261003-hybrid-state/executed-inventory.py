import hashlib,json
from pathlib import Path
rows=[]
for label,directory in [('implicit','/tmp/native-hybrid-holdout-archive-20261003'),('grounded','/tmp/native-hybrid-grounded-archive-20261003')]:
 root=Path(directory)/'published';view=json.loads((root/'CURRENT').read_text())['view'];manifest=json.loads((root/'objects'/view).read_text());index=json.loads((root/'objects'/manifest['index']).read_text());records=[];count=0
 with (root/'objects'/manifest['data']).open('rb') as f:
  for line in f:
   r=json.loads(line);count+=1
   if not r['id'].startswith('distractor'):records.append(r)
 assert count==len(index['entries'])
 for objectid in [view,manifest['data'],manifest['index']]:assert hashlib.sha256((root/'objects'/objectid).read_bytes()).hexdigest()==objectid
 rows.append({'label':label,'view':view,'physical_records':count,'data_sha256':manifest['data'],'index_sha256':manifest['index'],'canonical_relevant_records':records,'approved_routes':manifest.get('serving',{}).get('candidate_routes',[]),'scaling':json.loads((Path(directory)/'scaling.json').read_text())})
Path('/tmp/native-hybrid-inventory.json').write_text(json.dumps(rows,indent=2)+'\n')
print([(r['label'],r['physical_records'],len(r['canonical_relevant_records'])) for r in rows])
