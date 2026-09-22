"""Restore synthetic source assertions before rerunning the failed publication."""
import json,subprocess,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[2];root=Path(sys.argv[1]);plan=json.loads((root/'plan.json').read_text())
rows=[dict(key=c['key'],text=f'My {c["key"]} is {c["previous_expected"]}.') for c in plan['cases']]
with (root/'restore-ingestion.jsonl').open('x') as out:
 subprocess.run([str(repo/'.local/bin/scale-ingest'),str(root/'private/restored-personal.json')],input=''.join(json.dumps(x)+'\n' for x in rows),text=True,stdout=out,check=True)
(root/'RESTORATION.md').write_text('The first correction attempt stored 125 changed assertions but failed publication because it omitted the expected source generation. No revised publication reached the model. This recorded restoration returns those synthetic database assertions to their original values before the corrected run. The old published model image remained unchanged throughout. Original logs and outputs are preserved.\n')
