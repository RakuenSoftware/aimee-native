"""Freeze own-only versus shared memory using pre-existing round-one candidates."""
import hashlib,json,sys
from pathlib import Path
from procedure_gate import validate
old,root=map(Path,sys.argv[1:3]);root.mkdir();root.chmod(0o755)
rows=[json.loads(x) for x in (old/'r1-gemma-training/results.jsonl').read_text().splitlines()]
for arm in ['own','shared']:
 out=root/arm;out.mkdir();selected=[]
 decisions=json.loads((old/'r1-decisions.json').read_text());by={d['key']:d for d in decisions}
 for r in rows:
  c=r['case_spec'];candidate=r['answer'];accepted=validate(candidate,c['examples'])['accepted']
  answer=(candidate if accepted else 'unknown') if arm=='own' else by[c['key']]['selected']
  selected.append(dict(case_spec=c,enabled=False,answer=answer,selection_provenance=dict(arm=arm,original=str(old))))
 (out/'results.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in selected));(out/'DONE').write_text('derived publication input, not model response')
(root/'protocol.json').write_text(json.dumps(dict(arms=['no memory','Gemma own accepted memory','same memory plus validated Qwen contributions'],source=str(old),cases_sha256=hashlib.sha256((old/'r1-plan/heldout.json').read_bytes()).hexdigest(),learning='none; saved candidates frozen before comparison',requests=1920,unit='24 workflows; 20 correlated inputs each'),indent=2))
