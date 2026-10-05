"""Collect exact owner-approved native selections for offline preparation.

The compiled reader selects records. This collector neither expands aliases nor
manufactures facts, grants or task answers. Empty selections get no native bank.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from hybrid_serving_profile import PROFILE, SYSTEM


def collect(reader, archive, tasks):
    process = subprocess.Popen([reader, 'serve-published', '--root', archive],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    def call(body):
        process.stdin.write(json.dumps(body) + '\n')
        process.stdin.flush()
        result = json.loads(process.stdout.readline())
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result
    bundles = {}
    mapping = {}
    bundle_facts = {}
    try:
        view = call({'op': 'pin'})['view']
        address = {'schema': 1, 'view': view, 'representation': 'text-query-v1', 'step': 0}
        for task in tasks:
            result = call({'op': 'native_recall', 'query': task['query'], 'limit': 6,
                           'authority': 'public-research', 'address': address})
            facts = result.get('response', {}).get('facts', [])
            if result.get('outcome') not in ('hit','miss') and task['expected']:
                raise RuntimeError('native selection unavailable: '+task['id']+' '+str(result))
            refs = [fact['memory_ref'] for fact in facts]
            expected = set(task['expected'])
            if set(ref['id'] for ref in refs) != expected:
                raise RuntimeError('canonical selection mismatch: ' + task['id'])
            if not refs:
                mapping[task['id']] = None
                continue
            key = hashlib.sha256(json.dumps(refs, separators=(',', ':')).encode()).hexdigest()
            bundles.setdefault(key, {'query': task['query'], 'expected_refs': refs, 'system_context': SYSTEM, 'consumption_profile': PROFILE})
            mapping[task['id']] = key
            bundle_facts[key]={'facts':facts}
        return {'view': view, 'requests': list(bundles.values()), 'bundle_ids': list(bundles),
                'task_bundles': mapping, 'bundle_facts':bundle_facts, 'system_context': SYSTEM, 'consumption_profile': PROFILE}
    finally:
        process.stdin.close()
        process.wait(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reader', 'archive', 'tasks', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    report = collect(args.reader, args.archive, json.loads(Path(args.tasks).read_text())['tasks'])
    with Path(args.output).open('x') as target:
        json.dump(report, target, indent=2)
        target.write('\n')
    print(json.dumps({'view': report['view'], 'bundles': len(report['requests']), 'tasks': len(report['task_bundles'])}))
