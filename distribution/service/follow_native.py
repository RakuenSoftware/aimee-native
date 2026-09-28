"""Private supervisor: existing Aimee follower -> approved preparation -> vLLM.
All argv/config paths are operator-owned. No policy issuance or public API here.
"""
import argparse,asyncio,hashlib,json,os,signal,tempfile,stat
from pathlib import Path

async def control(path,op):
    reader,writer=await asyncio.wait_for(asyncio.open_unix_connection(path),10)
    try:
        writer.write(json.dumps({'op':op} if isinstance(op,str) else op).encode()+b'\n');await writer.drain()
        operation=op.get('op') if isinstance(op,dict) else op
        result=json.loads(await asyncio.wait_for(reader.readline(),720 if operation=='refresh' else 120))
        if result.get('error'):raise RuntimeError('native control rejected update')
        return result
    finally:writer.close();await writer.wait_closed()

async def stop(child):
    if child is None:return
    try:os.killpg(child.pid,signal.SIGTERM)
    except ProcessLookupError:return
    try:await asyncio.wait_for(child.wait(),10)
    except asyncio.TimeoutError:
        os.killpg(child.pid,signal.SIGKILL);await child.wait()

async def prepare(command):
    child=await asyncio.create_subprocess_exec(*command,stdout=asyncio.subprocess.PIPE,start_new_session=True)
    try:
        output,_=await child.communicate()
        if child.returncode:raise RuntimeError('approved preparation failed')
        return json.loads(output)
    finally:await stop(child)

def publish(path,catalog):
    path=Path(path)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as f:
        staged=Path(f.name)
        try:
            os.chmod(staged,0o600);json.dump(catalog,f);f.flush();os.fsync(f.fileno())
            staged.replace(path)
            fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        finally:staged.unlink(missing_ok=True)

async def events(stream, socket):
    # Keep one pending read: health polling must not discard a partial feed line.
    pending=asyncio.create_task(stream.readline())
    loop=asyncio.get_running_loop();health_at=loop.time()+2
    try:
        while True:
            done,_=await asyncio.wait({pending},timeout=max(0,health_at-loop.time()))
            if loop.time()>=health_at:
                if (await control(socket,'status')).get('state')=='restart_required':
                    raise RuntimeError('native serving recovery required')
                health_at=loop.time()+2
            if not done:continue
            line=pending.result()
            if not line:return
            yield line
            pending=asyncio.create_task(stream.readline())
    finally:
        pending.cancel()
        try:await pending
        except asyncio.CancelledError:pass

async def follow(config):
    serving=json.loads(Path(config['serving_config']).read_text());socket=serving['control_socket']
    if not serving.get('start_paused'):raise RuntimeError('supervised serving must start with admission paused')
    server=await asyncio.create_subprocess_exec(*config['server'],start_new_session=True)
    follower=None;pending=None;socket_identity=None
    try:
        for _ in range(180):
            if server.returncode is not None:raise RuntimeError('serving process exited')
            try:
                await control(socket,'withdraw')
                info=Path(socket).lstat()
                socket_identity=(info.st_dev,info.st_ino)
                break
            except (OSError,asyncio.TimeoutError):await asyncio.sleep(1)
        else:raise RuntimeError('native control socket unavailable')
        follower=await asyncio.create_subprocess_exec(*config['follower'],stdout=asyncio.subprocess.PIPE,start_new_session=True)
        async def update(view,generation):
            publications={};selections=[]
            try:
                for name,command in config['preparations'].items():
                    result=await prepare(command)
                    if result['authorized_view']!=view or result['recipient']!=serving['recipient']:
                        raise RuntimeError('prepared publication binding changed')
                    publications[name]={k:result[k] for k in ('root','model','key')}
                    selections.append({'publication':name,'authorized_view':view,'records':result['records']})
                catalog={'recipient':serving['recipient'],'model_config_sha256':hashlib.sha256((Path(serving['model'])/'config.json').read_bytes()).hexdigest(),'publications':publications,'selections':selections}
                publish(serving['catalog'],catalog)
                result=await control(socket,{'op':'refresh','generation':generation})
                print(json.dumps({'state':'active','view':view,'publications':len(publications)}),flush=True)
                return True
            except asyncio.CancelledError:raise
            except Exception:
                # A failed update must not restore old authority implicitly.
                try:await control(socket,'withdraw')
                except Exception:
                    await stop(server)
                    raise
                print(json.dumps({'state':'unavailable','reason':'preparation_or_activation_failed'}),flush=True)
                return False
        last=None
        async for line in events(follower.stdout,socket):
            event=json.loads(line)
            if event.get('state')=='unchanged' and event.get('view')==last and pending is not None:
                if not pending.done():continue
                if pending.result():continue
            withdrawal=await control(socket,'withdraw')
            if pending is not None:
                pending.cancel()
                try:await pending
                except asyncio.CancelledError:pass
            if event.get('state') in ('installed','unchanged') and event.get('view'):
                last=event['view'];pending=asyncio.create_task(update(last,withdrawal['generation']))
            else:
                last=None;pending=None
                print(json.dumps({'state':'withdrawn'}),flush=True)
        raise RuntimeError('authoritative publication stream ended')
    finally:
        if pending is not None:
            pending.cancel()
            try:await pending
            except (asyncio.CancelledError,Exception):pass
        # Never leave a model serving native memory after its authority feed dies.
        await stop(server);await stop(follower)
        # Forced termination does not execute ASGI socket cleanup. Remove only
        # the endpoint observed on our owned server, never a replacement socket.
        if socket_identity is not None:
            try:
                info=Path(socket).lstat()
                if stat.S_ISSOCK(info.st_mode) and (info.st_dev,info.st_ino)==socket_identity:
                    Path(socket).unlink()
            except FileNotFoundError:pass

async def main(config):
    loop=asyncio.get_running_loop();task=asyncio.current_task()
    for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,task.cancel)
    try:
        for attempt in range(config.get('restart_limit',3)+1):
            try:
                await follow(config)
                return
            except asyncio.CancelledError:raise
            except Exception:
                if attempt==config.get('restart_limit',3):raise
                print(json.dumps({'state':'restarting','attempt':attempt+1}),flush=True)
                await asyncio.sleep(2)
    except asyncio.CancelledError:
        pass  # Normal operator shutdown; child/socket cleanup runs above.
    finally:
        for sig in (signal.SIGTERM,signal.SIGINT):loop.remove_signal_handler(sig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);a=p.parse_args()
    asyncio.run(main(json.loads(Path(a.config).read_text())))
