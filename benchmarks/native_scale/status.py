"""Read-only campaign progress, including paired fact recovery."""
import collections,json,sys,time
from pathlib import Path
root=Path(sys.argv[1]);out={}
for name in ['native-scale-gemma-r1','native-scale-qwen-r1']:
 p=root/name/'results.jsonl'
 if not p.exists():continue
 groups=collections.defaultdict(lambda:dict(n=0,correct=0,errors=0,unknown=0));pairs=collections.defaultdict(dict)
 for line in p.read_text().splitlines():
  try:r=json.loads(line)
  except json.JSONDecodeError:continue
  c=r['case_spec'];g=groups[c['source']+('-native' if r['enabled'] else '-disabled')];g['n']+=1;g['correct']+=r['correct'];g['errors']+='error' in r;g['unknown']+=r['abstained'];pairs[c['id']][r['enabled']]=r
 out[name]={'groups':dict(groups),'completed':sum(g['n'] for g in groups.values()),'done':(p.parent/'DONE').exists(),'recovered':sum(len(v)==2 and not v[False]['correct'] and v[True]['correct'] for v in pairs.values()),'regressed':sum(len(v)==2 and v[False]['correct'] and not v[True]['correct'] for v in pairs.values())}
print(json.dumps(out,indent=2))
