"""Freeze synthetic workflow training and unseen task inputs before inference."""
import hashlib,json,random,sys
from pathlib import Path
root=Path(sys.argv[1]);root.mkdir();root.chmod(0o755)
image=Path(sys.argv[2]);(root/'image').symlink_to(image.resolve(),target_is_directory=True)
rng=random.Random(2026092202);workflows=[];training=[];heldout=[]
parameters=rng.sample([(a,b) for a in range(2,10) for b in range(1,20)],24)
for i,(a,b) in enumerate(parameters):
 name=f'Cedar{i:03d}';key=f'procedure for workflow {name}'
 examples=[dict(input=x,output=a*x+b) for x in [1,4,9]]
 query=f'Learn the integer transformation used by private workflow {name} from executor feedback. '+ '; '.join(f'input {e["input"]} produced required output {e["output"]}' for e in examples)+'. Infer one reusable arithmetic rule for new inputs. Return only one sentence under 100 characters specifying the multiplication and addition; do not list examples.'
 training.append(dict(id=f'learn-{name}',domain='affine-procedure',source='training',query=query,expected=f'Multiply by {a} then add {b}',scorer='text',workflow=name,key=key,examples=examples))
 inputs=rng.sample(list(range(20,120)),20)
 workflows.append(dict(name=name,key=key,multiplier=a,offset=b,training_inputs=[1,4,9],heldout_inputs=inputs))
 for x in inputs:heldout.append(dict(id=f'task-{name}-{x}',domain='affine-procedure',source='learned-task',workflow=name,key=key,input=x,query=f'Execute my private workflow {name} on input {x}. Return only the integer result. If the procedure is unknown, return unknown.',expected=str(a*x+b),scorer='integer'))
rng.shuffle(heldout)
for name,obj in [('cases.json',training),('heldout.json',heldout),('workflows.json',workflows)]:
 with (root/name).open('x') as f:json.dump(obj,f,indent=2)
with (root/'plan.json').open('x') as f:json.dump(dict(seed=2026092202,workflows=24,training_requests_per_model=24,heldout_inputs_per_workflow=20,heldout_cases_per_model=480,evaluation_requests_per_model=960,models=['Gemma 4','Qwen 3.8'],conditions=['disabled','native-model-learned-procedure'],training='three executor-labeled examples; model induces rule; no gold rule substituted',heldout_sha256=hashlib.sha256((root/'heldout.json').read_bytes()).hexdigest(),interpretation='Supervised procedural induction and persistent native transfer; not autonomous discovery of tasks, optimizer updates, or repeated-answer recall.'),f,indent=2)
