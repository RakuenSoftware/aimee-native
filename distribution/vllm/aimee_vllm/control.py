"""Publisher-owned Unix control socket. Never mounted as an HTTP API."""
import asyncio,json,os,socket,struct
from pathlib import Path

async def start(owner, engine):
    path=owner.config.get('control_socket')
    if not path:return None
    path=Path(path)
    if path.exists():raise RuntimeError('native control socket already exists')
    lock=asyncio.Lock()
    async def handle(reader,writer):
        try:
            sock=writer.get_extra_info('socket')
            _,uid,_=struct.unpack('3i',sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if uid!=os.geteuid():raise RuntimeError('publisher UID mismatch')
            request=json.loads(await asyncio.wait_for(reader.readline(),10))
            async with lock:result=await operate(owner,engine,request)
        except Exception:result={'error':'native control operation failed; admission remains stopped'}
        writer.write(json.dumps(result).encode()+b'\n');await writer.drain();writer.close();await writer.wait_closed()
    server=await asyncio.start_unix_server(handle,path=str(path),limit=4096)
    os.chmod(path,0o600)
    return server

async def operate(owner,engine,request):
    if request == {'op':'status'}:
        return {'state':'restart_required' if owner.poisoned else ('paused' if owner.paused else 'active')}
    if request not in ({'op':'refresh'},{'op':'withdraw'}):raise ValueError('unsupported control operation')
    owner.paused=True
    if request['op']=='withdraw':return {'state':'withdrawn','active_requests':owner.active}
    if owner.poisoned:raise RuntimeError('worker restart required')
    try:
        await asyncio.wait_for(owner.idle.wait(),60)
        # Publication I/O/admission checks run away from attention and HTTP reads.
        banks=await asyncio.to_thread(owner.load_banks)
        results=await engine.collective_rpc('aimee_refresh_catalog',timeout=60)
        expected=owner.config.get('serve',{}).get('tensor_parallel_size',1)
        if len(results)!=expected or any(r['publications']!=len(banks) or r['pinned_requests']!=0 or r.get('catalog_digest')!=owner.pending_digest for r in results):
            raise RuntimeError('inconsistent worker refresh')
        owner.banks=banks
        owner.catalog_digest=owner.pending_digest
        owner.paused=False
        return {'state':'active','publications':len(banks),'workers':len(results)}
    except BaseException:
        # A failed collective refresh may leave ranks at different revisions.
        # No request is allowed through until a consistent worker restart.
        owner.poisoned=True
        raise
