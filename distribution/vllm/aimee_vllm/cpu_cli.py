"""Explicit bounded CPU native serving profile; not a GPU compatibility bypass."""
import argparse,json,os,runpy,sys
from pathlib import Path
def command(path):
    config=json.loads(Path(path).read_text())
    if config.get('cpu_native_profile') is not True:raise ValueError('explicit CPU native profile required')
    if not config.get('research_owner_fixture') and not config.get('selection_socket'):raise ValueError('enrolled owner selection required')
    if config.get('model_revision') is None:raise ValueError('immutable checkpoint revision required')
    if not Path(config['model']).is_dir():raise ValueError('local stock checkpoint required')
    port=config.get('port',8437);length=config.get('max_model_len',4096)
    if type(port) is not int or not 1<=port<=65535 or type(length) is not int or not 1024<=length<=8192:raise ValueError('invalid CPU serving bounds')
    return ['--model',config['model'],'--served-model-name',config.get('served_model_name','research-e2b'),'--host','127.0.0.1','--port',str(port),'--dtype','float32','--max-model-len',str(length),'--max-num-seqs',str(config.get('max_num_seqs',2)),'--max-num-batched-tokens','1024','--kv-cache-memory-bytes',str(config.get('kv_cache_memory_bytes',1024**3)),'--enforce-eager','--language-model-only','--no-enable-prefix-caching','--no-async-scheduling','--enable-log-requests','--worker-cls','aimee_vllm.cpu_worker.AimeeCPUWorker','--attention-config','{"backend":"CUSTOM"}','--middleware','aimee_vllm.cpu_admission.NativeCPUAdmission']
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);opt=parser.parse_args();args=command(opt.config)
    from .compatibility import check_interface
    check_interface()
    import torch
    if torch.version.cuda is not None or torch.cuda.is_available():raise RuntimeError('CPU profile requires a CPU-only Torch build')
    os.environ['AIMEE_VLLM_CPU_CONFIG']=str(Path(opt.config).resolve());os.environ['VLLM_USE_V2_MODEL_RUNNER']='0';os.environ['VLLM_PLUGINS']='aimee_cpu_native_platform'
    for key in ['CUDA_VISIBLE_DEVICES','HIP_VISIBLE_DEVICES','ROCR_VISIBLE_DEVICES']:os.environ[key]=''
    # Register the CPU backend in both API and worker processes through the
    # documented worker_cls extension, without modifying upstream classes.
    from . import cpu_worker
    from vllm.platforms import current_platform
    from .cpu_platform import AimeeCPUPlatform
    if not isinstance(current_platform,AimeeCPUPlatform):raise RuntimeError("out-of-tree CPU platform was not activated")
    sys.argv=['vllm.entrypoints.openai.api_server',*args]
    runpy.run_module('vllm.entrypoints.openai.api_server',run_name='__main__')
if __name__=='__main__':main()
