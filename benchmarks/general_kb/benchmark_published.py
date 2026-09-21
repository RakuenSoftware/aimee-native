"""Matched local protocol timing; no gateway process or network reads."""
import argparse
import json
from pathlib import Path
import random
import statistics
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument('--root', required=True)
p.add_argument('--records', required=True)
p.add_argument('--reader', required=True)
p.add_argument('--rust', required=True)
p.add_argument('--output', required=True)
a = p.parse_args()
root = Path(a.root)
rows = json.loads(Path(a.records).read_text())['records']
sample = random.Random(99317).sample(rows, 256)
results = {}
for mode in ['legacy_guarded', 'published', 'rust_published']:
    if mode == 'rust_published':
        args = [a.rust, 'read-check', '--image-reader', a.reader, '--memory-image', str(root/'image'),
                '--read-authority', 'research-aimee-103', '--read-gateway', str(root/'NO_GATEWAY.sock')]
    else:
        args = [a.reader, 'serve' if mode == 'legacy_guarded' else 'serve-published', '--root', str(root/'image')]
        if mode == 'legacy_guarded':
            args += ['--authorization', str(root/'authorization.json'), '--authority-key', str(root/'issuer-public.hex'),
                     '--subject', 'general-kb-research', '--policy-epoch', 'research-1']
    start = time.perf_counter()
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    def call(payload):
        started = time.perf_counter_ns()
        proc.stdin.write(json.dumps(payload)+'\n')
        proc.stdin.flush()
        raw = proc.stdout.readline()
        if not raw:
            raise RuntimeError('reader exited')
        response = json.loads(raw)
        return response, (time.perf_counter_ns()-started)/1e6
    r, _ = call(dict(op='begin' if mode == 'rust_published' else 'pin'))
    assert 'error' not in r.get('result', r), r
    startup = time.perf_counter()-start
    durations = []
    def read(row):
        response, ms = call(dict(op='native_search' if mode == 'rust_published' else 'recall',
            query=f'Please provide the reference entry for {row["key"]}.', limit=4, authority='research-aimee-103'))
        answer = response.get('result', response.get('response', {}))
        facts = answer.get('facts', [])
        assert len(facts) == 1 and facts[0]['id'] == row['id'] and facts[0]['content'] == row['content'], response
        if mode != 'legacy_guarded':
            assert facts[0]['memory_ref'] == {k: row[k] for k in ['namespace','id','revision']}
        return ms
    try:
        for row in sample:
            durations.append(read(row))
        exhaustive = None
        if mode == 'rust_published':
            for row in rows:
                read(row)
            exhaustive = len(rows)
    finally:
        proc.stdin.close()
        proc.wait(timeout=5)
        proc.stdout.close()
    results[mode] = dict(sampled=len(sample), matched=len(sample), startup_seconds=startup,
        protocol_ms=dict(median=statistics.median(durations), mean=statistics.mean(durations),
            p95=sorted(durations)[int(.95*len(durations))-1], max=max(durations)),
        exhaustive_matched=exhaustive)
out = dict(corpus_records=len(rows), results=results, gateway_running=False, network_dependencies=0,
    note='Same image, host and seeded queries; legacy includes repeated grant verification. Rust path includes canonical refs without a second round trip.')
Path(a.output).write_text(json.dumps(out, indent=2)+'\n')
print(json.dumps(out, indent=2))
