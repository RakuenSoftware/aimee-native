#!/usr/bin/env python3
"""Extract the pinned legacy Go dependency without changing an Aimee checkout."""
import argparse
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    pin = json.loads((root / 'dependencies/aimee-source.json').read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-checkout', type=Path, default=root.parent / 'aimee',
                        help='Git checkout containing the pinned historical Aimee commit')
    args = parser.parse_args()
    commit = subprocess.check_output(['git', '-C', str(args.source_checkout),
        'rev-parse', pin['commit'] + '^{commit}'], text=True).strip()
    if commit != pin['commit']:
        parser.error('Aimee source commit does not match the historical pin')
    destination = root / '.local/aimee-research-ad3585ac'
    marker = destination / '.source-commit'
    if destination.exists():
        if not marker.is_file() or marker.read_text().strip() != commit:
            parser.error('existing dependency directory has no matching source marker')
    else:
        destination.parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.research-source-') as temporary:
            staging = Path(temporary) / 'source'
            staging.mkdir()
            archive = Path(temporary) / 'source.tar'
            with archive.open('wb') as out:
                subprocess.run(['git', '-C', str(args.source_checkout), 'archive', commit,
                                'server-go'], stdout=out, check=True)
            with tarfile.open(archive) as source:
                source.extractall(staging, filter='data')
            (staging / '.source-commit').write_text(commit + '\n')
            staging.rename(destination)
    print('Legacy Go research dependency ready:', destination)
    print('This source pin is not the current Aimee server release.')


if __name__ == '__main__':
    main()
