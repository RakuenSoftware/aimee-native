"""Replay first coding action with identical input and no/text/native experience.

Diagnostic only: these responses are not scored SWE-bench attempts.
"""
import importlib.util,json,pathlib,re,time,urllib.request,os
ROOT=pathlib.Path('/opt/swe-native')
spec=importlib.util.spec_from_file_location('swe_runner',ROOT/'run.py')
run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)
with urllib.request.urlopen(run.BASE+'/v1/models') as r:run.MODEL=json.load(r)['data'][0]['id']
failure_history=bool(os.environ.get('FAILURE_HISTORY'))
out=ROOT/os.environ.get('DIAG_OUTPUT', 'diagnosis-20260927-failure' if failure_history else 'diagnosis-20260927');out.mkdir(exist_ok=True)
for iid in ['astropy__astropy-13438','django__django-11377','matplotlib__matplotlib-25340','mwaskom__seaborn-3187']:
    base=ROOT/'results'/'learn-1'/iid
    lesson=json.loads((base/'experience.json').read_text())['lesson']
    if os.environ.get('DIAG_PUBLICATIONS'):
        pubs=json.loads(pathlib.Path(os.environ['DIAG_PUBLICATIONS']).read_text())
        pub={'publication':next(x['key'] for x in pubs if x['task']==iid)}
    else:pub=run.bridge({'op':'publish','facts':[lesson],'retain':[]})
    trajectory=json.loads((base/'trajectory.json').read_text())
    messages=[{k:m[k] for k in ('role','content')} for m in trajectory['messages'][:2]]
    if failure_history:
        trajectory=json.loads((ROOT/'results'/'learn-2'/iid/'trajectory.json').read_text())
        messages=[]
        for m in trajectory['messages']:
            if m.get('extra',{}).get('interrupt_type')=='FormatError':break
            if m['role'] in ('system','user','assistant'):messages.append({k:m[k] for k in ('role','content')})
        while len(messages)>3 and run.api('/tokenize',{'model':run.MODEL,'messages':messages,'chat_template_kwargs':{'enable_thinking':False}})['count']>7400:
            del messages[2:4]
    for mode in os.environ.get('DIAG_MODES','none,text,native').split(','):
        target=out/(iid+'-'+mode+'.json')
        if target.exists():continue
        ms=[dict(m) for m in messages]
        if mode=='text':ms[0]['content']+='\nPrior coding experience:\n'+lesson
        body={'model':run.MODEL,'messages':ms,'temperature':0,'seed':20260926,'max_tokens':512,'chat_template_kwargs':{'enable_thinking':False}}
        if mode=='native':body['vllm_xargs']={'aimee_publication':pub['publication']}
        start=time.monotonic();response=run.api('/v1/chat/completions',body)
        content=response['choices'][0]['message'].get('content') or ''
        row={'task':iid,'mode':mode,'request':body,'response':response,'seconds':time.monotonic()-start,'bash_blocks':len(re.findall(r'```(?:bash|mswea_bash_command)\s*\n(.*?)\n```',content,re.S)),'thought_count':content.count('thought')}
        target.write_text(json.dumps(row,indent=2)+'\n')
        print(json.dumps({k:row[k] for k in ('task','mode','seconds','bash_blocks','thought_count')}),flush=True)
