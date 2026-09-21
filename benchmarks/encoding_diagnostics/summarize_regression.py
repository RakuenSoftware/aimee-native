"""Audit paired prompt/bank identity and report all scores, including routing misses."""
import argparse, collections, json
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); a=p.parse_args()
rows=list(map(json.loads,(a.root/'regression.jsonl').read_text().splitlines()))
groups=collections.defaultdict(list)
for r in rows: groups[(r['format'],r['before_prompt'])].append(r)
by_case=collections.defaultdict(list)
for r in rows: by_case[r['case']].append(r)
checks=[]
for case, variants in by_case.items():
    reference=next(r for r in variants if r['format']=='content' and not r['before_prompt'])
    def bank(r): return r['bank_events'][-1] if r['bank_events'] else []
    checks.append(dict(case=case,variants=len(variants),same_prompt=all(r['prompt_token_ids']==reference['prompt_token_ids'] for r in variants),same_ordered_bank=all(bank(r)==bank(reference) for r in variants),has_memory=bool(bank(reference))))
summary=dict(groups=[dict(format=fmt,before_prompt=before,total=len(rr),passed=sum(r['pass_'] for r in rr),original_passed=sum(r['pass_'] for r in rr if not r['case'].startswith('new-place')),original_total=sum(not r['case'].startswith('new-place') for r in rr),failures=[dict(case=r['case'],answer=r['answer'],bank=r['bank_events'][-1] if r['bank_events'] else []) for r in rr if not r['pass_']]) for (fmt,before),rr in groups.items()],comparisons=checks)
(a.root/'regression-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
assert len(rows)==138 and len(by_case)==46 and all(c['variants']==3 for c in checks)
assert all(c['same_prompt'] and c['same_ordered_bank'] for c in checks)
