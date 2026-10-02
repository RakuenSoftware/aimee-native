"""Separate learned-rule correctness from execution; scoring only, never feedback."""
import json,sys
from pathlib import Path
from procedure_gate import validate
plan,source,evaluation=map(Path,sys.argv[1:4]);cases=json.loads((plan/'cases.json').read_text());selected=json.loads((source/'selected-procedures.json').read_text())
valid={c['workflow']:validate(selected[c['key']],c['examples'])['accepted'] for c in cases}
rows=[json.loads(x) for x in (evaluation/'results.jsonl').read_text().splitlines()];native=[r for r in rows if r['enabled']]
print(json.dumps(dict(correct_procedures=sum(valid.values()),total_procedures=len(valid),native_correct=sum(r['correct'] for r in native),execution_failures_with_valid_procedure=sum(not r['correct'] and valid[r['case_spec']['workflow']] for r in native),failures_with_invalid_procedure=sum(not r['correct'] and not valid[r['case_spec']['workflow']] for r in native)),indent=2))
