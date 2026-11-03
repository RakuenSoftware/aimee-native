"""Exploratory private CPU thread tuning; not an end-to-end request benchmark."""
import argparse,sys,pathlib,os,json,time,hashlib
p=argparse.ArgumentParser();p.add_argument("--output",required=True);args=p.parse_args()
root=pathlib.Path(args.output);root.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,'/opt/aimee-native-compiler')
os.environ['AIMEE_NATIVE_LIBRARY']='/opt/aimee-memory-lab/aimee-native/target/release/libaimee_native.so'
os.environ['HF_HUB_OFFLINE']='1'
from gemma_compile import GemmaCompiler
import torch
compiler=GemmaCompiler('/opt/aimee-memory-lab/gemma4');compiler.load()
facts=['The verification vault code is 53728.','The verification project is named Willow.','The verification drink is chamomile tea.']
request={'identity':{'records':[{'id':str(i)} for i in range(3)]},'response':{'facts':[{'content':s} for s in facts]}}
rows=[]
for i,threads in enumerate([12,8,16,8,12,16]):
 torch.set_num_threads(threads);start=time.perf_counter();tokens,banks=compiler.encode(request);elapsed=time.perf_counter()-start
 h=hashlib.sha256()
 for _,pair in sorted(banks.items()):
  for tensor in pair:h.update(tensor.contiguous().view(torch.uint8).numpy().tobytes())
 row={'threads':threads,'seconds':elapsed,'tokens':len(tokens),'tensor_sha256':h.hexdigest()};rows.append(row);del tokens,banks
 (root/'report.json').write_text(json.dumps({'status':'running','rows':rows},indent=2)+'\n');print(json.dumps(row),flush=True)
assert len({r['tensor_sha256'] for r in rows})==1
(root/'report.json').write_text(json.dumps({'status':'passed','rows':rows},indent=2)+'\n')
