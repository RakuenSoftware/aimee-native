"""Paired 2,500-request Gemma evaluation with fixed cases and native traces."""
import decimal,json,os,subprocess,sys,time
from pathlib import Path
repo=Path(__file__).resolve().parents[2];source=Path(sys.argv[1]);root=Path(sys.argv[2]);root.mkdir();os.chmod(root,0o755)
cases=json.loads((source/'cases.json').read_text());command=['runuser','-u','memory-model','--','/opt/aimee-memory-lab/venv/bin/python',str(repo/'benchmarks/native_replication/reuse_worker.py'),'--model','/opt/aimee-memory-lab/gemma4','--image',str(source/'image')]
(root/'command.json').write_text(json.dumps(command));(root/'image-current.json').write_bytes((source/'image/CURRENT').read_bytes())
def score(answer,c):
 if c['scorer']=='number':
  try:
   a=decimal.Decimal(answer.strip());b=decimal.Decimal(c['expected']);return a.is_finite() and abs(a-b)<=abs(b)*decimal.Decimal('0.00001')
  except decimal.InvalidOperation:return False
 return answer.strip().rstrip('.').casefold()==c['expected'].strip().rstrip('.').casefold()
log=(root/'worker.stderr').open('x');worker=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1)
try:
 ready=json.loads(worker.stdout.readline());assert ready['ready'];(root/'runtime.json').write_text(json.dumps(ready))
 for i,c in enumerate(cases):
  for enabled in [False,True]:
   worker.stdin.write(json.dumps(dict(case=c['id']+('-native' if enabled else '-disabled'),query=c['query'],enabled=enabled,reuse_encoding=False))+'\n');worker.stdin.flush()
   line=worker.stdout.readline()
   if not line:raise RuntimeError('model worker exited')
   row=json.loads(line);row.update(case_spec=c,correct=score(row.get('answer',''),c));row['abstained']=row.get('answer','').strip().rstrip('.').casefold()=='unknown'
   with (root/'results.jsonl').open('a') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())
  if i%25==0:print(json.dumps(dict(completed=(i+1)*2,last=c['id'],answer=row.get('answer'),correct=row['correct'])),flush=True)
finally:
 worker.stdin.close();worker.wait(timeout=60);log.close()
(root/'DONE').write_text(str(time.time()))
