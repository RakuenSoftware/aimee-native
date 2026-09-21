"""Public-data publisher cue compiler; never run over unapproved private metadata.
Canonical source names own their normalized addresses. Alternate names are
fallback addresses only; duplicate canonical names remain explicitly ambiguous.
No model-side policy, learning, or canonical-object mutation is involved.
"""
import argparse
import json
import unicodedata
from pathlib import Path


def normalize_cue(text):
    """Match the reader's simple Unicode lowercase/letter-number word policy."""
    # Per-character lower avoids Python's contextual final-sigma mapping;
    # U+0130's simple lowercase is i, without the full-mapping combining dot.
    text = ''.join(c.lower()[0] for c in text)
    words = ''.join(c if unicodedata.category(c)[0] in 'LN' or c in '-_/.' else ' '
                    for c in text).split()
    return ' '.join(w.strip('.') for w in words if w.strip('.'))


def cue_parts(record):
    s = record['metadata']['semantic']
    domain = s['domain']
    if domain == 'geonames':
        country = s['country_code'] or 'unassigned'
        qualify = lambda names: sorted({name + ' ' + country for name in names if name.strip()})
        return qualify([s['name'], s['asciiname']]), qualify(s['alternate_names'][:6])
    if domain == 'iana':
        return ['service ' + s['subject'], 'port for ' + s['subject']], []
    if domain == 'nasa':
        return ['exoplanet ' + s['pl_name']], []
    if domain == 'nist':
        return ['CODATA ' + s['subject']], []
    if domain == 'worldbank':
        return ['country ' + s['name'], 'capital of ' + s['name']], []
    return [], []


def cues(record):
    """Raw per-object candidates, retained for auditing the original compiler."""
    primary, alternate = cue_parts(record)
    return sorted(set(primary + alternate))


def compile_cues(records, authority):
    # Decide across the entire approved release, never by iteration order.
    primary_addresses = {normalize_cue(cue) for r in records for cue in cue_parts(r)[0]}
    result = []
    for record in records:
        primary, alternate = cue_parts(record)
        accepted = set(primary)
        accepted.update(cue for cue in alternate if normalize_cue(cue) not in primary_addresses)
        for cue in sorted(accepted):
            result.append(dict(ref={k: record[k] for k in ['namespace', 'id', 'revision']},
                               cue=cue, authority=authority))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--records', type=Path, required=True)
    p.add_argument('--authority', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    rows = json.loads(a.records.read_text())['records']
    out = compile_cues(rows, a.authority)
    a.output.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(json.dumps(dict(objects=len(rows), approved_cues=len(out), bytes=a.output.stat().st_size)))
