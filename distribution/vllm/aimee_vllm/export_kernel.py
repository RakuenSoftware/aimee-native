"""Private build-only export. Never package source or intermediate GPU IR."""
import json
from pathlib import Path
from .binary_kernel import identity

def export(root,kernel,args):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    key=identity(args);path=root/'manifest.json'
    data=json.loads(path.read_text()) if path.exists() else {'kernels':[]}
    if any(item['identity']==key for item in data['kernels']):return
    files=[]
    for name,source in kernel.metadata_group.items():
        if not name.endswith(('.json','.hsaco')):continue
        destination=kernel.hash+'-'+Path(source).name
        (root/destination).write_bytes(Path(source).read_bytes());files.append(destination)
    def entries(mapping):
        return [[list(k) if isinstance(k,tuple) else [kernel.src.fn.arg_names.index(k)],v] for k,v in mapping.items()]
    data['kernels'].append({'identity':key,'signature':entries(kernel.src.signature),'constants':entries(kernel.src.constants),'hash':kernel.hash,'files':files})
    stage=path.with_suffix('.next');stage.write_text(json.dumps(data,indent=2));stage.replace(path)
