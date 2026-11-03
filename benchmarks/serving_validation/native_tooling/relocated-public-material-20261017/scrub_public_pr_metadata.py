"""Remove backed-up research metadata through the registered public Git tool."""
from pathlib import Path
import json
import subprocess

HERE = Path(__file__).resolve().parent
PUBLIC = '/home/virant/dev/aimee-native-tooling-owner'
records = []
for number in (3001, 3002, 3006, 3013, 3014, 3015, 3016, 3017, 3020):
    if not (HERE / f'pr-{number}.json').is_file():
        raise RuntimeError('original PR record was not preserved')
    if not (HERE / f'pr-{number}-source-inventory.json').is_file():
        raise RuntimeError('original source was not preserved')
    result = subprocess.run([
        '/home/virant/.local/bin/aimee', 'git', 'pr', 'edit',
        'number='+str(number), 'title=Withdrawn',
        "body=Details removed at the repository owner's request.",
        'path='+PUBLIC,
    ], capture_output=True, text=True, timeout=120)
    record = dict(number=number, returncode=result.returncode,
                  stdout=result.stdout, stderr=result.stderr)
    records.append(record)
    (HERE / 'public-pr-metadata-cleanup-results.json').write_text(json.dumps(records, indent=2)+'\n')
    if result.returncode or 'error:' in result.stdout.lower():
        raise RuntimeError('PR edit failed: '+str(number))
    print('Removed research title/body from public PR '+str(number), flush=True)
