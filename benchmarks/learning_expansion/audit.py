"""Independent category and causal-context accounting from saved rows."""
import json,statistics,sys,hashlib,re
from pathlib import Path
from collections import defaultdict
root=Path(sys.argv[1]);fixture=json.loads((root/'fixture.json').read_text()); rows=[]
for rep in range(fixture['process_repetitions']):
 m=json.loads((root/f'metadata-{rep}.json').read_text());L=m['layer_count']; B=m['bytes_per_KV_token']
 assert m['all_parameter_devices']==['cuda:0']
 for line in (root/f'rows-{rep}.jsonl').read_text().splitlines():
  r=json.loads(line); rows.append(r); H=r['prior_history_tokens']; P=r['selected_prefix_tokens']; Q=len(r['task_token_ids']);M=r['prefill_memory_tokens'];D=r['decode_tokens'];C=r['prefill_cleanup_tokens']
  assert r['prefill_tokens']==M+Q+C and r['prefill_task_tokens']==Q
  base=H+(M if r['arm']=='persistent-text' else 0)
  predicted=L*(M*H+M*(M+1)//2+Q*P+Q*(Q+1)//2+D*(P+Q)+D*(D+1)//2+C*base+C*(C+1)//2)
  assert r['attention_memory']+r['attention_task_and_decode']+r['attention_cleanup']==r['attention_context_steps']
  assert predicted==r['attention_context_steps'],(r['arm'],r['episode'],r['turn'],predicted,r['attention_context_steps'])
  assert r['cache_bytes_before']==B*H and r['cache_bytes_after_cleanup']==B*r['public_history_tokens']
  assert r['history_reprefill_tokens']==0 and r['window_headroom_tokens']>=0
cells=defaultdict(list)
for r in rows: cells[(r['record_target_tokens'],r['history_target'],r['arm'])].append(r)
bykey={(r['repeat'],r['episode'],r['arm'],r['turn']):r for r in rows}; result=[]
for (size,h,arm),rr in sorted(cells.items()):
 selected=[r for r in rr if r['kind']=='injection'];withdraw=[r for r in rr if r['kind']=='withdrawal']; unrelated=[r for r in rr if r['kind']=='unrelated']
 correct=lambda rr:sum(r['answer'].strip().lower().rstrip('.').strip()==r['expected'] for r in rr)
 item={'record_tokens':size,'additional_history_tokens':h,'arm':arm,'requests':len(rr),'selected_correct':correct(selected),'selected_n':len(selected),'withdrawal_correct':correct(withdraw),'withdrawal_n':len(withdraw),'unrelated_correct':correct(unrelated),'unrelated_n':len(unrelated),'old_code_echoes':sum(any(re.search(r'\b'+re.escape(v)+r'\b',r['answer']) for v in r['forbidden']) for r in withdraw),'prefill_by_category':{k:sum(r[k] for r in rr) for k in ['prefill_memory_tokens','prefill_task_tokens','prefill_cleanup_tokens']},'attention_context_steps':sum(r['attention_context_steps'] for r in rr),'cache_byte_seconds_stage_proxy':sum(r['cache_byte_seconds_stage_proxy'] for r in rr),'selected_turn_median_ms':statistics.median(r['turn_total_seconds'] for r in selected)*1000,'attachment_median_ms':statistics.median(r['attachment_seconds'] for r in selected)*1000,'maximum_public_history_tokens':max(r['public_history_tokens'] for r in rr),'minimum_window_headroom_tokens':min(r['window_headroom_tokens'] for r in rr)}
 if arm=='native-at-injection':item['paired_native_minus_removed_turn_median_ms']=statistics.median((r['turn_total_seconds']-bykey[(r['repeat'],r['episode'],'removed-text',r['turn'])]['turn_total_seconds'])*1000 for r in selected)
 result.append(item)
episodes=defaultdict(dict)
for r in rows:
 k=(r['repeat'],r['episode']);episodes[k].setdefault(r['arm'],[]).append(r)
cold=[]
for (rep,eid),arms in sorted(episodes.items()):
 n=arms['native-at-injection'];t=arms['removed-text'];p=arms['persistent-text'];prep=n[0]['episode_bank_preparation_seconds'];boot=n[0]['bootstrap_seconds']
 cold.append({'repeat':rep,'episode':eid,'record_tokens':n[0]['record_target_tokens'],'additional_history_tokens':n[0]['history_target'],'bootstrap_seconds_common':boot,'native_bank_preparation_seconds':prep,'native_complete_episode_seconds':sum(r['turn_total_seconds'] for r in n)+prep+boot,'removed_complete_episode_seconds':sum(r['turn_total_seconds'] for r in t)+boot,'persistent_complete_episode_seconds':sum(r['turn_total_seconds'] for r in p)+boot,'native_minus_removed_including_preparation_seconds':sum(r['turn_total_seconds'] for r in n)-sum(r['turn_total_seconds'] for r in t)+prep})
output={'passed':True,'cold_episode_cost':cold,'requests':len(rows),'cells':result,'maximum_cuda_reserved_bytes':max(r['cuda_reserved_bytes'] for r in rows),'scope':'24-turn synthetic record-size pressure; BF16 full-attention Qwen3-0.6B. Context-steps are verified causal query-key counts, not kernel FLOPs. Stage byte-time is an endpoint proxy and excludes idle intervals/other concurrent cache owners. No window-saturation result inferred if all headroom values remain positive. Process repeats are dependent.','input_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.jsonl')}}
assert output['maximum_cuda_reserved_bytes']<16*1024**3
(root/'accounting-audit.json').write_text(json.dumps(output,indent=2)+'\n'); print(json.dumps({'passed':True,'requests':len(rows),'cells':len(result)}))
