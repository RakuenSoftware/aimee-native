"""Matched lossless transport prototype. Preallocated buffers; not serving latency."""
import argparse,array,ctypes,json,mmap,os,pathlib,statistics,time
import torch
p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--library',required=True);p.add_argument('--output',required=True);p.add_argument('--trials',type=int,default=30);a=p.parse_args()
r=pathlib.Path(a.root);meta=json.loads((r/'format.json').read_text());raw=(r/'raw.pack').read_bytes();code_size=(r/'encoded.pack').stat().st_size
index_offset=(code_size+3)&~3;index=array.array('I',meta['exception_positions']);total=index_offset+len(index)*4
host_raw=torch.empty(len(raw),dtype=torch.uint8,pin_memory=True);host_code=torch.empty(total,dtype=torch.uint8,pin_memory=True)
host_code[index_offset:]=torch.frombuffer(index,dtype=torch.uint8);host_code[code_size:index_offset]=0
out=torch.empty(len(raw),dtype=torch.uint8,device='cuda:0');packed=torch.empty(total,dtype=torch.uint8,device='cuda:0');expected=torch.frombuffer(bytearray(raw),dtype=torch.uint8)
lib=ctypes.CDLL(a.library);fn=lib.aimee_decode_bf16;fn.argtypes=[ctypes.c_void_p]*3+[ctypes.c_size_t]*3+[ctypes.c_uint64]*2+[ctypes.c_void_p,ctypes.c_int];fn.restype=ctypes.c_int
stream=torch.cuda.current_stream().cuda_stream;t0=int.from_bytes(bytes(meta['table'][:8]),'little');t1=int.from_bytes(bytes(meta['table'][8:]),'little')
fds={k:os.open(r/(k+'.pack'),os.O_RDONLY) for k in ['raw','encoded']};maps={};anchors={};states={}
libc=ctypes.CDLL(None,use_errno=True);libc.mincore.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p]
for k,fd in fds.items():
 os.fsync(fd);size=os.fstat(fd).st_size;maps[k]=mmap.mmap(fd,size,access=mmap.ACCESS_COPY);anchors[k]=ctypes.c_char.from_buffer(maps[k]);states[k]=(ctypes.c_ubyte*((size+mmap.PAGESIZE-1)//mmap.PAGESIZE))()
def resident(k):
 if libc.mincore(ctypes.addressof(anchors[k]),len(maps[k]),states[k]):raise OSError(ctypes.get_errno())
 return sum(bool(x&1) for x in states[k])
def decode():
 if fn(packed.data_ptr(),packed.data_ptr()+index_offset,out.data_ptr(),meta['words'],meta['exception_offset'],meta['exceptions'],t0,t1,stream,0):raise RuntimeError('lossless GPU decoder launch failed')
views={'raw':memoryview(host_raw.numpy()),'encoded':memoryview(host_code.numpy())[:code_size]}
os.preadv(fds['encoded'],[views['encoded']],0);packed.copy_(host_code,non_blocking=True);decode();torch.cuda.synchronize();assert torch.equal(out.cpu(),expected)
start_event=torch.cuda.Event(enable_timing=True);end_event=torch.cuda.Event(enable_timing=True);rows=[]
for trial in range(a.trials):
 for mode in (['raw','encoded'] if trial%2==0 else ['encoded','raw']):
  for _ in range(20):
   os.posix_fadvise(fds[mode],0,0,os.POSIX_FADV_DONTNEED)
   if not resident(mode):break
   time.sleep(.01)
  if resident(mode):raise RuntimeError('source is not page-cache cold')
  start=time.perf_counter_ns();n=os.preadv(fds[mode],[views[mode]],0);read=time.perf_counter_ns()
  if n!=len(views[mode]):raise RuntimeError('short fixture read')
  if mode=='raw':out.copy_(host_raw,non_blocking=True)
  else:packed.copy_(host_code,non_blocking=True)
  if mode=='encoded':start_event.record();decode();end_event.record()
  submit=time.perf_counter_ns();torch.cuda.synchronize();done=time.perf_counter_ns()
  row={'trial':trial,'mode':mode,'read_us':(read-start)/1000,'submit_us':(submit-read)/1000,'wait_us':(done-submit)/1000,'total_us':(done-start)/1000,'source_resident_pages_before':0}
  if mode=='encoded':row['gpu_decode_us']=start_event.elapsed_time(end_event)*1000
  assert torch.equal(out.cpu(),expected),'GPU reconstruction changed bits';rows.append(row)
summary={m:{field:statistics.median(x[field] for x in rows if x['mode']==m) for field in ['read_us','submit_us','wait_us','total_us']} for m in ['raw','encoded']}
summary['encoded']['gpu_decode_us']=statistics.median(x['gpu_decode_us'] for x in rows if x['mode']=='encoded')
report={'status':'passed','scope':__doc__,'raw_disk_and_transfer_bytes':len(raw),'encoded_disk_bytes':code_size,'encoded_transfer_bytes':total,'index_ram_bytes':len(index)*4,'all_bits_equal':True,'summary':summary,'rows':rows};pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
