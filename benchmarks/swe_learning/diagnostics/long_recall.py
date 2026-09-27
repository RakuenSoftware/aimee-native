"""All selected records consumed across the local-window boundary; diagnostic."""
import importlib.util,json,pathlib,time,urllib.request
ROOT=pathlib.Path('/opt/swe-native');spec=importlib.util.spec_from_file_location('swe_runner',ROOT/'run.py');run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)
with urllib.request.urlopen(run.BASE+'/v1/models') as r:run.MODEL=json.load(r)['data'][0]['id']
facts=['The synthetic audit vault code is 593827.','The synthetic audit project codename is Juniper Lantern.','The synthetic audit preferred drink is saffron tea.']
pub=run.bridge({'op':'publish','facts':facts,'retain':[]});rows=[]
out=ROOT/'diagnosis-20260927-long-recall.json'
for repeats in (0,80,160,400,700):
 for mode in ('none','text','native'):
  messages=[{'role':'user','content':('Background note: ordinary software maintenance is ongoing.\n'*repeats)+'Report the synthetic audit vault code, project codename and preferred drink. Give just those three values.'}]
  if mode=='text':messages.insert(0,{'role':'system','content':'Authoritative memory:\n'+'\n'.join(facts)})
  body={'model':run.MODEL,'messages':messages,'temperature':0,'seed':20260926,'max_tokens':100,'chat_template_kwargs':{'enable_thinking':False}}
  if mode=='native':body['vllm_xargs']={'aimee_publication':pub['publication']}
  start=time.monotonic();response=run.api('/v1/chat/completions',body);answer=response['choices'][0]['message']['content'] or ''
  row={'repeats':repeats,'mode':mode,'response':response,'seconds':time.monotonic()-start,'all_three':all(s.lower() in answer.lower() for s in ('593827','Juniper Lantern','saffron tea'))};rows.append(row);out.write_text(json.dumps({'publication':pub,'facts':facts,'rows':rows},indent=2)+'\n');print(json.dumps({'mode':mode,'repeats':repeats,'tokens':response['usage']['prompt_tokens'],'all_three':row['all_three']}),flush=True)
