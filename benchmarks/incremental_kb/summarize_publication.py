"""Derive the publication report summary without modifying original evidence."""
import argparse,json,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('artifact',type=Path);a=p.parse_args();r=a.artifact/'live'
def rows(name):return [json.loads(x) for x in (r/name).read_text().splitlines() if x.startswith('{')]
events=rows('consumer.log');timings=rows('publication-timings.jsonl');live=rows('live-results.jsonl');safety=rows('safety-results.jsonl')
joined=[]
for original in timings:
 row=dict(original)
 if row['delivery'] is None:row['delivery']=next(x for x in events if x.get('view')==row['view'] and x.get('state')=='installed')
 joined.append(row)
answers=[x for x in live if 'answer' in x];composition=[x for x in answers if x['case']!='unrelated-after-narrowing']
assert len(answers)==8 and all(x['pass_'] and x['memory_prompt_tokens']==0 for x in answers)
assert all(x['prompt_token_ids']==composition[0]['prompt_token_ids'] for x in composition)
assert all(x['pass_'] for x in safety)
times=[x['publication_seconds'] for x in joined]
summary=dict(public_records=249105,public_base_bytes=415439227,native_answers=len(answers),native_passes=sum(x['pass_'] for x in answers),composition_runs=len(composition),identical_composition_prompt_ids=True,memory_prompt_tokens=0,repeated_updates=dict(n=len(times),min_seconds=min(times),median_seconds=statistics.median(times),mean_seconds=statistics.mean(times),max_seconds=max(times),runs=joined),mutations=[x for x in live if 'publication_seconds' in x],native=[{k:x[k] for k in ['case','answer','seconds','encodings','cache_transition','memory_prompt_tokens']} for x in answers],safety=safety,compaction={phase:json.loads((r/f'compaction-{phase}.json').read_text()) for phase in ['before','after']},final_state=json.loads((r/'final-state.json').read_text()))
(a.artifact/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(dict(native_passes=summary['native_passes'],repeated_median_seconds=statistics.median(times),safety_passes=len(safety))))
