#!/usr/bin/env python3
"""Audit wheel identity, RECORD, namespace isolation and Rust adapter symbols."""
import argparse
import base64
import configparser
import csv
from email.parser import BytesParser
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

MODELS = {"gemma4-12b":"aimee_gemma4_12b", "gemma4-26b":"aimee_gemma4_26b", "qwen3-8-27b":"aimee_qwen3_8_27b", "gemma4-e2b":"aimee_gemma4_e2b", "gemma4-e4b":"aimee_gemma4_e4b"}


def audit(root, models=("gemma4-12b","gemma4-26b","qwen3-8-27b")):
    selected={name:MODELS[name] for name in models}
    reports=[]
    owned=set()
    shared_requirements=[]
    for model,package in selected.items():
        wheels=list(root.glob(package+'-*.whl'))
        if len(wheels)!=1:raise ValueError('expected exactly one wheel for '+model)
        wheel=wheels[0]
        with zipfile.ZipFile(wheel) as z:
            names=z.namelist()
            assert len(names)==len(set(names))
            info=next(n.rsplit('/',1)[0] for n in names if n.endswith('.dist-info/METADATA'))
            metadata=BytesParser().parsebytes(z.read(info+'/METADATA'))
            shared=[value for value in metadata.get_all('Requires-Dist',[]) if value.startswith('aimee-native-runtime==')]
            shared_requirements.extend(shared)
            assert metadata['Name'].replace('-','_')==package
            if model.startswith('gemma'):
                assert metadata.get_all('Provides-Extra')==['gguf'], 'pip cannot see the GGUF extra'
                assert 'vllm-gguf-plugin==0.0.5+triton; extra == "gguf"' in metadata.get_all('Requires-Dist'), 'GGUF dependency missing from metadata headers'
            assert all(n.startswith((package+'/',package+'-')) for n in names)
            assert not owned.intersection(names),'plugins overwrite each other'
            owned.update(names)
            entries=configparser.ConfigParser();entries.read_string(z.read(info+'/entry_points.txt').decode())
            assert dict(entries['vllm.general_plugins'])=={package:package+':register'}
            assert dict(entries['console_scripts'])=={package.replace('_','-'):package+'.cli:main'}
            assert not any('/native_compiler/' in n or n.endswith(('.c','.cpp','.pyx','.gguf','.safetensors')) for n in names)
            assert package+'/native/aimee-model-client' not in names, 'shared connection client duplicated into model wheel'
            if shared:
                assert not any(name.endswith('.so') and '/native/' not in name for name in names), 'common compiled bridge duplicated into model wheel'
            raw=z.read(package+'/native/libaimee_native.so')
            binding=json.loads(z.read(package+'/native/adapter.json'))
            assert binding['adapter']==model
            assert binding['library_sha256']==hashlib.sha256(raw).hexdigest()
            with tempfile.NamedTemporaryFile() as f:
                f.write(raw);f.flush()
                symbols=subprocess.check_output(['nm','-D',f.name],text=True)
            for other,candidate in MODELS.items():
                assert (candidate+'_adapter' in symbols)==(other==model)
            record=list(csv.reader(io.StringIO(z.read(info+'/RECORD').decode())))
            assert {r[0] for r in record}==set(names)
            for name,digest,size in record:
                if name==info+'/RECORD':continue
                data=z.read(name)
                assert len(data)==int(size)
                assert digest=='sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
            reports.append({'adapter':model,'wheel':wheel.name,'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),'bytes':wheel.stat().st_size,'members':len(names),'library_sha256':binding['library_sha256']})
    runtime=None
    if shared_requirements:
        assert len(shared_requirements)==len(selected) and len(set(shared_requirements))==1,'plugins must pin the same shared runtime'
        runtime_wheels=list(root.glob('aimee_native_runtime-*.whl'))
        assert len(runtime_wheels)==1,'shared runtime wheel missing'
        wheel=runtime_wheels[0]
        with zipfile.ZipFile(wheel) as z:
            names=z.namelist()
            assert len(names)==len(set(names))
            assert all(name.startswith(('aimee_native_runtime/', 'aimee_native_runtime-')) for name in names)
            assert not owned.intersection(names)
            executable='aimee_native_runtime/native/aimee-model-client'
            assert executable in names
            assert (z.getinfo(executable).external_attr >> 16) & 0o111, 'shared connection client is not executable'
            assert not any(name.endswith('libaimee_native.so') for name in z.namelist()),'shared runtime contains a model adapter'
            info=next(n.rsplit('/',1)[0] for n in z.namelist() if n.endswith('.dist-info/METADATA'))
            metadata=BytesParser().parsebytes(z.read(info+'/METADATA'))
            assert shared_requirements[0]=='aimee-native-runtime=='+metadata['Version']
            record=list(csv.reader(io.StringIO(z.read(info+'/RECORD').decode())))
            assert {row[0] for row in record}==set(names)
            for name,digest,size in record:
                if name==info+'/RECORD':continue
                data=z.read(name)
                assert len(data)==int(size)
                assert digest=='sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
            assert not any(name.endswith('/entry_points.txt') for name in names), 'shared runtime must not register a model plugin'
        runtime={'wheel':wheel.name,'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),'required_by':len(selected)}
    return {'status':'passed','scope':__doc__,'plugins':reports,'shared_runtime':runtime}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--wheels',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--models',nargs='+',choices=MODELS,default=['gemma4-12b','gemma4-26b','qwen3-8-27b']);a=p.parse_args()
    report=audit(a.wheels,a.models);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
