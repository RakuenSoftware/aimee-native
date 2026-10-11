"""Pure seven-arm plan. No inference, admission or template execution."""
import hashlib,json,random
ARMS=('None','Native','Text','Replay','Oracle','Unvalidated','Shuffled')
SYSTEM='Translate the English phrase into the invented language. Use the supplied lexicon. Return only the translated phrase, without explanation.'

def shuffled_records(records):
    groups={};mapping={}
    for record in records:groups.setdefault(record['language'],[]).append(record)
    for language,group in groups.items():
        ordered=sorted(group,key=lambda r:hashlib.sha256(('retained-transfer-shuffle/'+r['family_id']).encode()).hexdigest())
        if len(ordered)<2:continue
        for i,record in enumerate(ordered):mapping[record['family_id']]=ordered[(i+1)%len(ordered)]
    return mapping

def record_for(arm,family,accepted,first_candidates,shuffled):
    fid=family['family_id']
    if arm in ('Native','Text'):return accepted.get(fid)
    if arm=='Shuffled':return shuffled.get(fid)
    if arm=='Unvalidated':return first_candidates.get(fid)
    if arm=='Oracle':return {'family_id':fid,'content':family['oracle_rule'],'control':'evaluator-only-reference'}
    return None

def messages(family,item,arm,record,training):
    # The same acquired record appears at the same position in Text and Native.
    fixed='Language: '+family['language']+'\nLexicon: '+json.dumps(family['lexicon'],sort_keys=True)+'\n'
    if record is not None:fixed+='Rule:\n'+record['content']+'\n'
    if arm=='Replay':fixed+='Experience:\n'+json.dumps(training['examples'],sort_keys=True)+'\n'
    task=json.dumps({'input':item['input'],'slots':item['slots']},sort_keys=True)
    return [{'role':'system','content':SYSTEM},{'role':'user','content':fixed+'Task:\n'+task}]

def order(families,repeat):
    rng=random.Random('retained-transfer-order-'+str(repeat));families=list(families);rng.shuffle(families)
    for family in families:
        arms=list(ARMS);rng.shuffle(arms)
        yield family,arms

def common_prefix(sequences):
    assert sequences
    for i in range(min(map(len,sequences))):
        if len({s[i] for s in sequences})!=1:return sequences[0][:i]
    return sequences[0][:min(map(len,sequences))]
