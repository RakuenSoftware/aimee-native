#!/usr/bin/env python3
"""Package upstream's existing Triton fallback without its optional GPU binary.

No source changes or monkey-patching. Preserve every other upstream asset.
"""
import argparse,base64,csv,hashlib,io,json,re,zipfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
with zipfile.ZipFile(a.source) as z:files={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
old=next(n.rsplit('/',1)[0] for n in files if n.endswith('.dist-info/METADATA'));new='vllm_gguf_plugin-0.0.5+triton.dist-info'
assert re.search(rb'(?m)^Version: 0\.0\.5(?:\+rocm723)?$',files[old+'/METADATA'])
removed=[n for n in files if n.endswith(('.so','.dll','.dylib'))]
assert removed==['vllm_gguf_plugin/_C_gguf.abi3.so'],removed
ops=files['vllm_gguf_plugin/ops.py'];assert b'except ImportError:' in ops and b'_CUDA_ENABLED = _USE_CUDA and _CUDA_AVAILABLE' in ops
original={n:hashlib.sha256(d).hexdigest() for n,d in files.items() if not n.startswith(old+'/') and n not in removed}
files={(new+n[len(old):] if n.startswith(old+'/') else n):d for n,d in files.items() if n not in removed}
files[new+'/METADATA']=re.sub(rb'(?m)^Version: [^\r\n]+',b'Version: 0.0.5+triton',files[new+'/METADATA'])
files[new+'/WHEEL']=b'Wheel-Version: 1.0\nGenerator: aimee-portable-dependency\nRoot-Is-Purelib: true\nTag: py3-none-any\n'
record=new+'/RECORD';files.pop(record,None);buf=io.StringIO();writer=csv.writer(buf,lineterminator='\n')
for n,d in sorted(files.items()):writer.writerow([n,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(d).digest()).decode().rstrip('='),len(d)])
writer.writerow([record,'','']);files[record]=buf.getvalue().encode()
a.output.mkdir(exist_ok=True,parents=True);out=a.output/'vllm_gguf_plugin-0.0.5+triton-py3-none-any.whl'
with out.open('xb') as f,zipfile.ZipFile(f,'w',zipfile.ZIP_DEFLATED) as z:
 for n,d in sorted(files.items()):z.writestr(n,d)
with zipfile.ZipFile(out) as z:assert all(hashlib.sha256(z.read(n)).hexdigest()==d for n,d in original.items())
report={'status':'passed','scope':__doc__,'original_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),'file':out.name,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'bytes':out.stat().st_size,'unchanged_code_assets':len(original),'omitted_optional_assets':removed}
(a.output/'dependency.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
