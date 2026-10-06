"""Read actual frozen launcher/runner bindings, without executing model code."""
import ast,json,hashlib
from pathlib import Path
HELPER=Path('/opt/jmlr-second-review-20261005/repair-cache/gemma-composition-candidate-r1/gpu-executor-recovery-r7')
NAS=Path('/mnt/pve/backup/aimee-experiments/root-evacuation-20261005-r1/gemma-composition-candidate-r1/gpu-validation-recovery-r7')
p=json.loads((NAS/'protocol.json').read_bytes());m=json.loads((NAS/'executor-manifest.json').read_bytes())
assert hashlib.sha256((NAS/'protocol.json').read_bytes()).hexdigest()==m['protocol_sha256']
scope={'Path':Path,'str':str}
def read_bindings(name,keys):
    tree=ast.parse((HELPER/name).read_text())
    for node in tree.body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in keys:
            scope[node.targets[0].id]=eval(compile(ast.Expression(node.value),name,'eval'),{'__builtins__':{}},scope)
    return tree
tree=read_bindings('run_integration.py',['ROOT','WORK','SHORT','NAS','EXPECTED'])
assert str(scope['WORK'])==p['execution']['task_root']
assert str(scope['NAS'])==p['execution']['artifact_root']
paths=p['execution']['runtime_paths'];assert str(scope['SHORT'])==paths['short_task_root']==m['runtime_paths']['short_task_root']
env=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='env' for t in n.targets))
for key,expected in [('TMPDIR',paths['temporary_and_zmq_base']),('VLLM_RPC_BASE_PATH',paths['temporary_and_zmq_base'])]:
    value=next(k.value for k in env.value.keywords if k.arg==key)
    assert eval(compile(ast.Expression(value),'env','eval'),{'__builtins__':{}},scope)==expected
update=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='config' and n.func.attr=='update')
control=next(k.value for k in update.keywords if k.arg=='control_socket')
assert eval(compile(ast.Expression(control),'control','eval'),{'__builtins__':{}},scope)==paths['control_socket']==m['runtime_paths']['control_socket']
read_bindings('capacity_observer.py',['BASE','OUT','UNIT','RUNNER'])
assert scope['UNIT']==p['execution']['unit']=='jmlr-gemma-prefix-integration-recovery-20261006-r7.service'
assert scope['RUNNER']==str(HELPER/'run_integration.py')
assert scope['EXPECTED']==m['protocol_sha256']
for name,h in m['executor_sha256'].items():assert hashlib.sha256((HELPER/name).read_bytes()).hexdigest()==h,name
print(json.dumps({'status':'passed','actual_runner_paths_match_protocol_manifest':True,'actual_capacity_launcher_unit_runner_match':True,'unit':scope['UNIT'],'short_task_root':str(scope['SHORT']),'no_model_execution':True},indent=2))
