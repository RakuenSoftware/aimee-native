"""Verify lossless content-addressed recurrent storage at checkpoint scale.

This gate is independent of model answer quality. It reads immutable prepared
bytes and checks complete base/positioned pairing, extents and SHA-256 identities.
"""
import argparse
import hashlib
import json
from pathlib import Path


def validate(root):
    root = Path(root)
    entries = json.loads((root / 'index.json').read_text())['entries']
    groups = {}
    for key, entry in entries.items():
        recurrent = entry['recurrent']
        digest = recurrent['sha256']
        if recurrent['payload'] != digest + '.rnn.bin':
            raise ValueError('non-content-addressed payload')
        path = root / recurrent['payload']
        if path.stat().st_size != recurrent['bytes']:
            raise ValueError('recurrent extent mismatch')
        groups.setdefault(digest, []).append((key, recurrent))
    for digest, pairs in groups.items():
        if len(pairs) != 2 or pairs[0][1] != pairs[1][1]:
            raise ValueError('base/positioned recurrence is not shared exactly')
        h = hashlib.sha256()
        with (root / (digest + '.rnn.bin')).open('rb') as source:
            for block in iter(lambda: source.read(8 * 1024**2), b''):
                h.update(block)
        if h.hexdigest() != digest:
            raise ValueError('recurrent checksum mismatch')
    payloads = set(root.glob('*.rnn.bin'))
    if payloads != {root / (digest + '.rnn.bin') for digest in groups}:
        raise ValueError('unexpected recurrent payloads')
    actual = sum(path.stat().st_size for path in payloads)
    duplicate = sum(entry['recurrent']['bytes'] for entry in entries.values())
    if not actual or actual * 2 != duplicate:
        raise ValueError('expected exact twofold storage saving')
    return {'entries': len(entries), 'distinct_recurrent_payloads': len(groups),
            'actual_recurrent_bytes': actual, 'entry_sum_recurrent_bytes': duplicate,
            'saved_bytes': duplicate - actual, 'ratio': actual / duplicate,
            'checksums_verified': True,
            'scope': 'immutable checkpoint payload storage; independent of answer quality'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = validate(args.root)
    with Path(args.output).open('x') as target:
        json.dump(report, target, indent=2)
        target.write('\n')
    print(json.dumps(report))
