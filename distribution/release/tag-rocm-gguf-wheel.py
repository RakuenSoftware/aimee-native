#!/usr/bin/env python3
"""Identify the existing ROCm build for pip; change metadata only, never upstream code."""
import argparse,base64,csv,hashlib,io,json,re,zipfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
assert hashlib.sha256(a.source.read_bytes()).hexdigest()=='32313e2dec05f88ff868d22c655a52127b5afe6ecba480fa2f5050b3eda771c4','unexpected build'
with zipfile.ZipFile(a.source) as z: files={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
old=next(n.rsplit('/',1)[0] for n in files if n.endswith('.dist-info/METADATA'));new='vllm_gguf_plugin-0.0.5+rocm723.dist-info'
original={n:hashlib.sha256(d).hexdigest() for n,d in files.items() if not n.startswith(old+'/')}
files={(new+n[len(old):] if n.startswith(old+'/') else n):d for n,d in files.items()}
files[new+'/METADATA']=re.sub(rb'(?m)^Version: [^\r\n]+',b'Version: 0.0.5+rocm723',files[new+'/METADATA'])
record=new+'/RECORD';files.pop(record,None);buf=io.StringIO();writer=csv.writer(buf,lineterminator='\n')
for n,d in sorted(files.items()):writer.writerow([n,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(d).digest()).decode().rstrip('='),len(d)])
writer.writerow([record,'','']);files[record]=buf.getvalue().encode()
a.output.mkdir(exist_ok=True,parents=True);out=a.output/'vllm_gguf_plugin-0.0.5+rocm723-cp310-abi3-linux_x86_64.whl'
with out.open('xb') as f,zipfile.ZipFile(f,'w',zipfile.ZIP_DEFLATED) as z:
 for n,d in sorted(files.items()):z.writestr(n,d)
with zipfile.ZipFile(out) as z:assert all(hashlib.sha256(z.read(n)).hexdigest()==d for n,d in original.items())
report={'status':'passed','scope':__doc__,'original_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),'file':out.name,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'bytes':out.stat().st_size,'unchanged_code_assets':len(original)}
(a.output/'retag.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
