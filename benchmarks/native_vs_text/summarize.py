"""Read-only interim summary. Accuracy and reuse cohorts stay separate."""
import collections,json,statistics,sys
from pathlib import Path
root=Path(sys.argv[1]);out={}
for run in sorted(root.iterdir()):
    file=run/'results.jsonl'
    if not file.exists():continue
    rows=[]
    for line in file.read_text().splitlines():
        try:rows.append(json.loads(line))
        except json.JSONDecodeError:break # actively appended final line
    groups=collections.defaultdict(list)
    for r in rows:groups[(r['phase'],r['mode'])].append(r)
    summary={'complete':(run/'DONE').exists(),'rows':len(rows),'conditions':{},'errors':sum(bool(r.get('error')) for r in rows)}
    for (phase,mode),rs in groups.items():
        entry={'n':len(rs),'correct':sum(bool(r['correct']) for r in rs)}
        for key in ['model_request_seconds','request_seconds','ttft_seconds','native_preparation_seconds','prompt_tokens','completion_tokens','added_prompt_tokens','prefix_preparation_seconds']:
            vals=sorted(r[key] for r in rs if r.get(key) is not None)
            if vals:entry[key]={'n':len(vals),'median':statistics.median(vals),'mean':statistics.mean(vals),'p95':vals[min(len(vals)-1,int(.95*(len(vals)-1)))]}
        summary['conditions'][phase+'/'+mode]=entry
    paired=collections.defaultdict(dict)
    for r in rows:
        if r['phase']=='accuracy':paired[r['case']][r['mode']]=r
    pairs=[r for r in paired.values() if 'native' in r and 'text' in r]
    summary['native_vs_text']={'completed_pairs':len(pairs),'native_only_correct':sum(r['native']['correct'] and not r['text']['correct'] for r in pairs),'text_only_correct':sum(r['text']['correct'] and not r['native']['correct'] for r in pairs),'both_correct':sum(r['native']['correct'] and r['text']['correct'] for r in pairs)}
    out[run.name]=summary
print(json.dumps(out,indent=2))
