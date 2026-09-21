#!/usr/bin/env python3
"""Withdraw research read contracts via a new publisher-owned image generation.
Retains canonical records and the upstream graph. Does not mutate Aimee.
"""
import argparse
import json
import subprocess
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--root', type=Path, required=True)
p.add_argument('--reader', required=True)
p.add_argument('--publication', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
prior = json.loads(a.publication.read_text())
current = json.loads((a.root / 'CURRENT').read_text())['view']
changes = {k: prior[k] for k in ('namespace', 'kind', 'upstream')}
changes.update(previous=current, generation=prior['generation'] + 1, records=[],
               source='Research publisher withdraws local read decisions', coverage=['withdrawn_read_contracts'])
a.output.write_text(json.dumps(changes, indent=2))
view = json.loads(subprocess.check_output([a.reader, 'build', '--root', str(a.root), '--input', str(a.output)]))['view']
subprocess.run([a.reader, 'publish', '--root', str(a.root), '--view', view, '--expected', current], check=True)
print(json.dumps({'previous': current, 'view': view, 'generation': changes['generation']}))
