"""Recreate private diagnostic sources; never include these in client artifacts."""
import argparse,pathlib,subprocess
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
repo=pathlib.Path(__file__).resolve().parents[3]
original=subprocess.check_output(['git','show','033ce67:distribution/vllm/aimee_vllm/kernel.py'],cwd=repo,text=True)
window=original.replace('for base in range(0,mem_len,TILE):','memory_start=0\n    if WINDOW>=0: memory_start=tl.maximum(0,mem_len+q_pos-WINDOW)\n    for base in range(memory_start,mem_len,TILE):')
root=pathlib.Path(a.output);root.mkdir(parents=True,exist_ok=True)
variants={'zero':original.replace('mem_len=tl.load(MLEN+req)','mem_len=0'),'window':window,'global':window.replace('mem_len=tl.load(MLEN+req)','mem_len=tl.load(MLEN+req)\n    if WINDOW>=0: mem_len=0')}
for name,source in variants.items():(root/('kernel_'+name+'.py')).write_text(source)
for name in ('export_kernel.py','binary_kernel.py'):(root/name).write_bytes((repo/'distribution/vllm/aimee_vllm'/name).read_bytes())
