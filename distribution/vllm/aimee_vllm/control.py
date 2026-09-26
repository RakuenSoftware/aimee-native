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
    if request == {'op':'metrics'}:
        # Explicit operator request, outside admission and attention. A missing
        # rank is a failed measurement, never reported as a smaller footprint.
        workers=await engine.collective_rpc('aimee_cache_stats',timeout=30)
        expected=owner.config.get('serve',{}).get('tensor_parallel_size',1)
        if len(workers)!=expected:raise RuntimeError('incomplete worker metrics')
        return {'workers':workers,'active_requests':owner.active,
                'state':'restart_required' if owner.poisoned else ('paused' if owner.paused else 'active')}
    guarded_refresh=(set(request)=={'op','generation'} and request['op']=='refresh'
                     and type(request['generation']) is int and request['generation']>=0)
    if request not in ({'op':'refresh'},{'op':'withdraw'}) and not guarded_refresh:
        raise ValueError('unsupported control operation')
    if guarded_refresh and request['generation']!=getattr(owner,'generation',0):
        raise RuntimeError('superseded publication activation')
    owner.paused=True
    if request['op']=='withdraw':
        owner.generation=getattr(owner,'generation',0)+1
        return {'state':'withdrawn','active_requests':owner.active,'generation':owner.generation}
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
