#!/usr/bin/env python3
"""Add pinned GGUF dependency metadata; preserve every executable wheel member."""
import argparse,base64,csv,hashlib,io,json
from pathlib import Path
from email.parser import BytesParser
import zipfile


def finalize(wheels,dependency,output,build_tag='2',notices=None,models=('gemma4-12b','gemma4-26b','qwen3-8-27b')):
    output.mkdir(parents=True,exist_ok=False)
    dependency_bytes=dependency.read_bytes()
    with zipfile.ZipFile(dependency) as z:
        metadata=next(z.read(n) for n in z.namelist() if n.endswith('.dist-info/METADATA'))
        assert b'Version: 0.0.5+triton\n' in metadata
    (output/dependency.name).write_bytes(dependency_bytes)
    reports=[]
    shared_runtime=None
    for wheel in sorted(wheels.glob('aimee_*.whl')):
        with zipfile.ZipFile(wheel) as z:
            files={n:z.read(n) for n in z.namelist()}
            attributes={entry.filename:entry for entry in z.infolist()}
        info=next(n.rsplit('/',1)[0] for n in files if n.endswith('.dist-info/METADATA'))
        code={n:hashlib.sha256(d).hexdigest() for n,d in files.items() if not n.startswith(info+'/')}
        if notices is not None:
            # Public dependency notices are distribution metadata. Adding them
            # must not replace any validated executable or adapter binding.
            selected = ['SHARED_CLIENT_NOTICES.txt', 'CYTHON_COPYING.txt', 'CYTHON_LICENSE.txt'] if info.startswith('aimee_native_runtime-') else ['THIRD_PARTY_NOTICES.txt']
            for name in selected:
                source=notices/name
                if not source.is_file():raise ValueError('missing dependency notice: '+name)
                files[info+'/licenses/'+name]=source.read_bytes()
        if info.startswith('aimee_gemma4_'):
            metadata=files[info+'/METADATA'].rstrip(b'\n')+b'\n\n'
            headers,_,body=metadata.partition(b'\n\n')
            headers+=b'\nProvides-Extra: gguf\nRequires-Dist: vllm-gguf-plugin==0.0.5+triton; extra == "gguf"'
            files[info+'/METADATA']=headers+b'\n\n'+body
            parsed=BytesParser().parsebytes(files[info+'/METADATA'])
            assert parsed.get_all('Provides-Extra')==['gguf']
            assert 'vllm-gguf-plugin==0.0.5+triton; extra == "gguf"' in parsed.get_all('Requires-Dist')
        record=info+'/RECORD';files.pop(record,None)
        buffer=io.StringIO();writer=csv.writer(buffer,lineterminator='\n')
        for name,data in sorted(files.items()):writer.writerow([name,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('='),len(data)])
        writer.writerow([record,'','']);files[record]=buffer.getvalue().encode()
        parts=wheel.name.split('-');assert len(parts)==5
        dest=output/'-'.join(parts[:2]+[build_tag]+parts[2:])
        with dest.open('xb') as f,zipfile.ZipFile(f,'w',zipfile.ZIP_DEFLATED) as z:
            for name,data in sorted(files.items()):
                entry=attributes.get(name, zipfile.ZipInfo(name))
                entry.compress_type=zipfile.ZIP_DEFLATED
                z.writestr(entry,data)
        with zipfile.ZipFile(dest) as z:assert all(hashlib.sha256(z.read(n)).hexdigest()==digest for n,digest in code.items())
        entry={'wheel':dest.name,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'code_identical_to':wheel.name,'original_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),'code_member_sha256':code}
        if info.startswith('aimee_native_runtime-'):
            shared_runtime=entry
        else:
            reports.append(entry)
    assert len(reports)==len(models)
    assert {entry["wheel"].split("-")[0] for entry in reports} == {"aimee_"+name.replace("-","_") for name in models}
    report={'status':'passed','scope':__doc__,'plugins':reports,'shared_runtime':shared_runtime,'gguf_dependency':{'file':dependency.name,'sha256':hashlib.sha256(dependency_bytes).hexdigest(),'bytes':len(dependency_bytes)}}
    (output/'finalization.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--wheels',type=Path,required=True);p.add_argument('--dependency',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--notices',type=Path);p.add_argument('--models',nargs='+',default=['gemma4-12b','gemma4-26b','qwen3-8-27b']);a=p.parse_args();finalize(a.wheels,a.dependency,a.output,notices=a.notices,models=a.models)
