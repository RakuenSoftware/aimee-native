"""Fail closed on fixture under-delivery; never score it as model failure."""
def validate_records(facts, expected_refs):
    actual = [f.get('memory_ref') for f in facts]
    if not expected_refs or actual != expected_refs:
        raise ValueError('record coverage mismatch: complete ordered fixture required')
    identities = [(r['namespace'], r['id']) for r in actual]
    if len(set(identities)) != len(identities):
        raise ValueError('duplicate canonical identity in working set')
    ids = [f['id'] for f in facts]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate native fact identity')
    return ids

def validate_encoding(state, expected_ids, expected_tokens):
    events = [e for e in state['recall_events'] if e.get('status') == 'bank_updated']
    if len(events) != 1 or events[0]['bank_memory_ids'] != expected_ids:
        raise ValueError('native bank did not encode the complete ordered record set')
    if state['memory_token_ids'] != expected_tokens:
        raise ValueError('native encoder token sequence differs from complete record content')
    if state['memory_encoding_tokens'] != len(expected_tokens):
        raise ValueError('native encoding length mismatch')
