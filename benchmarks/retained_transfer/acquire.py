"""Training-only acquisition driver. Does not read evaluator exports.

Outputs are proposal evidence, not canonical-store admission receipts. Store
admission must be performed separately through Aimee before receiver scoring.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
from pathlib import Path
import urllib.request

SYSTEM = ('Infer and apply translation rules using the supplied fixed lexicon. '
          'For proposals return only a reusable rule, without examples. '
          'For validation return the requested JSON array of translations.')


def checked_record(raw, examples, allow_training_examples=False):
    if not isinstance(raw,str) or not raw.strip() or len(raw)>2000:
        raise ValueError('missing or oversized written rule')
    if not allow_training_examples and any(x['input'] in raw or x['output'] in raw or x['id'] in raw for x in examples):
        raise ValueError('record repeats experience instead of a rule')
    return raw


def validation_outputs(raw):
    # Strip only a complete transport fence from the validation response.
    # Rule records themselves are never parsed, stripped or rewritten.
    text=raw.strip()
    match=re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```',text,re.S)
    if match:text=match.group(1)
    outputs=json.loads(text)
    if not isinstance(outputs,list) or len(outputs)!=8 or not all(isinstance(x,str) for x in outputs):
        raise ValueError('validation schema')
    return outputs


def revision_feedback(raw, outputs, examples, error):
    """Deployment-visible training evidence only; never evaluator references."""
    failures=[{'example_id':example['id'], 'expected':example['output'], 'observed':observed}
              for example,observed in zip(examples,outputs or [])
              if observed.strip()!=example['output']]
    return {'previous_rule': raw[:512] if raw else raw,
            'previous_rule_excerpted': bool(raw and len(raw)>512),
            'validation_error': error, 'failure_count':len(failures),
            'training_failures': failures[:2]}



def append(stream,value):
    stream.write(json.dumps(value,sort_keys=True)+'\n');stream.flush();os.fsync(stream.fileno())


def main():
    p=argparse.ArgumentParser();p.add_argument('--training',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--url',required=True)
    p.add_argument('--model',required=True);p.add_argument('--session',required=True)
    p.add_argument('--expected-training-sha256',required=True)
    p.add_argument('--max-attempts',type=int,default=3)
    p.add_argument('--record-policy',choices=('rule-only','experience-derived'),default='rule-only',help='New protocol arm: experience-derived records may retain worked training examples')
    p.add_argument('--refine',action='store_true',help='New protocol: expose previous rule and training failures to retries')
    args=p.parse_args()
    assert 1 <= args.max_attempts <= 10
    blob=args.training.read_bytes();assert hashlib.sha256(blob).hexdigest()==args.expected_training_sha256
    families=[json.loads(x) for x in blob.splitlines()]
    assert len(families)==60
    assert all(set(f)=={'family_id','language','construction','lexicon','source_pattern','examples','record_schema'} for f in families)
    args.out.mkdir(parents=True,exist_ok=False)
    requests=(args.out/'requests.jsonl').open('x')
    def call(payload,tag):
        body={'model':args.model,'messages':[{'role':'system','content':SYSTEM if args.record_policy=='rule-only' else SYSTEM.replace('For proposals return only a reusable rule, without examples.', 'For proposals return a reusable rule, optionally with one or two worked training examples.')},
            {'role':'user','content':json.dumps(payload,sort_keys=True)}],
            'temperature':0,'seed':20261011,'max_tokens':512,
            'chat_template_kwargs':{'enable_thinking':False}}
        append(requests,{'tag':tag,'body':body,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
        headers={'Content-Type':'application/json'}
        token=os.environ.get('RETAINED_STUDY_API_KEY')
        if token:headers['Authorization']='Bearer '+token
        request=urllib.request.Request(args.url.rstrip('/')+'/v1/chat/completions',data=json.dumps(body).encode(),headers=headers)
        with urllib.request.urlopen(request,timeout=600) as response:value=json.load(response)
        append(requests,{'tag':tag,'response':value})
        return value['choices'][0]['message']['content']
    with (args.out/'acquisition_log.jsonl').open('x') as log, (args.out/'proposed_records.jsonl').open('x') as records:
        for family in families:
            feedback=None; revision=None
            for attempt in range(1,args.max_attempts+1):
                raw=None;validation=None;outputs=None;score=0;error=None
                try:
                    proposal={'operation':'propose','family':family,'prior_match_count':feedback,
                        'instruction':'Write one reusable translation rule, using the supplied placeholder notation where helpful. Derive order and particles from examples. Return the rule only, not the examples.'}
                    if args.refine:
                        proposal['revision_feedback']=revision
                        proposal['instruction']='Return a reusable output template using {noun}, {verb}, {adjective} and literal particles/affixes. State any conditions separately. Use training failures to correct your previous rule; no worked examples.'
                    if args.record_policy=='experience-derived':
                        proposal['instruction']+=' You may retain one or two worked training examples alongside the reusable rule; no executable code.'
                    raw=call(proposal,[family['family_id'],attempt,'proposal'])
                    checked_record(raw,family['examples'],allow_training_examples=args.record_policy=='experience-derived')
                    validation=call({'operation':'validate','lexicon':family['lexicon'],
                        'source_pattern':family['source_pattern'],'record_text':raw,
                        'inputs':[{'id':x['id'],'input':x['input'],'slots':x['slots']} for x in family['examples']],
                        'instruction':'Apply this proposed rule. Return a JSON array of exactly eight translated output strings, in input order.'},[family['family_id'],attempt,'validation'])
                    outputs=validation_outputs(validation)
                    score=sum(a.strip()==b['output'] for a,b in zip(outputs,family['examples']))
                except (ValueError,KeyError,IndexError,OSError) as exc:error=repr(exc)
                admitted=error is None and score>=7
                row={'family_id':family['family_id'],'language':family['language'],'source_session':args.session,
                     'attempt':attempt,'rule_text':raw,'validation_raw':validation,'training_matches':score,
                     'admitted_candidate':admitted,'error':error,'record_policy':args.record_policy}
                append(log,row)
                if admitted:
                    append(records,{'family_id':family['family_id'],'language':family['language'],
                        'content':raw,'source_session':args.session,'validation':{'matches':score,'total':8,'threshold':7},
                        'version':1,'record_policy':args.record_policy,'content_sha256':hashlib.sha256(raw.encode()).hexdigest(),
                        'canonical_admission':'pending-authorized-store-receipt'})
                    break
                feedback=score
                revision=revision_feedback(raw,outputs,family['examples'],error)
    requests.close()
    (args.out/'completion.json').write_text(json.dumps({'training_sha256':args.expected_training_sha256,
        'driver_pid':os.getpid(),'source_session':args.session,'driver_complete':True,
        'canonical_admission_complete':False,'learner_process_termination':'Must be attested by controller'},indent=2)+'\n')

if __name__=='__main__':main()
