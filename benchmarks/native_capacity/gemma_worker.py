"""Working-set experiment; frozen copy of native_vs_text worker at 1ec32e6.
Selected authorized records are unioned without ranking, truncation or rewriting.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import copy
from coverage import validate_records, validate_encoding
from contextlib import nullcontext

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'integrations/qwen_aimee'))
import torch
import accelerate.hooks
from accelerate.utils.operations import send_to_device as original_send

def host_staged_send(value, device, non_blocking=False, skip_keys=None):
    # The dual-7900-XTX runtime already stages inter-device transfers via RAM.
    if isinstance(value, torch.Tensor):
        target=torch.device('cuda',device) if isinstance(device,int) else torch.device(device)
        if value.device.type=='cuda' and target.type=='cuda' and value.device!=target:
            return value.cpu().to(target,non_blocking=False)
        return original_send(value,device,non_blocking=non_blocking,skip_keys=skip_keys)
    if isinstance(value,(tuple,list)):
        return type(value)(host_staged_send(v,device,non_blocking,skip_keys) for v in value)
    if isinstance(value,dict):
        return type(value)({k:v if skip_keys and k in skip_keys else host_staged_send(v,device,non_blocking,skip_keys) for k,v in value.items()})
    return value
accelerate.hooks.send_to_device=host_staged_send
from transformers import AutoTokenizer, Gemma4UnifiedForConditionalGeneration
from local_image import AimeeImageClient
from qwen_adapter import QwenAimeeAdapter, _ReadBankCache

class PublishedClient(AimeeImageClient):
    def __init__(self,reader,image):
        self.process=subprocess.Popen([str(reader),'serve-published','--root',str(image)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)
        self.timeout=30
        self.view=None
        self.authorization_id=None
    def search(self,query,limit):
        result=self.recall(query,limit,'test')
        if result['outcome']!='hit':raise RuntimeError('published fact not selected')
        return result['response']

p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--image',required=True);a=p.parse_args()
torch.set_num_threads(8)
tokenizer=AutoTokenizer.from_pretrained(a.model,local_files_only=True)
model=Gemma4UnifiedForConditionalGeneration.from_pretrained(a.model,local_files_only=True,dtype=torch.bfloat16,device_map='balanced',max_memory={0:'20GiB',1:'20GiB','cpu':'40GiB'},attn_implementation='eager').eval()
model.requires_grad_(False)
versions={name:p._version for name,p in model.named_parameters()}
client=PublishedClient(REPO/'.local/bin/aimee-memory-image',a.image)
device=model.get_input_embeddings().weight.device
adapter=QwenAimeeAdapter(model,tokenizer,client,input_device=device,host_memory=True, encoding_cache_bytes=0, max_memory_tokens=8192)
# Observe actual encoder calls and the banks handed to attention, independently
# of the selected-record response. Instrumentation does not change model output.
encoder_inputs = []
attention_bank_reads = {}
def observe_encoder(module, args, kwargs):
    if adapter.encoding:
        actual = kwargs.get('input_ids', args[0] if args else None)
        assert actual is not None and actual.shape[0] == 1
        encoder_inputs.append(actual[0].detach().cpu().tolist())
encoder_hook = model.register_forward_pre_hook(observe_encoder, with_kwargs=True)
original_bank_update = _ReadBankCache.update
def audited_bank_update(cache, key, value, layer_idx, *args, **kwargs):
    bank = adapter.active['banks'][layer_idx]
    assert cache.key is bank[0] and cache.value is bank[1], 'attention received a different bank'
    result = original_bank_update(cache, key, value, layer_idx, *args, **kwargs)
    native_length = cache.key.shape[-2]
    assert native_length == cache.value.shape[-2] and native_length > 0
    assert result[0].shape[-2] == result[1].shape[-2] > native_length
    item = attention_bank_reads.setdefault(str(layer_idx), {'calls':0,'native_positions':native_length})
    assert item['native_positions'] == native_length
    item['calls'] += 1
    return result
_ReadBankCache.update = audited_bank_update
from profiling import TokenClock, synchronize
print(json.dumps({'ready':True,'model':'google/gemma-4-12B-it','torch_version':torch.__version__,'gpu_names':[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],'device_map':model.hf_device_map,'trainable_parameters':sum(p.numel() for p in model.parameters() if p.requires_grad)}),flush=True)

class SelectedClient:
    def __init__(self, reply, view, query):
        self.reply, self.view, self.query = reply, view, query
        self.authorization_id = client.authorization_id
    def begin_request(self): return self.view
    def search(self, query, limit):
        assert query == self.query
        assert limit >= len(self.reply['facts']), 'configured recall limit below working set'
        return copy.deepcopy(self.reply)

native_preparation_times = []
original_recall = adapter.recall
def timed_recall(*args, **kwargs):
    synchronize(); start = time.perf_counter()
    try: return original_recall(*args, **kwargs)
    finally:
        synchronize(); native_preparation_times.append(time.perf_counter()-start)
adapter.recall = timed_recall
prefix_key = None
prefix_cache = None
prefix_length = 0
for line in sys.stdin:
    command = json.loads(line)
    query, mode = command['query'], command['mode']
    row = {'case': command['case'], 'mode': mode}
    native_preparation_times.clear()
    encoder_inputs.clear()
    attention_bank_reads.clear()
    try:
        synchronize()
        for gpu in range(torch.cuda.device_count()): torch.cuda.reset_peak_memory_stats(gpu)
        started = time.perf_counter()
        view = client.begin_request()
        selection_queries = command.get('selection_queries', [query])
        replies = [client.search(q, 4) for q in selection_queries]
        facts_by_id = {}
        for selected in replies:
            assert selected['facts'] and not selected.get('windows')
            for fact in selected['facts']:
                assert fact['id'] not in facts_by_id, 'duplicate record in working set'
                facts_by_id[fact['id']] = fact
        reply = copy.deepcopy(replies[0])
        reply['facts'] = list(facts_by_id.values())
        row['selection_queries'] = selection_queries
        row['selected_record_count'] = len(reply['facts'])
        selection_done = time.perf_counter()
        facts = reply['facts']
        expected_ids = validate_records(facts, command['expected_refs'])
        adapter.memory_limit = len(facts)
        assert facts and not reply.get('windows')
        content = 'Authoritative memory:\n' + '\n'.join(f['content'] for f in facts)
        framed = tokenizer.apply_chat_template([{'role':'system','content':content}], tokenize=False, add_generation_prompt=False, enable_thinking=False)
        expected_memory_tokens = tokenizer.encode(framed, add_special_tokens=False)
        row['expected_native_tokens'] = len(expected_memory_tokens)
        row['selected_facts'] = facts
        row['selection_seconds'] = selection_done-started
        row['record_sha256'] = hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()
        row['source_view'] = view
        messages = [{'role':'user', 'content':query}]
        if mode.startswith('text'):
            messages.insert(0, {'role':'system', 'content':content})
        def tokenize(msgs):
            return tokenizer.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True,
                enable_thinking=False, return_tensors='pt', return_dict=True)['input_ids'].to(device)
        ids = tokenize(messages)
        plain_ids = tokenize([{'role':'user','content':query}])
        prompt = ids[0].cpu().tolist()
        row.update(prompt_token_ids=prompt, question_token_ids=plain_ids[0].cpu().tolist(),
            prompt_tokens=len(prompt), added_prompt_tokens=len(prompt)-plain_ids.shape[1],
            selected_content_bytes=len(content.encode()), prefix_cache_hit=False)
        adapter.client = SelectedClient(reply, view, query)
        state = None
        extra = {}
        prefix_prepare = 0.0
        if mode == 'text_prefix':
            # Cache only the token prefix shared with a DIFFERENT question.
            other = tokenize([{'role':'system','content':content},
                              {'role':'user','content':'Independent prefix boundary sentinel.'}])[0].cpu().tolist()
            common = 0
            for a_id,b_id in zip(prompt, other):
                if a_id != b_id: break
                common += 1
            common = min(common, len(prompt)-1)
            key = tuple(prompt[:common])
            assert common > 0
            if key != prefix_key:
                prefix_cache = None
                synchronize(); begin = time.perf_counter()
                with torch.inference_mode():
                    prepared = model(input_ids=ids[:,:common],attention_mask=torch.ones_like(ids[:,:common]),use_cache=True)
                prefix_cache = prepared.past_key_values
                del prepared
                synchronize(); prefix_prepare=time.perf_counter()-begin
                prefix_key, prefix_length = key, common
            else: row['prefix_cache_hit'] = True
            extra['past_key_values'] = copy.deepcopy(prefix_cache)
            row['cached_prefix_tokens'] = prefix_length
        row['prefix_preparation_seconds'] = prefix_prepare
        synchronize(); inference_start = time.perf_counter()
        clock = TokenClock()
        context = adapter.request(query,recall_mode='prefill',reuse_encoding=command.get('reuse_encoding',False)) if mode=='native' else nullcontext()
        with torch.inference_mode(), context as state:
            output = model.generate(input_ids=ids,attention_mask=torch.ones_like(ids),max_new_tokens=32,
                do_sample=False,return_dict_in_generate=True,use_cache=True,streamer=clock,**extra)
            if state is not None:
                validate_encoding(state, expected_ids, expected_memory_tokens)
                assert encoder_inputs == [expected_memory_tokens], 'actual encoder call omitted or changed record content'
                assert set(attention_bank_reads) == {str(i) for i in state['banks']}, 'installed native bank not consumed by attention'
                row['actual_encoder_token_ids'] = encoder_inputs[0]
                row['attention_bank_reads'] = copy.deepcopy(attention_bank_reads)
                row['encoded_record_count'] = len(expected_ids)
                row['native_bank_shapes'] = {str(i): [list(k.shape),list(v.shape)] for i,(k,v) in state['banks'].items()}
                assert state['banks'], 'no native banks installed'
                assert max(k.shape[-2] for k,v in state['banks'].values()) == len(expected_memory_tokens), 'no native bank retains the complete sequence'
                row['native_state_bytes']=sum(t.numel()*t.element_size() for bank in state['banks'].values() for t in bank)
        synchronize(); done = time.perf_counter()
        generated = output.sequences[0,len(prompt):].cpu().tolist()
        row.update(answer=tokenizer.decode(generated,skip_special_tokens=True).strip(),
            generated_ids=generated,completion_tokens=len(generated),
            model_request_seconds=done-inference_start,request_seconds=done-started,
            ttft_seconds=(clock.times[0]-started if clock.times else None),
            model_ttft_seconds=(clock.times[0]-inference_start if clock.times else None),
            peak_allocated_bytes=[torch.cuda.max_memory_allocated(i) for i in range(torch.cuda.device_count())],
            peak_reserved_bytes=[torch.cuda.max_memory_reserved(i) for i in range(torch.cuda.device_count())],
            main_cache_length=output.past_key_values.get_seq_length())
        if state is not None:
            row['memory']=state
            row['native_preparation_seconds']=sum(native_preparation_times)
            assert state['native_reads']>0
            assert state['aimee_response']['facts']==facts
            assert row['added_prompt_tokens']==0
        row['parameter_versions_unchanged']=all(p._version==versions[n] for n,p in model.named_parameters())
        assert row['parameter_versions_unchanged']
        if mode not in ('native','none','text','text_prefix'): raise ValueError('unknown condition')
        del output, extra
    except Exception as exc:
        import traceback
        traceback.print_exc(file=sys.stderr)
        row['error']=type(exc).__name__+': '+str(exc)
    print(json.dumps(row),flush=True)
encoder_hook.remove();adapter.close();client.close()
