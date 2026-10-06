"""Actual pinned vLLM IPC constructor + POSIX sockets, no CUDA initialization."""
import os,json,socket,tempfile
from pathlib import Path
short=Path('/opt/jmlr-second-review-20261005/repair-cache/gpr2')
parent=Path('/opt/jmlr-second-review-20261005/repair-cache')
short.mkdir(mode=0o700,exist_ok=True);(short/'t').mkdir(mode=0o700,exist_ok=True)
assert short.resolve().parent==parent.resolve() and os.stat(short).st_dev==os.stat(parent).st_dev
os.environ['TMPDIR']=str(short/'t');os.environ['VLLM_RPC_BASE_PATH']=str(short/'t')
from vllm.utils.network_utils import get_open_zmq_ipc_path
import torch,zmq
path=get_open_zmq_ipc_path();raw=path.removeprefix('ipc://')
assert len(raw.encode())<=zmq.IPC_PATH_MAX_LEN and tempfile.gettempdir()==str(short/'t')
context=zmq.Context();sock=context.socket(zmq.PAIR)
try:sock.bind(path)
finally:
 sock.close(linger=0);context.term();Path(raw).unlink(missing_ok=True)
probe=short/'cpu.sock'
with socket.socket(socket.AF_UNIX) as unix:
 try:unix.bind(str(probe))
 finally:probe.unlink(missing_ok=True)
assert not torch.cuda.is_initialized()
print(json.dumps({'status':'passed','zmq_path_bytes':len(raw.encode()),'zmq_ipc_max_bytes':zmq.IPC_PATH_MAX_LEN,'actual_vllm_ipc_bind_passed':True,'unix_control_bind_passed':True,'tmpdir':tempfile.gettempdir(),'cuda_initialized':False},indent=2))
