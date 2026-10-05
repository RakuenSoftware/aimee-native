"""Verify full trace coverage and exact gates; do not infer success from counts."""
import argparse,hashlib,itertools,json,statistics
from pathlib import Path
from campaign import new_json

def summarize(root):
 root=Path(root);out={};all_rows=[]
 for name in ['development-online','holdout-online','development-strict-prepared','holdout-strict-prepared']:
  directory=root/name;protocol=json.loads((directory/'protocol.json').read_text());result=json.loads((directory/'results.json').read_text());rows=result['rows'];tasks={t['id']:t for t in protocol['tasks']}
  expected=set(itertools.product(protocol['schedules'],protocol['turns'],tasks));seen=set();groups={}
  for row in rows:
   key=(row['schedule'],row['turns'],row['task']);assert key in expected and key not in seen;seen.add(key)
   raw=(directory/row['trace']).read_bytes();assert hashlib.sha256(raw).hexdigest()==row['trace_sha256'];trace=json.loads(raw);task=tasks[row['task']]
   answer=trace['answer'].strip().rstrip('.');assert answer==row['answer'];correct=answer.lower()==task['answer'].lower()
   actual={(f['memory_ref']['namespace'],f['memory_ref']['id'],f['memory_ref']['revision']) for e in trace['recall_events'] for f in e.get('aimee_response',{}).get('facts',[])}
   required={('public-research-fixture',identifier,'1') for identifier in task['expected']};selection=required<=actual if required else not actual
   assert correct==row['correct'] and selection==row['selection_correct'];assert correct and selection
   assert trace['native_recurrent_state'] is True and trace['memory_prompt_tokens']==0
   assert trace['native_memory_metrics']==row['metrics'];metrics=row['metrics']
   assert metrics['peak_active_records']<=6 and metrics['peak_active_positions']<=2048
   assert metrics['peak_active_recurrent_bytes']<=256*1024**2
   if row['schedule']=='preload-only':assert metrics['source_reads']==1
   if row['schedule']=='bounded-refresh':assert metrics['source_reads']<=8
   if 'strict-prepared' in name:assert trace['memory_encoding_passes']==0
   group=groups.setdefault(row['schedule'],{'n':0,'correct':0,'selection_correct':0,'source_reads':0,'replays':0,'elapsed_ms':[]})
   for field in ('n','correct','selection_correct'):group[field]+=1
   group['source_reads']+=metrics['source_reads'];group['replays']+=metrics['native_replays'];group['elapsed_ms'].append(row['elapsed_ms']);all_rows.append(row)
  assert seen==expected and result['n']==len(expected)
  for group in groups.values():group['median_elapsed_ms']=statistics.median(group.pop('elapsed_ms'))
  out[name]={'n':len(rows),'correct':sum(r['correct'] for r in rows),'selection_correct':sum(r['selection_correct'] for r in rows),'schedules':groups,'binary_sha256':protocol['binary_sha256'],'protocol_sha256':hashlib.sha256((directory/'protocol.json').read_bytes()).hexdigest()}
 for prefix in ['development','holdout']:
  online=json.loads((root/(prefix+'-online')/'results.json').read_text())['rows'];prepared=json.loads((root/(prefix+'-strict-prepared')/'results.json').read_text())['rows']
  assert {(r['schedule'],r['turns'],r['task'],r['answer']) for r in online}=={(r['schedule'],r['turns'],r['task'],r['answer']) for r in prepared}
 assert len({cell['binary_sha256'] for cell in out.values()})==1
 return {'schema':'complete-hybrid-validation-v1','gate':'passed','campaigns':out,'total_requests':len(all_rows),'correct':sum(r['correct'] for r in all_rows),'selection_correct':sum(r['selection_correct'] for r in all_rows),'max_native_positions':max(r['metrics']['peak_active_positions'] for r in all_rows),'max_native_records':max(r['metrics']['peak_active_records'] for r in all_rows),'max_logical_attention_bytes':max(r['metrics']['peak_active_encoded_bytes'] for r in all_rows),'max_immutable_recurrent_bytes':max(r['metrics']['peak_active_recurrent_bytes'] for r in all_rows),'scope':'public synthetic full-model native engineering; exact cue owner routing; frozen new facts; no production deployment or universal accuracy claim','timing_scope':'descriptive HTTP wall; fixed run order, startup excluded; no speedup claim'}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root');p.add_argument('--output',required=True);a=p.parse_args();new_json(a.output,summarize(a.root))
