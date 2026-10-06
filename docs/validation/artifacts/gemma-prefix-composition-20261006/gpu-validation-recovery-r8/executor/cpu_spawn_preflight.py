"""Actual multiprocessing spawn reimport of test service entrypoint, CPU only."""
import os,sys,runpy,multiprocessing,json
from pathlib import Path
HELPER=Path('/opt/jmlr-second-review-20261005/repair-cache/gemma-composition-candidate-r1/gpu-executor-recovery-r8/service_boot.py')
def child(connection):
    sys.argv=['vllm','serve','unused-config-after-spawn']
    namespace=runpy.run_path(str(HELPER),run_name='__mp_main__')
    import torch
    assert callable(namespace['main']) and not torch.cuda.is_initialized()
    connection.send({'spawn_reimport_passed':True,'cuda_initialized':False,'no_cli_reentry':True})
    connection.close()
if __name__=='__main__':
    ctx=multiprocessing.get_context('spawn');parent,remote=ctx.Pipe()
    worker=ctx.Process(target=child,args=(remote,));worker.start();remote.close()
    assert parent.poll(60),'CPU spawn timed out';result=parent.recv();worker.join(60)
    assert worker.exitcode==0
    print(json.dumps(dict(status='passed',**result),indent=2))
