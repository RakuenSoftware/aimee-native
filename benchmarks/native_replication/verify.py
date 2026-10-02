"""Recompute outcomes and invariants from preserved JSONL; no model required."""
import collections,hashlib,json,statistics,sys
from pathlib import Path
root=Path(sys.argv[1]);summary={}
for directory in ['native-replication-r2','native-paraphrase-r1']:
    path=root/directory/'results.jsonl'
    if not path.exists():continue
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    phases={}
    for phase in dict.fromkeys(r['phase'] for r in rows):
        group=[r for r in rows if r['phase']==phase]
        phases[phase]={'n':len(group),'correct':sum(r['pass'] for r in group),'encoding_passes':sum(r.get('memory',{}).get('memory_encoding_passes',0) for r in group)}
    prompts={}
    for r in rows:
        assert r['pass']==(r.get('answer','').strip().rstrip('.').casefold()==r['expected'])
        assert 'error' not in r,r
        assert r['parameter_versions_unchanged'] and r['memory_prompt_tokens']==0
        assert r['main_cache_length']==r['expected_main_cache_length']
        key=(r['item'],r.get('template',0));prompts.setdefault(key,r['prompt_token_ids']);assert prompts[key]==r['prompt_token_ids']
        if r['enabled']:
            assert r['memory']['native_reads']>0
            facts=r['memory']['aimee_response']['facts'];assert len(facts)==1
            assert facts[0]['memory_ref']['id']==f"code-{r['item']:02d}"
            assert facts[0]['content'].endswith(r['expected']+'.')
    item={'phases':phases,'requests':len(rows),'all_invariants':True}
    updates=[r for r in rows if 'publication' in r]
    for label,values in [('publication_seconds',[r['publication']['publication_seconds'] for r in updates]),('mutation_to_answer_seconds',[r['mutation_to_answer_seconds'] for r in updates])]:
        if values:item[label]={'n':len(values),'min':min(values),'median':statistics.median(values),'max':max(values)}
    summary[directory]=item
path=root/'native-replication-r2/withdrawals.jsonl'
if path.exists():
    rows=[json.loads(line) for line in path.read_text().splitlines()];assert len(rows)==3
    assert all(r['result']['outcome']=='uncovered' and 'response' not in r['result'] for r in rows)
    summary['withdrawal_probes']={'n':3,'outcome':'uncovered; no model answer scored'}
path=root/'qwen-handoff-r2/results.jsonl'
if path.exists():
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    folder=path.parent
    assert json.loads((folder/'image-before.json').read_text())==json.loads((folder/'image-after.json').read_text())
    groups={}
    for enabled in [False,True]:
        group=[r for r in rows if r['enabled']==enabled]
        groups[str(enabled)]={'n':len(group),'correct':sum(r['passed'] for r in group)}
    summary['qwen_handoff']={'phases':groups,'image_unchanged':True}
print(json.dumps(summary,indent=2))
