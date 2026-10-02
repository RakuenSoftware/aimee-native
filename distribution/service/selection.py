"""Private selection/preparation gateway using Aimee's existing published reader.
No authorization policy or retrieval algorithm is reimplemented here.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import struct
import tempfile
from follow_native import control, prepare, publish, stop


def refs(records):
    return tuple((r['namespace'], r['id'], r['revision']) for r in records)


class Selector:
    def __init__(self, config):
        self.config = config
        self.lock = asyncio.Lock()
        self.reader = None

    async def call(self, request):
        if self.reader is None or self.reader.returncode is not None:
            self.reader = await asyncio.create_subprocess_exec(
                self.config['image_reader'], 'serve-published', '--root',
                self.config['memory_image'], stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, limit=16*1024*1024,
                start_new_session=True)
        try:
            self.reader.stdin.write(json.dumps(request).encode()+b'\n')
            await self.reader.stdin.drain()
            result = json.loads(await asyncio.wait_for(self.reader.stdout.readline(), 30))
        except BaseException:
            # A delayed response must never be consumed as the next request's
            # approval. Drop the entire pinned reader after a protocol failure.
            await self.close()
            raise
        if 'error' in result:
            raise RuntimeError('published memory unavailable')
        return result

    async def select(self, query):
        if not isinstance(query, str) or not query or len(query.encode()) > 65536:
            raise ValueError('unsupported memory query')
        async with self.lock:
            pin = await self.call({'op':'pin'})
            recalled = await self.call({'op':'recall', 'query':query,
                                        'limit':self.config.get('limit', 8),
                                        'authority':self.config['authority']})
            view = pin['view']
            if recalled.get('view') != view:
                raise RuntimeError('selection changed publication')
            if recalled.get('outcome') != 'hit':
                # A complex/missing read must go back to Aimee, not be silently
                # treated as an empty approved native-memory selection.
                raise RuntimeError('authoritative fallback or preparation required')
            response = recalled['response']
            approval = await self.call({'op':'resolve_local_response','response':response})
            selected = refs(approval['refs'])
            if approval['view'] != view or not selected or len(selected) != len(response['facts']):
                raise RuntimeError('incomplete approved working set')
            raw = Path(self.config['catalog']).read_bytes()
            catalog = json.loads(raw)
            if catalog['recipient'] != self.config['recipient']:
                raise RuntimeError('recipient binding mismatch')
            publication = None
            for binding in catalog.get('selections', []):
                if binding['authorized_view'] == view and refs(binding['records']) == selected:
                    name = binding['publication']
                    if name in catalog['publications']:
                        publication = name
                        break
            if publication is None:
                template = self.config.get('preparation_config')
                if template is None:
                    raise RuntimeError('approved working set needs preparation')
                # Only query changes; recipient, source, runtime and compiler are
                # fixed by private operator configuration, never HTTP input.
                preparation = json.loads(Path(template).read_text())
                if preparation['recipient'] != self.config['recipient']:
                    raise RuntimeError('preparation recipient mismatch')
                if preparation['memory_image'] != self.config['memory_image'] or preparation['authority'] != self.config['authority'] or preparation['limit'] != self.config.get('limit',8):
                    raise RuntimeError('preparation selection configuration mismatch')
                preparation['query'] = query
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json') as f:
                    os.chmod(f.name,0o600)
                    json.dump(preparation, f); f.flush()
                    result = await prepare([self.config['native_prepare'], f.name])
                if result['authorized_view'] != view or result['recipient'] != self.config['recipient'] or refs(result['records']) != selected:
                    raise RuntimeError('prepared working set mismatch')
                # Recheck after potentially long compilation before publishing.
                check = await self.call({'op':'resolve_local_response','response':response})
                if check['view'] != view or refs(check['refs']) != selected:
                    raise RuntimeError('publication changed during preparation')
                withdrawal = await control(self.config['control_socket'],'withdraw')
                publication = result['key']
                # Discard entries from obsolete authorization views.
                bindings = [b for b in catalog.get('selections',[]) if b['authorized_view']==view]
                names = {b['publication'] for b in bindings}
                catalog['publications'] = {k:v for k,v in catalog['publications'].items() if k in names}
                catalog['publications'][publication] = {k:result[k] for k in ('root','model','key')}
                catalog['selections'] = bindings + [{'publication':publication,'authorized_view':view,'records':result['records']}]
                publish(self.config['catalog'],catalog)
                await control(self.config['control_socket'],{'op':'refresh','generation':withdrawal['generation']})
                raw = Path(self.config['catalog']).read_bytes()
            # Resolve even cache hits; retained bytes are not continuing authority.
            check = await self.call({'op':'resolve_local_response','response':response})
            if check['view'] != view or refs(check['refs']) != selected:
                raise RuntimeError('selection approval changed')
            return {'publication':publication,'catalog_digest':hashlib.sha256(raw).hexdigest()}

    async def close(self):
        await stop(self.reader)
        self.reader = None


async def serve(config):
    selector = Selector(config)
    path = Path(config['socket'])
    if path.exists():
        raise RuntimeError('selection endpoint already exists')
    async def handle(reader, writer):
        try:
            peer = writer.get_extra_info('socket')
            _,uid,_ = struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if uid != config.get('peer_uid',os.geteuid()):
                raise RuntimeError('selection peer mismatch')
            request = json.loads(await asyncio.wait_for(reader.readline(),10))
            if set(request) != {'query'}:
                raise ValueError('selection accepts only a query')
            result = await selector.select(request['query'])
        except Exception:
            result = {'error':'native_selection_unavailable'}
        try:
            writer.write(json.dumps(result).encode()+b'\n'); await writer.drain()
        finally:
            writer.close(); await writer.wait_closed()
    server = await asyncio.start_unix_server(handle,path=str(path),limit=1024*1024)
    os.chmod(path,0o600)
    try:
        async with server:
            await server.serve_forever()
    finally:
        await selector.close();path.unlink(missing_ok=True)


async def main(config):
    loop=asyncio.get_running_loop();task=asyncio.current_task()
    for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,task.cancel)
    try:await serve(config)
    except asyncio.CancelledError:
        pass  # Normal operator shutdown; child/socket cleanup runs above.
    finally:
        for sig in (signal.SIGTERM,signal.SIGINT):loop.remove_signal_handler(sig)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True)
    asyncio.run(main(json.loads(Path(parser.parse_args().config).read_text())))
