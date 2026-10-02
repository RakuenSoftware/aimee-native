"""Branch retry prompts without revealing evaluation answers."""
import json,subprocess,sys
from pathlib import Path
from procedure_gate import validate
plan,training,evaluation,source,root=map(Path,sys.argv[1:6]);attempt=sys.argv[6];arm=sys.argv[7]
assert arm == 'feedback', 'Reasoning and combined branches cancelled by author'
args=[sys.executable,str(Path(__file__).with_name('prepare_retry.py')),str(plan),str(training),str(evaluation),str(root),attempt]
if (source/'selected-procedures.json').exists():args+=['--accepted-source',str(source)]
subprocess.run(args,check=True)
prior=json.loads((source/'selected-procedures.json').read_text()) if (source/'selected-procedures.json').exists() else {r['key']:r['text'].split(' is ',1)[1].rstrip('.') for r in json.loads((source/'assertions.json').read_text())}
cases=json.loads((root/'cases.json').read_text())
for c in cases:
 if arm in ('feedback','combined'):
  v=validate(prior[c['key']],c['examples'])
  c['query']+=' Checks of your stored rule against the original training examples: '+json.dumps(v,separators=(',',':'))+'. Correct the rule if these checks fail.'
 if arm in ('reasoning','combined'):
  c['query']=c['query'].replace('Return only one sentence under 100 characters specifying the multiplication and addition; do not list examples.','').replace('Return only the reusable multiplication-and-addition rule in one sentence under 100 characters.','')
  c['query']+=' Derive the multiplication and addition from the original examples. Show your calculation and check the proposed rule against all three examples before committing. End with one line: FINAL: Multiply the input by A and add B. Use subtract if needed.'
(root/'cases.json').write_text(json.dumps(cases,indent=2))
p=root/'plan.json';m=json.loads(p.read_text());m.update(arm=arm,learning_token_budget=512 if arm!='feedback' else 32,validation='original three examples only');p.write_text(json.dumps(m,indent=2))
