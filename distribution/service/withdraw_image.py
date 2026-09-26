"""Withdraw a stopped follower's last image using the owner's CAS operation."""
import argparse
import json
import pathlib
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--reader', required=True)
p.add_argument('--root', required=True)
a = p.parse_args()
try:
    with (pathlib.Path(a.root) / 'CURRENT').open('rb') as source:
        raw = source.read(16385)
except FileNotFoundError:
    raise SystemExit(0)
if len(raw) > 16384:
    raise SystemExit('invalid publication pointer')
view = json.loads(raw)['view']
subprocess.run([a.reader, 'withdraw-published', '--root', a.root, '--expected', view], check=True)
