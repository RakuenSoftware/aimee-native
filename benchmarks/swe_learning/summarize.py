"""Partial progress is labeled; repeated-task gains are not unseen-task accuracy."""
import json,pathlib,statistics,os
ROOT=pathlib.Path(os.environ.get('SWE_RUN_ROOT','/opt/swe-native'));rows=[json.loads(p.read_text()) for p in (ROOT/'results').glob('*/*/result.json')]
rounds=int(os.environ.get('SWE_LEARNING_ROUNDS','5'))
scheduled_tasks=len(json.loads((ROOT/'tasks.json').read_text()));scheduled_attempts=scheduled_tasks*(rounds+1)
arms=['control']+[f'learn-{i}' for i in range(1,rounds+1)]
by={};table=[]
for arm in arms:
 rs=[r for r in rows if r['arm']==arm];by[arm]={r['instance_id']:r for r in rs}
 table.append({'arm':arm,'finished':len(rs),'resolved':sum(r.get('resolved') is True for r in rs),'graded_or_empty':sum(r.get('resolved') is not None for r in rs),'infrastructure':sum(r.get('resolved') is None for r in rs),'with_native_memory':sum(bool(r.get('publication')) for r in rs),'median_agent_seconds':statistics.median([r['agent_seconds'] for r in rs if 'agent_seconds' in r]) if any('agent_seconds' in r for r in rs) else None})
transitions=[]
for before,after in zip(arms,arms[1:]):
 ids=[i for i in by[before].keys()&by[after].keys() if by[before][i].get('resolved') is not None and by[after][i].get('resolved') is not None]
 transitions.append({'before':before,'after':after,'paired_tasks':len(ids),'gains':sum(not by[before][i]['resolved'] and by[after][i]['resolved'] for i in ids),'regressions':sum(by[before][i]['resolved'] and not by[after][i]['resolved'] for i in ids)})
result={'scheduled_tasks':scheduled_tasks,'scheduled_attempts':scheduled_attempts,'finished_attempts':len(rows),'complete':len(rows)==scheduled_attempts,'arms':table,'paired_transitions':transitions,'interpretation':'Repeated-task, native-memory experience study. Partial results and infrastructure failures remain explicit. Not unseen-task generalization or changed model weights.'}
(ROOT/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
lines=['# SWE-bench native-learning progress','',result['interpretation'],'',f"Completed attempt records: {len(rows)}/{scheduled_attempts}.",'','| Arm | Finished | Resolved | Scored incl. empty | Infrastructure | With native memory |','|---|---:|---:|---:|---:|---:|']
for r in table:lines.append('| {arm} | {finished} | {resolved} | {graded_or_empty} | {infrastructure} | {with_native_memory} |'.format(**r))
lines+=['',f'Paired transitions are in summary.json. Do not divide by {scheduled_tasks} until the scheduled arm is complete, or hide incomplete tasks behind a partial percentage.','']
(ROOT/'progress.md').write_text('\n'.join(lines));print(json.dumps(result))
