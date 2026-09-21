"""Summarize preserved results, retaining raw scores and explicit corrections."""
import argparse
import json
import statistics
import unicodedata
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--artifacts', default='docs/validation/artifacts/general-kb-2026-09-20')
a = p.parse_args()
root = Path(a.artifacts)
initial = [json.loads(s) for s in (root / 'results.jsonl').read_text().splitlines()]
fixed = [json.loads(s) for s in (root / 'native-fixed.jsonl').read_text().splitlines()]

def accents(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s.casefold()) if not unicodedata.combining(c))

def summary(rows):
    return dict(
        requests=len(rows), correct=sum(r['pass_'] for r in rows),
        correct_with_capital_diacritic_equivalence=sum(
            r['pass_'] or (r['domain'] == 'worldbank' and accents(r['answer']) == accents(r['expected'])) for r in rows),
        failures=[dict(case=r['case'], answer=r['answer'], expected=r['expected']) for r in rows if not r['pass_']],
        latency_seconds=dict(median=statistics.median(r['seconds'] for r in rows),
                             mean=statistics.mean(r['seconds'] for r in rows),
                             total=sum(r['seconds'] for r in rows)),
        prompt_tokens=sum(r['response']['usage']['prompt_tokens'] for r in rows),
        completion_tokens=sum(r['response']['usage']['completion_tokens'] for r in rows),
        by_domain={d: dict(requests=sum(r['domain'] == d for r in rows),
                           correct=sum(r['domain'] == d and r['pass_'] for r in rows)) for d in sorted({r['domain'] for r in rows})},
    )

result = {mode: summary([r for r in initial if r['mode'] == mode]) for mode in ['none', 'text', 'native']}
result['native_fixed'] = summary(fixed)
result['notes'] = [
    'Raw results unchanged. Diacritic equivalence only corrects Tórshavn versus Torshavn in the no-memory capital answer.',
    'Text is an oracle compact selection, not a full-KB context arm.',
    'End-to-end times include different generated output lengths and are not an isolated local/remote speed comparison.',
]
(root / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
