"""Additional saved-output audit and episode-level cost accounting.

Input receipts are read-only. The caller chooses a new output file explicitly.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import statistics


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();root=a.root
    fixture=json.loads((root/'fixture.json').read_text());official=json.loads((root/'summary.json').read_text())
    assert official['passed'] and not fixture['pilot']
    rows=[];preparation=[];identities=[]
    for rep in range(fixture['process_repetitions']):
        rows.extend(json.loads(l) for l in (root/f'rows-{rep}.jsonl').read_text().splitlines())
        preparation.extend(dict(json.loads(l),repeat=rep) for l in (root/f'preparation-{rep}.jsonl').read_text().splitlines())
        meta=json.loads((root/f'metadata-{rep}.json').read_text());identities.append(meta)
        assert meta['all_parameter_devices']==['cuda:0'] and meta['dtype']=='FP32'
        assert meta['model_files']==identities[0]['model_files']
    assert len(rows)==2592 and len(fixture['episodes'])==24 and len(preparation)==216
    keyed={(r['repeat'],r['episode'],r['arm'],r['turn']):r for r in rows}
    assert len(keyed)==len(rows)
    transcripts=[]
    for r in rows:
        assert r['history_checkpoint_unchanged'] and r['history_reprefill_tokens']==0
        assert r['physical_devices']==['cuda:0']
        if r['arm']=='native-at-injection':
            t=keyed[(r['repeat'],r['episode'],'removed-text',r['turn'])]
            assert t['task_token_ids']==r['task_token_ids']
            assert t['public_transcript_sha256']==r['public_transcript_sha256']
            assert t['prior_history_tokens']==r['prior_history_tokens']
            transcripts.append(r['public_transcript_sha256'])
    totals={};process_scores={}
    for arm in fixture['arms']:
        selected=[r for r in rows if r['arm']==arm]
        scores={}
        for kind in ['injection','unrelated','withdrawal']:
            cases=[r for r in selected if r['kind']==kind]
            scores[kind]={'n':len(cases),'correct':sum(r['answer'].strip().lower().rstrip('.')==r['expected'] for r in cases)}
        stale=sum(any(re.search(r'\b'+re.escape(v)+r'\b',r['answer']) for v in r['forbidden']) for r in selected if r['kind']=='withdrawal')
        totals[arm]={'scores':scores,'old_code_echoes':stale,'prefill_tokens':sum(r['prefill_tokens'] for r in selected)}
        process_scores[arm]=[{kind:sum(r['answer'].strip().lower().rstrip('.')==r['expected'] for r in selected if r['repeat']==rep and r['kind']==kind) for kind in scores} for rep in range(3)]
    cost=[];phase_cost=[];cold=[];accumulation=[]
    for h in [128,1024,4096]:
        medians={}
        for arm in fixture['arms']:
            z=[r for r in rows if r['history_target']==h and r['arm']==arm and r['kind']=='injection']
            medians[arm]={field:statistics.median(r[field] for r in z)*1000 for field in ['request_first_seconds','turn_total_seconds','attachment_seconds','cleanup_seconds']}
        n=[r for r in rows if r['history_target']==h and r['arm']=='native-at-injection' and r['kind']=='injection']
        differences=[(r['turn_total_seconds']-keyed[(r['repeat'],r['episode'],'removed-text',r['turn'])]['turn_total_seconds'])*1000 for r in n]
        cost.append({'history':h,'injection_requests_per_arm':len(n),'medians_ms':medians,'paired_native_minus_removed_total_median_ms':statistics.median(differences)})
        for phase in ['first-use','reselect']:
            z=[r for r in n if r['phase']==phase]
            diff=[(r['turn_total_seconds']-keyed[(r['repeat'],r['episode'],'removed-text',r['turn'])]['turn_total_seconds'])*1000 for r in z]
            phase_cost.append({'history':h,'phase':phase,'n':len(z),'paired_native_minus_removed_total_median_ms':statistics.median(diff)})
        differences=[]
        prep_times=[]
        for rep in range(3):
            for e in fixture['episodes']:
                if e['history_target']!=h:continue
                prep=sum(x['seconds'] for x in preparation if x['repeat']==rep and x['episode']==e['id'])
                prep_times.append(prep*1000)
                nt=sum(r['turn_total_seconds'] for r in rows if (r['repeat'],r['episode'],r['arm'])==(rep,e['id'],'native-at-injection'))
                tt=sum(r['turn_total_seconds'] for r in rows if (r['repeat'],r['episode'],r['arm'])==(rep,e['id'],'removed-text'))
                differences.append((nt+prep-tt)*1000)
        cold.append({'history':h,'episodes':8,'process_measurements':24,'three_bank_preparation_median_ms':statistics.median(prep_times),'paired_native_minus_removed_episode_cost_including_preparation_median_ms':statistics.median(differences),'excludes':'Shared initial public-history prefill, model loading and forensic hashing.'})
        for arm in fixture['arms']:
            ends=[r for r in rows if r['history_target']==h and r['arm']==arm and r['turn']==11]
            accumulation.append({'history':h,'arm':arm,'final_public_history_tokens_min':min(r['public_history_tokens'] for r in ends),'final_public_history_tokens_max':max(r['public_history_tokens'] for r in ends)})
    qualified_values=[r['expected'] for e in fixture['episodes'] for r in e['records']]
    assert len(qualified_values)==len(set(qualified_values))==72
    result={'passed':True,'responses':len(rows),'unique_episodes':24,'unique_record_versions':72,'process_repetitions':3,
            'totals':totals,'process_scores':process_scores,'cost':cost,'phase_cost':phase_cost,'cold_episode_cost':cold,
            'accumulation':accumulation,'native_removed_public_transcript_pairs':len(transcripts),
            'maximum_cuda_reserved_bytes':max(r['cuda_reserved_bytes'] for r in rows),
            'maximum_cuda_allocated_bytes':max(r['cuda_allocated_bytes'] for r in rows),
            'source_inputs_sha256':{f.name:sha(f) for f in root.iterdir() if f.suffix in {'.json','.jsonl'}},
            'timing_endpoint':'Time to first synchronized logits; full turn includes generation and clean public-history reconstruction.',
            'scope':fixture['scope'],'inference':'Descriptive fixed-fixture results; episodes, shared record versions and process repeats are dependent.'}
    assert not a.output.exists(), 'Derived audit is additive; select a new output file'
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['passed','responses','totals','cost','cold_episode_cost']},indent=2))


if __name__=='__main__':main()
