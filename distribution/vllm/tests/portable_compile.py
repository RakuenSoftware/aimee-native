"""Cross-compile device operations without claiming execution on absent GPUs."""
import argparse,json
from pathlib import Path
import triton
from triton.compiler import ASTSource
from triton.backends.compiler import GPUTarget
from aimee_vllm.kernel import native_attention
from aimee_vllm.decoder_kernel import decode_words,decode_escapes
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--profile-manifest',type=Path);a=p.parse_args()
attention={n:t for n,t in zip(native_attention.arg_names[:9],['*bf16','*bf16','*bf16','*i32','*i32','*i32','*i64','*i64','*i32'])}
constants=dict(zip(native_attention.arg_names[9:],[256,64,1024,512,128,256,64,2,4,2,64,4,.125,3,30.,32,64]))
word_sig={n:'u64' for n in decode_words.arg_names if n!='BLOCK'}
escape_sig={n:'u64' for n in decode_escapes.arg_names if n!='BLOCK'}
profiles=[(native_attention,attention,constants)]
if a.profile_manifest:
 profiles=[]
 for item in json.loads(a.profile_manifest.read_text())['kernels']:
  signature={native_attention.arg_names[k[0]]:v for k,v in item['signature'] if v!='constexpr'}
  constexprs={native_attention.arg_names[k[0]]:v for k,v in item['constants']}
  profiles.append((native_attention,signature,constexprs))
results=[]
for target in [GPUTarget('cuda',80,32),GPUTarget('cuda',89,32),GPUTarget('cuda',90,32),GPUTarget('cuda',120,32),GPUTarget('hip','gfx942',64),GPUTarget('hip','gfx1100',32),GPUTarget('hip','gfx1201',32)]:
 for fn,signature,constexprs in profiles+[(decode_words,word_sig,{'BLOCK':256}),(decode_escapes,escape_sig,{'BLOCK':256})]:
  kernel=triton.compile(ASTSource(fn,signature,constexprs=constexprs),target=target,options={'num_warps':4})
  results.append({'backend':target.backend,'arch':str(target.arch),'kernel':fn.__name__,'head_width':constexprs.get('D'),'compiled':True,'executed':False,'artifact_types':sorted(kernel.asm)})
a.output.write_text(json.dumps({'status':'passed','scope':__doc__,'results':results},indent=2)+'\n');print(a.output.read_text())
