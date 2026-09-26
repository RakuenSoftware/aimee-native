"""Exact compiled-consumer activation timings, with verified OS page residency.

Preparation and initial integrity admission are separate. Activation measurements
include framework wrapping, page faults where labeled, and completed GPU work.
They are not isolated DMA, SSD controller latency, or attention/answer latency.
"""
import argparse,ctypes,json,math,mmap,os,pathlib,statistics,time,subprocess,sys,tempfile
import torch

p=argparse.ArgumentParser();p.add_argument('--catalog',required=True);p.add_argument('--publication',required=True);p.add_argument('--library',default='/opt/aimee/libaimee_native.so');p.add_argument('--output',required=True);p.add_argument('--repetitions',type=int,default=100);p.add_argument('--single-cold',action='store_true');p.add_argument('--cold-repetitions',type=int,default=20);p.add_argument('--packed',action='store_true');p.add_argument('--bridge-file');p.add_argument('--native-profile',action='store_true');p.add_argument('--raw-transport',action='store_true');a=p.parse_args()
if a.bridge_file:
    import importlib.util
    module=importlib.util.spec_from_file_location('native_store_probe',a.bridge_file);bridge=importlib.util.module_from_spec(module);module.loader.exec_module(bridge);PreparedStore=bridge.PreparedStore
else:
    from aimee_vllm.store import PreparedStore
def activate():
    return store.activate(device,0,2,profile=True) if a.native_profile else store.activate(device,0,2)
spec=json.loads(pathlib.Path(a.catalog).read_text())['publications'][a.publication]
spec=dict(spec,disk_backed=True,byte_budget=512*1024**2)
if a.bridge_file or a.raw_transport:spec.update(lossless_transport=not a.raw_transport,device_budget=256*1024**2)
lib=ctypes.CDLL(a.library);device=torch.device('cuda:0');torch.cuda.set_device(device)
# Initialize GPU context before measuring admission or application.
torch.empty(1,device=device);torch.cuda.synchronize()
warmup_us=0
if hasattr(lib,'aimee_store_runtime_warmup'):
    lib.aimee_store_runtime_warmup.argtypes=[ctypes.c_int];lib.aimee_store_runtime_warmup.restype=ctypes.c_bool
    started=time.perf_counter_ns()
    if not lib.aimee_store_runtime_warmup(0):raise RuntimeError('native runtime warmup failed')
    warmup_us=(time.perf_counter_ns()-started)/1000
started=time.perf_counter_ns();store=PreparedStore(lib,spec);admission_us=(time.perf_counter_ns()-started)/1000
started=time.perf_counter_ns()
plan=store.prepare_plan(0,2)[1] if hasattr(store,'prepare_plan') else {}
plan_us=(time.perf_counter_ns()-started)/1000
path=pathlib.Path(spec['root'])/'compact.pack';original_size=path.stat().st_size
source=plan.get('transport_source')
if source:fd=os.dup(source['fd']);size=source['bytes'];source_offset=source['offset']
else:fd=os.open(path,os.O_RDONLY);size=os.fstat(fd).st_size;source_offset=0
# Flush the benchmark-owned file before attempting clean-page eviction. This
# is setup outside measurement; DONTNEED is allowed to retain dirty pages.
os.fsync(fd)
mapping=mmap.mmap(fd,size,access=mmap.ACCESS_COPY,offset=source_offset);anchor=ctypes.c_char.from_buffer(mapping)
address=ctypes.addressof(anchor);pages=(size+mmap.PAGESIZE-1)//mmap.PAGESIZE
libc=ctypes.CDLL(None,use_errno=True);libc.mincore.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p]
def resident_pages():
    state=(ctypes.c_ubyte*pages)()
    if libc.mincore(address,size,state):raise OSError(ctypes.get_errno(),'mincore')
    return sum(bool(x&1) for x in state)
def warm():
    for offset in range(0,size,1024*1024):os.pread(fd,min(1024*1024,size-offset),source_offset+offset)
def summary(rows):
    x=sorted(r['us'] for r in rows)
    return {'n':len(x),'median_us':statistics.median(x),'p95_us':x[math.ceil(.95*len(x))-1],'min_us':x[0],'max_us':x[-1]}
