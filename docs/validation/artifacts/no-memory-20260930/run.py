from pathlib import Path
import fcntl,os,subprocess,json
r=Path(__file__).parent;old=r.parent/'cuda-5080-20260930'
with (r.parent/'gpu-5080-validation.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
 env=dict(os.environ,PATH=str(old/'env/bin')+':'+os.environ['PATH'],CUDA_VISIBLE_DEVICES='0',TRITON_CACHE_DIR=str(old/'triton-cache'),VLLM_USE_FLASHINFER_SAMPLER='0')
 p=subprocess.run([str(old/'env/bin/python'),str(r/'probe.py'),'--root',str(old/'client'),'--config',str(r/'config.json'),'--output',str(r/'live.json'),'--repeat','24','--interleave-controls','--start-with-empty','--interrupt-and-recover'],env=env)
 (r/'exit.json').write_text(json.dumps({'returncode':p.returncode}))
