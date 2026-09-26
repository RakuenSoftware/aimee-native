"""Summarize the unchanged streaming evidence, keeping rounds separate."""
import argparse,hashlib,json,math,pathlib,statistics
p=argparse.ArgumentParser();p.add_argument('root',type=pathlib.Path);a=p.parse_args();root=a.root
report=json.loads((root/'serving/report.json').read_text());rows=report['rows']
assert report['status']=='passed' and len(rows)==336

def stats(x):
 x=sorted(x);return {'n':len(x),'median':statistics.median(x),'p95':x[math.ceil(.95*len(x))-1],'p99':x[math.ceil(.99*len(x))-1]}
summary={'scope':'Real Gemma Q8 TP2 vLLM, 32-record synthetic fixture, three rounds; repeated questions are not independent knowledge samples','correct':sum(r['correct'] for r in rows),'responses':len(rows),'conditions':{}}
for rnd in [None,1,2,3]:
 for mode in ['native','text']:
  rs=[r for r in rows if r['mode']==mode and (rnd is None or r['round']==rnd)]
  summary['conditions'][f'{mode}/round-{rnd or "all"}']={'correct':sum(r['correct'] for r in rs),**{k:stats([r[k] for r in rs]) for k in ['first_content_ms','request_ms']},**{k:stats([r['usage'][k] for r in rs]) for k in ['prompt_tokens','completion_tokens','total_tokens']}}
pairs={}
for r in rows:pairs.setdefault((r['round'],tuple(r['records_queried'])),{})[r['mode']]=r
summary['prompt_tokens_avoided']=sum(v['text']['usage']['prompt_tokens']-v['native']['usage']['prompt_tokens'] for v in pairs.values())
summary['activation']={n:json.loads((root/(n+'-activation.json')).read_text())['summary'] for n in ['alpha','wide']}
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(root/'SHA256.json').write_text(json.dumps({str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(root.rglob('*')) if f.is_file() and f.name!='SHA256.json'},indent=2)+'\n')
print(json.dumps(summary,indent=2))
