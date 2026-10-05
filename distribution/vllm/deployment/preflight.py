"""Fail closed on deployment/configuration drift before loading GPU weights."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def check(config):
    c=json.loads(Path(config).read_text())
    import importlib
    module=c.get('python_module','aimee_vllm')
    if module not in ('aimee_vllm','aimee_gemma4_12b','aimee_gemma4_26b','aimee_qwen3_8_27b'):
        raise RuntimeError('unknown installed model plugin')
    importlib.import_module(module+'.cli').command(config)
    if c.get('offline_prefix_capture'):raise ValueError('offline capture is forbidden in the service')
    gpu=subprocess.check_output(['nvidia-smi','--query-gpu=name','--format=csv,noheader'],text=True).strip()
    if gpu!='NVIDIA GeForce RTX 5080':raise RuntimeError('this deployment requires the RTX 5080')
    catalog=json.loads(Path(c['catalog']).read_text())
    actual=hashlib.sha256((Path(c['model'])/'config.json').read_bytes()).hexdigest()
    if catalog['recipient']!=c['recipient'] or catalog['model_config_sha256']!=actual:
        raise RuntimeError('deployment catalogue binding mismatch')
    root=Path(c['model'])
    provenance=root/'weight-provenance.json'
    if c.get('quantization'):
        raw=provenance.read_bytes()
        model_config=json.loads((root/'config.json').read_text())
        if hashlib.sha256(raw).hexdigest()!=model_config.get('aimee_weight_manifest_sha256'):
            raise RuntimeError('quantized checkpoint provenance mismatch')
        for item in json.loads(raw)['files']:
            path=root/item['file']
            if path.name!=item['file'] or path.stat().st_size!=item['bytes']:
                raise RuntimeError('quantized checkpoint extent mismatch')
            checksum=hashlib.sha256()
            with path.open('rb') as source:
                for chunk in iter(lambda:source.read(8*1024**2),b''):checksum.update(chunk)
            if checksum.hexdigest()!=item['sha256']:
                raise RuntimeError('quantized checkpoint checksum mismatch')
    Path('/opt/aimee-native-serving/jit-runtime/tmp').mkdir(parents=True,exist_ok=True,mode=0o700)
    Path(c['control_socket']).unlink(missing_ok=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);a=p.parse_args();check(a.config)
