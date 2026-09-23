"""Matched native-answer difference with workflow-cluster bootstrap intervals."""
import collections,json,random,sys
from pathlib import Path
def load(p):
 r=[json.loads(x) for x in (Path(p)/'results.jsonl').read_text().splitlines()]
 return {x['case_spec']['id']:x for x in r if x['enabled']}
a,b=map(load,sys.argv[1:3]);assert a.keys()==b.keys();groups=collections.defaultdict(list)
for k in a:
 for field in ['query','expected','scorer','workflow']:assert a[k]['case_spec'][field]==b[k]['case_spec'][field]
 assert a[k]['prompt_token_ids']==b[k]['prompt_token_ids']
 groups[a[k]['case_spec']['workflow']].append(int(b[k]['correct'])-int(a[k]['correct']))
effects=[sum(v)/len(v) for v in groups.values()];rng=random.Random(2026092405)
boot=sorted(sum(rng.choices(effects,k=len(effects)))/len(effects) for _ in range(10000))
print(json.dumps(dict(workflows=len(effects),tasks=len(a),first_correct=sum(x['correct'] for x in a.values()),second_correct=sum(x['correct'] for x in b.values()),gained=sum(not a[k]['correct'] and b[k]['correct'] for k in a),lost=sum(a[k]['correct'] and not b[k]['correct'] for k in a),mean_workflow_difference=sum(effects)/len(effects),workflow_bootstrap_95_percentile=[boot[249],boot[9749]],bootstrap_seed=2026092405,workflow_effects={k:sum(v)/len(v) for k,v in groups.items()},limitation='Exploratory workflow-resampled interval; not independent task-level trials.'),indent=2))
