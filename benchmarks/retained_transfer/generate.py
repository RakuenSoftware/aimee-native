"""Deterministic controlled language fragments; no model imports or inference.

Learner export contains examples, lexicon and schema only. References remain in
an evaluator-only export. A record is a model-written output template; the
receiver, not this program, applies it at inference time.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random

SEED = 'retained-transfer-20261011-v1'
NOUNS = 'cat dog bird rabbit fox goat horse tiger lion bear wolf duck frog mouse cow pig deer sheep fish turtle'.split()
VERBS = 'jump walk run swim sing dance sleep eat drink read write laugh smile wait look listen climb stand sit play'.split()
ADJECTIVES = 'red blue green white black yellow small big tall short fast slow young old bright dark calm loud soft warm'.split()
CONSTRUCTIONS = [
 ('plural', 'The {adjective} {noun}s {verb}.'),
 ('possession', 'The {adjective} {noun} owns something and can {verb}.'),
 ('past', 'Yesterday the {adjective} {noun} did {verb}.'),
 ('future', 'Tomorrow the {adjective} {noun} will {verb}.'),
 ('progressive', 'The {adjective} {noun} is now doing the action {verb}.'),
 ('negation', 'The {adjective} {noun} does not {verb}.'),
 ('question', 'Does the {adjective} {noun} {verb}?'),
 ('comparative', 'The {noun} is more {adjective} and can {verb}.'),
 ('superlative', 'The {noun} is the most {adjective} and can {verb}.'),
 ('agent', 'The {adjective} {noun} is one who can {verb}.'),
 ('manner', 'The {noun} does {verb} in a {adjective} manner.'),
 ('conditional', 'If the {noun} is {adjective}, it will {verb}.'),
 ('conjunction', 'The {noun} is {adjective} and can {verb}.'),
 ('imperative', 'Let the {adjective} {noun} {verb}!'),
 ('passive', 'The {adjective} {noun} receives the action {verb}.'),
 ('location', 'Here the {adjective} {noun} can {verb}.'),
 ('benefactive', 'For someone else the {adjective} {noun} will {verb}.'),
 ('habitual', 'Usually the {adjective} {noun} does {verb}.'),
 ('dual', 'Exactly two {adjective} {noun}s {verb}.'),
 ('evidential', 'Reportedly the {adjective} {noun} can {verb}.')]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def bundle(seed=SEED):
    rng = random.Random(seed)
    used = set()
    def word():
        while True:
            w = ''.join(rng.choice('ptkmnsrl')+rng.choice('aeiou') for _ in range(3))
            if w not in used:
                used.add(w); return w
    learner, evaluation, calibration = [], [], []
    for li in range(3):
        language = f'Language-{li+1}'
        lexicon = {kind: dict(zip(words, [word() for _ in words]))
                   for kind, words in [('noun', NOUNS), ('verb', VERBS), ('adjective', ADJECTIVES)]}
        for fi, (name, english) in enumerate(CONSTRUCTIONS):
            fid = f'L{li+1}-F{fi+1:02d}'
            fields = ['{noun}', '{verb}', '{adjective}']; rng.shuffle(fields)
            marker = word()
            # Four frozen, transparent hypothesis classes; position and marker
            # are not disclosed in the schema or learner export.
            mode = fi % 4
            if mode == 0:
                target = ' '.join([marker, *fields])
            elif mode == 1:
                target = ' '.join([*fields, marker])
            elif mode == 2:
                fields[0] = marker+'-'+fields[0]; target = ' '.join(fields)
            else:
                fields[-1] += '-'+marker; target = ' '.join(fields)
            def example(indices, split, index):
                slots = {kind: words[i] for (kind, words), i in zip(
                    [('noun', NOUNS), ('verb', VERBS), ('adjective', ADJECTIVES)], indices)}
                mapped = {k: lexicon[k][v] for k, v in slots.items()}
                return {'id': f'{fid}-{split}-{index:02d}', 'input': english.format(**slots),
                        'slots': slots, 'output': target.format(**mapped)}
            train = [example(((i+fi)%8, (i*3+fi)%8, (i*5+li)%8), 'train', i) for i in range(8)]
            choices = [(a,b,c) for a in range(8,16) for b in range(8,16) for c in range(8,16)]
            heldout = [example(ix, 'heldout', i) for i,ix in enumerate(rng.sample(choices,20))]
            choices = [(a,b,c) for a in range(16,20) for b in range(16,20) for c in range(16,20)]
            cal = [example(ix, 'calibration', i) for i,ix in enumerate(rng.sample(choices,8))]
            common = {'family_id':fid, 'language':language, 'construction':name,
                      'lexicon':lexicon, 'source_pattern':english}
            learner.append(dict(common, examples=train,
                record_schema={'output_template':'A string containing {noun}, {verb}, {adjective} exactly once each, in learned order, with the learned literal particles or affixes. Placeholders mean the target-language lexicon entries. No executable code.'}))
            evaluation.append(dict(common, oracle_rule=json.dumps({'output_template':target},sort_keys=True), inputs=heldout))
            calibration.append(dict(common, inputs=cal))
    return {'learner':learner, 'evaluation':evaluation, 'calibration':calibration}


def export(root, seed=SEED):
    root.mkdir(parents=True, exist_ok=False)
    data = bundle(seed); manifest = {'seed':seed, 'family_count':60, 'training_pairs':480,
        'heldout_inputs':1200, 'calibration_inputs':480, 'files':{}}
    for role, families in data.items():
        folder=root/role; folder.mkdir()
        blob=b''.join(canonical(f)+b'\n' for f in families)
        path=folder/'families.jsonl'; path.write_bytes(blob)
        manifest['files'][str(path.relative_to(root))]=hashlib.sha256(blob).hexdigest()
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--seed',default=SEED)
    args=p.parse_args()
    print(json.dumps(export(args.root,args.seed),indent=2))
