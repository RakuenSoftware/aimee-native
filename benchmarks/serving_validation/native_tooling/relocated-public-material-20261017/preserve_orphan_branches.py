from pathlib import Path
import hashlib
import json
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
SOURCE = Path('/home/virant/dev/aimee-native-tooling-owner')
for index in range(3):
    row = json.loads((HERE/f'orphan-branch-{index}.json').read_text())
    args = ['/home/virant/.local/bin/aimee', 'git', 'branch', 'create',
            f'name=audit/preserve-orphan-native-{index}-20261017',
            'base=origin/'+row['branch'], 'path='+str(SOURCE)]
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if result.returncode or 'error:' in result.stdout.lower():
        raise RuntimeError(result.stdout+result.stderr)
    (HERE/f'orphan-branch-{index}-checkout.txt').write_text(result.stdout)
    files = []
    for listing in sorted(HERE.glob(f'orphan-branch-{index}-files-*.json')):
        files.extend(json.loads(listing.read_text()))
    inventory = []
    archive_path = HERE/f'orphan-branch-{index}-source.tar.gz'
    with tarfile.open(archive_path, 'w:gz') as archive:
        for name in files:
            path = SOURCE/name
            if not path.is_file(): raise ValueError('source path missing: '+name)
            raw = path.read_bytes()
            archive.add(path, arcname=name, recursive=False)
            inventory.append(dict(path=name, sha256=hashlib.sha256(raw).hexdigest()))
    with tarfile.open(archive_path) as archive:
        for item in inventory:
            if hashlib.sha256(archive.extractfile(item['path']).read()).hexdigest() != item['sha256']:
                raise ValueError('source archive verification failed')
    (HERE/f'orphan-branch-{index}-inventory.json').write_text(json.dumps(dict(
        branch=row['branch'], checkout=result.stdout, files=inventory,
        archive_sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest()), indent=2)+'\n')
    print('Preserved branch '+row['branch']+': '+str(len(inventory))+' source files', flush=True)
subprocess.run(['/home/virant/.local/bin/aimee', 'git', 'switch',
                'audit/private-research-transfer-20261017', 'path='+str(SOURCE)], check=True)
