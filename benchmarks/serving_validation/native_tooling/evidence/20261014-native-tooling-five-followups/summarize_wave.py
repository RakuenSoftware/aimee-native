import json,collections,statistics
from pathlib import Path
P=Path(__file__).parent

def rows(name):
 p=P/name
 return [json.loads(line) for line in p.read_text().splitlines() if line] if p.exists() else []
def usage_from_resolution(resolution):
 totals=collections.Counter()
 for observation in resolution.get('observations',[]) or []:
  try:r=json.loads(observation['response'])
  except (ValueError,KeyError,TypeError):continue
  for key in ['prompt_tokens','completion_tokens','total_tokens']:totals[key]+=r.get('usage',{}).get(key,0)
 return dict(totals)
report={'qualification':'CPU research fixtures; live enrolled identity/source release and complete serving-to-owner-to-dispatch chain remain separately unqualified. Native/ordinary reference equivalence is not universal tool competence or an effective context multiplier.'}
reference={r['id']:r['reference'] for r in json.loads((P/'reference-v99.json').read_text())}
report['intake']={}
report['scoring_note']='Invalid or unavailable intake is not scored as correct semantic classification; it can still be a safe refusal. Completion counts for report artifacts denote exact fixture write only, never assessment correctness.'
for name in ['automatic-intake-results.jsonl','schema-intake-r1-results.jsonl','speech-act-e2b-results.jsonl','speech-act-qwen-results.jsonl','9205-kind-first-e2b-results.jsonl','9222-kind-first-qwen-results.jsonl']:
 data=rows(name)
 if not data:continue
 outcomes=[]
 for x in data:
  decision=x.get('intake',{}).get('decision',{});actionable=not x.get('error') and decision.get('kind') in ['content','need'];ref=reference.get(x['id'],{})
  outcomes.append(dict(id=x['id'],validated=not bool(x.get('error')),kind=decision.get('kind'),actionable=bool(actionable),reference_usable=ref.get('usable_component'),usable_detection_correct=not bool(x.get('error')) and bool(actionable)==bool(ref.get('usable_component')),expected_speech_act='content' if ref.get('usable_component') else 'abstain',speech_act_correct=not bool(x.get('error')) and ((decision.get('kind')=='content') if ref.get('usable_component') else not actionable),error=x.get('error'),unsupported_claims=decision.get('unsupported_claims',[])))
 report['intake'][name]=dict(n=len(data),validated=sum(x['validated'] for x in outcomes),actionable=sum(x['actionable'] for x in outcomes),usable_detection_correct=sum(x['usable_detection_correct'] for x in outcomes),speech_act_correct=sum(x['speech_act_correct'] for x in outcomes),false_usable=sum(x['actionable'] and not x['reference_usable'] for x in outcomes),missed_usable=sum(not x['actionable'] and x['reference_usable'] for x in outcomes),usage= dict(sum((collections.Counter(usage_from_resolution(x)) for x in data),collections.Counter())),outcomes=outcomes)
