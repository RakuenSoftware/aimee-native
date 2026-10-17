"""Preserve public PR head versions privately through registered Git commands."""
from pathlib import Path
import hashlib
import json
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
SOURCE = Path('/home/virant/dev/aimee-native-tooling-owner')
CLI = '/home/virant/.local/bin/aimee'


def command(*args):
    result = subprocess.run([CLI, 'git', *args, 'path='+str(SOURCE)],
                            capture_output=True, text=True, timeout=120)
    if result.returncode or 'error:' in result.stdout.lower():
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def main():
    records = []
    for number in (3001, 3002, 3006, 3013, 3014, 3015, 3016, 3017, 3020):
        metadata = json.loads((HERE / f'pr-{number}.json').read_text())
        files = list(metadata.get('files', []))
        for listing in sorted(HERE.glob(f'pr-{number}-files-*.json')):
            files.extend(json.loads(listing.read_text()))
        branch = f'audit/preserve-private-source-{number}-20261017'
        output = command('branch', 'create', 'name='+branch, 'base='+metadata['head_sha'])
        (HERE / f'pr-{number}-checkout.txt').write_text(output)
        manifest, absent = [], []
        archive_path = HERE / f'pr-{number}-head-source.tar.gz'
        with tarfile.open(archive_path, 'w:gz') as archive:
            for name in sorted(set(files)):
                path = SOURCE / name
                if not path.is_file():
                    absent.append(name)
                    continue
                raw = path.read_bytes()
                archive.add(path, arcname=name, recursive=False)
                manifest.append(dict(path=name, bytes=len(raw),
                                     sha256=hashlib.sha256(raw).hexdigest()))
        with tarfile.open(archive_path) as archive:
            for item in manifest:
                raw = archive.extractfile(item['path']).read()
                if hashlib.sha256(raw).hexdigest() != item['sha256']:
                    raise ValueError('archive verification failed: '+item['path'])
        record = dict(pr=number, head_sha=metadata['head_sha'], files=manifest,
                      paths_absent_at_head=absent,
                      archive_sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest())
        (HERE / f'pr-{number}-source-inventory.json').write_text(json.dumps(record, indent=2)+'\n')
        records.append(record)
        print(json.dumps(dict(pr=number, verified_files=len(manifest), absent=len(absent),
                              archive_bytes=archive_path.stat().st_size)), flush=True)
    print(command('switch', 'audit/private-research-transfer-20261017'), flush=True)
    (HERE / 'historical-source-preservation.json').write_text(json.dumps(records, indent=2)+'\n')


if __name__ == '__main__':
    main()
