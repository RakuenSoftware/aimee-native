"""Dispatch certified GPU binaries. Contains no kernel source or encoder."""
import json
from pathlib import Path
from types import SimpleNamespace
from triton.compiler.compiler import CompiledKernel

def identity(args):
    return json.dumps([list(args[9:]),[str(t.dtype) for t in args[:9]]],separators=(',',':'))

class BinaryAttention:
    def __init__(self, root):
        root=Path(root);self.kernels={}
        manifest=json.loads((root/'manifest.json').read_text())
        for item in manifest['kernels']:
            src=SimpleNamespace(signature={tuple(k):v for k,v in item['signature']},constants={tuple(k):v for k,v in item['constants']})
            group={n:str(root/n) for n in item['files']}
            constants,dtypes=json.loads(item['identity'])
            self.kernels[(tuple(constants),tuple(dtypes))]=CompiledKernel(src,group,item['hash'])
    def __getitem__(self, grid):
        def launch(*args,**kwargs):
            kernel=self.kernels.get((args[9:],tuple(str(t.dtype) for t in args[:9])))
            if kernel is None:raise RuntimeError('native kernel profile is not certified in this binary package')
            kernel[grid](*args)
            return kernel
        return launch
