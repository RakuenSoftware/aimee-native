from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import asyncio,ctypes,hashlib,json,os,sys,tempfile
root=Path('/opt/jmlr-second-review-20261005/repair-cache/gemma-composition-candidate-r1')
sys.path.insert(0,str(root/'candidate-site'))
import aimee_native_runtime.composition as c
from transformers import AutoTokenizer
model='/var/lib/aimee-large-release-validation/cuda-5080-20260930/models'
binding='/opt/aimee-native-serving/clean-release-env-build2/lib/python3.12/site-packages/aimee_gemma4_12b/native/adapter.json'
os.environ['AIMEE_NATIVE_PLUGIN_CONTRACT']=binding
library=str(Path(binding).parent/'libaimee_native.so')
tokenizer=AutoTokenizer.from_pretrained(model,local_files_only=True)
for context in ['', 'Use memory.']:
 text,bank,contract=c.prepare_contract(tokenizer,model,context,['A fact containing literal <bos> and <|turn>user markers.'],'revision')
 tasks=[{'role':'user','content':'First question?'},{'role':'assistant','content':'Previous answer.'},{'role':'user','content':'Follow-up question?'}]
 request=[{'role':'system','content':context}]+tasks
 incoming=tokenizer.encode(tokenizer.apply_chat_template(request,tokenize=False,add_generation_prompt=True,enable_thinking=False),add_special_tokens=False)
 control=tokenizer.encode(tokenizer.apply_chat_template([{'role':'system','content':context.strip()+'\n\nAuthoritative memory:\nA fact containing literal <bos> and <|turn>user markers.'}]+tasks,tokenize=False,add_generation_prompt=True,enable_thinking=False),add_special_tokens=False)
 remainder=c.remaining_input({'type':'token','prompt_token_ids':incoming},contract)['prompt_token_ids']
 assert bank+remainder==control
 print(json.dumps({'test':'compiled-real-stock-tokenizer','context_empty':not context,'bank_tokens':len(bank),'removed_request_prefix_tokens':len(contract['request_prefix_tokens']),'task_tokens':len(remainder),'exact_control_token_identity':True}))

# Run the actual candidate compiled worker RPC and real capture constructor.
# Device-capability metadata is mocked explicitly: this CPU check must not initialize CUDA.
import aimee_native_runtime.worker as worker
import aimee_native_runtime.capture_session as session
config={'offline_prefix_capture':True,'model':model,'adapter':'gemma4-12b','library':library,
        'gguf_weights':'synthetic-not-loaded.gguf','gguf_weights_sha256':'a'*64,
        'gguf_weight_profile':'synthetic-cpu-fixture','native_system_context':context,
        'model_revision':'revision','serve':{'max_model_len':2048}}
fake=NS(_aimee_capture_config=lambda exclusive:config,model_runner=NS())
try:
 with patch('torch.cuda.get_device_capability',return_value=(12,0)):
  result=worker.AimeeWorker.aimee_attention_capture_begin(fake,bank,{'text':text,'composition':contract},'/unused-synthetic-candidate-capture',True)
 assert result=={'state':'armed'} and session.CURRENT.profile['composition']==contract
 print(json.dumps({'test':'compiled-worker-real-capture-envelope','passed':True,'cuda_initialization':'mocked-not-run'}))
finally:session.CURRENT=None

# Exercise the actual stock vLLM serving method extension point on an instance.
from vllm.entrypoints.openai.chat_completion.serving import OpenAIServingChat
from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest
from vllm.inputs import tokens_input
handler=OpenAIServingChat.__new__(OpenAIServingChat)
async def check_model(request):return None
async def render_chat(request):return request.messages,[tokens_input(incoming)]
handler._check_model=check_model;handler._preflight=lambda n:None;handler.online_renderer=NS(render_chat=render_chat)
owner=NS(gemma_contexts={'publication':contract},catalog_digest='revision-a')
c.install_renderer(owner,NS(state=NS(openai_serving_chat=handler)))
try:
 request=ChatCompletionRequest(model=model,messages=request,vllm_xargs={'aimee_publication':'publication','aimee_catalog_digest':'revision-a'})
 result=asyncio.run(handler.render_chat_request(request))
 assert result[1][0]['prompt_token_ids']==remainder
 print(json.dumps({'test':'actual-stock-vllm-instance-render-method','passed':True,'engine_input_type':result[1][0]['type']}))
finally:c.uninstall_renderer(owner)

# Verify candidate composition identity against the installed immutable Rust publisher.
lib=ctypes.CDLL(library);entry=lib.aimee_gemma4_12b_adapter;entry.argtypes=[ctypes.c_char_p];entry.restype=ctypes.c_void_p
free=lib.aimee_model_adapter_result_free;free.argtypes=[ctypes.c_void_p];free.restype=None
architecture=json.loads((Path(model)/'config.json').read_bytes());tokens=[11,12];segments=[]
for layer in range(48):
 for value in [False,True]:segments.append({'layer':layer,'value':value,'heads':1 if layer%6==5 else 8,'width':512 if layer%6==5 else 256,'positions':2})
profile={'composition':dict(contract,bank_prefix_sha256=c.digest(tokens)),'test_fixture':'actual-installed-rust-publication'}
with tempfile.TemporaryDirectory(dir=root/'buildtmp',prefix='rust-publication-') as directory:
 path=Path(directory);payload=path/'payload';payload.write_bytes(bytes(sum(s['heads']*s['width']*s['positions']*2 for s in segments)))
 pointer=entry(json.dumps({'op':'publish','config':architecture,'tokens':tokens,'positions':2,'segments':segments,'payload':str(payload),'destination':str(path/'artifact'),'profile':profile}).encode());assert pointer
 try:spec=json.loads(ctypes.string_at(pointer))
 finally:free(pointer)
 raw=(path/'artifact/profile.json').read_bytes();index=json.loads((path/'artifact/index.json').read_bytes())
 c.validate_publication(raw,index,spec)
 try:c.validate_publication(raw+b' ',index,spec)
 except ValueError:pass
 else:raise AssertionError('altered profile bytes accepted')
 print(json.dumps({'test':'compiled-contract-installed-rust-publication','passed':True,'segments':96,'positions':2,'payload_bytes':payload.stat().st_size,'tampered_profile_rejected':True}))
assert not __import__('torch').cuda.is_initialized()
print(json.dumps({'cpu_only':True,'compiled_module':c.__file__,'cuda_initialized':False}))
