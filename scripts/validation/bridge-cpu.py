#!/usr/bin/env python3
"""Run isolated source bridge CPU tests with a real portable Rust library.

Three tests require the installed upstream GPU/vLLM/GGUF environment and are
listed as excluded, never silently treated as passes. GPU attention execution
has its existing hardware skip. CPU fixtures model worker/scheduler behavior.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

EXCLUDED = {
    'test_enrolled_authentication.py': 'installed vLLM authentication middleware',
    'test_gguf_loader.py': 'installed upstream vLLM and GGUF loader',
    'test_hybrid_v2_gate.py': 'installed upstream GPU worker and hybrid model state',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    library = args.library.resolve(strict=True)
    tests = root / 'distribution/vllm/tests'
    environment = dict(os.environ, AIMEE_STORE_LIBRARY=str(library),
                       PYTHONPATH=str(root / 'distribution/vllm'))
    results = []
    for test in sorted(tests.glob('test_*.py')):
        if test.name in EXCLUDED:
            continue
        completed = subprocess.run([sys.executable, '-m', 'unittest', 'discover',
            '-s', str(tests), '-p', test.name, '-v'], env=environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        print(completed.stdout, end='', flush=True)
        count = re.search(r'Ran (\d+) tests?', completed.stdout)
        skipped = re.search(r'skipped=(\d+)', completed.stdout)
        results.append({'module': test.name, 'passed': completed.returncode == 0,
                        'tests': int(count[1]) if count else 0,
                        'skipped': int(skipped[1]) if skipped else 0})
    report = {'scope': __doc__, 'modules': results, 'excluded': EXCLUDED,
              'tests': sum(row['tests'] for row in results),
              'skipped': sum(row['skipped'] for row in results),
              'passed': bool(results) and all(row['passed'] for row in results)}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
