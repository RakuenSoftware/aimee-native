import pathlib,json,subprocess,time
ROOT=pathlib.Path('/root/aimee-broader-prefetch-20260928');ROOT.mkdir(exist_ok=True)
REMOTE='/opt/swe-native/broader-source-learning-20260928'
tasks=json.loads(subprocess.check_output(['pct','exec','113','--','cat',REMOTE+'/tasks.json']))
state={'status':'running','started':time.time(),'host_pool_reserve_GiB':40,'images':[]}
def save():
 state['updated']=time.time();data=json.dumps(state,indent=2)+'\n';(ROOT/'status.json').write_text(data)
 script='import pathlib\npathlib.Path('+repr(REMOTE+'/image-readiness.json')+').write_text('+repr(data)+')\n'
 subprocess.run(['pct','exec','113','--','python3','-'],input=script,text=True,check=True)
def pool_free():
 data=json.loads(subprocess.check_output(['lvs','--reportformat','json','--units','b','--nosuffix','-o','lv_size,data_percent','storage/storage']))['report'][0]['lv'][0]
 return float(data['lv_size'])*(1-float(data['data_percent'])/100)
save()
try:
 for task in tasks:
  iid=task['instance_id'];image='docker.io/swebench/sweb.eval.x86_64.'+iid.replace('__','_1776_').lower()+':latest';p=subprocess.run(['pct','exec','113','--','docker','image','inspect',image,'--format','{{.Id}}'],capture_output=True,text=True)
  row={'instance_id':iid,'image':image,'already_present':p.returncode==0}
  if p.returncode:
   free=pool_free();row['pool_free_before_GiB']=free/1024**3
   if free<40*1024**3:raise RuntimeError('stopped at host thin-pool reserve; no further automatic image pulls')
   state['current']=iid;save()
   with (ROOT/(iid+'.log')).open('w') as log:subprocess.run(['pct','exec','113','--','docker','pull',image],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
   p=subprocess.run(['pct','exec','113','--','docker','image','inspect',image,'--format','{{.Id}}'],capture_output=True,text=True,check=True)
  row['id']=p.stdout.strip();state['images'].append(row);save()
 state['status']='complete'
except BaseException as error:state.update(status='failed',error=repr(error));raise
finally:state['finished']=time.time();state['pool_free_GiB']=pool_free()/1024**3;save()
