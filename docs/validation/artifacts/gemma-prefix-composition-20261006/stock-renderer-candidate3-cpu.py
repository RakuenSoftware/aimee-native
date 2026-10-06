"""CPU regression through installed vLLM render_messages, without engine/GPU."""
import importlib.util,json,sys,hashlib
from pathlib import Path
from types import SimpleNamespace
import torch
from transformers import AutoTokenizer,AutoConfig
from vllm.renderers.hf import HfRenderer
if sys.argv[1] == '--compiled':
    from aimee_native_runtime import composition as c
    assert c.__file__.endswith('.so') and '/candidate3-site/' in c.__file__
else:
    spec=importlib.util.spec_from_file_location('candidate_composition',sys.argv[1])
    c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
root='/var/lib/aimee-large-release-validation/cuda-5080-20260930/models'
tokenizer=AutoTokenizer.from_pretrained(root,local_files_only=True)
model=SimpleNamespace(model=root,revision=None,code_revision=None,trust_remote_code=False,
    hf_config=AutoConfig.from_pretrained(root,local_files_only=True),
    enable_prompt_embeds=False,multimodal_config=None,is_multimodal_model=False)
# No engine or renderer constructor: execute the actual synchronous text path.
renderer=HfRenderer.__new__(HfRenderer);renderer.model_config=model
renderer.tokenizer=tokenizer;renderer.use_unified_vision_chunk=False
handler=SimpleNamespace(model_config=model,renderer=renderer,chat_template=None,
    chat_template_content_format='auto',default_chat_template_kwargs={})
render=c.stock_request_renderer(handler)
instruction='Use the external memory available to you. Answer with only the shortest exact answer span, without explanation. If the memory lacks the answer, reply unknown.'
rows=[]
cases=json.loads(Path(sys.argv[2]).read_bytes())
for case in cases:
    text,bank,contract=c.prepare_contract(tokenizer,root,instruction,[case['context']],stock_render=render)
    _,incoming=render([{'role':'system','content':instruction},{'role':'user','content':case['question']}],True)
    _,full=render([{'role':'system','content':instruction+'\n\nAuthoritative memory:\n'+case['context']},{'role':'user','content':case['question']}],True)
    engine_input=renderer.process_for_engine({'prompt_token_ids':incoming},4501.25)
    assert engine_input['type']=='token' and engine_input['arrival_time']==4501.25
    adjusted=c.remaining_input(engine_input,contract)
    assert adjusted['arrival_time']==4501.25
    suffix=adjusted['prompt_token_ids']
    assert bank+suffix==full
    rows.append({'id':case['id'],'bank_tokens':len(bank),'request_prefix_tokens':len(contract['request_prefix_tokens']),'suffix_tokens':len(suffix),'composition_passed':True})
empty=[{'role':'system','content':instruction},{'role':'user','content':'Reply with the word ready.'}]
_,stock=render(empty,True)
old=tokenizer.apply_chat_template(empty,tokenize=True,add_generation_prompt=True,enable_thinking=False)['input_ids']
assert stock!=old and len(stock)==len(old)+1
for context in ('', 'Literal <bos> and <|turn> markers.'):
    _,bank,contract=c.prepare_contract(tokenizer,root,context,['Fact.'],stock_render=render)
    tasks=[{'role':'user','content':'Question?'},{'role':'assistant','content':'Prior answer.'},{'role':'user','content':'Follow-up?'}]
    _,incoming=render([{'role':'system','content':context}]+tasks,True)
    _,full=render([{'role':'system','content':context+'\n\nAuthoritative memory:\nFact.'}]+tasks,True)
    suffix=c.remaining_input(renderer.process_for_engine({'prompt_token_ids':incoming},4501.25),contract)['prompt_token_ids']
    assert bank+suffix==full
assert not torch.cuda.is_initialized()
print(json.dumps({'status':'passed','vllm':'0.30.0','scope':'actual installed vLLM synchronous text renderer; no engine/model inference','cuda_initialized':False,'raw_string_tokens':len(old),'stock_request_tokens':len(stock),'cases':rows},indent=2))
