"""Summarize admission, positions, next-token margins and observed attention.
Attention mass is descriptive; causal claims require the controlled ablations.
"""
import argparse,json,math,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root
rows=[]
for file in ['formats.jsonl','positions.jsonl','controls.jsonl']:
 if (root/file).exists():rows += [dict(json.loads(x),phase=file[:-6]) for x in (root/file).read_text().splitlines()]
summary=[];baselines={}
for row in rows:
 trace=json.loads((root/'traces'/(row['response']['id']+'.json')).read_text())
 events=row.get('encoding_events',[])
 enc=events[-1]['encoding'] if events else {}
 ordered_refs=events[-1].get('bank_memory_ids') if events else []
 if row['phase']=='formats' and row['format']=='content':baselines[row['case']]=(row['prompt_token_ids'],ordered_refs)
 base=baselines.get(row['case']);same=base==(row['prompt_token_ids'],ordered_refs)
 logits=trace.get('logit_trace',[])
 step0=logits[0] if logits else {}
 candidates={r['text']:math.exp(r['logp']) for r in step0.get('candidates',[])}
 targets={}
 # Decode via token offsets recorded in source regions; values' token ranges
 # are derived later with the same tokenizer rather than guessing word spans.
 attention=[]
 for point in trace.get('attention_trace') or []:
  if point['step']!=0:continue
  weights=point['weights'];n=point['memory_tokens'];by_record=[]
  for region in enc.get('regions',[]):
   by_record.append(dict(id=region['memory_ref']['id'],mass=sum(weights[i] for i in region['record_positions']),key_mass=sum(weights[i] for i in region['key_positions'])))
  attention.append(dict(layer=point['layer'],native_mass=sum(weights[:n]),records=by_record))
 item={k:row[k] for k in ['phase','case','format','shift','before_prompt','native','tag','answer','pass_','seconds']}
 # These probes require exact fields, not exact whitespace around separators.
 # Preserve the archived strict scorer; report factual match separately.
 if row['case'].startswith('personal'):
  value_match = [x.strip().lower() for x in row['answer'].split(';')] == [x.strip().lower() for x in row['expected'].split(';')]
 else:
  value_match = row['pass_']
 drink = {}
 if row['case'].startswith('personal') and len(logits) > 5:
  point = logits[5]
  drink = dict(step=5, prefix_token_ids=trace['generated_token_ids'][:5], candidates={r['text']:math.exp(r['logp']) for r in point['candidates'] if r['text'] in ['oolong','unknown']})
  drink['attention'] = []
  for point in trace.get('attention_trace') or []:
   if point['step'] != 5: continue
   by_record = {region['memory_ref']['id']:sum(point['weights'][i] for i in region['record_positions']) for region in enc.get('regions',[])}
   drink['attention'].append(dict(layer=point['layer'],record_mass=by_record))
 item.update(value_match=value_match,drink_decision=drink)
 item.update(same_prompt_and_ordered_bank=same if row['native'] else None,ordered_refs=ordered_refs,memory_tokens=len(enc.get('token_ids',[])),prompt_tokens=len(row['prompt_token_ids']),first_token_candidates=candidates,attention_step0=attention,trace=row['response']['id'])
 summary.append(item)
(root/'analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
for r in summary:
 print(json.dumps({k:r[k] for k in ['phase','case','format','shift','before_prompt','answer','same_prompt_and_ordered_bank','memory_tokens','first_token_candidates']}))
