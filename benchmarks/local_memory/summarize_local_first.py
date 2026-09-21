#!/usr/bin/env python3
"""Summarize recorded runs; compare complete recall payloads and model inputs."""
import argparse
import collections
import json
import statistics
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('samples', type=Path)
p.add_argument('--traces', type=Path, required=True)
a = p.parse_args()
rows = [json.loads(line) for line in a.samples.read_text().splitlines()]
errors = [r for r in rows if 'error' in r]
groups = collections.defaultdict(list)
signatures = collections.Counter()
for row in rows:
    if 'error' in row or row.get('warmup', row['pair'] < 0):
        continue
    trace = json.loads((a.traces / (row['response']['id'] + '.json')).read_text())
    stages = collections.defaultdict(float)
    for event in trace['profile_events']:
        stages[event['stage']] += event['seconds']
    signature = dict(prompt=trace['prompt_token_ids'], output=trace['generated_ids'],
                     recalls=[{k: e.get(k) for k in ('query', 'aimee_response', 'bank_memory_ids', 'memory_encoding_sha256')}
                              for e in trace['recall_events']])
    signatures[json.dumps(signature, sort_keys=True)] += 1
    groups[row['arm']].append((row, trace, stages))
summary = {'errors': errors, 'distinct_complete_input_recall_output_signatures': len(signatures),
           'signature_counts': sorted(signatures.values()), 'arms': {}}
for arm, values in groups.items():
    stages = sorted(set(k for _, _, s in values for k in s))
    summary['arms'][arm] = {
        'n': len(values),
        'median_seconds': statistics.median(r['seconds'] for r, _, _ in values),
        'min_seconds': min(r['seconds'] for r, _, _ in values),
        'max_seconds': max(r['seconds'] for r, _, _ in values),
        'answers': dict(collections.Counter(t['answer'] for _, t, _ in values)),
        'median_ttft_seconds': statistics.median(t['ttft_seconds'] for _, t, _ in values),
        'median_profile_seconds': {k: statistics.median(s[k] for _, _, s in values) for k in stages},
        'local_hits': sum(r['response']['aimee']['local_hits'] for r, _, _ in values),
        'remote_calls': sum(r['response']['aimee']['remote_calls'] for r, _, _ in values),
        'encoding_passes': sum(r['response']['aimee']['memory_encoding_passes'] for r, _, _ in values),
        'encoding_cache_bytes': max(t['encoding_cache_bytes'] for _, t, _ in values),
    }
print(json.dumps(summary, indent=2))
