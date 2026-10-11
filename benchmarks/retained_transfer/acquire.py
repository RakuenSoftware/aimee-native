"""Training-only acquisition driver. Does not read evaluator exports.

Outputs are proposal evidence, not canonical-store admission receipts. Store
admission must be performed separately through Aimee before receiver scoring.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import string
import urllib.request

SYSTEM = ('Infer the translation rule from the supplied examples. Lexicon entries '
          'are fixed. Do not invent examples or claim test results. Follow the '
          'requested JSON output schema exactly; no markdown or explanation.')


def rule(raw):
    value=json.loads(raw)
    if not isinstance(value,dict) or set(value)!={'output_template'}:raise ValueError('record schema')
    text=value['output_template']
    if not isinstance(text,str) or len(text)>2000:raise ValueError('template length/type')
    fields=[]
    for _,name,format_spec,conversion in string.Formatter().parse(text):
        if name is not None:
            if format_spec or conversion:raise ValueError('unsafe formatting')
            fields.append(name)
    if sorted(fields)!=['adjective','noun','verb']:raise ValueError('placeholders')
    return value


def append(stream,value):
    stream.write(json.dumps(value,sort_keys=True)+'\n');stream.flush();os.fsync(stream.fileno())


def main():
    p=argparse.ArgumentParser();p.add_argument('--training',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--url',required=True)
    p.add_argument('--model',required=True);p.add_argument('--session',required=True)
    p.add_argument('--expected-training-sha256',required=True)
    args=p.parse_args()
    blob=args.training.read_bytes();assert hashlib.sha256(blob).hexdigest()==args.expected_training_sha256
    families=[json.loads(x) for x in blob.splitlines()]
    assert len(families)==60
    assert all(set(f)=={'family_id','language','construction','lexicon','source_pattern','examples','record_schema'} for f in families)
    args.out.mkdir(parents=True,exist_ok=False)
    requests=(args.out/'requests.jsonl').open('x')
    def call(payload,tag):
        body={'model':args.model,'messages':[{'role':'system','content':SYSTEM},
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
            feedback=None
            for attempt in range(1,4):
                raw=None;validation=None;score=0;error=None
                try:
                    raw=call({'operation':'propose','family':family,'prior_match_count':feedback,
                        'instruction':'Return only a JSON object matching record_schema. Placeholders use target-language words; derive word order and literals from examples.'},[family['family_id'],attempt,'proposal'])
                    rule(raw)
                    validation=call({'operation':'validate','lexicon':family['lexicon'],
                        'source_pattern':family['source_pattern'],'record_text':raw,
                        'inputs':[{'id':x['id'],'input':x['input'],'slots':x['slots']} for x in family['examples']],
                        'instruction':'Apply this proposed rule. Return a JSON array of exactly eight translated output strings, in input order.'},[family['family_id'],attempt,'validation'])
                    outputs=json.loads(validation)
                    if not isinstance(outputs,list) or len(outputs)!=8 or not all(isinstance(x,str) for x in outputs):raise ValueError('validation schema')
                    score=sum(a.strip()==b['output'] for a,b in zip(outputs,family['examples']))
                except (ValueError,KeyError,IndexError,OSError) as exc:error=repr(exc)
                admitted=error is None and score>=7
                row={'family_id':family['family_id'],'language':family['language'],'source_session':args.session,
                     'attempt':attempt,'rule_text':raw,'validation_raw':validation,'training_matches':score,
                     'admitted_candidate':admitted,'error':error}
                append(log,row)
                if admitted:
                    append(records,{'family_id':family['family_id'],'language':family['language'],
                        'content':raw,'source_session':args.session,'validation':{'matches':score,'total':8,'threshold':7},
                        'version':1,'content_sha256':hashlib.sha256(raw.encode()).hexdigest(),
                        'canonical_admission':'pending-authorized-store-receipt'})
                    break
                feedback=score
    requests.close()
    (args.out/'completion.json').write_text(json.dumps({'training_sha256':args.expected_training_sha256,
        'driver_pid':os.getpid(),'source_session':args.session,'driver_complete':True,
        'canonical_admission_complete':False,'learner_process_termination':'Must be attested by controller'},indent=2)+'\n')

if __name__=='__main__':main()
