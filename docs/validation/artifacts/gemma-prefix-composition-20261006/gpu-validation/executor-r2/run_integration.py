#!/usr/bin/env python3
"""Owned adapter integration. Never stop another workload or service."""
import os,sys,json,time,hashlib,socket,subprocess,signal,fcntl,shutil,urllib.request,urllib.error,re,string,collections
from pathlib import Path
ROOT=Path('/opt/jmlr-second-review-20261005/repair-cache/gemma-composition-candidate-r1')
WORK=ROOT/'gpu-validation'
NAS=Path('/mnt/pve/backup/aimee-experiments/root-evacuation-20261005-r1/gemma-composition-candidate-r1/gpu-validation')
PYTHON='/opt/aimee-native-serving/clean-release-env-build2/bin/python'
EXPECTED='0e8ff8850e71f353ac45b547644a37674bd065e8223188f80a9ab98c203dac22'
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def gpu_pids():return subprocess.check_output(['nvidia-smi','--id=0','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
def scores(answer,golds):
 def norm(s):return ' '.join(re.sub(r'\b(a|an|the)\b',' ',''.join(c for c in s.lower() if c not in string.punctuation)).split()).split()
 a=norm(answer);em=0;f1=0
 for g in golds:
  b=norm(g);em=max(em,int(a==b));n=sum((collections.Counter(a)&collections.Counter(b)).values());f1=max(f1,int(a==b) if not a or not b else 2*n/(len(a)+len(b)))
 return {'em':em,'f1':f1}
def control(request):
 with socket.socket(socket.AF_UNIX) as s:
  s.settimeout(600);s.connect(str(WORK/'control.sock'));s.sendall(json.dumps(request).encode()+b'\n');return json.loads(s.makefile('rb').readline())
def http(body):
 req=urllib.request.Request('http://127.0.0.1:18968/v1/chat/completions',json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer isolated-gemma-integration-only'})
 try:
  with urllib.request.urlopen(req,timeout=600) as r:return r.status,json.load(r)
 except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
def body(instruction,question,publication=None):
 b={'model':P['model']['model'],'messages':[{'role':'system','content':instruction},{'role':'user','content':question}],'chat_template_kwargs':{'enable_thinking':False},**P['decoding']}
 if publication is not None:b['vllm_xargs']={'aimee_publication':publication}
 return b
def prompt(r):
 assert isinstance(r.get('prompt_token_ids'),list),'actual prompt-token proof absent'
 return r['prompt_token_ids']
def output(r):
 assert isinstance(r['choices'][0].get('token_ids'),list),'actual output-token IDs absent'
 return r['choices'][0]['token_ids']
def refresh(publications):
 w=control({'op':'withdraw'});assert w.get('state')=='withdrawn',w
 write(WORK/'catalog.json',{'recipient':'gemma-prefix-integration-private','model_config_sha256':P['model']['config_sha256'],'publications':publications})
 r=control({'op':'refresh','generation':w['generation']});assert r.get('state')=='active',r
 return r
def pair(name,facts,question,golds):
 w=control({'op':'withdraw'});assert w.get('state')=='withdrawn',w
 dest=WORK/'prepared'/hashlib.sha256(json.dumps({'name':name,'facts':facts,'protocol':EXPECTED},sort_keys=True).encode()).hexdigest()
 req={'op':'prepare','generation':w['generation'],'facts':facts,'context':P['instruction'],'destination':str(dest)}
 prep=control(req);write(WORK/(name+'-preparation.json'),{'request':req,'response':prep});assert prep.get('state')=='prepared',prep
 spec=prep['publication'];assert spec['root']==str(dest),spec;refresh({name:spec})
 nb=body(P['instruction'],question,name);tb=body(P['instruction']+'\n\nAuthoritative memory:\n'+'\n'.join(facts),question)
 assert all(fact not in json.dumps(nb,ensure_ascii=False) for fact in facts)
 ts,tr=http(tb);ns,nr=http(nb);assert ts==ns==200,(ts,tr,ns,nr)
 index=json.loads((dest/'index.json').read_bytes());bank=index['records'][spec['key']]['tokens'];tp=prompt(tr);np=prompt(nr)
 result={'name':name,'publication':spec,'bank_token_ids':bank,'text_prompt_token_ids':tp,'native_prompt_token_ids':np,'request_native_token_proof_passed':bank+np==tp,'native_request_contains_no_canonical_facts':True,'text_request':tb,'native_request':nb,'text_response':tr,'native_response':nr,'text_output_ids':output(tr),'native_output_ids':output(nr),'greedy_output_ids_equal':output(tr)==output(nr),'text_scores':scores(tr['choices'][0]['message']['content'] or '',golds),'native_scores':scores(nr['choices'][0]['message']['content'] or '',golds)}
 write(WORK/(name+'-pair.json'),result);assert result['request_native_token_proof_passed'],'token composition mismatch'
 return result
P=json.loads((NAS/'protocol.json').read_bytes());assert sha(NAS/'protocol.json')==EXPECTED
receipt={'status':'failed','completed':False,'gpu_released':False,'protocol_sha256':EXPECTED,'protocol_relative_path':'protocol.json','candidate_runtime_sha256':P['candidate']['runtime_wheel_sha256'],'six_case_ids':P['six_case_ids'],'scope':P['scope']}
WORK.mkdir(exist_ok=False,mode=0o700);process=None;lock=None
try:
 prior=json.loads(Path(P['prerequisite']['receipt']).read_bytes())
 assert prior.get('complete') is True and prior.get('gpu_released') is True and prior.get('independent_rescore_coverage_passed') is True,prior
 assert prior.get('protocol_sha256')==P['prerequisite']['protocol_sha256'],prior
 prior_root=Path(P['prerequisite']['receipt']).parent
 assert sha(prior_root/'protocol.json')==P['prerequisite']['protocol_sha256']
 assert sha(prior_root/'analysis.json')==prior['analysis_sha256']
 for group in ['source_sha256','result_sha256']:
  assert prior.get(group),('missing prerequisite map',group)
  for name,digest in prior[group].items():
   resolved=(prior_root/name).resolve();assert resolved.is_relative_to(prior_root.resolve()),('unsafe prerequisite path',name)
   assert sha(resolved)==digest,('invalid prerequisite artifact',name)
 assert subprocess.run(['systemctl','is-active','--quiet',P['prerequisite']['unit']]).returncode!=0,'full SQuAD active'
 lock=open(P['prerequisite']['gpu_lock'],'a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert not gpu_pids(),'foreign GPU processes'
 manifest=json.loads((NAS/'executor-manifest-r2.json').read_bytes())
 for name,digest in manifest['executor_sha256'].items():
  path=(ROOT/'gpu-executor-r2'/name).resolve();assert path.is_relative_to((ROOT/'gpu-executor-r2').resolve())
  assert sha(path)==digest,('executor changed',name)
 assert sha(NAS/'frozen-sources.json')=='18a881813cfdbff1c24843980d025b5d9d9d834f38d62acb7ddff75a21d052f3'
 frozen=json.loads((NAS/'frozen-sources.json').read_bytes())
 frozen['source_sha256'].update(manifest['source_external_pins'])
 for path,digest in frozen['source_sha256'].items():assert sha(path)==digest,('source mismatch',path)
 for name,digest in P['inputs_sha256'].items():assert sha(NAS/name)==digest,name
 write(WORK/'preflight.json',{'source_sha256':frozen['source_sha256'],'dependency_versions':frozen['dependency_versions'],'gpu_empty':True})
 for n in ['protocol.json','cases.json','research-fixture.json','frozen-sources.json']:shutil.copy2(NAS/n,WORK/n)
 for n in ['prepared','cache','tmp']:(WORK/n).mkdir()
 base_config=Path('/opt/aimee-native-serving/q4-serving-config-r6.json')
 assert sha(base_config)=='cd6a99aa4a207304fbdb3fca1f87401a1dc1dce1af2b3bba2bd40a86485bf3da','released base serving config changed'
 config=json.loads(base_config.read_bytes())
 config.update(library='/opt/aimee-native-serving/clean-release-env-build2/lib/python3.12/site-packages/aimee_gemma4_12b/native/libaimee_native.so',catalog=str(WORK/'catalog.json'),recipient='gemma-prefix-integration-private',control_socket=str(WORK/'control.sock'),native_preparation_enabled=True,preparation_root=str(WORK/'prepared'),start_paused=True,native_system_context=P['instruction'])
 config['serve']=dict(P['model']['serve'],host='127.0.0.1',port=18968)
 assert config['gguf_weights']==P['model']['gguf_weights'] and config['gguf_weights_sha256']==P['model']['gguf_sha256'] and config['model']==P['model']['model']
 write(WORK/'config.json',config);write(WORK/'catalog.json',{'recipient':config['recipient'],'model_config_sha256':P['model']['config_sha256'],'publications':{}})
 helper=ROOT/'gpu-executor-r2'
 env=dict(os.environ,PYTHONPATH=str(helper)+':'+str(ROOT/'candidate-site'),CUDA_VISIBLE_DEVICES='0',OMP_NUM_THREADS='8',VLLM_NO_USAGE_STATS='1',VLLM_API_KEY='isolated-gemma-integration-only',GEMMA_INTEGRATION_TRACE=str(WORK/'native-calls.jsonl'),TMPDIR=str(WORK/'tmp'),XDG_CACHE_HOME=str(WORK/'cache'),TRITON_CACHE_DIR=str(WORK/'cache/triton'),HF_HOME=str(WORK/'cache/huggingface'),VLLM_CONFIG_ROOT=str(WORK/'cache/config'))
 log=open(WORK/'service.log','wb');process=subprocess.Popen([PYTHON,str(helper/'service_boot.py'),str(WORK/'config.json')],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 deadline=time.monotonic()+900
 while True:
  assert process.poll() is None,'isolated service exited'
  try:
   req=urllib.request.Request('http://127.0.0.1:18968/health',headers={'Authorization':'Bearer isolated-gemma-integration-only'})
   with urllib.request.urlopen(req,timeout=3):break
  except OSError:
   assert time.monotonic()<deadline,'startup deadline';time.sleep(2)
 refresh({});eb=body(P['instruction'],'Reply with the word ready.');es,er=http(eb);assert es==200,(es,er)
 from transformers import AutoTokenizer
 tokenizer=AutoTokenizer.from_pretrained(config['model'],local_files_only=True);expected=tokenizer.apply_chat_template(eb['messages'],tokenize=True,add_generation_prompt=True,enable_thinking=False)['input_ids']
 ep=prompt(er)==expected and not (WORK/'native-calls.jsonl').exists();write(WORK/'empty-selection.json',{'request':eb,'response':er,'expected_prompt_token_ids':expected,'stock_tokens_unchanged':ep,'native_calls_absent':not (WORK/'native-calls.jsonl').exists()});assert ep
 paired=[pair(c['id'],[c['context']],c['question'],[a['text'] for a in c['answers']]) for c in json.loads((WORK/'cases.json').read_bytes())]
 revisions=[pair('revision-'+str(i+1),c['facts'],c['query'],[c['expected']]) for i,c in enumerate(P['controls']['canonical_revisions'])]
 assert revisions[0]['publication']['key']!=revisions[1]['publication']['key']
 assert all(r['text_scores']['em']==r['native_scores']['em']==1 for r in revisions)
 last=revisions[-1];sb=body(P['instruction']+' foreign context',P['controls']['canonical_revisions'][-1]['query'],last['name']);ss,sr=http(sb);assert ss==400,(ss,sr)
 w=control({'op':'withdraw'});bad={'op':'prepare','generation':w['generation'],'facts':['overbudget '*4096],'context':P['instruction'],'destination':str(WORK/'prepared'/('f'*64))};br=control(bad);assert 'error' in br,br
 healthy=control({'op':'status'});assert healthy.get('state')=='paused',healthy;activated=refresh({last['name']:last['publication']})
 write(WORK/'denial-controls.json',{'stale_context':{'request':sb,'status':ss,'response':sr},'failed_preparation':{'request':bad,'response':br,'status_after':healthy,'activation_after':activated},'legacy_admission':{'exercised':False,'reason':'legacy admission denial covered by compiled actual admission CPU tests; no unprofiled extra GPU capture'}})
 traces=[json.loads(line) for line in (WORK/'native-calls.jsonl').read_text().splitlines()]
 for r in paired+revisions:
  calls=[t for t in traces if any(p['publication_key']==r['publication']['key'] and p['publication']==r['name'] for p in t['pins'])];assert calls and all(c['native_kernel_returned'] for c in calls);r['native_kernel_call_count']=len(calls)
 keys=['name','publication','request_native_token_proof_passed','native_kernel_call_count','greedy_output_ids_equal','text_scores','native_scores']
 disagreements=[r['name'] for r in paired+revisions if not r['greedy_output_ids_equal']]
 write(WORK/'pairs-summary.json',{'six_case_ids':P['six_case_ids'],'pairs':[{k:r[k] for k in keys} for r in paired],'canonical_revisions':[{k:r[k] for k in keys} for r in revisions],'all_disagreements':disagreements})
 for path,digest in frozen['source_sha256'].items():assert sha(path)==digest,('postflight mismatch',path)
 write(WORK/'postflight.json',{'source_sha256':frozen['source_sha256'],'all_unchanged':True})
 receipt.update(status='passed',paired_case_count=6,request_native_token_proof_passed=True,native_kernel_proof_passed=True,canonical_revision_controls_passed=True,empty_selection_control_passed=True,stale_context_denial_passed=True,failed_preparation_control_passed=True,weights_unchanged=True,config_unchanged=True,tokenizer_unchanged=True,source_sha256=frozen['source_sha256'],greedy_output_disagreements=disagreements)
except BaseException as e:receipt['error']=repr(e)
finally:
 if process is not None:
  try:os.killpg(process.pid,signal.SIGTERM)
  except ProcessLookupError:pass
  try:process.wait(timeout=60)
  except subprocess.TimeoutExpired:
   try:os.killpg(process.pid,signal.SIGKILL)
   except ProcessLookupError:pass
   process.wait(timeout=30)
 for _ in range(30):
  if not gpu_pids():receipt['gpu_released']=True;break
  time.sleep(2)
 if not receipt['gpu_released']:receipt['status']='failed';receipt['error']='GPU not released after owned cleanup'
 receipt['completed']=True
 for p in WORK.rglob('*'):
  if p.is_file() and not {'cache','tmp'}&set(p.relative_to(WORK).parts):
   target=NAS/p.relative_to(WORK);target.parent.mkdir(exist_ok=True,parents=True)
   if target.exists():assert sha(target)==sha(p),('existing immutable evidence differs',str(target))
   else:
    with p.open('rb') as src,target.open('xb') as dest:shutil.copyfileobj(src,dest)
 receipt['artifact_sha256']={str(p.relative_to(NAS)):sha(p) for p in NAS.rglob('*') if p.is_file() and p.name!='verified-completion.json'}
 receipt['result_relative_paths']={'pairs':'pairs-summary.json','native_calls':'native-calls.jsonl','empty_selection':'empty-selection.json','denials':'denial-controls.json','preflight':'preflight.json','postflight':'postflight.json'}
 with (NAS/'verified-completion.json').open('x') as f:f.write(json.dumps(receipt,indent=2)+'\n')
 if lock is not None:fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
print(json.dumps(receipt,indent=2));sys.exit(0 if receipt['status']=='passed' else 1)
