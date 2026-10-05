"""Close explicit engineering gates; never infer quality from fewer reads."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
from router import evaluate,private_new


def analyze(root):
    protocol=json.loads((root/'protocol.json').read_text())
    results=json.loads((root/'results.json').read_text());groups={}
    baseline={(r['task_id'],r['replicate']):r for r in results if r['schedule']=='every-step'}
    for schedule in ('every-step','preload-only','bounded-refresh'):
        rows=[r for r in results if r['schedule']==schedule]
        if set((r['task_id'],r['replicate']) for r in rows)!=set(baseline):raise ValueError('unpaired schedule conditions')
        regressions=[r['task_id'] for r in rows if baseline[(r['task_id'],r['replicate'])]['correct'] and not r['correct']]
        groups[schedule]={'n':len(rows),'correct':sum(r['correct'] for r in rows),
            'correct_selection':sum(r['selection_correct'] for r in rows),'source_reads':sum(r['source_reads'] for r in rows),
            'addressing_attempts':sum(r['addressing_attempts'] for r in rows),
            'median_elapsed_ms':statistics.median(r['elapsed_ms'] for r in rows),
            'quality_regressions':regressions}
    for schedule in ('preload-only','bounded-refresh'):
        g=groups[schedule];g['engineering_gate_passed']=not g['quality_regressions'] and g['source_reads']<groups['every-step']['source_reads']
    diagnostics=json.loads((root/'routing-features.json').read_text())['samples']
    variants={}
    for sample in diagnostics:
        for row in sample['features_by_layer']:
            key=(row['layer'],row['representation'],row['pooling'],row['position'],row['width'])
            variants.setdefault(key,[]).append({'features':row['features'],'split':sample['split'],
                'family':sample['family'],'partition':sample['partition']})
    router_rows=[];gate=protocol['routing_gate'];primary=None
    for key,samples in sorted(variants.items()):
        layer,representation,pooling,position,width=key
        data={'contract':{'model_revision':protocol['model_weight_index_sha256']+'-int8-'+protocol['runtime_sha256'],
            'layer':layer,'representation':representation,'pooling':pooling,'position':position,'width':width},
              'samples':samples,'available_partitions':sorted(set(s['partition'] for s in samples))}
        report,weights=evaluate(data,gate['partition_budget'],gate['min_score'],gate['min_margin'])
        report['features_sha256']=hashlib.sha256((root/'routing-features.json').read_bytes()).hexdigest()
        name=f"layer-{layer}-{representation}-{pooling}"
        private_new(root/f'{name}-evaluation.json',report);private_new(root/f'{name}-router.json',weights)
        row={k:report[k] for k in ('contract','candidate_hits','heldout_examples','fallbacks')}
        router_rows.append(row)
        if (layer,representation,pooling)==(gate['primary_layer'],gate['primary_representation'],gate['primary_pooling']):primary=row
    if primary is None:raise ValueError('predeclared primary representation missing')
    # The public fixture's aliases provide a deterministic perfect comparator.
    tasks={t['id']:t for t in protocol['tasks']}
    deterministic_hits=sum(any(t['partition'].lower()==token for token in re.findall(r'\w+',t['query'].lower()))
                           for t in list(tasks.values())[:6])
    return {'schema':'native-addressing-decision-v1','scope':'public synthetic full-model engineering; fixed archive; small closed-domain router',
        'schedule_conditions':groups,'router_primary':primary,'deterministic_development_cue_hits':deterministic_hits,
        'router_matches_fixture_deterministic':primary['candidate_hits']==primary['heldout_examples'],
        'router_exploratory_variants':router_rows,
        'deployment_promoted':False,
        'compression_decision':'No new lossy codec: exact record reuse is already implemented; no demonstrated semantic benefit justifies another representation.',
        'write_decision':'No native mutation path: hidden address observations are not validated proposed factual content. Preserve authority-owned textual proposal validation.',
        'limitations':['No production authorization fixture','No general semantic archive-scaling claim',
            'No cross-model/quantization stability campaign','Routing is a candidate-only offline prototype, not an integrated authority lookup',
            'Schedule latency is descriptive; variable answer length and fixed schedule order prevent a controlled compute speedup claim']}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('campaign');p.add_argument('--output',required=True)
    a=p.parse_args();private_new(a.output,analyze(Path(a.campaign)))
