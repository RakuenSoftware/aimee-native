"""Full-checkpoint private preparation smoke test; synthetic source facts only."""
import argparse
import hashlib
import json
import pathlib
import sys
import time

p=argparse.ArgumentParser()
p.add_argument('--source',required=True)
p.add_argument('--model',required=True)
p.add_argument('--output',required=True)
p.add_argument('--memory-positions', choices=['negative', 'nonnegative'])
p.add_argument('--wait-for-pid-file')
p.add_argument('--wait-for-status-file')
a=p.parse_args()
if bool(a.wait_for_pid_file) != bool(a.wait_for_status_file):
    p.error('both predecessor files are required')
if a.wait_for_pid_file:
    while True:
        pid=int(pathlib.Path(a.wait_for_pid_file).read_text())
        stat=pathlib.Path('/proc',str(pid),'stat')
        if not stat.exists() or stat.read_text().split()[2]=='Z':
            status=json.loads(pathlib.Path(a.wait_for_status_file).read_text())['status']
            if status not in ('complete','failed'):
                raise RuntimeError('predecessor exited without terminal status')
            break
        time.sleep(10)
sys.path.insert(0,a.source)
from bounded_compile import BoundedTextCompiler
import torch

output=pathlib.Path(a.output)
output.mkdir(exist_ok=False)
request={'response':{'facts':[
    {'content':'The release verification vault code is 28461.'},
    {'content':'The release verification project is Juniper.'},
    {'content':'The release verification drink is hibiscus tea.'},
]},'identity':{'records':[{'id':i,'revision':1} for i in (5,6,7)]}}
(output/'request.json').write_text(json.dumps(request,indent=2)+'\n')
compiler=BoundedTextCompiler(a.model,threads=8,memory_positions=a.memory_positions)
started=time.monotonic()
try:
    tokens,banks=compiler.encode(request)
    artifact=output/'native-state.pt'
    torch.save({'tokens':tokens,'banks':banks},artifact)
    with artifact.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    report={'status':'prepared','scope':'Synthetic three-record full-checkpoint FP32 preparation only; no serving or authorization certification',
        'selected_records':3,'tokens':len(tokens),'layers':list(banks),
        'bank_shapes':{str(i):[list(k.shape),list(v.shape)] for i,(k,v) in banks.items()},
        'metrics':compiler.last_metrics,'seconds':time.monotonic()-started,
        'artifact_bytes':artifact.stat().st_size,'artifact_sha256':digest,
        'all_parameters_released':all(p.device.type=='meta' for p in compiler.model.parameters())}
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
finally:
    compiler.close()
