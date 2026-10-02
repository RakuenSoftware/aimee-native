"""Freeze a repository-stratified subset before inference. No outcome filtering."""
import collections,hashlib,json,pathlib
import pyarrow.parquet as pq
p=pathlib.Path('/opt/swe-native');rows=pq.read_table(p/'full.parquet').to_pylist();by=collections.defaultdict(list)
for r in rows:by[r['repo']].append(r)
for group in by.values():group.sort(key=lambda r:hashlib.sha256(('aimee-20260926-v1:'+r['instance_id']).encode()).hexdigest())
selected=[]
while len(selected)<150:
 for repo in sorted(by):
  if by[repo] and len(selected)<150:selected.append(by[repo].pop())
(p/'selected-grader-only.json').write_text(json.dumps(selected))
public=[{k:r[k] for k in ['instance_id','repo','base_commit','problem_statement','version']} for r in selected]
(p/'tasks.json').write_text(json.dumps(public,indent=2)+'\n')
manifest={'dataset':'princeton-nlp/SWE-bench','full_count':len(rows),'count':len(selected),'selection':'round-robin repositories, SHA256(aimee-20260926-v1:instance_id) descending within repository','dataset_sha256':hashlib.sha256((p/'full.parquet').read_bytes()).hexdigest(),'tasks_sha256':hashlib.sha256((p/'tasks.json').read_bytes()).hexdigest(),'repositories':dict(collections.Counter(r['repo'] for r in selected))}
(p/'selection.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest))