report['models']={}
for ct in [9205,9222]:
 model={}
 lifecycle=rows(f'{ct}-cpu-lifecycle-results.jsonl');dec=[x for x in lifecycle if x['kind']=='decode']
 if dec:model['lifecycle']=dict(n=len(dec),correct=sum(x['expected'] in x['result']['response']['choices'][0]['message']['content'].lower() for x in dec),withdrawals=[x['result']['status'] for x in lifecycle if x['kind']=='withdrawn-query'],capture_denials=[x['result']['status'] for x in lifecycle if x['kind']=='capture-denial'],terminal=any(x['kind']=='terminal' for x in lifecycle))
 long=rows(f'{ct}-cpu-longrun-results.jsonl');arms={}
 for arm in ['native-current','ordinary-current','ordinary-history']:
  data=[x for x in long if x.get('arm')==arm]
  if data:arms[arm]=dict(n=len(data),correct=sum(x['correct'] for x in data),prompt_tokens_total=sum(x['ordinary_prompt_tokens'] for x in data),prompt_tokens_first=data[0]['ordinary_prompt_tokens'],prompt_tokens_last=data[-1]['ordinary_prompt_tokens'],native_bytes_max=max(x['private_bank']['bytes'] for x in data),native_prefix_tokens=data[-1]['private_bank']['tokens'],seconds_total=sum(x['seconds'] for x in data))
 if arms:model['longrun']=dict(arms=arms,parity_pairs=sum(x['kind']=='parity' for x in long),token_equal_pairs=sum(x.get('same_tokens',False) for x in long),terminal=any(x['kind']=='terminal' for x in long),history_comparison_confound='owner state compaction; current-prefix reference isolates native transport')
 for stem in ['cpu-episode-results','cpu-compiled-episode-v112-results','cpu-scalar-v113-results','cpu-scalar-feedback-v114-results','cpu-budget-v116-results']:
  data=rows(f'{ct}-{stem}.jsonl')
  if not data:continue
  summary=dict(records=len(data),terminal=any(x['kind']=='terminal' for x in data))
  if 'scalar' in stem:
   proposals=[x for x in data if x['kind'] in ['proposal','attempt']];episodes=[x for x in data if x['kind']=='episode'];summary.update(contributions=len(proposals),validated=sum(not x['owner_resolution'].get('error') for x in proposals),compiled=sum(bool(x['owner_resolution'].get('compiled')) for x in proposals),eligible=sum(x['eligible'] for x in proposals),observed_fixture_effects=sum(bool(x['effect']) and x['effect']['exact_readback'] for x in proposals),owner_backend_calls=sum(len(x['owner_resolution'].get('observations') or []) for x in proposals),episodes=len(episodes),completed_episodes=sum(x.get('completed',False) for x in episodes))
  else:
   episodes=[x for x in data if x['kind']=='episode'];turns=[x for x in data if x['kind']=='turn'];summary.update(episodes=len(episodes),additional_need_discovered=sum(x['additional_need_discovered'] for x in episodes),compiled_reports=sum(x['compiled_report'] for x in episodes),owner_reads=sum(len(x['owner_reads']) for x in episodes),owner_usage=dict(sum((collections.Counter(usage_from_resolution(x['owner_resolution'])) for x in turns),collections.Counter())))
  contribution_rows=[x for x in data if x['kind'] in ['turn','proposal','attempt']]
  summary['context_by_arm']={}
  for arm in sorted({x['arm'] for x in contribution_rows}):
   selected=[x for x in contribution_rows if x['arm']==arm]
   summary['context_by_arm'][arm]=dict(calls=len(selected),ordinary_prompt_tokens=sum(x['ordinary_prompt_tokens'] for x in selected),task_output_tokens=sum(x['response'].get('usage',{}).get('completion_tokens',0) for x in selected),publication_tokens_total=sum(x['private_prefix_tokens'] for x in selected),owner_usage=dict(sum((collections.Counter(usage_from_resolution(x['owner_resolution'])) for x in selected),collections.Counter())))
  model[stem]=summary
 inflight=rows(f'{ct}-cpu-inflight-measure-results.jsonl')
 if inflight:
  samples=[s for x in inflight for s in x.get('samples',[])];model['inflight']=dict(records=len(inflight),terminal=any(x['kind']=='terminal' for x in inflight),active_at_withdraw=next((x['withdrawn']['active_requests'] for x in inflight if x['kind']=='withdraw-inflight'),None),after_withdraw_status=next((x['result']['status'] for x in inflight if x['kind']=='new-request-after-withdraw'),None),shadow_bytes_sampled_peak=max((s['metrics']['workers'][0]['shadow_text_bytes'] for s in samples),default=0),cgroup_memory_current_sampled_peak=max((s['memory'].get('memory.current',0) for s in samples),default=0),audit_instrumentation='full tensor hash RPCs perturb latency; not a speed benchmark')
 report['models'][str(ct)]=model
(P/'summary-current.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='intake'},indent=2))