report={'scope':__doc__,'source_bytes':size,'original_source_bytes':original_size,'runtime_warmup_us':warmup_us,'transport_preparation_us':plan_us,'lossless_transport':plan.get('lossless_transport',False),'transfer_bytes':plan.get('transfer_bytes',store.device_bytes(2)),'rank':0,'world':2,'device_bytes':store.device_bytes(2),'initial_admission_us':admission_us,'rows':{'os_page_cache_cold':[],'os_page_cache_warm':[],'already_device_resident':[]},'status':'running'}
try:
    if a.single_cold:
        # Prime allocation/transfer paths with unrelated zeros. Reading the target
        # bank here can leave pages resident even after DONTNEED; do not do that.
        if a.packed:
            pinned=torch.empty(plan.get('transfer_bytes',store.device_bytes(2))//2,dtype=torch.bfloat16,pin_memory=True)
            pinned.zero_();dummy_packed=pinned.to(device,non_blocking=True)
            dummy_dense=torch.empty(store.device_bytes(2)//2,dtype=torch.bfloat16,device=device)
            torch.cuda.synchronize();del dummy_packed,pinned,dummy_dense
        dummy=[]
        for segment in store.metadata['segments']:
            heads=segment['heads']//2 if segment['heads']>=2 else 1
            dummy.append(torch.zeros((heads,segment['positions'],segment['width']),dtype=torch.bfloat16).to(device))
        torch.cuda.synchronize();del dummy
        lib.aimee_store_release_pages(store.handle)
        for attempt in range(20):
            os.posix_fadvise(fd,0,0,os.POSIX_FADV_DONTNEED)
            if resident_pages()==0:break
            time.sleep(.01)
        before=resident_pages()
        if before:raise RuntimeError(f'cold precondition failed: {before}/{pages} resident')
        started=time.perf_counter_ns();activate();torch.cuda.synchronize()
        report['rows']['os_page_cache_cold'].append({'us':(time.perf_counter_ns()-started)/1000,'phases_us':getattr(store,'last_profile',{}),'resident_pages_before':before,'conditioning_attempts':attempt+1})
        report['status']='passed';report['summary']={'os_page_cache_cold':summary(report['rows']['os_page_cache_cold'])}
    else:
        # Fresh child address spaces make each cold trial independently checkable;
        # process/GPU setup and integrity admission stay outside measured activation.
        with tempfile.TemporaryDirectory(prefix='native-cold-') as temp:
            for i in range(a.cold_repetitions):
                target=pathlib.Path(temp)/f'{i}.json'
                subprocess.run([sys.executable,__file__,'--catalog',a.catalog,'--publication',a.publication,'--library',a.library,'--output',str(target),'--single-cold']+(['--packed'] if a.packed else [])+(['--bridge-file',a.bridge_file] if a.bridge_file else [])+(['--native-profile'] if a.native_profile else [])+(['--raw-transport'] if a.raw_transport else []),check=True,stdout=subprocess.DEVNULL)
                trial=json.loads(target.read_text());assert trial['status']=='passed'
                report['rows']['os_page_cache_cold']+=trial['rows']['os_page_cache_cold']
        activate();torch.cuda.synchronize();store.evict(device,0,2)
        for i in range(a.repetitions):
            store.evict(device,0,2);torch.cuda.synchronize();lib.aimee_store_release_pages(store.handle)
            warm();before=resident_pages()
            if before!=pages:raise RuntimeError(f'warm precondition failed: {before}/{pages} resident')
            started=time.perf_counter_ns();activate();torch.cuda.synchronize()
            report['rows']['os_page_cache_warm'].append({'us':(time.perf_counter_ns()-started)/1000,'phases_us':getattr(store,'last_profile',{}),'resident_pages_before':before})
    for _ in range(0 if a.single_cold else a.repetitions):
        started=time.perf_counter_ns();store.activate(device,0,2)
        report['rows']['already_device_resident'].append({'us':(time.perf_counter_ns()-started)/1000})
    # Verify complete GPU bytes against the admitted source after measurement.
    banks=store.activate(device,0,2);checked=0
    for seg in store.metadata['segments']:
        raw=(ctypes.c_ubyte*seg['bytes']).from_address(seg['pointer'])
        expected=torch.frombuffer(raw,dtype=torch.bfloat16).reshape(seg['heads'],seg['positions'],seg['width'])
        expected=expected.chunk(2,dim=0)[0] if seg['heads']>=2 else expected
        actual=banks[(seg['layer'],seg['value'])].cpu()
        if not torch.equal(actual.contiguous().view(torch.uint8),expected.contiguous().view(torch.uint8)):
            raise RuntimeError('native transfer changed tensor bytes')
        checked+=1
    report['exact_segments_verified']=checked
    report['summary']={k:summary(v) for k,v in report['rows'].items() if v};report['status']='passed'
    report['phase_medians_us']={k:{stage:statistics.median(row['phases_us'][stage] for row in rows) for stage in rows[0]['phases_us']} for k,rows in report['rows'].items() if rows and rows[0].get('phases_us')}
except BaseException as e:
    report['status']='failed';report['error']=str(e);raise
finally:
    pathlib.Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
    store.close();del anchor;mapping.close();os.close(fd)
print(json.dumps(report['summary']))
