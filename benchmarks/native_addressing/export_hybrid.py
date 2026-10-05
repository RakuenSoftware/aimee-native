"""Export an exact positioned prepared prefix for catalogue-controlled serving.

Offline byte publication only: no model execution, record selection or policy.
The model/revision/weight profile, attention and recurrent checksums are verified.
"""
import argparse,errno,hashlib,json,os,shutil
from pathlib import Path

def digest(raw):return hashlib.sha256(raw).hexdigest()
def write(path,raw):
 with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())

def export(root,base_key,model_path,revision,int8,encoding,context,destination):
 root,model_path,destination=map(Path,(root,model_path,destination))
 config_raw=(model_path/'config.json').read_bytes();config=json.loads(config_raw);c=config.get('text_config',config)
 expected=digest(b'aimee-complete-hybrid-v1'+revision.encode()+bytes([int8])+config_raw+(model_path/'tokenizer.json').read_bytes())
 index=json.loads((root/'index.json').read_text())
 if index['model']!=expected or index['version']!=1:raise ValueError('prepared model/profile mismatch')
 key=digest(b'hybrid-native-prefix-absolute-v1:'+base_key.encode());entry=index['entries'][base_key]
 if entry['dtype']!='bf16' or entry.get('codec','raw')!='raw' or entry.get('intermediate',False):raise ValueError('export requires lossless BF16 native banks')
 with (root/'native.pack').open('rb') as f:f.seek(entry['offset']);data=f.read(entry['bytes'])
 if len(data)!=entry['bytes'] or digest(data)!=entry['sha256']:raise ValueError('attention payload mismatch')
 recurrent=entry['recurrent'];path=root/recurrent.get('payload',base_key+'.rnn.bin')
 if path.stat().st_size!=recurrent['bytes']:raise ValueError('recurrent byte extent mismatch')
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(8*1024**2),b''):h.update(chunk)
 if h.hexdigest()!=recurrent['sha256']:raise ValueError('recurrent checksum mismatch')
 # Check that the closed system prefix actually contains the declared context.
 from tokenizers import Tokenizer
 tokenizer=Tokenizer.from_file(str(model_path/'tokenizer.json'));text=tokenizer.decode(entry['tokens'],skip_special_tokens=False)
 if encoding=='system-message':
  prefix='<|im_start|>system\n'+(context.strip()+'\n\n' if context.strip() else '')+'Authoritative memory:\n'
  if not text.startswith(prefix) or not text.endswith('<|im_end|>\n'):raise ValueError('native instruction context mismatch')
 elif encoding!='content':raise ValueError('unsupported hybrid encoding')
 layers={i for i,k in enumerate(c['layer_types']) if k=='full_attention'};seen=set();end=0;segments=[]
 for layout in entry['layouts']:
  layer=layout['layer'];shape=layout['shape']
  if layer not in layers or layer in seen or shape!=[1,c['num_key_value_heads'],len(entry['tokens']),c['head_dim']]:raise ValueError('native attention geometry mismatch')
  n=c['num_key_value_heads']*len(entry['tokens'])*c['head_dim']
  if layout['elements']!=n or layout['offset']!=end:raise ValueError('attention extent mismatch')
  for value in [False,True]:segments.append({'layer':layer,'value':value,'heads':shape[1],'width':shape[3],'positions':shape[2]})
  seen.add(layer);end+=2*n
 if seen!=layers or end*2!=len(data):raise ValueError('incomplete attention prefix')
 destination.mkdir(mode=0o700)
 offset=(4096+len(data)+4095)&~4095
 pack=b'\0'*4096+data+b'\0'*(offset-4096-len(data))+b''.join(i.to_bytes(4,'little') for i in range(len(entry['tokens'])))
 write(destination/'compact.pack',pack)
 native={'version':1,'model':expected,'schema':{'segments':segments,'row_bytes':sum(s['heads']*s['width']*2 for s in segments)},'prototypes':len(entry['tokens']),'dictionary_bytes':len(data),'dictionary_sha256':digest(data),'records':{key:{'offset':offset,'tokens':entry['tokens']}},'experimental_approximation':False,'head_major':False,'native_layout':True}
 native_raw=(json.dumps(native,sort_keys=True)+'\n').encode();write(destination/'index.json',native_raw)
 payload=recurrent['sha256']+'.rnn.bin'
 # Prepared payloads are immutable digest objects. Preserve one physical copy
 # on the same filesystem; cross-filesystem publication remains self-contained.
 try:os.link(path,destination/payload)
 except OSError as error:
  if error.errno!=errno.EXDEV:raise
  with path.open('rb') as source,os.fdopen(os.open(destination/payload,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as target:
   shutil.copyfileobj(source,target);target.flush();os.fsync(target.fileno())
 complete={'schema':1,'model':expected,'key':key,'positioning':'native-prefix-absolute-v1','attention_index_sha256':digest(native_raw),'model_config_sha256':digest(config_raw),'architecture':c,'model_revision':revision,'tokenizer_sha256':digest((model_path/'tokenizer.json').read_bytes()),'encoder_weight_profile':'int8' if int8 else 'bf16','encoding':encoding,'system_context_sha256':digest(context.strip().encode()),'recurrent':{**recurrent,'payload':payload}}
 raw=(json.dumps(complete,sort_keys=True)+'\n').encode();write(destination/'hybrid.json',raw)
 return {'root':str(destination),'model':expected,'key':key,'hybrid_state':digest(raw)}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for k in ('root','base-key','model','revision','destination'):p.add_argument('--'+k,required=True)
 p.add_argument('--int8',action='store_true');p.add_argument('--encoding',choices=['content','system-message'],default='system-message');p.add_argument('--system-context',default='')
 a=p.parse_args();print(json.dumps(export(a.root,a.base_key,a.model,a.revision,a.int8,a.encoding,a.system_context,a.destination)))
