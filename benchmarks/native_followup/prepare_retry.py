"""Freeze next procedure-learning round using prior responses and binary feedback."""
import hashlib,json,sys
from pathlib import Path
plan,training,evaluation,root=map(Path,sys.argv[1:5]);attempt=int(sys.argv[5])
assert 2<=attempt<=5
assert (training/'DONE').exists() and (evaluation/'DONE').exists()
rows=[json.loads(x) for x in (evaluation/'results.jsonl').read_text().splitlines()]
previous=[json.loads(x) for x in (training/'results.jsonl').read_text().splitlines()]
assert len(rows)==960 and len(previous)==24
rules={r['case_spec']['workflow']:r['answer'] for r in previous}
original=json.loads((plan/'cases.json').read_text());cases=[]
for c in original:
 outcomes=[r for r in rows if r['enabled'] and r['case_spec']['workflow']==c['workflow']]
 assert len(outcomes)==20
 # Binary executor feedback only: no expected test answers or gold rules enter learning.
 feedback=[dict(input=r['case_spec']['input'],answer=r['answer'],success=bool(r['correct'])) for r in outcomes]
 c=dict(c)
 c['query']+=' Your previous stored procedure was '+json.dumps(rules[c['workflow']])+'. Executor feedback from its use: '+json.dumps(feedback,separators=(',',':'))+'. Keep a successful rule or correct an unsuccessful rule using the original examples. Return only the reusable multiplication-and-addition rule in one sentence under 100 characters.'
 cases.append(c)
root.mkdir();root.chmod(0o755);(root/'image').symlink_to((plan/'image').resolve(),target_is_directory=True)
(root/'cases.json').write_text(json.dumps(cases,indent=2))
(root/'heldout.json').write_bytes((plan/'heldout.json').read_bytes())
manifest=dict(attempt=attempt,feedback='Previous procedure and all 20 previous task responses with binary executor success; no expected evaluation answers',evaluation='Same fixed 480 inputs repeated; no longer an unseen-input generalization test after round 1',inputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [plan/'cases.json',plan/'heldout.json',training/'results.jsonl',evaluation/'results.jsonl']})
(root/'plan.json').write_text(json.dumps(manifest,indent=2))
