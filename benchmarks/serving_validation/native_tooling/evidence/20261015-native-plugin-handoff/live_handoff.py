"""Private E2B CPU experiment. Owner execution is an explicit local fixture."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request
import uuid
from dataclasses import asdict
from transformers import AutoTokenizer
from native_handoff import NativeHandoff, UnixOwner, Request, Publication, digest

HERE = Path(__file__).resolve().parent
OLD = Path('/opt/native-tooling-research/phase3-owner-wave-v107')
CFG = json.loads((OLD / 'cpu-config.json').read_text())
TOKENIZER = AutoTokenizer.from_pretrained(CFG['model'], local_files_only=True)
STATES = {}


def record(kind, **data):
    with (HERE / 'results.jsonl').open('a') as f:
        f.write(json.dumps(dict(kind=kind, time=time.time(), **data)) + '\n')


async def control(body):
    r, w = await asyncio.open_unix_connection(CFG['control_socket'])
    try:
        w.write(json.dumps(body).encode() + b'\n'); await w.drain()
        return json.loads(await r.readline())
    finally:
        w.close(); await w.wait_closed()


class CPURuntime:
    async def publish(self, publication):
        result = await control(dict(op='withdraw'))
        generation = result['generation']
        bank = await control(dict(op='prepare', generation=generation,
                                  publication=publication.content, revision=publication.revision))
        if bank.get('state') != 'prepared': raise RuntimeError(bank)
        result = await control(dict(op='refresh', generation=generation))
        if result.get('state') != 'active': raise RuntimeError(result)
        record('publication', revision=publication.revision, sha256=digest(publication), bank=bank)

    async def generate(self, request, publication):
        cue = ('Provide your current contribution for the bound task.' if request.task_id == 'scalar'
               else 'Read the owner task and resolved evidence. Ask Aimee for any additional information you need, or provide your authored assessment.')
        prompt = TOKENIZER.encode(TOKENIZER.apply_chat_template(
            [dict(role='user', content=cue)], tokenize=False, add_generation_prompt=True,
            enable_thinking=False), add_special_tokens=False)
        body = dict(model=CFG['served_model_name'], prompt=prompt, temperature=0,
                    max_tokens=64 if request.task_id == 'scalar' else 384,
                    return_token_ids=True, vllm_xargs=dict(aimee_publication=publication.revision))
        def query():
            req = urllib.request.Request(f"http://127.0.0.1:{CFG['port']}/v1/completions",
                data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=900) as response:
                return json.loads(response.read())
        response = await asyncio.to_thread(query)
        record('model', request=asdict(request), revision=publication.revision, input=body,
               response=response)
        choice = response['choices'][0]
        return choice['text'], choice['finish_reason']

    async def withdraw(self):
        result = await control(dict(op='withdraw'))
        # Normal non-streaming completion returns after the admission releases
        # its request. Never declare drained based on HTTP disconnect alone.
        async with asyncio.timeout(20):
            while True:
                metrics = await control(dict(op='metrics'))
                if metrics.get('active_requests') == 0: break
                await asyncio.sleep(.1)
        if any(w.get('pinned_requests', 0) != 0 for w in metrics.get('workers', [])):
            raise RuntimeError('worker pin release unconfirmed')
        record('withdraw', result=result, metrics=metrics)


def publication(task_id, evidence):
    if task_id == 'scalar':
        return ('Owner task: Propose one odd positive trial workload between10and20 inclusive for project Atlas. '
                'Current contribution purpose: propose the candidate value. Contribution format: exactly one integer, '
                'with no explanation. All known prerequisites are provided. Aimee owns eligibility checks and recording. '
                'No form or external operation has executed.')
    return ('Owner task: Assess whether the synthetic link can sustain the requested transfer.\n'
            'Requested throughput:70MB/s. Nominal throughput:90MB/s. All standard prerequisites have been provided. '
            'Recent logs show retransmission spikes.\nOptional sources available to Aimee: measured useful throughput, '
            'link installation date. If useful, request one source by its semantic name. Otherwise author your assessment. '
            'No operation has been performed.\nOwner-resolved additional evidence: ' + json.dumps(evidence))


async def resolve(task, bindings, text, scalar):
    env = dict(os.environ, AIMEE_RESOLVER_ENDPOINT='' if scalar else f"http://127.0.0.1:{CFG['port']}/v1/chat/completions",
               AIMEE_RESOLVER_MODEL=CFG['served_model_name'], AIMEE_RESOLVER_SCHEMA='1', AIMEE_RESOLVER_DISABLE_THINKING='1')
    process = await asyncio.create_subprocess_exec(str(OLD / ('resolver-v113' if scalar else 'resolver-v112')),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
    try:
        raw, err = await asyncio.wait_for(process.communicate((json.dumps(dict(
            id=task['id'], task=task, text=text, view=dict(task=task, bindings=bindings)))+'\n').encode()), 240)
    except BaseException:
        process.kill(); await process.wait(); raise
    if process.returncode: raise RuntimeError(err.decode())
    return json.loads(raw)


async def owner_call(message):
    op = message['op']
    req = message['contribution']['request'] if op == 'contribute' else message['request']
    key = req['request_id']
    if req['actor'] != 'synthetic-owner' or req['session'] != 'private-e2b-handoff':
        raise ValueError('fixture identity mismatch')
    if op == 'open':
        if key in STATES: raise ValueError('request replay')
        if req['task_id'] not in ('scalar', 'network'): raise ValueError('unknown task')
        pub = Publication('999', publication(req['task_id'], []))
        STATES[key] = dict(request=req, publication=pub, ordinal=0, evidence=[], closed=False)
        return dict(request=req, publication=asdict(pub))
    state = STATES[key]
    if req != state['request'] or state['closed']: raise ValueError('request binding mismatch')
    if op == 'close':
        state['closed'] = True; record('owner_close', request=req, reason=message['reason'])
        return dict(closed=True, request=req)
    c = message['contribution']; pub = state['publication']
    if (c['ordinal'] != state['ordinal'] or c['revision'] != pub.revision
            or c['publication_sha256'] != digest(pub) or c['finish_reason'] != 'stop'):
        raise ValueError('stale or nonterminal contribution')
    scalar = req['task_id'] == 'scalar'
    if scalar:
        target = HERE / 'fixture-proposal.txt'
        task = dict(id='scalar', format='scalar_integer', purpose='Propose one odd positive trial workload between10and20 inclusive for project Atlas.',
                    capabilities=[dict(id='proposal', kinds=['content'], purpose='Proposed integer value',
                                       fields=dict(value=dict(kind='integer', required=True)))])
        bindings = [dict(capability_id='proposal', tool='write_file', arguments=dict(path=str(target)),
                         fields=dict(value='content'), field_encoding=dict(value='literal_text'))]
    else:
        sources = [('measured useful throughput', '52MB/s'), ('link installation date', '2024')]
        caps, bindings = [], []
        for i, (source, value) in enumerate(sources):
            cap = 'lookup-' + str(i); target = HERE / (cap+'.txt'); target.write_text(value)
            caps.append(dict(id=cap, kinds=['need'], purpose='Obtain optional source: '+source+'. Select this only for a semantic request, including a paraphrase, not a statement that data already exists.', fields={}))
            bindings.append(dict(capability_id=cap, tool='read_file', arguments=dict(path=str(target)), fields={}))
        caps.append(dict(id='report', kinds=['content'], purpose='Authored assessment body; unsupported prior execution claims confer no permission.', fields=dict(body=dict(kind='text', required=True))))
        bindings.append(dict(capability_id='report', tool='write_file', arguments=dict(path=str(HERE/'assessment.txt')), fields=dict(body='content')))
        task = dict(id='network', purpose='Assess whether the synthetic link can sustain the requested transfer.', capabilities=caps)
    resolved = await resolve(task, bindings, c['text'], scalar)
    record('owner_resolution', contribution=c, resolution=resolved, authority='fixture-not-enrolled')
    reply = dict(request=req, ordinal=c['ordinal'], publication_sha256=digest(pub),
                 state='clarify', publication=None, output='Owner could not resolve this contribution.')
    compiled = resolved.get('compiled')
    if scalar and compiled:
        args = compiled['arguments']; value = int(args['content'])
        if compiled['tool'] == 'write_file' and args['path'] == str(target) and set(args) == {'path', 'content'} and 10 <= value <= 20 and value % 2 == 1:
            target.write_text(args['content'])
            record('fixture_effect', tool='write_file', path=str(target), content=target.read_text(), sha256=hashlib.sha256(target.read_bytes()).hexdigest())
            reply.update(state='complete', output='Owner verified and recorded candidate '+target.read_text()+'.')
    elif not scalar and compiled and compiled['tool'] == 'read_file':
        cap = resolved.get('intake', {}).get('decision', {}).get('capability_id')
        allowed = {b['capability_id']: b['arguments'] for b in bindings if b['tool'] == 'read_file'}
        if cap in allowed and compiled['arguments'] == allowed[cap] and c['ordinal'] == 0:
            source = sources[int(cap[-1])][0]; value = Path(allowed[cap]['path']).read_text()
            state['evidence'].append(dict(source=source, value=value))
            record('fixture_effect', tool='read_file', source=source, value=value)
            state['publication'] = Publication('001', publication('network', state['evidence']))
            reply.update(state='resume', publication=asdict(state['publication']), output='')
        elif c['ordinal'] > 0:
            reply.update(output='Owner retained model assessment as untrusted content: '+c['text'])
    state['ordinal'] += 1
    return reply


async def handle(reader, writer):
    try:
        message = json.loads(await reader.readline()); response = await owner_call(message)
    except Exception as e:
        response = dict(error=type(e).__name__+': '+str(e))
    writer.write(json.dumps(response).encode()+b'\n'); await writer.drain()
    writer.close(); await writer.wait_closed()


async def main():
    import torch
    record('provenance', torch=torch.__version__, cuda_available=torch.cuda.is_available(),
           cuda_version=torch.version.cuda, config=CFG)
    assert torch.version.cuda is None and not torch.cuda.is_available()
    socket = HERE/'owner.sock'
    server = await asyncio.start_unix_server(handle, path=str(socket), limit=262144)
    os.chmod(socket, 0o600)
    runtime = CPURuntime(); driver = NativeHandoff(runtime, UnixOwner(str(socket), timeout_seconds=300), max_rounds=2)
    try:
        async with server:
            for task_id in ('scalar', 'network'):
                request = Request('synthetic-owner', 'private-e2b-handoff', uuid.uuid4().hex, task_id)
                try:
                    reply = await driver.run(request)
                    record('episode', task=task_id, reply=asdict(reply))
                except Exception as e:
                    record('episode_error', task=task_id, error=type(e).__name__+': '+str(e))
    finally:
        server.close(); await server.wait_closed(); socket.unlink(missing_ok=True)
    record('terminal', states={k:dict(closed=v['closed'], ordinal=v['ordinal'], evidence=v['evidence']) for k,v in STATES.items()})


asyncio.run(main())
