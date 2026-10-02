#!/usr/bin/env python3
"""Inventory signed candidates and exact normal lifecycle evidence; no release approval."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--artifacts', type=Path, required=True)
ap.add_argument('--output', type=Path, required=True)
a = ap.parse_args()
base = a.artifacts
key = base / 'larger-normal-signed-20260928/release-public.pem'
profiles = [
    ('gemma12', 'signed-candidate-20260928', 'normal-signed-lifecycle-20260928',
     ['fresh5', 'updated6', 'rolled_back5', 'restored6']),
    ('gemma26', 'larger-normal-signed-20260928/gemma26/2', 'larger-normal-lifecycle-20260928/gemma26',
     ['fresh1', 'updated2', 'rollback1', 'restored2']),
    ('qwen27', 'larger-normal-signed-20260928/qwen27/2', 'larger-normal-lifecycle-20260928/qwen27',
     ['fresh1', 'updated2', 'rollback1', 'restored2']),
]
rows = []
for profile, package, lifecycle, phases in profiles:
    root = base / package
    raw = (root / 'manifest.json').read_bytes()
    manifest = json.loads(raw)
    subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-inkey', str(key), '-rawin',
                    '-in', str(root / 'manifest.json'), '-sigfile', str(root / 'manifest.sig')],
                   check=True, capture_output=True)
    digest = hashlib.sha256(raw).hexdigest()
    if profile == 'gemma12':
        previous_digest = 'd56c92bfade06bf91ad6cb713d04fe791815b65350f4414f91cd82514554960b'
        previous_sequence = 5
    else:
        previous = root.parent / '1' / 'manifest.json'
        previous_digest = hashlib.sha256(previous.read_bytes()).hexdigest()
        previous_sequence = json.loads(previous.read_text())['sequence']
    results = []
    for phase in phases:
        path = base / lifecycle / (phase + '.json')
        result = {'phase': phase, 'evidence': str(path.relative_to(base))}
        if not path.exists():
            result['status'] = 'pending'
        else:
            data = json.loads(path.read_text())
            if data.get('status') != 'passed' or len(data.get('answers', [])) != 2:
                raise ValueError(f'Incomplete or failed evidence: {path}')
            if not all(answer.get('passed') is True for answer in data['answers']):
                raise ValueError(f'Failed answer in {path}')
            active = data['active']
            index = phases.index(phase)
            expected_current = previous_digest if index in (0, 2) else digest
            expected_previous = None if index == 0 else (digest if index == 2 else previous_digest)
            expected_high_water = previous_sequence if index == 0 else manifest['sequence']
            if active != {'current': expected_current, 'previous': expected_previous,
                          'high_water_sequence': expected_high_water}:
                raise ValueError(f'Unexpected lifecycle state: {profile}/{phase}')
            result.update(status='passed', native_queries=2, active=active,
                          evidence_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        results.append(result)
    rows.append({'profile': profile, 'model': manifest['model'], 'sequence': manifest['sequence'],
                 'version': manifest['version'], 'manifest_sha256': digest, 'signature_verified': True,
                 'artifact_bytes': sum(item['bytes'] for item in manifest['artifacts']),
                 'phases': results, 'lifecycle_complete': all(r['status'] == 'passed' for r in results)})
report = {'scope': __doc__, 'candidates': rows,
          'all_lifecycles_complete': all(r['lifecycle_complete'] for r in rows),
          'limitations': ['Repeated synthetic native canaries are lifecycle evidence, not independent task-learning trials.',
                         'The 12B lifecycle begins at sequence 5 and updates/restores sequence 6; fresh5 is not fresh6 evidence.',
                         'This inventory does not approve external redistribution or promote channels.']}
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'all_lifecycles_complete': report['all_lifecycles_complete'],
                  'completed_phases': {r['profile']: sum(p['status'] == 'passed' for p in r['phases']) for r in rows}}))
