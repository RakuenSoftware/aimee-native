import json,hashlib,subprocess,os
from pathlib import Path
base=Path('/opt/aimee-qwen-rust');live=base/'live';out=live/'evidence';out.mkdir(exist_ok=True)
results=json.loads((live/'results.json').read_text());traces={}
for row in results:
 id=row['response'].get('id')
 if id:
  t=json.loads((live/'traces'/f'{id}.json').read_text());traces[row['case']]=t
  (out/f'{row["case"]}-trace.json').write_text(json.dumps(t,indent=2))
assert len({json.dumps(t['prompt_token_ids']) for t in traces.values()})==1
assert all(t['memory_prompt_tokens']==0 and 'oolong' not in t['generation_prompt'] and 'Lima' not in t['generation_prompt'] for t in traces.values())
assert traces['native_cold']['memory_encoding_passes']==1
assert traces['native_reuse']['memory_encoding_passes']==0
assert all(e['origin']=='qwen_attention_query' for e in traces['attention_only']['recall_events'])
checks={c:{'prompt_tokens':len(t['prompt_token_ids']),'memory_prompt_tokens':t['memory_prompt_tokens'],'encoding_passes':t['memory_encoding_passes'],'native_attention_reads':t['native_reads'],'recall_calls':len(t['recall_events'] or []),'main_cache_length':t['main_cache_length'],'answer':t['answer']} for c,t in traces.items()}
for c,t in traces.items():
 if c!='none':assert {f['id'] for e in t['recall_events'] for f in e['aimee_response']['facts']}=={5,6}
for name in ['results.json','summary.json']:(out/name).write_bytes((live/name).read_bytes())
(out/'trace-checks.json').write_text(json.dumps(checks,indent=2))
pids={u:int(subprocess.check_output(['systemctl','show',u,'--property=MainPID','--value'])) for u in ['aimee-rust-qwen','aimee-rust-gateway']}
audit={}
for unit,pid in pids.items():
 maps=Path(f'/proc/{pid}/maps').read_text();cmd=Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\x00',b' ').decode()
 libs=sorted({line.split()[-1] for line in maps.splitlines() if '/' in line})
 audit[unit]={'pid':pid,'executable':os.readlink(f'/proc/{pid}/exe'),'command':cmd,'libpython_loaded':any('/libpython' in x or '/libtorch_python' in x for x in libs),'mapped_libraries':libs}
 assert not audit[unit]['libpython_loaded']
audit['binary']={'bytes':(base/'target/release/aimee-qwen').stat().st_size,'sha256':hashlib.sha256((base/'target/release/aimee-qwen').read_bytes()).hexdigest(),'file':subprocess.check_output(['file',str(base/'target/release/aimee-qwen')],text=True).strip()}
(out/'runtime-audit.json').write_text(json.dumps(audit,indent=2))
print(json.dumps(checks,indent=2));print(json.dumps(audit['binary']))
